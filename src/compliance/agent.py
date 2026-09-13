"""Compliance agent: RAG retrieve → one LLM prompt with check_type enum → findings."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.compliance.check_types import CHECK_TYPES, RAG_QUERIES, CheckType
from src.compliance.models import ComplianceLLMResult
from src.compliance.prompts import build_user_prompt, format_rag_hits, get_system_prompt
from src.observability.otel import get_tracer, set_span_attributes, tokens_from_message
from src.rag.retrieve import retrieve

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)

LLMFactory = Callable[[], BaseChatModel]


def load_pipeline_config(root: Path | None = None) -> dict[str, Any]:
    root = root or ROOT
    path = root / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _compliance_cfg(root: Path | None = None) -> dict[str, Any]:
    return dict(load_pipeline_config(root).get("compliance") or {})


def default_llm_factory(root: Path | None = None) -> BaseChatModel:
    load_dotenv(ROOT / ".env")
    cfg = _compliance_cfg(root)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env or the environment "
            "before running the compliance agent."
        )
    return ChatOpenAI(
        model=str(cfg.get("model") or "gpt-4o-mini"),
        temperature=float(cfg.get("temperature", 0)),
        api_key=api_key,
    )


def _regulation_ref_from_hits(hits: list[dict], llm_ref: str) -> str:
    """Prefer the model ref; fall back to top hit metadata."""
    ref = (llm_ref or "").strip()
    if ref:
        return ref
    if not hits:
        return ""
    meta = hits[0].get("metadata") or {}
    article = str(meta.get("article") or "").strip()
    topic = str(meta.get("topic") or "").strip()
    if article and topic:
        return f"GDPR {article} ({topic})"
    if article:
        return f"GDPR {article}"
    if topic:
        return topic
    return str(meta.get("source") or "").strip()


def analyze_clause_check(
    *,
    clause: dict[str, Any],
    check_type: CheckType,
    llm: Any,
    top_k: int = 5,
    root: Path | None = None,
    token_sink: list[int] | None = None,
) -> dict[str, Any] | None:
    """Run one check_type on one clause. Returns a finding dict only when flag=True."""
    clause_id = str(clause.get("id") or "unknown")
    clause_text = str(clause.get("text") or "").strip()
    if not clause_text:
        return None

    query = RAG_QUERIES[check_type]
    hits = retrieve(query, top_k=top_k, root=root, log_hits=False)
    rag_block = format_rag_hits(hits)
    user_prompt = build_user_prompt(
        check_type=check_type,
        clause_id=clause_id,
        clause_text=clause_text,
        rag_block=rag_block,
    )

    messages = [
        SystemMessage(content=get_system_prompt()),
        HumanMessage(content=user_prompt),
    ]
    try:
        structured = llm.with_structured_output(
            ComplianceLLMResult, include_raw=True
        )
        raw = structured.invoke(messages)
    except TypeError:
        structured = llm.with_structured_output(ComplianceLLMResult)
        raw = structured.invoke(messages)

    if isinstance(raw, dict) and "parsed" in raw:
        tokens = tokens_from_message(raw.get("raw"))
        if tokens is not None and token_sink is not None:
            token_sink.append(tokens)
        parsed = raw.get("parsed")
        if parsed is None:
            return None
        result = (
            parsed
            if isinstance(parsed, ComplianceLLMResult)
            else ComplianceLLMResult.model_validate(parsed)
        )
    else:
        result = (
            raw
            if isinstance(raw, ComplianceLLMResult)
            else ComplianceLLMResult.model_validate(raw)
        )
    if not result.flag:
        return None

    quote = (result.evidence_quote or "").strip()
    # Early noise gate (Day 6 verifier also checks quotes + refs + confidence).
    if not quote or quote not in clause_text:
        logger.info(
            "drop_ungrounded_finding clause=%s check=%s quote=%r",
            clause_id,
            check_type.value,
            quote[:80] if quote else "",
        )
        return None

    severity = result.severity or "medium"
    return {
        "finding_id": f"{clause_id}:{check_type.value}",
        "clause_id": clause_id,
        "check_type": check_type.value,
        "issue": result.issue.strip() or f"Potential gap for {check_type.value}",
        "evidence_quote": quote,
        "regulation_ref": _regulation_ref_from_hits(hits, result.regulation_ref),
        "severity": severity,
        "confidence": float(result.confidence),
    }


def run_compliance(
    clauses: list[dict[str, Any]],
    *,
    llm: Any | None = None,
    llm_factory: LLMFactory | None = None,
    top_k: int | None = None,
    max_clauses: int | None = None,
    root: Path | None = None,
    doc_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run all five checks on every clause. Returns (findings, errors)."""
    cfg = _compliance_cfg(root)
    k = int(top_k if top_k is not None else cfg.get("top_k", 5))
    limit = max_clauses if max_clauses is not None else cfg.get("max_clauses")
    limit_n = int(limit) if limit is not None else None
    model_name = str(cfg.get("model") or "gpt-4o-mini")

    work = list(clauses)
    if limit_n is not None and limit_n >= 0:
        work = work[:limit_n]

    model = llm
    if model is None:
        factory = llm_factory or (lambda: default_llm_factory(root))
        model = factory()

    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    tracer = get_tracer()
    for clause in work:
        clause_id = str(clause.get("id") or "unknown")
        clause_findings = 0
        token_sink: list[int] = []
        with tracer.start_as_current_span(f"compliance.clause:{clause_id}") as span:
            set_span_attributes(
                span,
                {
                    "agent": "compliance",
                    "doc_id": doc_id or "",
                    "clause_id": clause_id,
                    "model": model_name,
                },
            )
            for check_type in CHECK_TYPES:
                try:
                    finding = analyze_clause_check(
                        clause=clause,
                        check_type=check_type,
                        llm=model,
                        top_k=k,
                        root=root,
                        token_sink=token_sink,
                    )
                except Exception as exc:  # noqa: BLE001 — keep pipeline running
                    msg = f"compliance:{clause_id}:{check_type.value}: {exc}"
                    logger.exception(msg)
                    errors.append(msg)
                    continue
                if finding is not None:
                    findings.append(finding)
                    clause_findings += 1
            set_span_attributes(
                span,
                {
                    "findings_count": clause_findings,
                    "tokens": sum(token_sink) if token_sink else 0,
                },
            )
    return findings, errors

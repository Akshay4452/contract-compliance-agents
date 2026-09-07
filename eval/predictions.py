"""Produce compliance / verifier predictions for eval (offline or live)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from eval.golden import ComplianceCase, contract_path
from src.segmenter.splitter import segment_text
from src.verifier.agent import run_verifier
from src.verifier.rules import quote_in_clause

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]

# Known-good GDPR-style refs that the Day 6 catalog accepts when corpus is present.
_DEFAULT_REG_REF = "GDPR Article 28"


def segment_contract(contract_id: str, contracts_dir: Path | None = None) -> list[dict]:
    path = contract_path(contract_id, contracts_dir)
    text = path.read_text(encoding="utf-8", errors="replace")
    return [c.to_dict() for c in segment_text(text)]


def findings_from_golden(
    contract_id: str,
    clauses: list[dict],
    cases: list[ComplianceCase],
    *,
    hallucinate_every_n: int = 0,
) -> list[dict[str, Any]]:
    """Build finding dicts from golden positives (no LLM / no RAG).

    When ``hallucinate_every_n`` > 0, every Nth positive finding gets an invalid
    evidence quote so the verifier / quote_valid_rate metrics are exercised.
    """
    by_id = {str(c.get("id") or ""): c for c in clauses}
    positives = [
        c
        for c in cases
        if c.contract_id == contract_id and c.expected_flag
    ]
    findings: list[dict[str, Any]] = []
    for i, case in enumerate(positives):
        clause = by_id.get(case.clause_id)
        if clause is None:
            raise KeyError(
                f"{contract_id}: golden clause_id={case.clause_id!r} not in segmenter output"
            )
        text = str(clause.get("text") or "")
        quote = case.evidence_must_contain
        if not quote:
            raise ValueError(
                f"{contract_id}/{case.clause_id}/{case.check_type}: "
                "positive golden row needs evidence_must_contain"
            )
        if quote not in text:
            raise ValueError(
                f"{contract_id}/{case.clause_id}/{case.check_type}: "
                f"evidence_must_contain not in clause text: {quote!r}"
            )
        bad = hallucinate_every_n > 0 and (i % hallucinate_every_n == 0)
        evidence = "THIS QUOTE DOES NOT APPEAR IN THE CLAUSE" if bad else quote
        findings.append(
            {
                "finding_id": f"{case.clause_id}:{case.check_type}",
                "clause_id": case.clause_id,
                "check_type": case.check_type,
                "issue": case.notes or f"Gap for {case.check_type}",
                "evidence_quote": evidence,
                "regulation_ref": _DEFAULT_REG_REF,
                "severity": case.expected_severity or "medium",
                "confidence": 0.9,
            }
        )
    return findings


def run_offline_contract(
    contract_id: str,
    cases: list[ComplianceCase],
    *,
    contracts_dir: Path | None = None,
    hallucinate_every_n: int = 0,
    root: Path | None = None,
) -> dict[str, Any]:
    """Segment + golden-scripted findings + real verifier (no OpenAI / no Chroma)."""
    root = root or ROOT
    clauses = segment_contract(contract_id, contracts_dir)
    findings = findings_from_golden(
        contract_id,
        clauses,
        cases,
        hallucinate_every_n=hallucinate_every_n,
    )
    annotated, verified = run_verifier(findings, clauses, root=root)
    return {
        "contract_id": contract_id,
        "clauses": clauses,
        "findings": annotated,
        "verified_findings": verified,
        "errors": [],
        "mode": "offline",
    }


def run_live_contract(
    contract_id: str,
    *,
    contracts_dir: Path | None = None,
    max_clauses: int | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Full LangGraph pipeline on one golden contract (needs OPENAI_API_KEY + Chroma)."""
    from src.graph.pipeline import run_contract

    path = contract_path(contract_id, contracts_dir)
    result = run_contract(
        path,
        max_clauses=max_clauses,
        top_k=top_k,
        auto_approve=True,
        write_report=False,
    )
    return {
        "contract_id": contract_id,
        "clauses": result.get("clauses") or [],
        "findings": result.get("findings") or [],
        "verified_findings": result.get("verified_findings") or [],
        "errors": result.get("errors") or [],
        "mode": "live",
    }


def quote_validity_for_findings(
    findings: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
    *,
    fuzzy: bool = True,
) -> list[tuple[dict[str, Any], bool]]:
    by_id = {str(c.get("id") or ""): str(c.get("text") or "") for c in clauses}
    rows: list[tuple[dict[str, Any], bool]] = []
    for finding in findings:
        clause_text = by_id.get(str(finding.get("clause_id") or ""), "")
        quote = str(finding.get("evidence_quote") or "")
        valid = bool(quote) and quote_in_clause(quote, clause_text, fuzzy=fuzzy)
        rows.append((finding, valid))
    return rows

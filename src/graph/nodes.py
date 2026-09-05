"""Graph nodes: ingest/segment + compliance + verifier + reporter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.compliance.agent import run_compliance
from src.graph.state import ComplianceState, DocumentPayload, ReportPayload
from src.reporter.agent import run_reporter
from src.segmenter.splitter import segment_text
from src.segmenter.store import document_id_from_path
from src.verifier.agent import run_verifier

# Optional overrides set by CLI before invoke (keeps ComplianceState lean).
_COMPLIANCE_OPTS: dict[str, Any] = {}
_VERIFIER_OPTS: dict[str, Any] = {}
_REPORTER_OPTS: dict[str, Any] = {}


def set_compliance_options(**kwargs: Any) -> None:
    """Configure the next compliance run (e.g. max_clauses from CLI)."""
    _COMPLIANCE_OPTS.clear()
    _COMPLIANCE_OPTS.update({k: v for k, v in kwargs.items() if v is not None})


def clear_compliance_options() -> None:
    _COMPLIANCE_OPTS.clear()


def set_verifier_options(**kwargs: Any) -> None:
    """Configure the next verifier run (e.g. min_confidence from CLI)."""
    _VERIFIER_OPTS.clear()
    _VERIFIER_OPTS.update({k: v for k, v in kwargs.items() if v is not None})


def clear_verifier_options() -> None:
    _VERIFIER_OPTS.clear()


def set_reporter_options(**kwargs: Any) -> None:
    """Configure the next reporter run (auto_approve, out_dir, write)."""
    _REPORTER_OPTS.clear()
    _REPORTER_OPTS.update({k: v for k, v in kwargs.items() if v is not None})


def clear_reporter_options() -> None:
    _REPORTER_OPTS.clear()


def ingest(state: ComplianceState) -> dict:
    """Load contract text from ``contract_path`` (or existing ``doc.source_path``)."""
    path_str = state.get("contract_path") or (state.get("doc") or {}).get("source_path") or ""
    if not path_str:
        return {"errors": ["ingest: missing contract_path"]}

    path = Path(path_str)
    if not path.is_file():
        return {"errors": [f"ingest: not a file: {path}"]}

    text = path.read_text(encoding="utf-8", errors="replace")
    doc: DocumentPayload = {
        "document_id": document_id_from_path(path),
        "source_path": str(path.resolve()),
        "text": text,
    }
    return {"doc": doc}


def segment(state: ComplianceState) -> dict:
    """Split ``doc.text`` into clauses via the Day 3 rule-based segmenter."""
    doc = state.get("doc")
    if not doc or not doc.get("text"):
        return {"errors": ["segment: empty doc.text"], "clauses": []}

    clauses = [c.to_dict() for c in segment_text(doc["text"])]
    return {"clauses": clauses}


def compliance(state: ComplianceState) -> dict:
    """RAG + LLM: all five check_types on every clause → raw ``findings``."""
    clauses = state.get("clauses") or []
    if not clauses:
        return {"findings": [], "errors": ["compliance: no clauses to check"]}

    findings, errors = run_compliance(clauses, **_COMPLIANCE_OPTS)
    out: dict[str, Any] = {"findings": findings}
    if errors:
        out["errors"] = errors
    return out


def verify(state: ComplianceState) -> dict:
    """Deterministic gate: quote in clause, known regulation_ref, min confidence."""
    findings = state.get("findings") or []
    clauses = state.get("clauses") or []
    if not findings:
        return {"findings": [], "verified_findings": []}

    annotated, verified = run_verifier(findings, clauses, **_VERIFIER_OPTS)
    return {"findings": annotated, "verified_findings": verified}


def report(state: ComplianceState) -> dict:
    """Package ``findings.json`` + ``audit_report.md``; set human-gate status."""
    doc = state.get("doc") or {}
    clauses = state.get("clauses") or []
    findings = state.get("findings") or []
    verified = state.get("verified_findings") or []
    errors = state.get("errors") or []

    document_id = str(doc.get("document_id") or "unknown")
    source_path = str(doc.get("source_path") or "")

    opts = dict(_REPORTER_OPTS)
    max_clauses = _COMPLIANCE_OPTS.get("max_clauses")
    analyzed_clause_count: int | None = None
    if max_clauses is not None:
        try:
            analyzed_clause_count = min(len(clauses), int(max_clauses))
        except (TypeError, ValueError):
            analyzed_clause_count = len(clauses)

    payload, _findings_doc = run_reporter(
        document_id=document_id,
        source_path=source_path,
        clauses=clauses,
        findings=findings,
        verified_findings=verified,
        errors=errors,
        auto_approve=bool(opts.get("auto_approve", False)),
        write=bool(opts.get("write", True)),
        out_dir=opts.get("out_dir"),
        root=opts.get("root"),
        analyzed_clause_count=analyzed_clause_count,
    )
    report_payload: ReportPayload = payload
    return {"report": report_payload}

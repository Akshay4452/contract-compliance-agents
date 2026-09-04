"""Graph nodes: ingest/segment + Day 5 compliance + Day 6 verifier; report still stub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.compliance.agent import run_compliance
from src.graph.state import ComplianceState, DocumentPayload, ReportPayload
from src.segmenter.splitter import segment_text
from src.segmenter.store import document_id_from_path
from src.verifier.agent import run_verifier

# Optional overrides set by CLI before invoke (keeps ComplianceState lean).
_COMPLIANCE_OPTS: dict[str, Any] = {}
_VERIFIER_OPTS: dict[str, Any] = {}


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
    """Stub report over verified findings; Day 7 packages Markdown/JSON for real."""
    raw = state.get("findings") or []
    verified = state.get("verified_findings") or []
    rejected = [f for f in raw if not f.get("verified")]
    reason_counts: dict[str, int] = {}
    for finding in rejected:
        reason = str(finding.get("reject_reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    reasons_line = ", ".join(
        f"{k}={v}" for k, v in sorted(reason_counts.items())
    ) or "none"

    payload: ReportPayload = {
        "status": "pending_review",
        "summary": (
            f"Day 6: raw={len(raw)}, verified={len(verified)}, "
            f"rejected={len(rejected)} ({reasons_line})."
        ),
        "finding_count": len(verified),
        "markdown": (
            "# Audit report (stub)\n\n"
            f"Raw findings from compliance: {len(raw)}\n"
            f"Verified findings: {len(verified)}\n"
            f"Rejected: {len(rejected)} ({reasons_line})\n\n"
            "Verifier is deterministic (quote + regulation_ref + confidence). "
            "Full Markdown packaging arrives on Day 7.\n"
        ),
    }
    return {"report": payload}

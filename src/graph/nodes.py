"""Graph nodes: ingest/segment + Day 5 compliance; verify/report still stubs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.compliance.agent import run_compliance
from src.graph.state import ComplianceState, DocumentPayload, ReportPayload
from src.segmenter.splitter import segment_text
from src.segmenter.store import document_id_from_path

# Optional overrides set by CLI before invoke (keeps ComplianceState lean).
_COMPLIANCE_OPTS: dict[str, Any] = {}


def set_compliance_options(**kwargs: Any) -> None:
    """Configure the next compliance run (e.g. max_clauses from CLI)."""
    _COMPLIANCE_OPTS.clear()
    _COMPLIANCE_OPTS.update({k: v for k, v in kwargs.items() if v is not None})


def clear_compliance_options() -> None:
    _COMPLIANCE_OPTS.clear()


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
    """Stub: quote/citation gate arrives on Day 6."""
    _ = state
    return {"verified_findings": []}


def report(state: ComplianceState) -> dict:
    """Stub report; Day 7 will package verified findings for real."""
    raw = state.get("findings") or []
    verified = state.get("verified_findings") or []
    payload: ReportPayload = {
        "status": "pending_review",
        "summary": (
            f"Day 5 raw findings={len(raw)}; "
            f"verified_findings={len(verified)} (verifier still stub)."
        ),
        "finding_count": len(verified),
        "markdown": (
            "# Audit report (stub)\n\n"
            f"Raw findings from compliance: {len(raw)}\n"
            f"Verified findings: {len(verified)}\n"
        ),
    }
    return {"report": payload}

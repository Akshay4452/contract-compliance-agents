"""Graph nodes: real ingest/segment; stub compliance/verify/report for Day 4."""

from __future__ import annotations

from pathlib import Path

from src.graph.state import ComplianceState, DocumentPayload, ReportPayload
from src.segmenter.splitter import segment_text
from src.segmenter.store import document_id_from_path


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
    """Stub: real RAG + LLM findings arrive on Day 5."""
    _ = state
    return {"findings": []}


def verify(state: ComplianceState) -> dict:
    """Stub: quote/citation gate arrives on Day 6."""
    _ = state
    return {"verified_findings": []}


def report(state: ComplianceState) -> dict:
    """Stub: empty findings → minimal pending_review report (Day 7 packages for real)."""
    findings = state.get("verified_findings") or []
    payload: ReportPayload = {
        "status": "pending_review",
        "summary": "No findings (pipeline smoke).",
        "finding_count": len(findings),
        "markdown": (
            "# Audit report (stub)\n\n"
            "Pipeline completed with empty findings.\n"
        ),
    }
    return {"report": payload}

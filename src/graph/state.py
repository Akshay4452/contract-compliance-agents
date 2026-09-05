"""Shared graph state and shapes for the compliance pipeline.

Day 4 declares the slots; Day 5 fills findings; Day 6 annotates verified_findings;
Day 7 packages the report (Markdown + findings.json).
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, NotRequired, TypedDict


class DocumentPayload(TypedDict):
    """Raw contract loaded by ``ingest``."""

    document_id: str
    source_path: str
    text: str


class Finding(TypedDict, total=False):
    """Structured allegation for human review (filled from Day 5 onward)."""

    finding_id: str
    clause_id: str
    check_type: str
    issue: str
    evidence_quote: str
    regulation_ref: str
    severity: Literal["high", "medium", "low"]
    confidence: float
    verified: bool
    reject_reason: str


class ReportPayload(TypedDict, total=False):
    """Reporter output + human gate (Day 7 packages Markdown/JSON artifacts)."""

    status: Literal["pending_review", "approved"]
    summary: str
    finding_count: int
    markdown: str
    findings_json_path: str
    audit_report_path: str


class ComplianceState(TypedDict):
    """Linear pipeline state: ingest → segment → compliance → verify → report."""

    doc: DocumentPayload
    clauses: list[dict[str, Any]]
    findings: list[Finding]
    verified_findings: list[Finding]
    report: ReportPayload | None
    errors: Annotated[list[str], add]
    # Input-only: CLI sets this; ingest reads the file.
    contract_path: NotRequired[str]

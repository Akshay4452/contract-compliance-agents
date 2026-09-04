"""Shared graph state and shapes for the compliance pipeline.

Day 4 declares the slots; Days 5–7 fill findings / verified_findings / report.
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
    """Reporter output + human gate (stub on Day 4; real packaging on Day 7)."""

    status: Literal["pending_review", "approved"]
    summary: str
    finding_count: int
    markdown: str


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

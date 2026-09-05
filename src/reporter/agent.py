"""Reporter agent: package verified findings into JSON + Markdown (no LLM)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from src.reporter.markdown import render_audit_markdown

ROOT = Path(__file__).resolve().parents[2]
HumanGateStatus = Literal["pending_review", "approved"]


def load_pipeline_config(root: Path | None = None) -> dict[str, Any]:
    root = root or ROOT
    path = root / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _reporter_cfg(root: Path | None = None) -> dict[str, Any]:
    return dict(load_pipeline_config(root).get("reporter") or {})


def default_output_root(root: Path | None = None) -> Path:
    """Day 7 exercise folder (mirrors day5 / day6 output homes)."""
    root = root or ROOT
    cfg = _reporter_cfg(root)
    rel = str(cfg.get("output_dir") or "data/exercises/day7_reporter")
    path = Path(rel)
    return path if path.is_absolute() else root / path


def document_output_dir(
    document_id: str,
    *,
    out_dir: Path | None = None,
    root: Path | None = None,
) -> Path:
    base = out_dir or default_output_root(root)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in document_id) or "doc"
    return Path(base) / safe


def build_findings_document(
    *,
    document_id: str,
    source_path: str,
    clauses: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    verified_findings: list[dict[str, Any]],
    status: HumanGateStatus,
    errors: list[str] | None = None,
    analyzed_clause_count: int | None = None,
) -> dict[str, Any]:
    """Structured ``findings.json`` body."""
    rejected = [f for f in findings if not f.get("verified")]
    analyzed = (
        analyzed_clause_count
        if analyzed_clause_count is not None
        else len(clauses)
    )
    return {
        "document_id": document_id,
        "source_path": source_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "clause_count": len(clauses),
        "analyzed_clause_count": analyzed,
        "finding_count": len(findings),
        "verified_count": len(verified_findings),
        "rejected_count": len(rejected),
        "errors": list(errors or []),
        "clauses": [
            {
                "clause_id": str(c.get("id") or ""),
                "clause_title": str(c.get("title") or ""),
            }
            for c in clauses
        ],
        "verified_findings": list(verified_findings),
        "rejected_findings": rejected,
        "findings": list(findings),
    }


def build_summary(
    *,
    verified_count: int,
    rejected_count: int,
    status: HumanGateStatus,
) -> str:
    return (
        f"verified={verified_count}, rejected={rejected_count}, "
        f"human_gate={status}"
    )


def run_reporter(
    *,
    document_id: str,
    source_path: str,
    clauses: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    verified_findings: list[dict[str, Any]],
    errors: list[str] | None = None,
    auto_approve: bool = False,
    write: bool = True,
    out_dir: Path | None = None,
    root: Path | None = None,
    analyzed_clause_count: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build report payload + findings.json; optionally write Day 7 artifacts.

    Returns ``(report_payload, findings_document)``.
    """
    status: HumanGateStatus = "approved" if auto_approve else "pending_review"
    rejected = [f for f in findings if not f.get("verified")]
    markdown = render_audit_markdown(
        document_id=document_id,
        source_path=source_path,
        clause_count=len(clauses),
        verified_findings=list(verified_findings),
        rejected_findings=rejected,
        clauses=clauses,
        status=status,
        errors=errors,
        analyzed_clause_count=analyzed_clause_count,
    )
    findings_doc = build_findings_document(
        document_id=document_id,
        source_path=source_path,
        clauses=clauses,
        findings=findings,
        verified_findings=list(verified_findings),
        status=status,
        errors=errors,
        analyzed_clause_count=analyzed_clause_count,
    )
    payload: dict[str, Any] = {
        "status": status,
        "summary": build_summary(
            verified_count=len(verified_findings),
            rejected_count=len(rejected),
            status=status,
        ),
        "finding_count": len(verified_findings),
        "markdown": markdown,
    }

    if write:
        dest = document_output_dir(document_id, out_dir=out_dir, root=root)
        paths = write_report_artifacts(
            dest,
            findings_doc=findings_doc,
            markdown=markdown,
        )
        payload["findings_json_path"] = str(paths["findings_json"])
        payload["audit_report_path"] = str(paths["audit_report"])

    return payload, findings_doc


def write_report_artifacts(
    out_dir: Path,
    *,
    findings_doc: dict[str, Any],
    markdown: str,
) -> dict[str, Path]:
    """Write ``findings.json`` and ``audit_report.md`` under ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    findings_path = out_dir / "findings.json"
    audit_path = out_dir / "audit_report.md"
    findings_path.write_text(
        json.dumps(findings_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    audit_path.write_text(markdown, encoding="utf-8")
    return {"findings_json": findings_path, "audit_report": audit_path}

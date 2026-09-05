"""Render audit_report.md from verified / rejected findings."""

from __future__ import annotations

from collections import Counter
from typing import Any


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _clause_titles(clauses: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(c.get("id") or ""): str(c.get("title") or "")
        for c in clauses
    }


def _esc_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(f.get("severity") or "unknown") for f in findings)
    return {k: counts[k] for k in ("high", "medium", "low") if k in counts}


def _check_type_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(f.get("check_type") or "unknown") for f in findings).items()))


def _sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER.get(str(f.get("severity") or ""), 9),
            str(f.get("clause_id") or ""),
            str(f.get("check_type") or ""),
        ),
    )


def _findings_table(
    findings: list[dict[str, Any]],
    titles: dict[str, str],
    *,
    include_reject_reason: bool = False,
) -> str:
    if not findings:
        return "_None._\n"

    headers = [
        "Severity",
        "Clause",
        "Check",
        "Issue",
        "Evidence",
        "Regulation",
        "Confidence",
    ]
    if include_reject_reason:
        headers.append("Reject reason")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for finding in _sort_findings(findings):
        clause_id = str(finding.get("clause_id") or "")
        title = titles.get(clause_id, "")
        clause_label = f"{clause_id}" + (f" ({title})" if title else "")
        conf = finding.get("confidence")
        conf_s = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else ""
        row = [
            _esc_cell(finding.get("severity")),
            _esc_cell(clause_label),
            _esc_cell(finding.get("check_type")),
            _esc_cell(finding.get("issue")),
            _esc_cell(finding.get("evidence_quote")),
            _esc_cell(finding.get("regulation_ref")),
            _esc_cell(conf_s),
        ]
        if include_reject_reason:
            row.append(_esc_cell(finding.get("reject_reason")))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def render_audit_markdown(
    *,
    document_id: str,
    source_path: str,
    clause_count: int,
    verified_findings: list[dict[str, Any]],
    rejected_findings: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
    status: str,
    errors: list[str] | None = None,
    analyzed_clause_count: int | None = None,
) -> str:
    """Executive summary + verified table + verifier-rejected appendix."""
    titles = _clause_titles(clauses)
    sev = _severity_counts(verified_findings)
    by_check = _check_type_counts(verified_findings)
    reject_reasons = dict(
        sorted(
            Counter(
                str(f.get("reject_reason") or "unknown") for f in rejected_findings
            ).items()
        )
    )

    sev_line = ", ".join(f"{k}={v}" for k, v in sev.items()) or "none"
    check_line = ", ".join(f"{k}={v}" for k, v in by_check.items()) or "none"
    reject_line = (
        ", ".join(f"{k}={v}" for k, v in reject_reasons.items()) or "none"
    )

    analyzed = (
        analyzed_clause_count
        if analyzed_clause_count is not None
        else clause_count
    )
    coverage_line = f"- Compliance analyzed: {analyzed} of {clause_count} clauses"
    if analyzed < clause_count:
        coverage_line += (
            " (capped by `--max-clauses` / `cuad-max-clauses` — "
            "earlier segments only; empty findings may mean those "
            "clauses were unrelated, not that the whole contract is clean)"
        )

    parts: list[str] = [
        f"# Audit report — `{document_id}`",
        "",
        f"**Human gate status:** `{status}`",
        "",
        "## Executive summary",
        "",
        f"- Source: `{source_path}`",
        f"- Clauses segmented: {clause_count}",
        coverage_line,
        f"- Verified findings: {len(verified_findings)} (by severity: {sev_line})",
        f"- Verified by check type: {check_line}",
        f"- Verifier rejected: {len(rejected_findings)} (reasons: {reject_line})",
        "",
        "Review question: does each evidence quote appear in the cited clause?",
        "",
        "## Verified findings",
        "",
        _findings_table(verified_findings, titles),
        "",
        "## Appendix — verifier rejected",
        "",
        "These allegations failed the deterministic gate "
        "(quote in clause, known regulation_ref, min confidence).",
        "",
        _findings_table(
            rejected_findings,
            titles,
            include_reject_reason=True,
        ),
    ]

    if errors:
        parts.extend(
            [
                "",
                "## Pipeline errors",
                "",
                *[f"- {_esc_cell(e)}" for e in errors],
                "",
            ]
        )

    parts.append("")
    return "\n".join(parts)

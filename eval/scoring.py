"""Score pipeline outputs against the Day 8 golden set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.golden import GoldenCase
from eval.metrics import ComplianceMetrics, quote_valid_rate, score_compliance
from src.segmenter.splitter import segment_text


def finding_key(
    contract_id: str,
    finding: dict[str, Any],
) -> tuple[str, str, str]:
    return (
        contract_id,
        str(finding.get("clause_id") or ""),
        str(finding.get("check_type") or ""),
    )


def _quote_from_clause(clause_text: str, max_len: int = 120) -> str:
    """Pick a grounded substring for oracle / fixture findings."""
    text = " ".join((clause_text or "").split())
    if not text:
        return ""
    return text[:max_len]


def build_oracle_runs(
    cases: list[GoldenCase],
    contracts: dict[str, Path],
    *,
    contract_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build perfect predictions from golden labels + real clause text.

    Offline harness check only — not a model baseline. Emits a finding for
    every ``expected_flag=true`` row with a quote taken from the clause.
    """
    wanted = set(contract_ids) if contract_ids else {c.contract_id for c in cases}
    runs: dict[str, dict[str, Any]] = {}

    for contract_id in sorted(wanted):
        path = contracts.get(contract_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(
                f"oracle: missing contract file for {contract_id}"
            )
        clauses = [c.to_dict() for c in segment_text(
            path.read_text(encoding="utf-8", errors="replace")
        )]
        by_id = {str(c["id"]): c for c in clauses}
        findings: list[dict[str, Any]] = []
        for case in cases:
            if case.contract_id != contract_id or not case.expected_flag:
                continue
            clause = by_id.get(case.clause_id)
            if clause is None:
                raise KeyError(
                    f"oracle: {contract_id}/{case.clause_id} not in segmenter output"
                )
            quote = _quote_from_clause(str(clause.get("text") or ""))
            findings.append(
                {
                    "finding_id": f"{case.clause_id}:{case.check_type}",
                    "clause_id": case.clause_id,
                    "check_type": case.check_type,
                    "issue": case.notes or "oracle golden positive",
                    "evidence_quote": quote,
                    "regulation_ref": "GDPR Article 28",
                    "severity": case.expected_severity or "high",
                    "confidence": 0.95,
                    "verified": True,
                    "reject_reason": "",
                }
            )
        runs[contract_id] = {
            "doc": {
                "document_id": contract_id,
                "source_path": str(path),
                "text": "",
            },
            "clauses": clauses,
            "findings": findings,
            "verified_findings": list(findings),
            "errors": [],
        }
    return runs


def enrich_runs_with_clause_text(
    runs: dict[str, dict[str, Any]],
    contracts: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    """Fill empty clause text from on-disk contracts when possible."""
    for contract_id, result in runs.items():
        clauses = result.get("clauses") or []
        needs_text = any(not str(c.get("text") or "") for c in clauses)
        path = contracts.get(contract_id)
        source = str((result.get("doc") or {}).get("source_path") or "")
        if path is None and source:
            candidate = Path(source)
            if candidate.is_file():
                path = candidate
        if not needs_text or path is None or not path.is_file():
            continue
        segmented = {
            c.id: c.to_dict()
            for c in segment_text(path.read_text(encoding="utf-8", errors="replace"))
        }
        if not clauses:
            result["clauses"] = list(segmented.values())
            continue
        for clause in clauses:
            cid = str(clause.get("id") or "")
            if not str(clause.get("text") or "") and cid in segmented:
                clause["text"] = segmented[cid]["text"]
                if not clause.get("title"):
                    clause["title"] = segmented[cid].get("title") or ""
    return runs


def collect_predictions(
    runs: dict[str, dict[str, Any]],
) -> tuple[
    set[tuple[str, str, str]],
    dict[tuple[str, str, str], str],
    list[dict[str, Any]],
    dict[str, dict[str, str]],
]:
    """Flatten pipeline runs into prediction sets.

    ``runs`` maps contract_id → ``{findings, clauses, ...}``.
    """
    keys: set[tuple[str, str, str]] = set()
    severity: dict[tuple[str, str, str], str] = {}
    all_findings: list[dict[str, Any]] = []
    clauses_by_contract: dict[str, dict[str, str]] = {}

    for contract_id, result in runs.items():
        clause_map = {
            str(c.get("id") or ""): str(c.get("text") or "")
            for c in (result.get("clauses") or [])
        }
        clauses_by_contract[contract_id] = clause_map
        for finding in result.get("findings") or []:
            key = finding_key(contract_id, finding)
            keys.add(key)
            sev = finding.get("severity")
            if sev:
                severity[key] = str(sev)
            all_findings.append(
                {
                    **finding,
                    "_contract_id": contract_id,
                }
            )

    return keys, severity, all_findings, clauses_by_contract


def score_runs(
    cases: list[GoldenCase],
    runs: dict[str, dict[str, Any]],
    *,
    fuzzy_quote: bool = True,
) -> dict[str, Any]:
    """Compute compliance + verifier quote metrics for golden contracts."""
    predicted_keys, predicted_severity, all_findings, clauses_by_contract = (
        collect_predictions(runs)
    )

    expected_rows = [
        (case.key, case.expected_flag, case.expected_severity) for case in cases
    ]
    # Only score cases whose contract was actually run.
    ran_ids = set(runs)
    expected_rows = [row for row in expected_rows if row[0][0] in ran_ids]
    scored_cases = [c for c in cases if c.contract_id in ran_ids]

    compliance: ComplianceMetrics = score_compliance(
        expected_rows=expected_rows,
        predicted_keys=predicted_keys,
        predicted_severity=predicted_severity,
    )

    # Quote rate over findings for contracts in this eval.
    flat_clauses: dict[str, str] = {}
    # Use compound keys so clause ids don't collide across contracts.
    remapped_findings: list[dict[str, Any]] = []
    for finding in all_findings:
        cid = str(finding.get("_contract_id") or "")
        clause_id = str(finding.get("clause_id") or "")
        compound = f"{cid}::{clause_id}"
        flat_clauses[compound] = clauses_by_contract.get(cid, {}).get(clause_id, "")
        remapped = dict(finding)
        remapped["clause_id"] = compound
        remapped_findings.append(remapped)

    quote = quote_valid_rate(
        remapped_findings,
        flat_clauses,
        fuzzy=fuzzy_quote,
    )

    return {
        "contracts_scored": sorted(ran_ids),
        "golden_cases_scored": len(scored_cases),
        "predicted_finding_count": len(all_findings),
        "compliance": compliance.as_dict(),
        "verifier": quote,
    }


def load_findings_document(path: Path) -> dict[str, Any]:
    """Load a Day 7 ``findings.json`` into a minimal run dict."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings = list(payload.get("findings") or [])
    clauses = [
        {
            "id": str(c.get("clause_id") or c.get("id") or ""),
            "text": str(c.get("text") or ""),
            "title": str(c.get("clause_title") or c.get("title") or ""),
        }
        for c in (payload.get("clauses") or [])
    ]
    source_path = str(payload.get("source_path") or "")
    # findings.json often omits clause body text; re-segment from source when present.
    if source_path and Path(source_path).is_file():
        segmented = {
            c.id: c.to_dict()
            for c in segment_text(
                Path(source_path).read_text(encoding="utf-8", errors="replace")
            )
        }
        if not clauses:
            clauses = list(segmented.values())
        else:
            for clause in clauses:
                cid = str(clause.get("id") or "")
                if not clause.get("text") and cid in segmented:
                    clause["text"] = segmented[cid]["text"]
                    if not clause.get("title"):
                        clause["title"] = segmented[cid].get("title") or ""
    return {
        "doc": {
            "document_id": str(payload.get("document_id") or path.parent.name),
            "source_path": source_path,
        },
        "clauses": clauses,
        "findings": findings,
        "verified_findings": list(payload.get("verified_findings") or []),
        "errors": list(payload.get("errors") or []),
    }


def load_predictions_dir(path: Path) -> dict[str, dict[str, Any]]:
    """Load ``<dir>/<contract_id>/findings.json`` trees (Day 7 layout)."""
    runs: dict[str, dict[str, Any]] = {}
    if not path.is_dir():
        raise FileNotFoundError(f"predictions dir not found: {path}")
    for child in sorted(path.iterdir()):
        findings_path = child / "findings.json"
        if child.is_dir() and findings_path.is_file():
            run = load_findings_document(findings_path)
            contract_id = str(
                (run.get("doc") or {}).get("document_id") or child.name
            )
            runs[contract_id] = run
            continue
        if child.is_file() and child.name.endswith("_llm_results.json"):
            payload = json.loads(child.read_text(encoding="utf-8"))
            contract_id = str(payload.get("contract_id") or child.stem)
            findings = []
            for row in payload.get("problematic_clauses") or []:
                findings.append(
                    {
                        "finding_id": row.get("finding_id"),
                        "clause_id": row.get("clause_id"),
                        "check_type": row.get("check_type"),
                        "issue": row.get("issue") or row.get("why"),
                        "evidence_quote": row.get("evidence_quote"),
                        "regulation_ref": row.get("regulation_ref"),
                        "severity": row.get("severity"),
                        "confidence": row.get("confidence"),
                        "verified": row.get("verified"),
                        "reject_reason": row.get("reject_reason"),
                    }
                )
            runs[contract_id] = {
                "doc": {"document_id": contract_id, "source_path": ""},
                "clauses": [
                    {
                        "id": str(c.get("clause_id") or ""),
                        "text": "",
                        "title": str(c.get("clause_title") or ""),
                    }
                    for c in (payload.get("clauses") or [])
                ],
                "findings": findings,
                "verified_findings": [],
                "errors": payload.get("errors") or [],
            }
    return runs

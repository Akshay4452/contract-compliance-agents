"""Offline Day 5 smoke: bad-contract fixtures + mocked LLM + real GDPR RAG."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.compliance.agent import run_compliance
from src.compliance.check_types import CHECK_TYPES, CheckType
from src.compliance.models import ComplianceLLMResult
from src.segmenter.splitter import segment_text

FIXTURES_DIR = ROOT / "data" / "exercises" / "day5_bad_contracts"
RESULTS_PATH = FIXTURES_DIR / "smoke_results.json"


class _ScriptedStructuredLLM:
    """Stand-in that only implements ``with_structured_output(...).invoke``."""

    def __init__(self, results: list[ComplianceLLMResult]):
        self._results = list(results)
        self._i = 0

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001, ARG002
        parent = self

        class _Runner:
            def invoke(self, _messages):  # noqa: ANN001
                if parent._i >= len(parent._results):
                    raise RuntimeError("fake LLM exhausted scripted results")
                item = parent._results[parent._i]
                parent._i += 1
                return item

        return _Runner()


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(FIXTURES_DIR.glob("*_expected.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    if not cases:
        raise SystemExit(f"no answer keys found under {FIXTURES_DIR}")
    return cases


def _find_clause(clauses: list[dict], title_contains: str) -> dict:
    needle = title_contains.upper()
    for clause in clauses:
        title = str(clause.get("title") or "").upper()
        head = str(clause.get("text") or "").split("\n", 1)[0].upper()
        if needle in title or needle in head:
            return clause
    titles = [str(c.get("title") or "") for c in clauses]
    raise SystemExit(
        f"no clause matching title_contains={title_contains!r}; titles={titles}"
    )


def _expectation_map(case: dict, clauses: list[dict]) -> dict[tuple[str, str], dict]:
    """Map (clause_id, check_type) → expected finding row (flag=true only)."""
    mapping: dict[tuple[str, str], dict] = {}
    for row in case.get("expected_findings") or []:
        clause = _find_clause(clauses, str(row["clause_title_contains"]))
        key = (str(clause["id"]), str(row["check_type"]))
        mapping[key] = row
    return mapping


def _no_flag_keys(case: dict, clauses: list[dict]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in case.get("expected_no_flag") or []:
        clause = _find_clause(clauses, str(row["clause_title_contains"]))
        keys.add((str(clause["id"]), str(row["check_type"])))
    return keys


def _script_results(
    clauses: list[dict],
    flag_map: dict[tuple[str, str], dict],
) -> list[ComplianceLLMResult]:
    """One result per (clause × check_type), matching run_compliance order."""
    scripted: list[ComplianceLLMResult] = []
    for clause in clauses:
        clause_id = str(clause.get("id") or "unknown")
        text = str(clause.get("text") or "")
        for check in CHECK_TYPES:
            row = flag_map.get((clause_id, check.value))
            if row is None:
                scripted.append(ComplianceLLMResult(flag=False, confidence=0.85))
                continue
            quote = str(row.get("evidence_must_contain") or "")
            if quote and quote not in text:
                raise SystemExit(
                    f"{clause_id}/{check.value}: evidence_must_contain not in clause "
                    f"text: {quote!r}"
                )
            scripted.append(
                ComplianceLLMResult(
                    flag=True,
                    issue=str(row.get("reason") or f"Gap for {check.value}"),
                    evidence_quote=quote,
                    regulation_ref=f"fixture:{check.value}",
                    severity=row.get("severity") or "medium",
                    confidence=0.9,
                )
            )
    return scripted


def _assert_findings(
    case: dict,
    clauses: list[dict],
    findings: list[dict],
    flag_map: dict[tuple[str, str], dict],
    quiet_keys: set[tuple[str, str]],
) -> None:
    contract_id = case["contract_id"]
    found_keys = {
        (str(f.get("clause_id")), str(f.get("check_type"))) for f in findings
    }
    expected_keys = set(flag_map)

    missing = expected_keys - found_keys
    extra = found_keys - expected_keys
    if missing or extra:
        raise SystemExit(
            f"{contract_id}: finding key mismatch missing={sorted(missing)} "
            f"extra={sorted(extra)} findings={findings}"
        )

    for finding in findings:
        key = (str(finding.get("clause_id")), str(finding.get("check_type")))
        row = flag_map[key]
        quote = str(finding.get("evidence_quote") or "")
        need = str(row.get("evidence_must_contain") or "")
        if need and need not in quote:
            raise SystemExit(
                f"{contract_id}: quote missing {need!r} in finding {finding}"
            )
        clause = next(c for c in clauses if c["id"] == finding["clause_id"])
        if quote and quote not in str(clause.get("text") or ""):
            raise SystemExit(
                f"{contract_id}: evidence_quote not a clause substring: {quote!r}"
            )

    leaked = found_keys & quiet_keys
    if leaked:
        raise SystemExit(
            f"{contract_id}: findings on clauses that should stay quiet: {sorted(leaked)}"
        )


def _clause_by_id(clauses: list[dict], clause_id: str) -> dict:
    for clause in clauses:
        if str(clause.get("id")) == clause_id:
            return clause
    raise KeyError(clause_id)


def _problematic_rows(
    case: dict,
    clauses: list[dict],
    findings: list[dict],
    flag_map: dict[tuple[str, str], dict],
) -> list[dict]:
    """Human-readable list: which clause is bad, which check, and why."""
    rows: list[dict] = []
    for finding in findings:
        clause_id = str(finding.get("clause_id"))
        check_type = str(finding.get("check_type"))
        clause = _clause_by_id(clauses, clause_id)
        expected = flag_map.get((clause_id, check_type)) or {}
        rows.append(
            {
                "clause_id": clause_id,
                "clause_title": str(clause.get("title") or ""),
                "check_type": check_type,
                "severity": finding.get("severity"),
                "confidence": finding.get("confidence"),
                "why": expected.get("reason")
                or finding.get("issue")
                or "Compliance gap flagged",
                "issue": finding.get("issue"),
                "evidence_quote": finding.get("evidence_quote"),
                "regulation_ref": finding.get("regulation_ref"),
                "finding_id": finding.get("finding_id"),
            }
        )
    rows.sort(key=lambda r: (r["clause_id"], r["check_type"]))
    return rows


def _quiet_rows(case: dict, clauses: list[dict]) -> list[dict]:
    """Clauses/checks that should stay clean (from the answer key)."""
    rows: list[dict] = []
    for row in case.get("expected_no_flag") or []:
        clause = _find_clause(clauses, str(row["clause_title_contains"]))
        rows.append(
            {
                "clause_id": str(clause["id"]),
                "clause_title": str(clause.get("title") or ""),
                "check_type": str(row["check_type"]),
                "why_ok": str(row.get("reason") or ""),
            }
        )
    return rows


def _run_case(case: dict) -> dict:
    contract_path = FIXTURES_DIR / case["contract_file"]
    if not contract_path.is_file():
        raise SystemExit(f"missing contract file: {contract_path}")

    text = contract_path.read_text(encoding="utf-8")
    clauses = [c.to_dict() for c in segment_text(text)]
    if not clauses:
        raise SystemExit(f"{case['contract_id']}: segmenter returned no clauses")

    flag_map = _expectation_map(case, clauses)
    quiet_keys = _no_flag_keys(case, clauses)
    overlap = set(flag_map) & quiet_keys
    if overlap:
        raise SystemExit(
            f"{case['contract_id']}: answer key conflict flag vs no_flag: {overlap}"
        )

    scripted = _script_results(clauses, flag_map)
    expected_calls = len(clauses) * len(CheckType)
    if len(scripted) != expected_calls:
        raise SystemExit(
            f"{case['contract_id']}: scripted {len(scripted)} != {expected_calls}"
        )

    findings, errors = run_compliance(
        clauses,
        llm=_ScriptedStructuredLLM(scripted),
        top_k=3,
    )
    if errors:
        raise SystemExit(f"{case['contract_id']}: unexpected errors: {errors}")

    _assert_findings(case, clauses, findings, flag_map, quiet_keys)
    problematic = _problematic_rows(case, clauses, findings, flag_map)

    print(
        f"ok {case['contract_id']}: clauses={len(clauses)} "
        f"findings={len(findings)} why_bad={case.get('why_bad', '')[:80]}…"
    )
    return {
        "contract_id": case["contract_id"],
        "contract_file": case["contract_file"],
        "why_contract_is_bad": case.get("why_bad", ""),
        "status": "ok",
        "clause_count": len(clauses),
        "finding_count": len(findings),
        "problematic_clauses": problematic,
        "clauses_that_should_stay_clean": _quiet_rows(case, clauses),
    }


def _write_results(report: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {RESULTS_PATH.relative_to(ROOT)}")


def main() -> None:
    cases = _load_cases()
    case_reports: list[dict] = []
    for case in cases:
        case_reports.append(_run_case(case))

    report = {
        "status": "ok",
        "mode": "offline_mocked_llm_real_rag",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(case_reports),
        "total_problematic_findings": sum(
            int(c["finding_count"]) for c in case_reports
        ),
        "cases": case_reports,
    }
    _write_results(report)
    print(f"compliance_smoke_ok cases={len(cases)}")


if __name__ == "__main__":
    main()

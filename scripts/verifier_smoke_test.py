"""Offline Day 6 smoke: hand-built findings through the verifier (no LLM)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.segmenter.splitter import segment_text
from src.verifier.agent import run_verifier
from src.verifier.corpus import load_corpus_catalog

FIXTURES = ROOT / "data" / "exercises" / "day5_bad_contracts"
OUT_PATH = ROOT / "data" / "exercises" / "day6_verifier" / "smoke_results.json"


def _load_contract(name: str) -> tuple[str, list[dict]]:
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    clauses = [c.to_dict() for c in segment_text(text)]
    return str(path), clauses


def _find_clause(clauses: list[dict], needle: str) -> dict:
    upper = needle.upper()
    for clause in clauses:
        title = str(clause.get("title") or "").upper()
        head = str(clause.get("text") or "").split("\n", 1)[0].upper()
        if upper in title or upper in head:
            return clause
    raise SystemExit(f"no clause matching {needle!r}")


def _cases(clauses: list[dict]) -> list[dict]:
    """Grounded + hallucinated findings against bad_01."""
    sub = _find_clause(clauses, "SUBPROCESSORS")
    retain = _find_clause(clauses, "DATA RETENTION")
    return [
        {
            "finding_id": f"{sub['id']}:subprocessor",
            "clause_id": sub["id"],
            "check_type": "subprocessor",
            "issue": "Open third-party sharing",
            "evidence_quote": "without prior notice",
            "regulation_ref": "GDPR 28 (Processor)",
            "severity": "high",
            "confidence": 0.92,
            "expect_verified": True,
        },
        {
            "finding_id": f"{retain['id']}:data_retention",
            "clause_id": retain["id"],
            "check_type": "data_retention",
            "issue": "Indefinite retention",
            "evidence_quote": "as long as Vendor deems useful",
            "regulation_ref": "GDPR 5",
            "severity": "high",
            "confidence": 0.88,
            "expect_verified": True,
        },
        {
            "finding_id": f"{sub['id']}:hallucinated_quote",
            "clause_id": sub["id"],
            "check_type": "subprocessor",
            "issue": "Invented quote",
            "evidence_quote": "Customer prior written approval is always required",
            "regulation_ref": "GDPR 28",
            "severity": "high",
            "confidence": 0.99,
            "expect_verified": False,
            "expect_reason": "quote_not_in_clause",
        },
        {
            "finding_id": f"{sub['id']}:fake_ref",
            "clause_id": sub["id"],
            "check_type": "subprocessor",
            "issue": "Fake citation",
            "evidence_quote": "without prior notice",
            "regulation_ref": "Made-Up Act Section 999",
            "severity": "high",
            "confidence": 0.9,
            "expect_verified": False,
            "expect_reason": "regulation_ref_not_in_corpus",
        },
        {
            "finding_id": f"{sub['id']}:low_conf",
            "clause_id": sub["id"],
            "check_type": "subprocessor",
            "issue": "Low confidence",
            "evidence_quote": "without prior notice",
            "regulation_ref": "GDPR 28",
            "severity": "medium",
            "confidence": 0.1,
            "expect_verified": False,
            "expect_reason": "confidence_below_threshold",
        },
    ]


def main() -> None:
    contract_path, clauses = _load_contract("bad_01_all_five_gaps.txt")
    catalog = load_corpus_catalog(ROOT)
    cases = _cases(clauses)
    findings = [{k: v for k, v in row.items() if not k.startswith("expect_")} for row in cases]

    annotated, verified = run_verifier(
        findings,
        clauses,
        catalog=catalog,
        min_confidence=0.5,
    )

    by_id = {str(r.get("finding_id")): r for r in annotated}
    failures: list[str] = []
    details: list[dict] = []
    for case in cases:
        fid = case["finding_id"]
        got = by_id[fid]
        ok = bool(got.get("verified")) == bool(case["expect_verified"])
        if case.get("expect_reason"):
            ok = ok and got.get("reject_reason") == case["expect_reason"]
        if not ok:
            failures.append(
                f"{fid}: expected verified={case['expect_verified']} "
                f"reason={case.get('expect_reason')}; "
                f"got verified={got.get('verified')} reason={got.get('reject_reason')}"
            )
        details.append(
            {
                "finding_id": fid,
                "expect_verified": case["expect_verified"],
                "got_verified": got.get("verified"),
                "reject_reason": got.get("reject_reason"),
                "pass": ok,
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "ok" if not failures else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_file": contract_path,
        "clause_count": len(clauses),
        "input_findings": len(findings),
        "verified_count": len(verified),
        "rejected_count": len(annotated) - len(verified),
        "details": details,
        "failures": failures,
    }
    OUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"status={report['status']}")
    print(f"verified={report['verified_count']} rejected={report['rejected_count']}")
    print(f"results={OUT_PATH}")
    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

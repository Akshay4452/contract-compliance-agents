"""Offline Day 7 smoke: verifier findings → reporter Markdown/JSON (no LLM)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporter.agent import run_reporter
from src.segmenter.splitter import segment_text
from src.verifier.agent import run_verifier
from src.verifier.corpus import load_corpus_catalog

FIXTURES = ROOT / "data" / "exercises" / "day5_bad_contracts"
OUT_DIR = ROOT / "data" / "exercises" / "day7_reporter"
SMOKE_META = OUT_DIR / "smoke_results.json"
SMOKE_DOC_DIR = OUT_DIR / "smoke_bad_01"


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
        },
    ]


def main() -> None:
    contract_path, clauses = _load_contract("bad_01_all_five_gaps.txt")
    catalog = load_corpus_catalog(ROOT)
    findings = _cases(clauses)
    annotated, verified = run_verifier(
        findings,
        clauses,
        catalog=catalog,
        min_confidence=0.5,
    )

    payload, findings_doc = run_reporter(
        document_id="smoke_bad_01",
        source_path=contract_path,
        clauses=clauses,
        findings=annotated,
        verified_findings=verified,
        auto_approve=False,
        write=True,
        out_dir=OUT_DIR,
        root=ROOT,
    )

    md = str(payload.get("markdown") or "")
    failures: list[str] = []
    if payload.get("status") != "pending_review":
        failures.append(f"status={payload.get('status')!r} expected pending_review")
    if "## Executive summary" not in md:
        failures.append("missing Executive summary section")
    if "## Verified findings" not in md:
        failures.append("missing Verified findings section")
    if "## Appendix — verifier rejected" not in md:
        failures.append("missing verifier rejected appendix")
    if "without prior notice" not in md:
        failures.append("verified evidence quote missing from markdown")
    if "quote_not_in_clause" not in md and "regulation_ref_not_in_corpus" not in md:
        failures.append("reject reasons missing from appendix")
    if findings_doc.get("verified_count") != len(verified):
        failures.append("findings.json verified_count mismatch")
    if findings_doc.get("rejected_count") != len(annotated) - len(verified):
        failures.append("findings.json rejected_count mismatch")

    findings_path = Path(str(payload.get("findings_json_path") or ""))
    audit_path = Path(str(payload.get("audit_report_path") or ""))
    if not findings_path.is_file():
        failures.append(f"missing findings.json at {findings_path}")
    if not audit_path.is_file():
        failures.append(f"missing audit_report.md at {audit_path}")

    # Confirm --auto-approve flips gate only
    approved, _ = run_reporter(
        document_id="smoke_bad_01_approved",
        source_path=contract_path,
        clauses=clauses,
        findings=annotated,
        verified_findings=verified,
        auto_approve=True,
        write=False,
        root=ROOT,
    )
    if approved.get("status") != "approved":
        failures.append("auto_approve did not set status=approved")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "status": "ok" if not failures else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_file": contract_path,
        "verified_count": len(verified),
        "rejected_count": len(annotated) - len(verified),
        "human_gate": payload.get("status"),
        "findings_json": str(findings_path),
        "audit_report": str(audit_path),
        "smoke_doc_dir": str(SMOKE_DOC_DIR),
        "failures": failures,
    }
    SMOKE_META.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"status={meta['status']}")
    print(f"verified={meta['verified_count']} rejected={meta['rejected_count']}")
    print(f"human_gate={meta['human_gate']}")
    print(f"audit_report={audit_path}")
    print(f"findings_json={findings_path}")
    print(f"smoke_meta={SMOKE_META}")
    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

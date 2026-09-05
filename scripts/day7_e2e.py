"""Day 7 live E2E: 3 synthetic bad contracts + 2 CUAD templates → audit reports.

Needs OPENAI_API_KEY and a built GDPR Chroma index.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.pipeline import run_contract
from src.segmenter.store import pick_cuad

OUT_DIR = ROOT / "data" / "exercises" / "day7_reporter"
BAD_DIR = ROOT / "data" / "exercises" / "day5_bad_contracts"
E2E_META = OUT_DIR / "e2e_results.json"

SYNTHETIC = [
    BAD_DIR / "bad_01_all_five_gaps.txt",
    BAD_DIR / "bad_02_breach_and_exit.txt",
    BAD_DIR / "bad_03_open_sharing.txt",
]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _run_one(
    contract: Path,
    *,
    max_clauses: int | None,
    auto_approve: bool,
    top_k: int | None,
) -> dict:
    result = run_contract(
        contract,
        max_clauses=max_clauses,
        top_k=top_k,
        auto_approve=auto_approve,
        out_dir=OUT_DIR,
        write_report=True,
    )
    doc = result.get("doc") or {}
    report = result.get("report") or {}
    findings = result.get("findings") or []
    return {
        "contract_file": _rel(contract),
        "document_id": doc.get("document_id"),
        "clause_count": len(result.get("clauses") or []),
        "finding_count": len(findings),
        "verified_count": len(result.get("verified_findings") or []),
        "rejected_count": sum(1 for f in findings if f.get("verified") is False),
        "human_gate": report.get("status"),
        "summary": report.get("summary"),
        "findings_json": report.get("findings_json_path"),
        "audit_report": report.get("audit_report_path"),
        "errors": result.get("errors") or [],
    }


def main(argv: list[str] | None = None) -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Day 7 end-to-end live runs (3 synthetic + 2 CUAD).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Mark human gate approved (still writes the same artifacts)",
    )
    parser.add_argument(
        "--max-clauses",
        type=int,
        default=None,
        help="Cap clauses for every contract (cost control)",
    )
    parser.add_argument(
        "--cuad-max-clauses",
        type=int,
        default=None,
        help="Cap clauses for CUAD templates only (synthetic still full)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override RAG top_k",
    )
    parser.add_argument(
        "--skip-cuad",
        action="store_true",
        help="Only run the three synthetic bad contracts",
    )
    args = parser.parse_args(argv)

    contracts: list[tuple[Path, int | None]] = [
        (path, args.max_clauses) for path in SYNTHETIC
    ]
    if not args.skip_cuad:
        try:
            cuad_paths = pick_cuad(2, root=ROOT)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        cuad_cap = (
            args.max_clauses
            if args.max_clauses is not None
            else args.cuad_max_clauses
        )
        for path in cuad_paths:
            contracts.append((path, cuad_cap))

    missing = [p for p, _ in contracts if not p.is_file()]
    if missing:
        raise SystemExit(f"missing contracts: {missing}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    failures: list[str] = []

    for path, cap in contracts:
        print(f"\n=== {_rel(path)} (max_clauses={cap}) ===")
        try:
            case = _run_one(
                path,
                max_clauses=cap,
                auto_approve=args.auto_approve,
                top_k=args.top_k,
            )
        except Exception as exc:  # noqa: BLE001 — surface per-contract failure
            case = {
                "contract_file": _rel(path),
                "errors": [str(exc)],
                "human_gate": None,
            }
            failures.append(f"{path.name}: {exc}")
        cases.append(case)
        print(
            f"gate={case.get('human_gate')} "
            f"verified={case.get('verified_count')} "
            f"rejected={case.get('rejected_count')}"
        )
        if case.get("audit_report"):
            print(f"audit_report={case['audit_report']}")
        if case.get("errors"):
            print(f"errors={case['errors']}")

    for case in cases:
        if not case.get("audit_report") and not case.get("errors"):
            failures.append(f"{case.get('contract_file')}: missing audit_report path")
        if case.get("errors"):
            failures.append(
                f"{case.get('contract_file')}: errors={case.get('errors')}"
            )

    meta = {
        "status": "ok" if not failures else "failed",
        "mode": "live_llm_e2e",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_approve": bool(args.auto_approve),
        "case_count": len(cases),
        "cases": cases,
        "failures": failures,
    }
    E2E_META.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nstatus={meta['status']} cases={meta['case_count']}")
    print(f"e2e_meta={E2E_META}")
    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

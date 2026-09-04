"""CLI entrypoint: ``python run.py --contract path/to/msa.txt``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.graph.pipeline import run_contract

ROOT = Path(__file__).resolve().parent
DEFAULT_RUNS_DIR = ROOT / "data" / "runs"


def _clause_title_map(clauses: list[dict]) -> dict[str, str]:
    return {
        str(c.get("id") or ""): str(c.get("title") or "")
        for c in clauses
    }


def _problematic_rows(clauses: list[dict], findings: list[dict]) -> list[dict]:
    titles = _clause_title_map(clauses)
    rows: list[dict] = []
    for finding in findings:
        clause_id = str(finding.get("clause_id") or "")
        rows.append(
            {
                "clause_id": clause_id,
                "clause_title": titles.get(clause_id, ""),
                "check_type": finding.get("check_type"),
                "severity": finding.get("severity"),
                "confidence": finding.get("confidence"),
                "why": finding.get("issue"),
                "issue": finding.get("issue"),
                "evidence_quote": finding.get("evidence_quote"),
                "regulation_ref": finding.get("regulation_ref"),
                "finding_id": finding.get("finding_id"),
                "verified": finding.get("verified"),
                "reject_reason": finding.get("reject_reason"),
            }
        )
    rows.sort(key=lambda r: (str(r["clause_id"]), str(r["check_type"])))
    return rows


def _default_results_path(contract_path: Path, document_id: str) -> Path:
    """Prefer writing next to day5 fixtures; otherwise ``data/runs/``."""
    parent = contract_path.resolve().parent
    stem = contract_path.stem
    if parent.name == "day5_bad_contracts":
        return parent / f"{stem}_llm_results.json"
    doc = document_id or stem
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in doc)
    return DEFAULT_RUNS_DIR / f"{safe}_llm_results.json"


def write_llm_results(
    *,
    contract_path: Path,
    result: dict,
    out_path: Path | None = None,
) -> Path:
    """Write a smoke-style JSON report for a live LLM pipeline run."""
    doc = result.get("doc") or {}
    clauses = result.get("clauses") or []
    findings = result.get("findings") or []
    document_id = str(doc.get("document_id") or contract_path.stem)

    path = out_path or _default_results_path(contract_path, document_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "status": "ok" if not (result.get("errors") or []) else "ok_with_errors",
        "mode": "live_llm",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_id": document_id,
        "contract_file": str(contract_path),
        "clause_count": len(clauses),
        "finding_count": len(findings),
        "verified_finding_count": len(result.get("verified_findings") or []),
        "rejected_finding_count": sum(
            1 for f in findings if f.get("verified") is False
        ),
        "report": result.get("report"),
        "errors": result.get("errors") or [],
        "clauses": [
            {
                "clause_id": str(c.get("id") or ""),
                "clause_title": str(c.get("title") or ""),
            }
            for c in clauses
        ],
        "problematic_clauses": _problematic_rows(clauses, findings),
        "verified_findings": _problematic_rows(
            clauses, result.get("verified_findings") or []
        ),
    }
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "Run the compliance LangGraph pipeline "
            "(Day 5 RAG+LLM + Day 6 verifier gate)."
        ),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        required=True,
        help="Path to a .txt contract",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full final state as JSON",
    )
    parser.add_argument(
        "--max-clauses",
        type=int,
        default=None,
        help="Only run compliance on the first N clauses (smoke / cost control)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override RAG top_k from config/pipeline.yaml",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Override verifier min_confidence from config/pipeline.yaml",
    )
    parser.add_argument(
        "--preview-findings",
        type=int,
        default=5,
        help="How many raw findings to print (0 = none); ignored with --json",
    )
    parser.add_argument(
        "--results-json",
        type=Path,
        default=None,
        help="Where to write the LLM findings report (default: next to day5 "
        "fixtures or data/runs/<doc>_llm_results.json)",
    )
    parser.add_argument(
        "--no-results-json",
        action="store_true",
        help="Do not write the LLM findings JSON report",
    )
    args = parser.parse_args(argv)

    path = args.contract
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")

    result = run_contract(
        path,
        max_clauses=args.max_clauses,
        top_k=args.top_k,
        min_confidence=args.min_confidence,
    )
    doc = result.get("doc") or {}
    clauses = result.get("clauses") or []
    findings = result.get("findings") or []
    verified = result.get("verified_findings") or []
    report = result.get("report") or {}
    errors = result.get("errors") or []

    results_path: Path | None = None
    if not args.no_results_json:
        results_path = write_llm_results(
            contract_path=path,
            result=result,
            out_path=args.results_json,
        )

    if args.json:
        dump = dict(result)
        if dump.get("doc"):
            dump["doc"] = {
                **dump["doc"],
                "text": f"<omitted {len(dump['doc'].get('text') or '')} chars>",
            }
        if results_path is not None:
            dump["results_json"] = str(results_path)
        print(json.dumps(dump, indent=2, ensure_ascii=False))
        return

    print(f"document_id={doc.get('document_id')}")
    print(f"source={doc.get('source_path')}")
    print(f"clauses={len(clauses)}")
    print(f"findings={len(findings)}")
    print(f"verified_findings={len(verified)}")
    print(f"report.status={report.get('status')}")
    print(f"report.summary={report.get('summary')}")
    if errors:
        print(f"errors={errors}")
    else:
        print("errors=[]")
    if results_path is not None:
        try:
            rel = results_path.resolve().relative_to(ROOT.resolve())
        except ValueError:
            rel = results_path
        print(f"results_json={rel}")

    preview_n = args.preview_findings
    if preview_n > 0 and findings:
        print()
        print(f"--- findings preview (up to {preview_n}) ---")
        for finding in findings[:preview_n]:
            verified_flag = finding.get("verified")
            reject = finding.get("reject_reason") or ""
            gate = (
                "verified"
                if verified_flag
                else f"rejected:{reject}" if verified_flag is False else "raw"
            )
            print(
                f"- {finding.get('finding_id')}  "
                f"severity={finding.get('severity')}  "
                f"conf={finding.get('confidence')}  "
                f"[{gate}]"
            )
            print(f"  issue: {finding.get('issue')}")
            quote = finding.get("evidence_quote") or ""
            if len(quote) > 160:
                quote = quote[:160] + "..."
            print(f"  quote: {quote}")
            print(f"  ref: {finding.get('regulation_ref')}")


if __name__ == "__main__":
    main(sys.argv[1:])

"""CLI entrypoint: ``python run.py --contract path/to/msa.txt``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.graph.pipeline import run_contract


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the compliance LangGraph pipeline (Day 4 skeleton).",
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
    args = parser.parse_args(argv)

    path = args.contract
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")

    result = run_contract(path)
    doc = result.get("doc") or {}
    clauses = result.get("clauses") or []
    findings = result.get("findings") or []
    verified = result.get("verified_findings") or []
    report = result.get("report") or {}
    errors = result.get("errors") or []

    if args.json:
        # Omit full contract body for readable dumps unless needed later.
        dump = dict(result)
        if dump.get("doc"):
            dump["doc"] = {
                **dump["doc"],
                "text": f"<omitted {len(dump['doc'].get('text') or '')} chars>",
            }
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


if __name__ == "__main__":
    main(sys.argv[1:])

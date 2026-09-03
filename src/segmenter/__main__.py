"""Print clauses for one contract: ``python -m src.segmenter path/to/contract.txt``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.segmenter.store import segment_file


def _print_document(path: Path, preview: int) -> None:
    doc = segment_file(path)
    print(f"document_id={doc.document_id}")
    print(f"source={doc.source_path}")
    print(f"clauses={len(doc.clauses)}")
    print()
    for clause in doc.clauses:
        print(f"===== {clause.id}  start_hint={clause.start_hint}  {clause.title} =====")
        body = clause.text if preview <= 0 else clause.text[:preview]
        print(body)
        if preview > 0 and len(clause.text) > preview:
            print(f"... ({len(clause.text)} chars total)")
        print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rule-based clause segmentation")
    parser.add_argument("contract", type=Path, help="Path to a .txt contract")
    parser.add_argument(
        "--preview",
        type=int,
        default=0,
        help="Max characters to print per clause (0 = full text)",
    )
    args = parser.parse_args(argv)
    path = args.contract
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")
    _print_document(path, args.preview)


if __name__ == "__main__":
    main(sys.argv[1:])

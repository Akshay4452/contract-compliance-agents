"""Day 3: segment 5 CUAD contracts into clauses.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.segmenter.models import SegmentedDocument
from src.segmenter.store import dump_documents, pick_cuad, segment_file

DEFAULT_OUT = ROOT / "data" / "exercises" / "day3_segmentation" / "clauses.json"
DEFAULT_CUAD_LIMIT = 5


def _print_clauses(doc: SegmentedDocument, preview: int, limit: int | None) -> None:
    print(f"\n=== {doc.document_id} ({doc.source_kind}) ===")
    print(f"source={doc.source_path}")
    print(f"clauses={len(doc.clauses)}")
    selected = doc.clauses if limit is None else doc.clauses[:limit]
    for clause in selected:
        print(f"\n----- {clause.id}  start_hint={clause.start_hint}  {clause.title} -----")
        body = clause.text if preview <= 0 else clause.text[:preview]
        print(body)
        if preview > 0 and len(clause.text) > preview:
            print(f"... ({len(clause.text)} chars)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build clauses.json from CUAD contracts")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cuad-limit", type=int, default=DEFAULT_CUAD_LIMIT)
    parser.add_argument(
        "--print",
        dest="print_id",
        default=None,
        help="document_id to print (default: first document)",
    )
    parser.add_argument("--preview", type=int, default=500)
    parser.add_argument(
        "--print-all",
        action="store_true",
        help="Print every clause of --print instead of the first three",
    )
    args = parser.parse_args(argv)

    try:
        paths = pick_cuad(args.cuad_limit, root=ROOT)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    documents: list[SegmentedDocument] = [
        segment_file(path, source_kind="cuad") for path in paths
    ]

    dump_documents(documents, args.out)

    print("Segmented documents:")
    for doc in documents:
        print(f"  {doc.document_id:40}  {len(doc.clauses):3} clauses  ({doc.source_kind})")
    print(f"Wrote {args.out}")

    target = None
    if args.print_id:
        target = next((doc for doc in documents if doc.document_id == args.print_id), None)
        if target is None:
            print(f"\nNo document_id={args.print_id!r}; printing first document")
    if target is None and documents:
        target = documents[0]
    if target is not None:
        limit = None if args.print_all else 3
        _print_clauses(target, preview=args.preview, limit=limit)
        print(
            "\nRead three clauses above and say what each is about "
            "(plain English). See data/exercises/day3_plain_english.md."
        )


if __name__ == "__main__":
    main()

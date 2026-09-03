"""Day 3: segment 3 templates + 2 CUAD contracts (or sample fallbacks)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.segmenter.models import SegmentedDocument
from src.segmenter.store import dump_documents, segment_file

TEMPLATE_FILES = [
    ROOT / "data" / "templates" / "nda_mutual.txt",
    ROOT / "data" / "templates" / "saas_msa.txt",
    ROOT / "data" / "templates" / "dpa_processor.txt",
]

FALLBACK_FILES = [
    ROOT / "data" / "samples" / "consulting_agreement.txt",
    ROOT / "data" / "samples" / "vendor_security_addendum.txt",
]

DEFAULT_OUT = ROOT / "data" / "exercises" / "day3_segmentation" / "clauses.json"


def _cuad_txt_dir() -> Path | None:
    config_path = ROOT / "config" / "data_paths.yaml"
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["cuad"]
    txt_dir = Path(cfg["contracts_txt_dir"])
    if txt_dir.is_dir():
        return txt_dir
    return None


def _pick_cuad(limit: int) -> list[Path]:
    txt_dir = _cuad_txt_dir()
    if txt_dir is None:
        return []
    files = sorted(txt_dir.glob("*.txt"))
    return files[:limit]


def collect_inputs(cuad_limit: int) -> list[tuple[Path, str]]:
    """Return (path, source_kind) for 3 templates + 2 CUAD or fallbacks."""
    chosen: list[tuple[Path, str]] = [(path, "template") for path in TEMPLATE_FILES]
    cuad = _pick_cuad(cuad_limit)
    if len(cuad) >= cuad_limit:
        chosen.extend((path, "cuad") for path in cuad[:cuad_limit])
        return chosen
    print(
        "CUAD txt dir missing or has fewer than "
        f"{cuad_limit} files; using bundled samples for the remaining slots."
    )
    chosen.extend((path, "sample") for path in FALLBACK_FILES[:cuad_limit])
    return chosen


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
    parser = argparse.ArgumentParser(description="Build clauses.json for Day 3")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cuad-limit", type=int, default=2)
    parser.add_argument(
        "--print",
        dest="print_id",
        default="saas-msa",
        help="document_id to print (default: saas-msa)",
    )
    parser.add_argument("--preview", type=int, default=500)
    parser.add_argument(
        "--print-all",
        action="store_true",
        help="Print every clause of --print instead of the first three",
    )
    args = parser.parse_args(argv)

    documents: list[SegmentedDocument] = []
    for path, kind in collect_inputs(args.cuad_limit):
        if not path.is_file():
            raise SystemExit(f"missing input: {path}")
        documents.append(segment_file(path, source_kind=kind))

    dump_documents(documents, args.out)

    print("Segmented documents:")
    for doc in documents:
        print(f"  {doc.document_id:40}  {len(doc.clauses):3} clauses  ({doc.source_kind})")
    print(f"Wrote {args.out}")

    target = next((doc for doc in documents if doc.document_id == args.print_id), None)
    if target is None and documents:
        target = documents[0]
        print(f"\nNo document_id={args.print_id!r}; printing {target.document_id}")
    if target is not None:
        limit = None if args.print_all else 3
        _print_clauses(target, preview=args.preview, limit=limit)
        print(
            "\nRead three clauses above and say what each is about "
            "(plain English). See data/exercises/day3_plain_english.md."
        )


if __name__ == "__main__":
    main()

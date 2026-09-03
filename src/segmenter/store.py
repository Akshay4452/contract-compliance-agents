"""Load contracts and persist ``{document_id, clauses[]}`` JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.segmenter.models import SegmentedDocument
from src.segmenter.splitter import segment_text

_SLUG = re.compile(r"[^a-z0-9]+")


def document_id_from_path(path: Path, prefix: str | None = None) -> str:
    stem = _SLUG.sub("-", path.stem.lower()).strip("-")
    if prefix:
        return f"{prefix}-{stem}"
    return stem


def segment_file(
    path: Path,
    *,
    document_id: str | None = None,
    source_kind: str = "file",
) -> SegmentedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    clauses = segment_text(text)
    return SegmentedDocument(
        document_id=document_id or document_id_from_path(path),
        clauses=clauses,
        source_path=str(path),
        source_kind=source_kind,
    )


def dump_documents(documents: list[SegmentedDocument], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_count": len(documents),
        "documents": [doc.to_dict() for doc in documents],
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_documents(path: Path) -> list[SegmentedDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SegmentedDocument.from_dict(item) for item in payload.get("documents") or []]

"""Load contracts and persist ``{document_id, clauses[]}`` JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from src.segmenter.models import SegmentedDocument
from src.segmenter.splitter import segment_text

ROOT = Path(__file__).resolve().parents[2]
_SLUG = re.compile(r"[^a-z0-9]+")


def cuad_txt_dir(root: Path | None = None) -> Path:
    """Resolve ``cuad.contracts_txt_dir`` from ``config/data_paths.yaml``."""
    root = root or ROOT
    with (root / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["cuad"]
    txt_dir = Path(cfg["contracts_txt_dir"])
    if not txt_dir.is_absolute():
        txt_dir = root / txt_dir
    if not txt_dir.is_dir():
        raise FileNotFoundError(
            f"CUAD contracts dir not found: {txt_dir}. "
            "Set cuad.contracts_txt_dir in config/data_paths.yaml"
        )
    return txt_dir


def pick_cuad(limit: int = 5, root: Path | None = None) -> list[Path]:
    """Return the first ``limit`` CUAD ``.txt`` files (sorted by name)."""
    txt_dir = cuad_txt_dir(root)
    files = sorted(txt_dir.glob("*.txt"))
    if len(files) < limit:
        raise FileNotFoundError(
            f"Need at least {limit} CUAD .txt files; found {len(files)} under {txt_dir}"
        )
    return files[:limit]


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

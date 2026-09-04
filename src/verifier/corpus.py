"""Build a lightweight GDPR corpus catalog for citation checks (no embeddings)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CorpusCatalog:
    """Known article numbers, topics, sources, and chunk ids from the GDPR corpus."""

    articles: frozenset[str] = field(default_factory=frozenset)
    topics: frozenset[str] = field(default_factory=frozenset)
    topics_lower: frozenset[str] = field(default_factory=frozenset)
    sources: frozenset[str] = field(default_factory=frozenset)
    sources_lower: frozenset[str] = field(default_factory=frozenset)
    chunk_ids: frozenset[str] = field(default_factory=frozenset)

    def __bool__(self) -> bool:
        return bool(self.articles or self.topics or self.sources or self.chunk_ids)


def _gdpr_cfg(root: Path) -> dict[str, Any]:
    with (root / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)["gdpr"]


def _topic(record: dict[str, Any]) -> str:
    """Mirror ``src.rag.chunker._topic`` without importing sentence-transformers."""
    rtype = record.get("type", "")
    if rtype == "article":
        return str(record.get("title") or "")
    if rtype == "qa":
        return str(record.get("category") or "")
    if rtype == "sanction":
        return str(record.get("violation_type") or "")
    if rtype == "checklist":
        return str(record.get("sector") or "")
    if rtype == "dpia":
        context = str(record.get("context") or "")
        return context[:80]
    return str(record.get("title") or record.get("category") or record.get("id") or "")


def _article(record: dict[str, Any]) -> str:
    article_number = record.get("article_number")
    return str(article_number).strip() if article_number not in (None, "") else ""


def _source(record: dict[str, Any]) -> str:
    return str(record.get("source_url") or "gdpr-en").strip()


def _chunk_id(record: dict[str, Any], chunk_index: int = 0) -> str:
    kind_map = {
        "article": "art",
        "qa": "qa",
        "sanction": "sanction",
        "checklist": "checklist",
        "dpia": "dpia",
    }
    kind = kind_map.get(str(record.get("type") or ""), str(record.get("type") or "unknown"))
    key = record.get("article_number") or record.get("id")
    return f"gdpr-{kind}-{key}-{chunk_index}"


def build_catalog_from_records(records: list[dict[str, Any]]) -> CorpusCatalog:
    articles: set[str] = set()
    topics: set[str] = set()
    sources: set[str] = set()
    chunk_ids: set[str] = set()

    for record in records:
        art = _article(record)
        if art:
            articles.add(art)
        topic = _topic(record).strip()
        if topic:
            topics.add(topic)
        source = _source(record)
        if source:
            sources.add(source)
        chunk_ids.add(_chunk_id(record, 0))

    topics_lower = frozenset(t.casefold() for t in topics)
    sources_lower = frozenset(s.casefold() for s in sources)
    return CorpusCatalog(
        articles=frozenset(articles),
        topics=frozenset(topics),
        topics_lower=topics_lower,
        sources=frozenset(sources),
        sources_lower=sources_lower,
        chunk_ids=frozenset(chunk_ids),
    )


def load_corpus_catalog(root: Path | None = None) -> CorpusCatalog:
    """Load catalog from local ``gdpr-en`` JSON (no Chroma / embeddings required)."""
    root = root or ROOT
    cfg = _gdpr_cfg(root)
    json_path = root / cfg["local_json"]
    if not json_path.is_file():
        raise FileNotFoundError(
            f"GDPR corpus JSON not found at {json_path}. "
            "Run: python scripts/download_gdpr_corpus.py"
        )
    records = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"expected a JSON list in {json_path}")
    return build_catalog_from_records(records)


@lru_cache(maxsize=4)
def cached_corpus_catalog(root_str: str) -> CorpusCatalog:
    return load_corpus_catalog(Path(root_str))

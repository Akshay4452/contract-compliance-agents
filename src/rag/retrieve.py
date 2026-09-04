"""Query the persisted GDPR Chroma collection."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml
from chromadb.errors import NotFoundError

from src.rag.chunker import token_count
from src.rag.store import (
    PROVENANCE_MODEL_KEY,
    PROVENANCE_WINDOW_KEY,
    open_gdpr_collection,
)

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


class StaleIndexError(RuntimeError):
    """Raised when the on-disk collection does not match current config."""


def _gdpr_cfg() -> dict:
    with (ROOT / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)["gdpr"]


def _assert_index_matches_config(collection, cfg: dict) -> None:
    stored = collection.metadata or {}
    stored_model = stored.get(PROVENANCE_MODEL_KEY)
    stored_window = stored.get(PROVENANCE_WINDOW_KEY)
    cfg_model = cfg["embedding_model"]

    if stored_model is None:
        raise StaleIndexError(
            "Persisted collection has no embedding_model metadata. "
            "Rebuild the index: python scripts/build_gdpr_index.py"
        )
    if stored_model != cfg_model:
        raise StaleIndexError(
            f"Index was built with embedding_model={stored_model!r} but config has "
            f"{cfg_model!r}. Rebuild the index: python scripts/build_gdpr_index.py"
        )
    if stored_window is not None and int(stored_window) != int(
        collection._embedding_function._model.max_seq_length
    ):
        raise StaleIndexError(
            f"Index max_seq_length={stored_window} does not match the live model "
            f"window {int(collection._embedding_function._model.max_seq_length)}. "
            "Rebuild the index: python scripts/build_gdpr_index.py"
        )


def _assert_query_fits(query: str, collection) -> None:
    model = collection._embedding_function._model
    tokenizer = model.tokenizer
    max_len = int(model.max_seq_length)
    n_tokens = token_count(tokenizer, query)
    if n_tokens > max_len:
        raise ValueError(
            f"query has {n_tokens} tokens > model window {max_len}; "
            "refusing to silently truncate"
        )


def _score_from_distance(distance: float) -> float:
    """Convert Chroma cosine distance (1 - similarity) to a higher-is-better score."""
    return float(1.0 - distance)


def _configure_logger() -> None:
    """Show retrieve hits on stderr without turning on Hugging Face HTTP logs."""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _log_hits(query: str, top_k: int, hits: list[dict], ids: list[str]) -> None:
    logger.info("query=%r  top_k=%s  hits=%s", query, top_k, len(hits))
    for rank, (chunk_id, hit) in enumerate(zip(ids, hits, strict=True), start=1):
        meta = hit["metadata"]
        logger.info("--- rank %s ---", rank)
        logger.info(
            "id=%s  type=%s  article=%s  topic=%s  score=%.4f",
            chunk_id,
            meta.get("type", ""),
            meta.get("article", ""),
            meta.get("topic", ""),
            hit["score"],
        )
        logger.info("source=%s", meta.get("source", ""))
        logger.info("text:\n%s", hit["text"])


def retrieve(
    query: str,
    top_k: int = 5,
    root: Path | None = None,
    *,
    log_hits: bool = True,
) -> list[dict]:
    """Return top_k hits: {text, score, metadata}. Opens the persisted index; does not rebuild."""
    if log_hits:
        _configure_logger()
    query = query.strip()
    if not query:
        raise ValueError("query must be non-empty")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    cfg = _gdpr_cfg()
    try:
        collection = open_gdpr_collection(root)
    except NotFoundError as exc:
        raise StaleIndexError(
            f"Collection {cfg['collection_name']!r} not found under {cfg['chroma_dir']}. "
            "Rebuild the index: python scripts/build_gdpr_index.py"
        ) from exc

    _assert_index_matches_config(collection, cfg)
    _assert_query_fits(query, collection)

    raw = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    hits: list[dict] = []
    for chunk_id, text, meta, distance in zip(
        ids, documents, metadatas, distances, strict=True
    ):
        hits.append(
            {
                "text": text or "",
                "score": _score_from_distance(distance),
                "metadata": dict(meta or {}),
            }
        )
    if log_hits:
        _log_hits(query, top_k, hits, ids)
    return hits


def _main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "subprocessor notification"
    retrieve(query, top_k=5)


if __name__ == "__main__":
    _main()

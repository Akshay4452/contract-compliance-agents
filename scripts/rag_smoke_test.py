"""Smoke-test the local GDPR RAG index (Day 2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.chunker import token_count
from src.rag.retrieve import retrieve
from src.rag.store import PROVENANCE_WINDOW_KEY, open_gdpr_collection

QUERIES = [
    "subprocessor notification",
    "data retention deletion",
    "personal data breach notification",
    "liability damages compensation",
    "return or delete data on contract end",
]


def _assert_all_chunks_fit(collection) -> None:
    max_len = int((collection.metadata or {}).get(PROVENANCE_WINDOW_KEY)
                  or collection._embedding_function._model.max_seq_length)
    tokenizer = collection._embedding_function._model.tokenizer
    raw = collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []

    overflow: list[str] = []
    token_counts: list[int] = []
    for chunk_id, text, meta in zip(ids, documents, metadatas, strict=True):
        n = token_count(tokenizer, text or "")
        token_counts.append(n)
        stored = (meta or {}).get("token_count")
        if stored is not None and int(stored) != n:
            overflow.append(
                f"{chunk_id}: stored token_count={stored} but re-tokenized={n}"
            )
        if n > max_len:
            overflow.append(f"{chunk_id}: {n} tokens > window {max_len}")

    peak = max(token_counts) if token_counts else 0
    print(f"window check: {len(ids)} chunks, max_token_count={peak} <= {max_len}")
    if overflow:
        raise AssertionError("chunks exceed embedding window:\n" + "\n".join(overflow))


def _query1_passes(hits: list[dict]) -> bool:
    """Top hits must include Article 28 / processor / sub-processor, not a random fine."""
    blob = " ".join(
        f"{hit['metadata'].get('article', '')} {hit['metadata'].get('topic', '')} {hit['text']}"
        for hit in hits
    ).lower()
    has_art28 = any(str(hit["metadata"].get("article")) == "28" for hit in hits)
    has_processor = any(
        marker in blob
        for marker in ("sub-processor", "subprocessor", "sub-processing", "processor")
    )
    top_is_random_sanction = (
        hits
        and hits[0]["metadata"].get("type") == "sanction"
        and "28" not in str(hits[0]["metadata"].get("article", ""))
    )
    return has_art28 and has_processor and not top_is_random_sanction


def _print_citations(query: str, hits: list[dict]) -> None:
    print(f"\n===== {query} =====")
    if not hits:
        print("  (no hits)")
        return
    for rank, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        snippet = hit["text"].replace("\n", " ")[:120]
        print(
            f"  {rank}. article={meta.get('article') or '-'}  "
            f"type={meta.get('type')}  topic={meta.get('topic')}  "
            f"score={hit['score']:.4f}"
        )
        print(f"     {snippet}")


def main() -> None:
    collection = open_gdpr_collection(ROOT)
    _assert_all_chunks_fit(collection)

    hits_q1: list[dict] | None = None
    for i, query in enumerate(QUERIES, start=1):
        hits = retrieve(query, top_k=5, root=ROOT)
        _print_citations(query, hits)
        if i == 1:
            hits_q1 = hits

    assert hits_q1 is not None
    if not _query1_passes(hits_q1):
        raise AssertionError(
            "query 'subprocessor notification' did not retrieve Article 28 / "
            "processor / sub-processor text. Fix flatten fields, then rebuild: "
            "python scripts/build_gdpr_index.py"
        )

    print("\nSMOKE PASS")


if __name__ == "__main__":
    main()

"""Build the local GDPR Chroma index (Day 2)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.chunker import _window, load_gdpr_chunks
from src.rag.store import build_gdpr_index


def main() -> None:
    with (ROOT / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["gdpr"]

    model_id = cfg["embedding_model"]
    overlap_ratio = float(cfg.get("chunk_overlap_ratio", 0.15))
    _, _, max_len, budget, overlap = _window(model_id, overlap_ratio)

    chunks = load_gdpr_chunks(ROOT)
    token_counts = [chunk["metadata"]["token_count"] for chunk in chunks]
    max_token_count = max(token_counts) if token_counts else 0

    print(f"model={model_id} max_seq_length={max_len} budget={budget} overlap={overlap}")
    print(f"chunks={len(chunks)} max_token_count={max_token_count}")

    art28 = next((chunk for chunk in chunks if chunk["id"] == "gdpr-art-28-0"), None)
    print("--- Article 28 sample ---")
    if art28:
        print(f"id={art28['id']} tokens={art28['metadata']['token_count']}")
        preview = art28["text"][:400].replace("\n", " ")
        print(f"text preview: {preview}")
    else:
        print("Article 28 chunk not found")

    print("Embedding and persisting ...")
    result = build_gdpr_index(root=ROOT, chunks=chunks)
    print(
        f"Wrote {result['n_chunks']} vectors -> {result['chroma_dir']} "
        f"(collection={result['collection_name']})"
    )


if __name__ == "__main__":
    main()

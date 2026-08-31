"""Persist GDPR chunks in a local Chroma collection."""

from __future__ import annotations

from pathlib import Path

import chromadb
import yaml
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from src.rag.chunker import load_gdpr_chunks

ROOT = Path(__file__).resolve().parents[2]

PROVENANCE_MODEL_KEY = "embedding_model"
PROVENANCE_WINDOW_KEY = "max_seq_length"


def _gdpr_cfg() -> dict:
    with (ROOT / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)["gdpr"]


def _chroma_metadata(meta: dict) -> dict:
    out: dict = {}
    for key, value in meta.items():
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif value is None:
            out[key] = ""
        else:
            out[key] = str(value)
    return out


def _embedding_function(model_id: str) -> SentenceTransformerEmbeddingFunction:
    return SentenceTransformerEmbeddingFunction(
        model_name=model_id,
        normalize_embeddings=True,
    )


def open_client(root: Path | None = None) -> chromadb.ClientAPI:
    """Open the persistent Chroma client under config chroma_dir."""
    root = root or ROOT
    cfg = _gdpr_cfg()
    persist_dir = root / cfg["chroma_dir"]
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def open_gdpr_collection(root: Path | None = None):
    """Open the persisted GDPR collection with the configured embedding function."""
    cfg = _gdpr_cfg()
    client = open_client(root)
    ef = _embedding_function(cfg["embedding_model"])
    return client.get_collection(
        name=cfg["collection_name"],
        embedding_function=ef,
    )


def build_gdpr_index(
    root: Path | None = None,
    chunks: list[dict] | None = None,
) -> dict:
    """Replace the GDPR collection with embeddings for the given (or loaded) chunks."""
    root = root or ROOT
    cfg = _gdpr_cfg()
    model_id = cfg["embedding_model"]
    collection_name = cfg["collection_name"]
    persist_dir = root / cfg["chroma_dir"]

    if chunks is None:
        chunks = load_gdpr_chunks(root)
    if not chunks:
        raise ValueError("no GDPR chunks to index")

    ef = _embedding_function(model_id)
    max_len = int(ef._model.max_seq_length)

    client = open_client(root)
    existing = {
        item if isinstance(item, str) else item.name
        for item in client.list_collections()
    }
    if collection_name in existing:
        client.delete_collection(collection_name)

    collection = client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={
            "hnsw:space": "cosine",
            PROVENANCE_MODEL_KEY: model_id,
            PROVENANCE_WINDOW_KEY: max_len,
        },
    )
    collection.add(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[_chroma_metadata(chunk["metadata"]) for chunk in chunks],
    )

    return {
        "collection_name": collection_name,
        "chroma_dir": str(persist_dir),
        "n_chunks": len(chunks),
        "embedding_model": model_id,
        "max_seq_length": max_len,
    }

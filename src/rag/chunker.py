"""Tokenizer-aware GDPR corpus chunker for RAG indexing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]

_KIND = {
    "article": "art",
    "qa": "qa",
    "sanction": "sanction",
    "checklist": "checklist",
    "dpia": "dpia",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def load_gdpr_chunks(root: Path | None = None) -> list[dict]:
    """Return chunks: {id, text, metadata}."""
    root = root or ROOT
    cfg = _gdpr_cfg()
    overlap_ratio = float(cfg.get("chunk_overlap_ratio", 0.15))
    _, tokenizer, max_len, budget, overlap = _window(cfg["embedding_model"], overlap_ratio)

    json_path = root / cfg["local_json"]
    records = json.loads(json_path.read_text(encoding="utf-8"))

    chunks: list[dict] = []
    for record in records:
        chunks.extend(record_to_chunks(record, tokenizer, max_len, budget, overlap))

    _assert_all_fit(chunks, tokenizer, max_len)
    return chunks


def _gdpr_cfg() -> dict:
    with (ROOT / "config" / "data_paths.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)["gdpr"]


def _window(model_id: str, overlap_ratio: float = 0.15):
    model = SentenceTransformer(model_id)
    max_len = int(model.max_seq_length)
    tokenizer = model.tokenizer
    n_special = len(tokenizer.encode("", add_special_tokens=True))
    budget = max_len - n_special
    overlap = max(1, int(budget * overlap_ratio))
    return model, tokenizer, max_len, budget, overlap


def token_count(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=True))


def _field(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        items = [str(item).strip() for item in value if item]
        return "; ".join(items) if items else None
    return str(value).strip()


def _join_parts(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def flatten_record(record: dict) -> str:
    rtype = record.get("type", "")

    if rtype == "article":
        parts = [
            _field(record.get("title")),
            _field(record.get("chapter")),
            _field(record.get("key_obligations")),
            _field(record.get("content")),
            _field(record.get("sanctions")),
            _field(record.get("practical_examples")),
        ]
    elif rtype == "checklist":
        parts = [
            _field(record.get("sector")),
            _field(record.get("priority")),
            _field(record.get("checklist_items")),
        ]
    elif rtype == "qa":
        parts = [
            _field(record.get("category")),
            _field(record.get("question")),
            _field(record.get("answer")),
            _field(record.get("regulatory_reference")),
        ]
    elif rtype == "sanction":
        parts = [
            _field(record.get("company")),
            _field(record.get("authority")),
            _field(record.get("violation_type")),
            _field(record.get("description")),
            _field(record.get("article_violated")),
            _field(record.get("amount_eur")),
        ]
    elif rtype == "dpia":
        parts = [
            _field(record.get("context")),
            _field(record.get("risk_description")),
            _field(record.get("mitigation_measures")),
            _field(record.get("residual_risk")),
        ]
    else:
        parts = []
        for key, value in record.items():
            if key in {"id", "type", "language"}:
                continue
            field = _field(value)
            if field:
                parts.append(field)

    return _join_parts([part for part in parts if part])


def _topic(record: dict) -> str:
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


def _source(record: dict) -> str:
    return str(record.get("source_url") or "gdpr-en")


def _article(record: dict) -> str:
    article_number = record.get("article_number")
    return str(article_number) if article_number else ""


def _chunk_id(record: dict, chunk_index: int) -> str:
    kind = _KIND.get(record.get("type", ""), str(record.get("type") or "unknown"))
    key = record.get("article_number") or record.get("id")
    return f"gdpr-{kind}-{key}-{chunk_index}"


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return paragraphs if paragraphs else [text.strip()]


def _split_sentences(text: str) -> list[str]:
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]
    return sentences if sentences else [text.strip()]


def _tail_overlap_text(tokenizer, text: str, overlap: int) -> str:
    if not text or overlap <= 0:
        return ""
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= overlap:
        return tokenizer.decode(token_ids, skip_special_tokens=True).strip()
    tail = token_ids[-overlap:]
    return tokenizer.decode(tail, skip_special_tokens=True).strip()


def _hard_token_chunks(text: str, tokenizer, budget: int, overlap: int) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []

    stride = max(1, budget - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(token_ids):
        window = token_ids[start : start + budget]
        piece = tokenizer.decode(window, skip_special_tokens=True).strip()
        if piece:
            chunks.append(piece)
        if start + budget >= len(token_ids):
            break
        start += stride
    return chunks


def chunk_text(text: str, tokenizer, max_len: int, budget: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if token_count(tokenizer, text) <= max_len:
        return [text]

    chunks: list[str] = []
    buffer = ""

    def emit_buffer() -> None:
        nonlocal buffer
        piece = buffer.strip()
        if piece:
            chunks.append(piece)
        buffer = ""

    def start_buffer(prefix: str, segment: str) -> None:
        nonlocal buffer
        candidate = f"{prefix} {segment}".strip() if prefix else segment
        if token_count(tokenizer, candidate) <= max_len:
            buffer = candidate
            return

        if prefix:
            emit_buffer()
            prefix = _tail_overlap_text(tokenizer, prefix, overlap)
            candidate = f"{prefix} {segment}".strip() if prefix else segment
            if token_count(tokenizer, candidate) <= max_len:
                buffer = candidate
                return

        if token_count(tokenizer, segment) <= max_len:
            buffer = segment
            return

        for piece in _hard_token_chunks(segment, tokenizer, budget, overlap):
            if token_count(tokenizer, piece) > max_len:
                raise ValueError(
                    f"hard window chunk has {token_count(tokenizer, piece)} tokens > {max_len}"
                )
            emit_buffer()
            chunks.append(piece)
        buffer = ""

    def add_segment(segment: str) -> None:
        nonlocal buffer
        segment = segment.strip()
        if not segment:
            return

        if token_count(tokenizer, segment) <= max_len:
            candidate = f"{buffer}\n\n{segment}".strip() if buffer else segment
            if token_count(tokenizer, candidate) <= max_len:
                buffer = candidate
                return

            previous = buffer
            emit_buffer()
            overlap_prefix = _tail_overlap_text(tokenizer, previous, overlap)
            start_buffer(overlap_prefix, segment)
            return

        if buffer:
            previous = buffer
            emit_buffer()
            overlap_prefix = _tail_overlap_text(tokenizer, previous, overlap)
        else:
            overlap_prefix = ""

        for sentence in _split_sentences(segment):
            if token_count(tokenizer, sentence) <= max_len:
                candidate = f"{buffer} {sentence}".strip() if buffer else sentence
                if token_count(tokenizer, candidate) <= max_len:
                    buffer = candidate
                    continue

                previous = buffer
                emit_buffer()
                overlap_prefix = _tail_overlap_text(tokenizer, previous, overlap)
                start_buffer(overlap_prefix, sentence)
                continue

            if buffer:
                emit_buffer()
            start_buffer("", sentence)

    for paragraph in _split_paragraphs(text):
        add_segment(paragraph)

    emit_buffer()
    return chunks


def record_to_chunks(
    record: dict,
    tokenizer,
    max_len: int,
    budget: int,
    overlap: int,
) -> list[dict]:
    flattened = flatten_record(record)
    if not flattened:
        return []

    texts = chunk_text(flattened, tokenizer, max_len, budget, overlap)
    article = _article(record)
    topic = _topic(record)
    source = _source(record)
    record_id = int(record["id"])
    record_type = str(record.get("type") or "")

    chunks: list[dict] = []
    for chunk_index, text in enumerate(texts):
        count = token_count(tokenizer, text)
        if count > max_len:
            raise ValueError(
                f"chunk {record_id}-{chunk_index} has {count} tokens > {max_len}"
            )
        chunks.append(
            {
                "id": _chunk_id(record, chunk_index),
                "text": text,
                "metadata": {
                    "topic": topic,
                    "source": source,
                    "type": record_type,
                    "article": article,
                    "record_id": record_id,
                    "chunk_index": chunk_index,
                    "token_count": count,
                },
            }
        )
    return chunks


def _assert_all_fit(chunks: list[dict], tokenizer, max_len: int) -> None:
    for chunk in chunks:
        count = chunk["metadata"]["token_count"]
        if count > max_len:
            raise ValueError(f"chunk {chunk['id']} has {count} tokens > {max_len}")


def _main() -> None:
    cfg = _gdpr_cfg()
    model_id = cfg["embedding_model"]
    overlap_ratio = float(cfg.get("chunk_overlap_ratio", 0.15))
    _, _, max_len, budget, overlap = _window(model_id, overlap_ratio)

    json_path = ROOT / cfg["local_json"]
    record_count = len(json.loads(json_path.read_text(encoding="utf-8")))
    chunks = load_gdpr_chunks()
    token_counts = [chunk["metadata"]["token_count"] for chunk in chunks]

    print(f"model={model_id} max_seq_length={max_len} budget={budget} overlap={overlap}")
    print(
        f"records={record_count} chunks={len(chunks)} "
        f"max_token_count={max(token_counts) if token_counts else 0}"
    )

    art28 = next((chunk for chunk in chunks if chunk["id"] == "gdpr-art-28-0"), None)
    print("--- Article 28 sample ---")
    if art28:
        print(f"id={art28['id']} tokens={art28['metadata']['token_count']}")
        preview = art28["text"][:400].replace("\n", " ")
        print(f"text preview: {preview}")
    else:
        print("Article 28 chunk not found")


if __name__ == "__main__":
    _main()

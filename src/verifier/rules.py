"""Pure verifier rules: quote grounding, regulation refs, confidence."""

from __future__ import annotations

import re
import unicodedata

from src.verifier.corpus import CorpusCatalog

# GDPR Article 28, Art. 32, article 5(1)(e), etc.
_ARTICLE_RE = re.compile(
    r"(?:gdpr\s*)?(?:articles?|arts?\.?)\s*(\d+[a-z]?(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)
# Bare "GDPR 28" / "GDPR 28 (Processors)" without the word Article
_GDPR_NUM_RE = re.compile(
    r"\bgdpr\s+(\d+[a-z]?)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Collapse whitespace and apply NFKC for stable substring checks."""
    if not text:
        return ""
    collapsed = " ".join(unicodedata.normalize("NFKC", text).split())
    return collapsed


def quote_in_clause(
    evidence_quote: str,
    clause_text: str,
    *,
    fuzzy: bool = True,
) -> bool:
    """True when the evidence quote appears in the clause.

    Exact match first. When ``fuzzy`` is True, also accept after whitespace
    normalization (still a substring — not an LLM rewrite).
    """
    quote = (evidence_quote or "").strip()
    clause = clause_text or ""
    if not quote or not clause:
        return False
    if quote in clause:
        return True
    if not fuzzy:
        return False
    return normalize_text(quote) in normalize_text(clause)


def extract_article_numbers(regulation_ref: str) -> list[str]:
    """Pull article numbers from a free-form regulation_ref string."""
    ref = (regulation_ref or "").strip()
    if not ref:
        return []
    found: list[str] = []
    for match in _ARTICLE_RE.finditer(ref):
        num = match.group(1).strip()
        # Keep the leading digits+optional letter as the catalog key
        base = re.match(r"(\d+[a-z]?)", num, re.IGNORECASE)
        if base:
            found.append(base.group(1))
    for match in _GDPR_NUM_RE.finditer(ref):
        found.append(match.group(1))
    # Dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for item in found:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def regulation_ref_known(regulation_ref: str, catalog: CorpusCatalog) -> bool:
    """True when the ref points at something in the GDPR corpus catalog.

    Accepts:
    - Article numbers present in the corpus (``GDPR 28``, ``Article 32``, …)
    - Topic / title strings that match (or are contained in) a known topic
    - Source URLs present in the corpus
    - Exact chunk ids (``gdpr-art-28-0``)
    """
    ref = (regulation_ref or "").strip()
    if not ref or not catalog:
        return False

    ref_cf = ref.casefold()

    if ref in catalog.chunk_ids or ref_cf in {c.casefold() for c in catalog.chunk_ids}:
        return True

    if ref in catalog.sources or ref_cf in catalog.sources_lower:
        return True

    for article in extract_article_numbers(ref):
        if article in catalog.articles or article.casefold() in {
            a.casefold() for a in catalog.articles
        }:
            return True

    # Topic: exact, or either side contains the other (handles truncated titles)
    if ref_cf in catalog.topics_lower:
        return True
    for topic in catalog.topics_lower:
        if topic and (topic in ref_cf or ref_cf in topic):
            return True

    return False


def confidence_ok(confidence: float | None, min_confidence: float) -> bool:
    try:
        value = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        return False
    return value >= float(min_confidence)

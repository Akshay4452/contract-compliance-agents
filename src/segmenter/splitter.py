"""Rule-based contract splitter (headings and numbered sections). No LLM."""

from __future__ import annotations

import re

from src.segmenter.models import Clause

# Top-level numbered headings: "1. DEFINITIONS." or "10) Limitation of Liability"
# Does not match subsections like "2.1 Overview" (no space after the first dot).
_NUMBERED = r"\d+[.)]\s+[A-Z][^\n]{0,90}$"

_ARTICLE = (
    r"(?:ARTICLE|Article)\s+(?:\d+|[IVXLCDM]+)"
    r"(?:\s*[-.:—–]\s*|\s+)[^\n]{0,90}$"
    r"|(?:ARTICLE|Article)\s+(?:\d+|[IVXLCDM]+)\s*$"
)

_SECTION = r"(?:Section|SECTION|Sec\.)\s+\d+(?:\.\d+)*\b[^\n]{0,90}$"

_CLAUSE_WORD = r"(?:CLAUSE|Clause)\s+\d+\b[^\n]{0,90}$"

# Short ALL-CAPS title line, not a preamble sentence.
_ALL_CAPS = r"[A-Z][A-Z0-9][A-Z0-9 /,&'()+.-]{4,70}$"

_HEADING = re.compile(
    rf"(?m)^(?:{_ARTICLE}|{_SECTION}|{_CLAUSE_WORD}|{_NUMBERED}|{_ALL_CAPS})"
)

_SKIP_ALL_CAPS_PREFIXES = (
    "THIS ",
    "WHEREAS",
    "NOW THEREFORE",
    "IN WITNESS",
    "WITNESSETH",
    "SOURCE:",
)

_ORPHAN_MAX_CHARS = 80


def _is_usable_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if any(upper.startswith(prefix) for prefix in _SKIP_ALL_CAPS_PREFIXES):
        return False
    if upper.startswith("SOURCE:"):
        return False
    return True


def _heading_matches(text: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for match in _HEADING.finditer(text):
        line = match.group(0)
        if _is_usable_heading(line):
            matches.append(match)
    return matches


def _title_from_chunk(chunk: str) -> str:
    first = chunk.strip().split("\n", 1)[0].strip()
    return first[:120]


def _offset_after_lstrip(raw: str, abs_start: int) -> int:
    leading = len(raw) - len(raw.lstrip())
    return abs_start + leading


def _merge_orphan_headings(
    spans: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """Fold a heading-only slice into the following clause."""
    if not spans:
        return []
    merged: list[tuple[int, int, str]] = []
    i = 0
    while i < len(spans):
        start, end, chunk = spans[i]
        body = chunk.strip()
        is_orphan = (
            i + 1 < len(spans)
            and len(body) <= _ORPHAN_MAX_CHARS
            and "\n" not in body.strip()
        )
        if is_orphan:
            n_start, n_end, n_chunk = spans[i + 1]
            combined = f"{body}\n\n{n_chunk.strip()}".strip()
            merged.append((start, n_end, combined))
            i += 2
            continue
        merged.append((start, end, chunk))
        i += 1
    return merged


def segment_text(text: str) -> list[Clause]:
    """Split contract text into ``Clause{id, text, start_hint}``."""
    if not text or not text.strip():
        return []

    matches = _heading_matches(text)
    spans: list[tuple[int, int, str]] = []

    if not matches:
        stripped = text.strip()
        start_hint = _offset_after_lstrip(text, 0)
        return [
            Clause(
                id="c1",
                text=stripped,
                start_hint=start_hint,
                title="full_document",
            )
        ]

    first_start = matches[0].start()
    if text[:first_start].strip():
        raw = text[:first_start]
        spans.append((0, first_start, raw))

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((start, end, text[start:end]))

    spans = _merge_orphan_headings(spans)

    clauses: list[Clause] = []
    for index, (start, end, raw) in enumerate(spans, start=1):
        chunk = raw.strip()
        if not chunk:
            continue
        start_hint = _offset_after_lstrip(text[start:end], start)
        title = _title_from_chunk(chunk)
        if index == 1 and start == 0 and not _HEADING.match(chunk.split("\n", 1)[0]):
            title = "Preamble"
        clauses.append(
            Clause(
                id=f"c{len(clauses) + 1}",
                text=chunk,
                start_hint=start_hint,
                title=title,
            )
        )
    return clauses

"""Build compliance prompts from text templates under ``src/prompts/``."""

from __future__ import annotations

from src.compliance.check_types import CHECK_DESCRIPTIONS, CheckType
from src.prompts import load_compliance_system_prompt, load_compliance_user_template


def get_system_prompt() -> str:
    """Load the compliance system prompt from disk (cached)."""
    return load_compliance_system_prompt()


def build_user_prompt(
    *,
    check_type: CheckType,
    clause_id: str,
    clause_text: str,
    rag_block: str,
) -> str:
    template = load_compliance_user_template()
    description = CHECK_DESCRIPTIONS[check_type]
    return template.format(
        check_type=check_type.value,
        check_description=description,
        clause_id=clause_id,
        clause_text=clause_text,
        rag_block=rag_block,
    )


def format_rag_hits(hits: list[dict]) -> str:
    if not hits:
        return "(no snippets retrieved)"
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or {}
        article = meta.get("article") or ""
        topic = meta.get("topic") or ""
        source = meta.get("source") or ""
        score = hit.get("score")
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else ""
        header = (
            f"[{i}] article={article} topic={topic} source={source} score={score_s}"
        )
        parts.append(f"{header}\n{hit.get('text') or ''}")
    return "\n\n".join(parts)

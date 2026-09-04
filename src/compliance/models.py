"""Pydantic schemas for compliance LLM structured output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComplianceLLMResult(BaseModel):
    """Single-check structured response from the LLM."""

    flag: bool = Field(
        description=(
            "True ONLY if this clause's subject is about the check_type AND "
            "the wording shows a clear gap for that check. False if the clause "
            "is adequate, unrelated (fees/definitions/preamble/etc.), or you "
            "would only argue that the topic is 'missing' from this clause. "
            "When unsure, false."
        )
    )
    issue: str = Field(
        default="",
        description="Short description of the gap when flag=True; empty otherwise.",
    )
    evidence_quote: str = Field(
        default="",
        description=(
            "When flag=True: required short verbatim substring from the clause "
            "that proves the gap. If you cannot quote such text, set flag=False. "
            "Must not be invented. Empty if flag=False."
        ),
    )
    regulation_ref: str = Field(
        default="",
        description=(
            "Best matching regulation pointer from the provided RAG snippets "
            "(e.g. article number or snippet id/topic). Empty if flag=False."
        ),
    )
    severity: Literal["high", "medium", "low"] | None = Field(
        default=None,
        description="Severity when flag=True; null when flag=False.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this assessment, 0 to 1.",
    )

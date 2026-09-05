"""Day 6 verifier: deterministic quote / citation / confidence gate."""

from __future__ import annotations

from src.verifier.agent import run_verifier, verify_finding
from src.verifier.rules import quote_in_clause, regulation_ref_known

__all__ = [
    "quote_in_clause",
    "regulation_ref_known",
    "run_verifier",
    "verify_finding",
]

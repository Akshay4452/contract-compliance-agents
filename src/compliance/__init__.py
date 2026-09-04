"""Compliance agent package (Day 5)."""

from __future__ import annotations

__all__ = [
    "CHECK_TYPES",
    "CheckType",
    "ComplianceLLMResult",
    "run_compliance",
]


def __getattr__(name: str):
    if name in {"CHECK_TYPES", "CheckType"}:
        from src.compliance import check_types

        return getattr(check_types, name)
    if name == "ComplianceLLMResult":
        from src.compliance.models import ComplianceLLMResult

        return ComplianceLLMResult
    if name == "run_compliance":
        from src.compliance.agent import run_compliance

        return run_compliance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""LangGraph compliance pipeline."""

from __future__ import annotations

__all__ = [
    "ComplianceState",
    "build_graph",
    "run_contract",
]


def __getattr__(name: str):
    if name == "ComplianceState":
        from src.graph.state import ComplianceState

        return ComplianceState
    if name in {"build_graph", "run_contract"}:
        from src.graph import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

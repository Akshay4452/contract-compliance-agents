"""Compile and run the linear Day 4 LangGraph pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.graph import nodes
from src.graph.state import ComplianceState


def build_graph():
    """``ingest → segment → compliance → verify → report → END``."""
    graph = StateGraph(ComplianceState)
    graph.add_node("ingest", nodes.ingest)
    graph.add_node("segment", nodes.segment)
    graph.add_node("compliance", nodes.compliance)
    graph.add_node("verify", nodes.verify)
    graph.add_node("report", nodes.report)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "segment")
    graph.add_edge("segment", "compliance")
    graph.add_edge("compliance", "verify")
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)
    return graph.compile()


def initial_state(contract_path: Path | str) -> ComplianceState:
    path = Path(contract_path)
    return {
        "contract_path": str(path),
        "doc": {"document_id": "", "source_path": str(path), "text": ""},
        "clauses": [],
        "findings": [],
        "verified_findings": [],
        "report": None,
        "errors": [],
    }


def run_contract(contract_path: Path | str) -> dict[str, Any]:
    """Invoke the compiled graph on one ``.txt`` contract."""
    app = build_graph()
    return app.invoke(initial_state(contract_path))

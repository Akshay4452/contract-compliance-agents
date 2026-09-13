"""Compile and run the linear LangGraph pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from src.graph import nodes
from src.graph.state import ComplianceState
from src.observability.otel import (
    get_tracer,
    set_span_attributes,
    setup_tracing,
    shutdown_tracing,
)
from src.segmenter.store import document_id_from_path

ROOT = Path(__file__).resolve().parents[2]


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


def run_contract(
    contract_path: Path | str,
    *,
    max_clauses: int | None = None,
    top_k: int | None = None,
    min_confidence: float | None = None,
    auto_approve: bool = False,
    out_dir: Path | str | None = None,
    write_report: bool = True,
    otel: bool | None = None,
    otel_exporter: str | None = None,
    otel_endpoint: str | None = None,
    otel_export_path: Path | str | None = None,
    shutdown_otel: bool = False,
) -> dict[str, Any]:
    """Invoke the compiled graph on one ``.txt`` contract.

    One OpenTelemetry trace = one contract run when OTel is enabled
    (``otel=True`` or ``otel.enabled`` in ``config/pipeline.yaml``).
    """
    load_dotenv(ROOT / ".env")
    tracing_on = setup_tracing(
        enabled=otel,
        exporter=otel_exporter,
        endpoint=otel_endpoint,
        export_path=otel_export_path,
        root=ROOT,
    )

    path = Path(contract_path)
    doc_hint = document_id_from_path(path) if path.exists() else path.stem
    from src.compliance.agent import load_pipeline_config

    pipe = load_pipeline_config(ROOT)
    model_name = str((pipe.get("compliance") or {}).get("model") or "gpt-4o-mini")

    nodes.set_compliance_options(max_clauses=max_clauses, top_k=top_k)
    nodes.set_verifier_options(min_confidence=min_confidence)
    nodes.set_reporter_options(
        auto_approve=auto_approve,
        out_dir=Path(out_dir) if out_dir is not None else None,
        write=write_report,
    )
    try:
        app = build_graph()
        state = initial_state(path)
        if not tracing_on:
            return app.invoke(state)

        tracer = get_tracer()
        with tracer.start_as_current_span("contract.run") as root_span:
            set_span_attributes(
                root_span,
                {
                    "agent": "pipeline",
                    "doc_id": doc_hint,
                    "contract_path": str(path),
                    "model": model_name,
                },
            )
            result = app.invoke(state)
            doc = result.get("doc") or {}
            findings = result.get("findings") or []
            verified = result.get("verified_findings") or []
            errors = result.get("errors") or []
            set_span_attributes(
                root_span,
                {
                    "doc_id": str(doc.get("document_id") or doc_hint),
                    "clause_count": len(result.get("clauses") or []),
                    "findings_count": len(findings),
                    "verified_count": len(verified),
                    "error_count": len(errors),
                },
            )
            return result
    finally:
        nodes.clear_compliance_options()
        nodes.clear_verifier_options()
        nodes.clear_reporter_options()
        if shutdown_otel:
            shutdown_tracing()

"""Day 10 — OpenTelemetry tracing unit tests (no LLM / no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.observability.otel import (
    JsonlSpanExporter,
    get_tracer,
    is_tracing_enabled,
    set_span_attributes,
    setup_tracing,
    shutdown_tracing,
    tokens_from_message,
)

ROOT = Path(__file__).resolve().parents[1]


class _FakeUsageMessage:
    def __init__(self, total: int) -> None:
        self.usage_metadata = {"total_tokens": total}
        self.response_metadata = {}


class OtelHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        shutdown_tracing()

    def tearDown(self) -> None:
        shutdown_tracing()

    def test_tokens_from_message(self) -> None:
        self.assertEqual(tokens_from_message(_FakeUsageMessage(42)), 42)
        self.assertIsNone(tokens_from_message(None))

    def test_jsonl_exporter_writes_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spans.jsonl"
            file_exporter = JsonlSpanExporter(path)
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(file_exporter))
            from src.observability.otel import _reset_global_tracer_provider

            _reset_global_tracer_provider()
            trace.set_tracer_provider(provider)
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("parent") as parent:
                set_span_attributes(parent, {"agent": "pipeline", "doc_id": "doc1"})
                with tracer.start_as_current_span("child") as child:
                    set_span_attributes(child, {"agent": "segment", "clause_id": "c1"})
            provider.force_flush()
            lines = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            names = {row["name"] for row in lines}
            self.assertEqual(names, {"parent", "child"})
            child_row = next(r for r in lines if r["name"] == "child")
            self.assertEqual(child_row["attributes"].get("clause_id"), "c1")
            self.assertTrue(child_row["parent_span_id"])


class PipelineTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        shutdown_tracing()

    def tearDown(self) -> None:
        shutdown_tracing()

    def test_setup_tracing_file_exporter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last_trace.jsonl"
            ok = setup_tracing(
                enabled=True,
                exporter="file",
                export_path=path,
                force=True,
            )
            self.assertTrue(ok)
            self.assertTrue(is_tracing_enabled())
            tracer = get_tracer()
            with tracer.start_as_current_span("contract.run") as span:
                set_span_attributes(span, {"agent": "pipeline", "doc_id": "x"})
                for name in ("ingest", "segment", "compliance", "verify", "report"):
                    with tracer.start_as_current_span(name):
                        pass
            shutdown_tracing()
            text = path.read_text(encoding="utf-8")
            for name in (
                "contract.run",
                "ingest",
                "segment",
                "compliance",
                "verify",
                "report",
            ):
                self.assertIn(name, text)

    def test_graph_emits_agent_and_clause_spans(self) -> None:
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        import src.observability.otel as otel_mod

        _reset = __import__(
            "src.observability.otel", fromlist=["_reset_global_tracer_provider"]
        )._reset_global_tracer_provider
        _reset()
        trace.set_tracer_provider(provider)
        otel_mod._ENABLED = True
        otel_mod._PROVIDER = provider

        contract = (
            ROOT
            / "data"
            / "exercises"
            / "day5_bad_contracts"
            / "bad_01_all_five_gaps.txt"
        )
        if not contract.is_file():
            self.skipTest(f"missing fixture: {contract}")

        def fake_compliance(clauses, **kwargs):  # noqa: ARG001
            if not clauses:
                return [], []
            text = str(clauses[0].get("text") or "x")
            clause_id = str(clauses[0].get("id") or "c1")
            finding = {
                "finding_id": f"{clause_id}:subprocessor",
                "clause_id": clause_id,
                "check_type": "subprocessor",
                "issue": "missing notice",
                "evidence_quote": text[: min(40, len(text))],
                "regulation_ref": "GDPR Article 28",
                "severity": "high",
                "confidence": 0.9,
            }
            return [finding], []

        from src.graph import nodes
        from src.graph.pipeline import build_graph, initial_state

        nodes.set_compliance_options(max_clauses=1)
        nodes.set_reporter_options(write=False, auto_approve=True)
        tracer = get_tracer()
        try:
            with patch("src.graph.nodes.run_compliance", side_effect=fake_compliance):
                with tracer.start_as_current_span("contract.run"):
                    result = build_graph().invoke(initial_state(contract))
        finally:
            nodes.clear_compliance_options()
            nodes.clear_reporter_options()

        names = [s.name for s in exporter.get_finished_spans()]
        self.assertIn("contract.run", names)
        for agent in ("ingest", "segment", "compliance", "verify", "report"):
            self.assertIn(agent, names, msg=f"missing span {agent}: {names}")
        self.assertTrue(
            any(n.startswith("verify.clause:") for n in names),
            msg=names,
        )
        self.assertGreaterEqual(len(result.get("clauses") or []), 1)
        self.assertGreaterEqual(len(result.get("findings") or []), 1)


if __name__ == "__main__":
    unittest.main()

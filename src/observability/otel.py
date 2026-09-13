"""Day 10 — OpenTelemetry setup (console / OTLP / optional JSONL dump)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
TRACER_NAME = "contract-compliance-agents"
logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_ENABLED = False
_PROVIDER: Any = None
_FILE_EXPORTER: "JsonlSpanExporter | None" = None


def load_otel_config(root: Path | None = None) -> dict[str, Any]:
    root = root or ROOT
    path = root / "config" / "pipeline.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return dict(raw.get("otel") or {})


def is_tracing_enabled() -> bool:
    return _ENABLED


def get_tracer():
    """Return the project tracer (no-op until ``setup_tracing`` succeeds)."""
    from opentelemetry import trace

    return trace.get_tracer(TRACER_NAME)


class JsonlSpanExporter:
    """Append finished spans as JSON lines (offline Day 10 deliverable)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Fresh file per process setup so the deliverable is readable.
        self.path.write_text("", encoding="utf-8")
        self._lock = threading.Lock()

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        lines: list[str] = []
        for span in spans:
            ctx = span.get_span_context()
            parent = span.parent
            parent_id = format(parent.span_id, "016x") if parent else None
            lines.append(
                json.dumps(
                    {
                        "name": span.name,
                        "trace_id": format(ctx.trace_id, "032x"),
                        "span_id": format(ctx.span_id, "016x"),
                        "parent_span_id": parent_id,
                        "start_time_unix_nano": span.start_time,
                        "end_time_unix_nano": span.end_time,
                        "status": str(span.status.status_code.name),
                        "attributes": dict(span.attributes or {}),
                    },
                    ensure_ascii=False,
                )
            )
        if lines:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return True


def _parse_exporters(exporter: str) -> set[str]:
    text = (exporter or "console").strip().lower()
    if text in {"both", "all", "console+otlp", "otlp+console"}:
        return {"console", "otlp"}
    parts = {p.strip() for p in text.replace(",", "+").split("+") if p.strip()}
    allowed = {"console", "otlp", "file"}
    unknown = parts - allowed
    if unknown:
        raise ValueError(
            f"unknown otel exporter(s): {sorted(unknown)}; "
            f"expected console, otlp, file (combine with +)"
        )
    return parts or {"console"}


def setup_tracing(
    *,
    enabled: bool | None = None,
    exporter: str | None = None,
    endpoint: str | None = None,
    service_name: str | None = None,
    export_path: str | Path | None = None,
    root: Path | None = None,
    force: bool = False,
) -> bool:
    """Configure the global TracerProvider. Returns True when tracing is active."""
    global _ENABLED, _PROVIDER, _FILE_EXPORTER

    root = root or ROOT
    cfg = load_otel_config(root)
    want = bool(cfg.get("enabled", False) if enabled is None else enabled)
    if not want:
        return False

    with _LOCK:
        if _ENABLED and not force:
            return True

        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        exporters = _parse_exporters(
            exporter if exporter is not None else str(cfg.get("exporter") or "console")
        )
        name = service_name or str(
            cfg.get("service_name") or "contract-compliance-agents"
        )
        resource = Resource.create(
            {
                "service.name": name,
                "service.namespace": "contract-compliance",
            }
        )
        provider = TracerProvider(resource=resource)

        if "console" in exporters:
            # Simple processor so smoke runs print spans immediately.
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        if "otlp" in exporters:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            ep = endpoint or str(
                cfg.get("endpoint") or "http://127.0.0.1:4318/v1/traces"
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=ep))
            )

        # Always write a local JSONL dump when export_path is configured,
        # or when "file" is listed — supports the Day 10 deliverable offline.
        path_raw = export_path if export_path is not None else cfg.get("export_path")
        if path_raw or "file" in exporters:
            path = Path(
                str(
                    path_raw
                    or "data/exercises/day10_otel/last_trace.jsonl"
                )
            )
            if not path.is_absolute():
                path = root / path
            file_exporter = JsonlSpanExporter(path)
            provider.add_span_processor(SimpleSpanProcessor(file_exporter))
            _FILE_EXPORTER = file_exporter
            logger.info("otel: writing spans to %s", path)
        else:
            _FILE_EXPORTER = None

        # Replace any prior provider (tests use force=True).
        if force:
            _reset_global_tracer_provider()
        trace.set_tracer_provider(provider)
        _PROVIDER = provider
        _ENABLED = True
        logger.info(
            "otel: enabled exporters=%s service=%s",
            sorted(exporters | ({"file"} if _FILE_EXPORTER else set())),
            name,
        )
        return True


def shutdown_tracing() -> None:
    """Flush exporters and reset module state (tests / process exit)."""
    global _ENABLED, _PROVIDER, _FILE_EXPORTER
    with _LOCK:
        provider = _PROVIDER
        _PROVIDER = None
        _FILE_EXPORTER = None
        _ENABLED = False
    if provider is not None:
        try:
            provider.force_flush()
        except Exception:  # noqa: BLE001
            logger.debug("otel force_flush failed", exc_info=True)
        try:
            provider.shutdown()
        except Exception:  # noqa: BLE001
            logger.debug("otel shutdown failed", exc_info=True)
    _reset_global_tracer_provider()


def _reset_global_tracer_provider() -> None:
    """Allow ``set_tracer_provider`` again (OTel normally allows only once)."""
    try:
        from opentelemetry.util._once import Once
        import opentelemetry.trace as trace_api

        trace_api._TRACER_PROVIDER = None  # type: ignore[attr-defined]
        trace_api._TRACER_PROVIDER_SET_ONCE = Once()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        logger.debug("otel provider reset skipped", exc_info=True)


def set_span_attributes(span: Any, attrs: dict[str, Any]) -> None:
    """Set attributes, skipping None and coercing to OTel-friendly types."""
    if span is None or not attrs:
        return
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float, str)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value))


def tokens_from_message(message: Any) -> int | None:
    """Best-effort token total from a LangChain AIMessage (or similar)."""
    if message is None:
        return None
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int):
            return total
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
        if isinstance(inp, int) or isinstance(out, int):
            return int(inp or 0) + int(out or 0)
    meta = getattr(message, "response_metadata", None)
    if isinstance(meta, dict):
        token_usage = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens")
            if isinstance(total, int):
                return total
    return None

# Day 10 — OpenTelemetry tracing

One trace per contract run. Spans: `contract.run` → ingest → segment →
compliance (per-clause) → verify (per-clause) → report.

Trace dumps (when enabled) write to `last_trace.jsonl` in this folder (gitignored).

## Commands

```powershell
pip install -r requirements.txt
py -3 -m unittest tests.test_otel -v

# Offline-friendly: console + JSONL
py -3 run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt `
  --max-clauses 1 --otel --auto-approve --no-report-files

# Jaeger (optional)
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.57
py -3 run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt `
  --max-clauses 1 --otel --otel-exporter otlp --auto-approve --no-report-files
```

Or set `otel.enabled: true` in `config/pipeline.yaml`.

**Span attributes:** `doc_id`, `clause_id`, `agent`, `model`, `tokens`, `findings_count`.

# Day 10 changes — OpenTelemetry tracing

Short record of Day 10. No CUAD F1 tuning (Day 11).

## Shipped

- OTel deps in `requirements.txt` (`opentelemetry-api/sdk` + OTLP HTTP exporter)
- Config: `otel:` block in `config/pipeline.yaml`
- `src/observability/otel.py` — setup (console / OTLP / JSONL file), helpers
- Graph instrumentation:
  - root span `contract.run` (one trace = one contract)
  - node spans: `ingest` → `segment` → `compliance` → `verify` → `report`
  - per-clause sub-spans under compliance + verify
- Attributes: `doc_id`, `clause_id`, `agent`, `model`, `tokens`, `findings_count`
- CLI: `run.py --otel` (+ `--otel-exporter`, `--otel-endpoint`, `--otel-export-path`)
- Offline tests: `tests/test_otel.py`

## How to run

```powershell
pip install -r requirements.txt
py -3 -m unittest tests.test_otel -v

# Console + JSONL dump (no Jaeger required)
py -3 run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt `
  --max-clauses 1 --otel --otel-exporter console --auto-approve --no-report-files

# Inspect saved spans
Get-Content data\exercises\day10_otel\last_trace.jsonl | Select-Object -First 20

# Optional: Jaeger all-in-one, then OTLP export
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.57
py -3 run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt `
  --max-clauses 1 --otel --otel-exporter otlp --auto-approve --no-report-files
# UI: http://127.0.0.1:16686  (service: contract-compliance-agents)
```

## Not this day

- Golden F1 targets / CUAD subset tuning (Day 11)
- Retries / production hardening (Day 12)

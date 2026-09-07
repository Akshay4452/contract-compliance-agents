# Day 8 changes — synthetic golden set + eval harness

Short record of Day 8. No MLflow or OpenTelemetry (Days 9–10).

## Shipped

- Golden set under `data/golden/`:
  - 8 synthetic contracts (`contracts/synthetic_01.txt` … `_08.txt`)
  - `compliance_cases.jsonl` — **50** labeled rows (`expected_flag` + optional severity / evidence anchor)
  - `segmentation_cases.jsonl` — expected clause counts for those contracts
- Eval package `eval/`:
  - `golden.py` — loaders
  - `metrics.py` — precision/recall/F1, quote_valid_rate, clause-count / span overlap
  - `predictions.py` — offline (script from golden) + live (full pipeline) runners
  - `run_eval.py` — prints baseline scores to console; writes `data/golden/baseline_results.json`
- Offline unit tests: `tests/test_eval.py`

## How to run

```powershell
python -m unittest tests.test_eval -v
python eval/run_eval.py
python eval/run_eval.py --hallucinate-every 5   # stress verifier quote rate
# live LLM baseline (needs OPENAI_API_KEY + built `.chroma/gdpr`):
python eval/run_eval.py --mode live --max-clauses 3
```

## Metrics

| Area | What is scored |
|------|----------------|
| Segmentation | Predicted clause count within tolerance; optional CUAD span overlap when `CUAD_v1` is present |
| Compliance | Precision / recall / F1 on `expected_flag` overall and per `check_type` |
| Verifier | `%` findings whose evidence quote appears in the clause; verifier pass rate |

Offline mode scripts positives from the golden set (harness sanity → F1≈1.0). Live mode is the real system baseline for trend tracking.

## Not this day

- MLflow experiment tracking (Day 9)
- OpenTelemetry traces (Day 10)
- Prompt A/B compare script

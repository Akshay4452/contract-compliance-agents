# Day 9 changes — MLflow eval experiment tracking

Short record of Day 9. No OpenTelemetry (Day 10).

## Shipped

- `mlflow>=2.14.0` in `requirements.txt`; local store `./mlruns` (gitignored)
- Config: `compliance.prompt_version` + `mlflow:` block in `config/pipeline.yaml`
- `eval/mlflow_tracking.py` — params / metrics / artifact helpers
- `eval/run_eval.py` — `--mlflow`, `--experiment`, `--run-name`, `--prompt-version`,
  `--tracking-uri`, latency p95 in the JSON report
- `eval/compare_runs.py` — table (or `--json`) comparing recent runs; group by
  `prompt_version` or `top_k`
- Offline tests cover param/metric extraction + 3-run MLflow round-trip

**Logged params:** `model`, `top_k`, `prompt_version`, `check_types`  
**Logged metrics:** `precision`, `recall`, `f1`, `quote_valid_rate`, `latency_p95`  
**Logged artifacts:** `eval_report.json`, `findings.json`, `audit_report.md` (when present)

## How to run

```powershell
pip install -r requirements.txt
py -3 -m unittest tests.test_eval -v

# Deliverable: 3 MLflow runs with different top_k (oracle = offline harness)
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 3 --run-name top_k_3
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 5 --run-name top_k_5
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 8 --run-name top_k_8
py -3 eval/compare_runs.py --param top_k

# Real model comparison (needs OPENAI_API_KEY + Chroma)
py -3 eval/run_eval.py --live --auto-approve --mlflow --top-k 3 --run-name live_k3
py -3 eval/run_eval.py --live --auto-approve --mlflow --top-k 5 --run-name live_k5

mlflow ui --backend-store-uri sqlite:///mlruns/tracking.db
```

Bump `compliance.prompt_version` (or pass `--prompt-version v2`) when you edit
`src/prompts/compliance_*.txt`, then compare with `eval/compare_runs.py --param prompt_version`.

## Not this day

- OpenTelemetry traces (Day 10)
- CUAD subset tuning / F1 targets (Day 11)

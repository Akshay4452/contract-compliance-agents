# Day 9 — MLflow eval tracking

Local experiment store for golden-eval runs. Tracking data lives in repo-root
`mlruns/` (gitignored).

## Commands

```powershell
pip install -r requirements.txt

# Three offline oracle runs with different top_k (harness demo; F1 stays 1.0)
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 3 --run-name top_k_3 --prompt-version v1
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 5 --run-name top_k_5 --prompt-version v1
py -3 eval/run_eval.py --oracle --skip-segmentation --mlflow --top-k 8 --run-name top_k_8 --prompt-version v1

# Compare logged runs
py -3 eval/compare_runs.py
py -3 eval/compare_runs.py --param top_k

# Live model baseline (needs OPENAI_API_KEY + Chroma)
py -3 eval/run_eval.py --live --auto-approve --mlflow --top-k 5 --run-name live_topk5

# UI (optional)
py -3 -m mlflow ui --backend-store-uri sqlite:///mlruns/tracking.db
```

Params logged: `model`, `top_k`, `prompt_version`, `check_types`.  
Metrics logged: `precision`, `recall`, `f1`, `quote_valid_rate`, `latency_p95`.  
Artifacts: `eval_report.json`, `findings.json`, `audit_report.md` (when present).

# Day 8 eval outputs

Artifacts from `eval/run_eval.py`.

| Path | Role |
|------|------|
| `last_eval.json` | Latest metrics dump (gitignored) |
| `reports/<doc_id>/` | Day 7-style artifacts from `--live` (gitignored) |

## Commands

```powershell
py -3 -m unittest tests.test_eval -v
py -3 eval/run_eval.py --validate-only
py -3 eval/run_eval.py --oracle
py -3 eval/run_eval.py
py -3 eval/run_eval.py --live --auto-approve
```

`--oracle` checks the harness (expect F1 ≈ 1.0). `--live` is the real model baseline
(requires `pip install -r requirements.txt`, `OPENAI_API_KEY`, and `.chroma/gdpr`).

Day 9 MLflow: add `--mlflow` (see `docs/day9_changes.md` and `data/exercises/day9_eval/`).

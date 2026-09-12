# Day 8 changes — synthetic golden set + eval harness

Short record of Day 8. No MLflow or OpenTelemetry (Day 9–10).

## Shipped

- Golden set `data/golden/compliance_cases.jsonl` — **47** labeled rows
  - Contracts: Day 5 bad trio + `good_01_clean_template` + `bad_04_soft_gaps`
  - Mix of `expected_flag: true` (gaps) and `false` (should stay quiet)
  - `contracts_index.yaml` maps `contract_id` → `.txt`
- Eval package `eval/`:
  - `run_eval.py` — CLI: `--validate-only`, `--oracle`, `--live`, `--predictions-dir`, CUAD segmentation
  - Compliance precision / recall / F1 (overall + per `check_type`)
  - Verifier `quote_valid_rate` via `quote_in_clause` (same as Day 6 gate)
  - Segmentation: clause-count tolerance + mean max-IoU vs CUAD SQuAD spans
- Config knobs under `eval:` in `config/pipeline.yaml`
- Offline tests: `tests/test_eval.py`

## How to run

```powershell
py -3 -m unittest tests.test_eval -v
py -3 eval/run_eval.py --validate-only
py -3 eval/run_eval.py --oracle
py -3 eval/run_eval.py
py -3 eval/run_eval.py --live --auto-approve
```

`--oracle` proves the scoring path offline (expect F1=1.0 — harness check, not model quality).
Live mode needs `OPENAI_API_KEY`, GDPR Chroma index, and `pip install -r requirements.txt`.
Without it, segmentation baselines still print; compliance/verifier need `--live`,
`--oracle`, or `--predictions-dir`.

## Not this day

- ~~MLflow experiment tracking (Day 9)~~ — done; see `docs/day9_changes.md`
- OpenTelemetry traces (Day 10)
- CUAD subset tuning / F1 targets (Day 11)

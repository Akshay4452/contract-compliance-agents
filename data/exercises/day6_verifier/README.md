# Day 6 — Verifier smoke fixtures

Offline checks for the deterministic verifier (no LLM). Uses Day 5
`bad_01_all_five_gaps.txt` as the clause source and hand-built findings
(grounded + hallucinated).

```powershell
python scripts/verifier_smoke_test.py
python -m unittest tests.test_verifier -v
```

Report: `smoke_results.json` in this folder (gitignored if large; safe to overwrite).

# Day 7 — Reporter + human gate + E2E

Packages verified (and rejected) findings into `findings.json` +
`audit_report.md`. Outputs live in this folder (same pattern as Day 5 / Day 6).

## Offline smoke (no LLM)

```powershell
python scripts/reporter_smoke_test.py
python -m unittest tests.test_reporter -v
```

Writes:

- `smoke_results.json` — pass/fail meta
- `smoke_bad_01/findings.json`
- `smoke_bad_01/audit_report.md`

## Live E2E (needs `OPENAI_API_KEY` + Chroma index)

3 synthetic bad contracts + first 2 CUAD templates from Day 3:

```powershell
python scripts/day7_e2e.py
# cost control on CUAD only:
python scripts/day7_e2e.py --cuad-max-clauses 2
# or synthetic only:
python scripts/day7_e2e.py --skip-cuad
# eval-style gate:
python scripts/day7_e2e.py --auto-approve
```

**Why a CUAD report can look “empty”:** `--cuad-max-clauses 2` only runs
compliance on the first N segments (often title/definitions). The LLM is
prompted to return `flag=false` for unrelated clauses, so you get zero
findings even though the report still lists all segmented clauses. The
executive summary now shows `Compliance analyzed: N of M clauses` when
capped. For a fuller CUAD pass, omit the cap (more LLM cost) or raise it.

Each run writes `<document_id>/findings.json` + `audit_report.md`, plus
`e2e_results.json` summarizing all cases.

## Single-contract CLI

```powershell
python run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt --preview-findings 10
python run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt --auto-approve
```

Default artifact parent: `data/exercises/day7_reporter` (override with `--out-dir`).

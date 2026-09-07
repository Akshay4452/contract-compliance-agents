# Day 8 golden set

Synthetic compliance answer keys for the Week 2 eval harness.

| Path | Role |
|------|------|
| `contracts/*.txt` | 8 synthetic contracts (01–03 from Day 5 fixtures; 04–08 new) |
| `compliance_cases.jsonl` | 50 labeled `(contract_id, clause_id, check_type)` rows |
| `segmentation_cases.jsonl` | Expected clause counts (± tolerance) for those contracts |

## Row schema (`compliance_cases.jsonl`)

```json
{
  "contract_id": "synthetic_01",
  "clause_id": "c4",
  "check_type": "subprocessor",
  "expected_flag": true,
  "expected_severity": "high",
  "notes": "removed approval requirement"
}
```

`clause_id` values match the Day 3 rule-based segmenter (`c1`, `c2`, …).
`expected_severity` is set only when `expected_flag` is true.

## Run eval

```powershell
python eval/run_eval.py
python eval/run_eval.py --mode live   # needs OPENAI_API_KEY
```

See [`docs/day8_changes.md`](../../docs/day8_changes.md).

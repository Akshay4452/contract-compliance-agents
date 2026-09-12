# Day 8 golden set

Hand-labeled `(contract_id, clause_id, check_type)` rows for compliance P/R.

| Artifact | Role |
|----------|------|
| `compliance_cases.jsonl` | 47 labeled cases (expected_flag true/false) |
| `contracts_index.yaml` | Maps `contract_id` → `.txt` path |
| `../exercises/day5_bad_contracts/` | Original Day 5 synthetics |
| `../exercises/day8_golden/` | Clean template + soft-gap MSA |

`contract_id` matches `document_id_from_path` (slug of the `.txt` stem).
`clause_id` matches the Day 3 rule-based segmenter on that file.

Authoring rule (from the 2-week plan): you own ground truth — verify each row
before trusting eval scores.

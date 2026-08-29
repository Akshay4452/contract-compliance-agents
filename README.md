# Contract Compliance Agents

Multi-agent contract review pipeline: segment clauses, check against GDPR corpus (RAG), verify citations, produce audit reports.

## Day 1 status

- [x] Project scaffold
- [x] CUAD v1 path config (510 contracts, external)
- [ ] GDPR corpus download
- [ ] Manual clause exercise

## Quick start

```powershell
cd C:\Users\Admin\Projects\contract-compliance-agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/inspect_cuad.py
python scripts/download_gdpr_corpus.py
python scripts/day1_manual_clause_exercise.py
```

## Data strategy

| Dataset | Role | In repo? |
|---------|------|----------|
| CUAD v1 (510 contracts) | Contracts + gold labels | No — path in `config/data_paths.yaml` |
| AYI-NEDJIMI/gdpr-en | GDPR RAG corpus | Downloaded to `data/regulations/` |
| Synthetic golden | Your answer key | Added Week 2 |

**Dev vs eval:** Build on 5–10 contracts daily; run full 510 only in eval jobs.

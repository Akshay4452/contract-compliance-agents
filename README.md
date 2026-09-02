# Contract Compliance Agents

Multi-agent contract review pipeline: segment clauses, check against GDPR corpus (RAG), verify citations, produce audit reports.

## Plan

The 14-day schedule (Days 1–3 done, Days 4–14 remaining) lives in [`docs/two_week_plan.md`](docs/two_week_plan.md). Use that file as the source of truth when picking up work.

## Day 1 status

- [x] Project scaffold
- [x] CUAD v1 path config (510 contracts, external)
- [x] GDPR corpus download
- [x] Manual clause exercise

## Day 2 status

- [x] Window-aware GDPR chunker (`src/rag/chunker.py`)
- [x] Local Chroma index (`scripts/build_gdpr_index.py`)
- [x] `retrieve(query, top_k)` with hit logging
- [x] 5-query smoke test

Chunk length is **not** a hardcoded 500–800 words. It follows the embedding model's `max_seq_length` (256 WordPieces for `all-MiniLM-L6-v2`).

## Day 3 status

- [x] Rule-based segmenter (`src/segmenter/`) → `Clause{id, text, start_hint}`
- [x] Graph-ready store: `{document_id, clauses[]}`
- [x] 3 templates + 2 CUAD (or bundled samples) → `data/exercises/day3_segmentation/clauses.json`
- [x] Print-one-contract CLI + smoke test

See [`docs/day3_changes.md`](docs/day3_changes.md). No LangGraph or LLM on this day.

## Quick start

```powershell
cd C:\AI\contract-compliance-agents
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/inspect_cuad.py
python scripts/download_gdpr_corpus.py
python scripts/day1_manual_clause_exercise.py
python scripts/build_gdpr_index.py
python scripts/rag_smoke_test.py
python scripts/segment_contracts.py
python scripts/segment_smoke_test.py
```

Single query against the persisted index:

```powershell
python -m src.rag.retrieve "subprocessor notification"
```

Print clauses for one file (Day 3):

```powershell
python -m src.segmenter data/templates/saas_msa.txt
```

## Data strategy

| Dataset | Role | In repo? |
|---------|------|----------|
| CUAD v1 (510 contracts) | Contracts + gold labels | No — path in `config/data_paths.yaml` |
| AYI-NEDJIMI/gdpr-en | GDPR RAG corpus | Downloaded to `data/regulations/` |
| Day 3 templates / samples | Dev contracts for segmentation | Yes — `data/templates/`, `data/samples/` |
| Synthetic golden | Your answer key | Added Week 2 |

**Dev vs eval:** Build on 5–10 contracts daily; run full 510 only in eval jobs.

RAG retrieves **GDPR rules** from `.chroma/gdpr`. CUAD contracts stay out of that index.

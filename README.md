# Contract Compliance Agents

Multi-agent contract review pipeline: segment clauses, check against GDPR corpus (RAG), verify citations, produce audit reports.

## Plan

The 14-day schedule (Days 1–7 done; Days 8–14 remaining) lives in [`docs/two_week_plan.md`](docs/two_week_plan.md). Use that file as the source of truth when picking up work.

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
- [x] 5 CUAD contracts → `data/exercises/day3_segmentation/clauses.json`
- [x] Print-one-contract CLI + smoke test

See [`docs/day3_changes.md`](docs/day3_changes.md). No LangGraph or LLM on this day.

## Day 4 status

- [x] `ComplianceState` + linear LangGraph: ingest → segment → stub compliance/verify/report
- [x] CLI: `python run.py --contract path/to/msa.txt` (empty findings, smoke report)

No RAG/LLM calls yet — stubs only. Real compliance agent is Day 5.

## Day 5 status

- [x] Compliance agent: RAG (`.chroma/gdpr`) + LLM structured findings
- [x] One prompt with enum `check_type`; all **5** checks on every clause
- [x] Config: `config/pipeline.yaml`; secrets: `.env` (`OPENAI_API_KEY`)
- [x] Synthetic bad contracts + answer keys: `data/exercises/day5_bad_contracts/`

Offline smoke (mocked LLM + real RAG; drives all three bad-contract fixtures):

```powershell
python scripts/compliance_smoke_test.py
```

Report (overwritten each run): `data/exercises/day5_bad_contracts/smoke_results.json`
— lists each problematic clause, check type, and why.

Live run on a known-bad MSA (needs `OPENAI_API_KEY`):

```powershell
python run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt --preview-findings 20
```

Writes `bad_01_all_five_gaps_llm_results.json` next to the contract (clause + why).
Prompts live in `src/prompts/compliance_system.txt` and `compliance_user.txt`.

## Day 6 status

- [x] Verifier gate: quote ∈ clause, regulation_ref ∈ GDPR catalog, min confidence
- [x] Annotates findings with `verified` / `reject_reason`; fills `verified_findings`
- [x] Config: `verifier.min_confidence` / `fuzzy_quote` in `config/pipeline.yaml`
- [x] Unit tests + offline smoke (no LLM)

```powershell
python -m unittest tests.test_verifier -v
python scripts/verifier_smoke_test.py
```

Report stub now summarizes verified vs rejected counts. Full Markdown packaging is Day 7 (done).

## Day 7 status

- [x] Reporter: `findings.json` + `audit_report.md` (exec summary, verified table, rejected appendix)
- [x] Human gate: `pending_review` / `--auto-approve` → `approved`
- [x] Artifacts under `data/exercises/day7_reporter/<doc_id>/`
- [x] Offline smoke + live E2E (3 synthetic + 2 CUAD)

```powershell
python -m unittest tests.test_reporter -v
python scripts/reporter_smoke_test.py
python scripts/day7_e2e.py --skip-cuad
# full E2E (needs OPENAI_API_KEY + CUAD):
python scripts/day7_e2e.py --cuad-max-clauses 2
```

See [`docs/day7_changes.md`](docs/day7_changes.md) and `data/exercises/day7_reporter/README.md`.

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
python scripts/compliance_smoke_test.py
python scripts/verifier_smoke_test.py
python -m unittest tests.test_verifier -v
python scripts/reporter_smoke_test.py
python -m unittest tests.test_reporter -v
```

Day 5–7 live run (needs `OPENAI_API_KEY` in `.env`):

```powershell
copy .env.example .env
# edit .env and set OPENAI_API_KEY=
python run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt --preview-findings 20
python run.py --contract data\exercises\day5_bad_contracts\bad_02_breach_and_exit.txt --preview-findings 20
python run.py --contract data\exercises\day5_bad_contracts\bad_03_open_sharing.txt --preview-findings 20
python scripts/day7_e2e.py --cuad-max-clauses 2
```

See `data/exercises/day5_bad_contracts/README.md` for why each file is “bad.”
Day 7 reports land in `data/exercises/day7_reporter/`.

Single query against the persisted index:

```powershell
python -m src.rag.retrieve "subprocessor notification"
```

Print clauses for one CUAD file (Day 3; path from your local CUAD tree):

```powershell
python -m src.segmenter CUAD_v1\full_contract_txt\2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.txt
```

Run the Day 5 pipeline (needs ``OPENAI_API_KEY``; use ``--max-clauses`` to limit cost):

```powershell
python run.py --contract CUAD_v1\full_contract_txt\2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.txt --max-clauses 1
```

## Data strategy

| Dataset | Role | In repo? |
|---------|------|----------|
| CUAD v1 (510 contracts) | Contracts + gold labels | No — path in `config/data_paths.yaml` |
| AYI-NEDJIMI/gdpr-en | GDPR RAG corpus | Downloaded to `data/regulations/` |
| Synthetic golden | Your answer key | Added Week 2 |

**Dev vs eval:** Build on 5–10 contracts daily; run full 510 only in eval jobs.

RAG retrieves **GDPR rules** from `.chroma/gdpr`. CUAD contracts stay out of that index.

# Day 3 changes — segmentation + clause store

Short record of Day 3. No LangGraph, no LLM, no SOC 2 index, CUAD is not written into Chroma.

## Code

- `src/segmenter/` — reusable package. Ingest a `.txt` contract, emit `Clause{id, text, start_hint}` (plus a heading `title` for humans).
- Rule-based splitter only: `ARTICLE` / `Section` / top-level `1.` numbered headings / short ALL-CAPS titles. Subsections like `10.1` stay inside the parent clause. No LLM cleanup.
- Store shape later graph state can reuse: `{document_id, clauses[]}`. Batch file is `data/exercises/day3_segmentation/clauses.json`.
- `scripts/segment_contracts.py` — segments **5 CUAD** `.txt` files from `config/data_paths.yaml` → `cuad.contracts_txt_dir` (default first 5 alphabetically; override with `--cuad-limit`).
- `scripts/segment_smoke_test.py` — numbered-heading fixture + 5-CUAD shape/round-trip checks.
- CLI: `python -m src.segmenter path/to/contract.txt` prints every clause for one file.

## Data

| Slot | Source |
|------|--------|
| 1–5 | First 5 files under `CUAD_v1/full_contract_txt` (path from YAML) |

Synthetic NDA/MSA/DPA templates and sample fallbacks were removed. CUAD must be present locally.

## Legal reading

Three CUAD clauses labeled in plain English: `data/exercises/day3_plain_english.md`. Glossary covers **liability cap** and **indemnification**.

## Out of scope (on purpose)

LangGraph, LLM-as-judge, SOC 2 corpus, CUAD in Chroma, full 510-contract eval.

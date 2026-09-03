# Day 3 changes — segmentation + clause store

Short record of what this branch adds. No LangGraph, no LLM, no SOC 2 index, CUAD is not written into Chroma.

## Code

- `src/segmenter/` — reusable package. Ingest a `.txt` contract, emit `Clause{id, text, start_hint}` (plus a heading `title` for humans).
- Rule-based splitter only: `ARTICLE` / `Section` / top-level `1.` numbered headings / short ALL-CAPS titles. Subsections like `10.1` stay inside the parent clause. No LLM cleanup.
- Store shape later graph state can reuse: `{document_id, clauses[]}`. Batch file is `data/exercises/day3_segmentation/clauses.json`.
- `scripts/segment_contracts.py` — 3 templates + 2 CUAD `.txt` files when `config/data_paths.yaml` points at a local CUAD tree; otherwise 2 bundled samples so the 5-document run still works.
- `scripts/segment_smoke_test.py` — numbered-heading fixture, MSA liability/indemnity checks, JSON round-trip.
- CLI: `python -m src.segmenter path/to/contract.txt` prints every clause for one file.

## Data

| Slot | Document | Kind |
|------|----------|------|
| 1 | `data/templates/nda_mutual.txt` | template |
| 2 | `data/templates/saas_msa.txt` | template |
| 3 | `data/templates/dpa_processor.txt` | template |
| 4–5 | first two CUAD `*.txt` **or** `data/samples/consulting_agreement.txt` + `data/samples/vendor_security_addendum.txt` | cuad / sample |

This environment had no CUAD checkout, so the committed `clauses.json` is the 3 templates + 2 samples (49 clauses total).

## Legal reading (same skill as Day 1, now on generated clauses)

Three MSA clauses labeled in plain English: `data/exercises/day3_plain_english.md`. Glossary updated for **liability cap** and **indemnification**.

## Out of scope (on purpose)

LangGraph, LLM-as-judge, SOC 2 corpus, CUAD in Chroma, full 510-contract eval.

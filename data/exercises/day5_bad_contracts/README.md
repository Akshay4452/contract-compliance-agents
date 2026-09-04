# Day 5 — Synthetic bad contracts

Hand-edited vendor MSAs with **known gaps** for the five compliance checks.
Not legal advice; test fixtures only.

| File | Intent |
|------|--------|
| `bad_01_all_five_gaps.txt` | Every check type has an obvious gap |
| `bad_02_breach_and_exit.txt` | Strong on some topics; weak on breach notice + data return |
| `bad_03_open_sharing.txt` | Weak on subprocessors + retention; other checks OK |

Each `*_expected.json` is the answer key: why the contract is bad, which
sections should flag, and which should stay quiet.

## Offline smoke (mocked LLM + real RAG)

```powershell
python scripts/compliance_smoke_test.py
```

Writes a readable report to `smoke_results.json` in this folder: which
`clause_id` / title failed which `check_type`, and **why**.

Live LLM runs write `{contract_stem}_llm_results.json` here (same shape).

## Live run (real OpenAI)

```powershell
python run.py --contract data\exercises\day5_bad_contracts\bad_01_all_five_gaps.txt --preview-findings 20
```

# Day 3 — three clauses in plain English

Source: `data/templates/saas_msa.txt`, document_id `saas-msa`, produced by `scripts/segment_contracts.py`.

Same exercise as Day 1: read the generated clause, say what it is about. These three are the Day 3 legal terms (indemnification, liability cap) plus one downstream check type (subprocessors).

## c2 — `1. SERVICES.`

**What it is about:** The vendor will run the analytics product for the customer, and may use its own vendors (subprocessors, e.g. a cloud host) to do that. The vendor still owns the outcome. Before a *new* subprocessor that handles personal data is added, the customer gets 30 days' written notice.

**Why it matters later:** Compliance check type 1 (subprocessor / third-party sharing). A missing notice duty is a flag.

## c10 — `9. INDEMNIFICATION.`

**What it is about:** If a third party sues the customer because the product copies someone else's IP, or because the vendor handled personal data in a way it was not allowed to, the vendor pays the legal costs. The other way around: if the customer's own data or misuse causes a lawsuit, the customer pays. The paying side runs the defense; the other side has to cooperate.

**Plain label:** Who picks up the bill if someone outside the contract sues.

## c11 — `10. LIMITATION OF LIABILITY.`

**What it is about:** If things go wrong, the most either side usually pays is the fees from the last 12 months. Lost profits and other indirect losses are off the table. Three exceptions are *not* capped that way: indemnity (section 9), a confidentiality breach, and unpaid invoices.

**Plain label:** Worst-case payout = 12 months of fees, unless it is indemnity, secrets, or unpaid bills.

`10.1` and `10.2` stayed in this one clause on purpose (subsections are not split). Downstream agents treat "limitation of liability" as a single unit of work.

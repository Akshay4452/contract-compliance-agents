# Legal Glossary (Day 1–3)

Plain-English definitions for this project. You are **not** becoming a lawyer; you are building a **first-pass reviewer**.

| Term | Plain English | Analogy |
|------|---------------|---------|
| **Contract** | Full legal agreement between two parties | Gym membership form, but 30 pages |
| **Clause** | One section / rule inside the contract — the unit of work for every later agent | One bullet: "You can cancel with 30 days notice" |
| **MSA** | Master Service Agreement — main commercial deal | The main "we'll use your software" contract |
| **DPA** | Data Processing Agreement — how vendor handles personal data | Add-on about privacy when they store customer data |
| **NDA** | Non-Disclosure Agreement — keep information secret | "Don't tell anyone our plans" |
| **Subprocessor** | Vendor's vendor (e.g. AWS under your SaaS provider) | You hire a caterer; they subcontract the bakery |
| **Liability cap** | Maximum amount one party pays if something goes wrong, often the last 12 months of fees; consequential damages (lost profits) are usually excluded | "Worst case, we only owe what you paid us this year" |
| **Indemnification** | One party pays legal costs if the other gets sued because of them (IP infringement, mishandled personal data, etc.) | "If we're sued because of your bug, you pay the lawyers" |
| **GDPR** | EU law on how personal data must be handled | Traffic rules, but for personal data |
| **Data retention** | How long you may keep personal data, and deleting it when that period ends | Keep the CCTV tape 30 days, then wipe it |
| **SOC 2** | Security audit framework (not a law) | A report card that says "this company secures data well" |

## Day 3 — read one real MSA section

From `data/templates/saas_msa.txt` (labeled in `data/exercises/day3_plain_english.md`):

- **Liability cap (section 10):** payout ceiling is 12 months of fees. Indirect / lost-profit damages are out. Indemnity, confidentiality breaches, and unpaid invoices sit *outside* that ceiling.
- **Indemnification (section 9):** vendor covers IP-infringement and unauthorized-processing lawsuits; customer covers lawsuits caused by customer data or misuse. The paying side controls the defense.

## What CUAD gives you

CUAD = **510 real contracts** where lawyers already highlighted important clauses (41 types).

- You do **not** judge if the law is right.
- You check: did our system find text that **overlaps** what CUAD highlighted?

## What GDPR corpus gives you

The rule book your compliance agent searches — like looking up "what does GDPR say about subprocessors?"

Day 2 RAG retrieves **these GDPR rules**, not CUAD contracts. CUAD is the contract set you will grade later.

# Day 3 — three clauses in plain English

Source: first and fifth documents in `data/exercises/day3_segmentation/clauses.json` (CUAD contracts), produced by `scripts/segment_contracts.py`.

Same exercise as Day 1: read the generated clause, say what it is about.

## From the co-branding agreement — `c2` `1. DEFINITIONS.`

**What it is about:** The parties define key terms used later (Content, Co-Branded Site, Customers, Escrow Services, Launch Date, Marks, and so on). Without these definitions, later sections would be ambiguous.

**Plain label:** Dictionary of words for this contract.

## From the co-branding agreement — `c7` `8. TERM AND TERMINATION.`

**What it is about:** How long the deal lasts, how either side can end it (breach, change of control, bankruptcy), and what happens after exit (rights end, money owed is paid, marks/content come down). Some sections survive termination.

**Plain label:** When the deal ends and what you must still do.

## From the Adams Golf endorsement agreement — `c12` `14. INDEMNITY`

**What it is about:** The consultant must pay Adams Golf’s legal costs if Adams Golf is sued because the consultant broke a promise in the agreement. That is indemnification: one party covers the other when a third-party claim is their fault.

**Plain label:** Who pays if a breach causes a lawsuit.

Day 3 glossary terms (liability cap / indemnification) still apply when you later spot limitation-of-liability text inside a larger clause — the segmenter keeps subsections together on purpose.

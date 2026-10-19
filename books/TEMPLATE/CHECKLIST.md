# <book> completion checklist — the only thing that grants DONE

Contract: `docs/verification-protocol.md` §6. Drafted at P0, adopted only after a
consensus swarm audits its **coverage**, then append-only. No item is ever
deleted or reworded to make it pass; an item ends `closed` (consensus) or
`waived` (operator, in their own words). No item may require reading the whole
book — split page ranges into batches small enough for one fresh verifier.

| id | item — one falsifiable claim | kind | deciding evidence (re-runnable) | status | receipts |
|---|---|---|---|---|---|
| C001 | strict extraction roundtrip is exact, including every join space | instrument | `venv/bin/python bin/validate_pdf.py out/remediated.pdf --book .` → PASS | open | |
| C002 | text never overflows or occludes, pages 1–40 | visual | primary, native-res pass; page list + per-page verdict recorded in REVIEW.md | open | |

`kind`: `instrument` (a command decides) · `visual` (primary looks at the stated
range, at the resolution the judgment needs) · `record` (an existing ledger is
audited for gaps).
`status`: `open` → `validating` → `closed` · `waived`

## Coverage census — every one of these must appear as one or more items

- [ ] each AGENTS.md defect category that applies to this book, per page range
- [ ] each playbook gate P0–P5, and both SHIPS-ONLY-IF-COMPLETE passes (P6-L layout, P6.5 verbatim)
- [ ] every explicit request in the operator brief
- [ ] every ISSUES.md row (resolved, or waived below)
- [ ] every figure in IMAGES.md (ladder rung taken, or its restoration claim closed)
- [ ] ship mechanics: one UA-2 deliverable; qpdf and veraPDF green; strict
      extraction exact; structure/role/association gates green; document
      metadata and producer string correct

## Appended after adoption (new findings; same coverage audit applies)

| id | item | kind | evidence | added because | status |
|---|---|---|---|---|---|
| | | | | | |

## Waived by the operator (quote them; never paraphrase, never self-waive)

| id | item | operator's words |
|---|---|---|
| | | |

## Final re-validation (run once everything is closed)

Every item is checked again — the primary re-reads each one, and an independent
consensus loop double-checks each one, in waves. A failed item reopens and the
cycle resumes; a newly discovered gap becomes a new item, not a shrug.

| wave | items | verdict | who re-derived it |
|---|---|---|---|
| | | | |

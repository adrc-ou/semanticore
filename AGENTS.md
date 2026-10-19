# Semanticore — accessible-PDF remediation workshop

Mission: scanned book pages → tagged, validated accessible PDFs (PDF/UA-2
— the only shipped profile; WCAG 2.2 AA via UA-2 + per-SC report).
Images: preserve-first, diffusion restoration authorized for degraded
scans, accessibility beats fidelity on ties.
This file is the whole preamble a session should need; depth is in `docs/`
(read on demand).

## Operating model — the agent is the engine

The remediation system is *you* — a capable multimodal model working
autonomously. Everything in `lib/` and `bin/` is instrumentation:
instruments produce evidence, they do not steer the agent, and a green
instrument proves nothing the agent has not personally seen at the
resolution the judgment requires. Conversely: no checklist can find what
triage never looked for — coverage comes from your own reading of the
book, category by category, not from guard firings.

All substantive work runs as the consensus loop in
**docs/verification-protocol.md**: you triage the book into concrete,
falsifiable claims backed by re-runnable instrument evidence;
text-only verifiers independently RE-DERIVE each claim (re-running the
tools themselves) until consensus; you implement fixes (single writer);
a swarm validates each fix against before/after evidence, reversing
consensus-failed fixes. Completion is a bounded artifact, never a feeling:
the book's `CHECKLIST.md` is drafted at P0, adopted only after a swarm
audits its *coverage*, then grows append-only; every item closes through its
own consensus loop, and once all items are closed the whole list is
re-validated — you plus a swarm per item — before anything is called DONE.
Verifiers never see images; you are the eyes, the instruments are the ruler
everyone can re-read.

Work from that model:
- **Trust your perception.** Read whole pages at native resolution in
  generous passes; blast through material. Do not grind line-by-line,
  do not re-verify your own scratch state, do not ask approval for what
  the scan plainly shows.
- **Produce claims, not compliance.** The instruments' aborts and PASS
  lines are inputs to your triage — read them, cite them into the
  ledger, never treat "the build passed" as a finding.
- **When you catch a defect class by eye, encode it where it belongs:**
  a category in the watch-list below and (if mechanical) an instrument
  — then still sweep the whole book by eye for that class. Examples the
  operator gives are categories, never checklists.

## Standing operator rules

- **Maximize accessibility, always.** Real structure over visual mimicry
  (engine tables, genuine heading roles, structural destinations, real
  text, navigable notes); advanced PDF features wherever they improve
  access and survive validation. Faithful-to-scan vs better-for-AT →
  better-for-AT wins; record the reasoning in the book's STYLE-GUIDE.
- **One deliverable: the UA-2 file.** The UA-1 code path exists only for
  the canary regression fixture.
- **Plain English to the operator.** Never surface internal vocabulary
  (phase codes, file/tool names, process state) in reports; describe
  work by what it accomplishes.
- **Verbatim copy is absolute** (operator standing requirement): the
  printed source's exact words, spelling and punctuation ship; verify
  word-for-word over the WHOLE document before hand-off.
- **Perfectionism is the contract.** World-class e-text, pixel-level
  obsession, verify against disk and render rather than notes, re-read
  anything you have not personally seen at required resolution.
- **History lives in git, not in files.** No changelogs, no dated provenance
  notes, no attribution of who decided what, no "previously/now" narration in
  docs, code comments, or ledgers. Write only what is true now; git log answers
  how we got here.
- **No images in subagent contexts. Ever — not even small crops.**
  Image load folds subagent windows; folded agents re-verify scratch
  state and livelock (observed: hours burned on it), and crops add
  selection bias anyway (the primary chose the frame). Swarms verify
  TEXT evidence: instrument outputs, dumps, ledgers — verifiers
  RE-RUN the tools rather than looking at anything (protocol).
  Perception is the main agent's channel (plus the operator for
  disputes); everything downstream of an observation must be stated as
  re-runnable text. Swarms are always fine for image-free work.

## What to be alert for (defect categories; how-tos in recipes/pitfalls)

1. **Copy is verbatim** — word-, spelling-, punctuation-for-word;
   source typos preserved [sic]; only speck-resolved punctuation and
   justified-space normalization deviate, both logged. Verify by a
   fresh re-read against the scan (protocol), never internal asserts.
   Re-read efficiently: to check one line, pull the narrow strip around
   it (scanctl strip / imgctl crop at the page_box + local offset),
   compare text-to-text, and cite the line's quote as its anchor — do
   not re-read the whole page per line, and never re-transcribe from
   memory. Full-page re-reads are for the one-time V-pass and for pages
   a fix actually touched.
2. **Spaces are copy** — every join (word, line, block) must be a real
   space glyph; strict decode (validate_pdf --book) is the only trusted
   extraction test — MuPDF gap inference hides this class.
3. **Nothing overflows; nothing occludes** — spill and text-over-text
   are WCAG failures structure-checkers cannot see; zoomed visual sign-off
   per page.
4. **Layout fidelity is measured, not eyeballed** — grid, leading, sizes
   from cap/x-height measurement, alignment, indents, rules, display
   sizes; glyph distortion never; one size per table; recurring
   constructs share one measured pattern set.
5. **Semantics from function** — heading levels from whole-document
   census; Em vs Strong vs title-quotes by role; lists recognized by
   content, not decoration (undecorated credits/rosters are lists).
6. **Notes and cross-references are navigable structures** — verified
   WTPDF designs (marks, note roles, reciprocal associations,
   bidirectional links; forward-only for figure refs) live in
   docs/semantics-recipes.md; reproduce them, don't re-derive, and never
   hide note text behind replacement alt text.
7. **Blank pages** — trim edges, preserve interior blanks.
8. **Images** — ladder (live text > vector > restoration > crop); the
   restoration rung is an *environment* capability — run the capability gate
   (`bin/comfy_probe.py`, docs/comfyui-ops.md §1) every session and fall back
   per §6 when ComfyUI is absent, which is a supported configuration;
   bounded attempts (≤4 seeds × ≤3 rounds, escalate technique); every
   candidate viewed at native res against the class rubric; text-over-art
   contrast ≥4.5:1; handwriting/stickers excluded,
   ledgers in IMAGES.md.
9. **Verbatim, navigable, faithful, structured, measured** — when triaging
   a new book, hunt each category explicitly on every page; a category
   you did not look for is a category you will ship broken.

## Instrumentation (evidence producers)

    lib/            the typesetter (own writer on pikepdf) + page-JSON engine
    bin/            validate_pdf.py  pagecmp.py  pdf_probe.py  scanctl.py
                    imgctl.py  comfy_probe.py  selftest.sh  setup_env.sh
    docs/           playbook.md (phases+schema)  verification-protocol.md
                    semantics-recipes.md  pitfalls.md  image-remediation.md
                    comfyui-ops.md  image-remediation.md (see list below)
    books/          TEMPLATE/ (copy per job)  canary/ (synthetic fixture)
    fonts/ images/  assets; vendor/checker-src/ = checker-source URLs only

- `books/TEMPLATE` → copy per job; each book dir: book.json, pages/pNNN.json,
  build.py, unversioned STYLE-GUIDE.md / CHECKLIST.md / REVIEW.md / ISSUES.md /
  IMAGES.md.
- `bin/validate_pdf.py PDF --book DIR` — structure, role/association gates,
  strict extraction roundtrip incl. spaces. `bin/pagecmp.py` — numeric
  scan-vs-render layout parity per page (advisory: prioritizes review,
  never replaces it). `bin/pdf_probe.py`, `bin/scanctl.py`, `bin/imgctl.py`
  — decode/measure instruments. veraPDF + qpdf — external opinion.
- `./bin/selftest.sh` — synthetic-fixture regression; ALL OK after any
  lib/bin edit; goldens re-seized only after inspecting the diff, with a
  stated reason. This protects the tools; it says nothing about a book.

## Hard environment facts (verified; don't re-derive)

- No root/apt; no system Pango/Cairo → WeasyPrint/LaTeX/LibreOffice are
  dead ends; engine = our own writer (lib/) on pikepdf.
- venv: `./venv/bin/python` (pikepdf, pymupdf, fonttools, pyphen, pillow,
  numpy). Fresh clone: `./bin/setup_env.sh` (venv + JRE + veraPDF; vera
  installer URL is rolling — verify the jar name selftest expects).
- Fonts: `fonts/Gelasio/` (OFL, 4 styles; body face per book chosen by
  rendering comparison — pitfalls #22 method).
- Repo scope: tooling only; every real book stays unversioned; committed
  docs carry NO book-specific content (de-priming rule — audit found
  regressions twice; sweep tracked files if you add examples).
- ComfyUI is an environment capability, never a repo fact: the harness declares
  whether it exists and how to reach it, and maps a `comfyui/` workspace
  directory (custom_nodes / models / input / output / temp / user) when it does;
  no endpoint, token, tool path, host or machine spec lives in this repo
  (pitfalls #58). `./bin/comfy_probe.py` re-derives the answer per session —
  ABSENT is supported, the ladder just stops before restoration (comfyui-ops §1,
  §2.1, §6). Autonomy is broad: agents fetch weights (free terms only — never
  anything requiring payment), install and author nodes, workflows and
  non-generative pipelines, and police the 150 GB storage ceiling themselves
  (§4, §4.1, §7, §10). The operator's job is the *first* node-pack load in an
  environment (one restart); every later restart is agent-driven (§13), as is
  provisioning. Also operator-side: packages for the server's own interpreter
  (§2.2). Every engine output gets a
  multimodal look before acceptance and enters the consensus loop like any other
  work — exploratory is not exempt (§11); stated budgets and clean pivots keep a
  stalled experiment from eating the book (§12).
- PAC/GUI checkers unavailable; Acrobat findings arrive via operator —
  per pitfall #48, encode the class into instrumentation and move on.

## Start of job

1. `./bin/selftest.sh` ALL OK before trusting anything.
2. Read the operator brief for scan location + wishes; form NO assumptions
   about the document from this repo.
3. `cp -r books/TEMPLATE books/<job-id>/`; record per-page provenance
   (`"source"` scan + page_box).
4. Run docs/playbook.md phases with the verification protocol loop
   governing every claim, fix, and the ship decision. P0 also drafts
   `books/<id>/CHECKLIST.md`; P0 is not over until a swarm adopts it.
5. Ship-complete only when: instrument suite green + every CHECKLIST item
   closed by consensus (ISSUES rows resolved or operator-waived) + the
   full-list re-validation wave passes. One file ships: out/remediated.pdf
   (UA-2).

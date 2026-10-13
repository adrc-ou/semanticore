# pds — accessible-PDF remediation workshop

Mission: turn scanned book pages into tagged, validated accessible PDFs
(PDF/UA-2 primary, PDF/UA-1 variant; WCAG 2.2 AA via UA-2 + per-SC report),
including images: preserve-first, diffusion restoration authorized for
degraded scans (ComfyUI host), accessibility beats fidelity on ties.
This file is the only preamble a session should need. Deep detail lives in
`docs/` — read on demand, not upfront.

## Hard environment facts (verified; do not re-derive)

- No root. No apt. No system Pango/Cairo → **WeasyPrint/LaTeX/LibreOffice
  are dead ends.** Engine = our own writer (`lib/`) on pikepdf.
- Python venv: `./venv/bin/python` (pikepdf, pymupdf, fonttools, pyphen,
  pillow, numpy). Fresh clone: `./bin/setup_env.sh` rebuilds venv +
  portable JRE + veraPDF from pinned URLs.
- Validators on tap: veraPDF (`-f ua1|ua2`), qpdf (via pikepdf Job),
  MuPDF `pdf_check_structure_tree`, `bin/validate_pdf.py`. PAC/other Java
  GUIs unavailable (docs/pitfalls.md §D).
- Fonts: `fonts/Gelasio/` (SIL OFL, 4 styles; default body face — chosen
  per book by rendering comparison, see pitfalls #22 for the METHOD).
- Repo scope: **tooling only.** `.gitignore` keeps every real book, scan,
  output, venv and tools/ unversioned; `books/TEMPLATE` + `books/canary`
  (synthetic fixture) are the only book-shaped things committed.

## Layout

    AGENTS.md           you are here
    lib/                pdfwriter.py (PDF object engine), typeset.py
                        (page-JSON → tagged PDF), pds_bootstrap.py
    bin/                selftest.sh (regression harness — run first, always)
                        setup_env.sh (fresh-clone bootstrap)
                        scanctl.py (scan meta/strips/halves/render/diffcols)
                        validate_pdf.py (structural + roundtrip validator)
                        pdf_probe.py (decode a build's tree/content for QA)
                        imgctl.py (image workbench: measure/crop/contact/
                        score/diffmap/contrast/wrapmap/ledger)
                        comfy_client.py (ComfyUI API client; HTTP untested)
    docs/playbook.md    phased process P0–P6, page-JSON schema, gates
    docs/pitfalls.md    numbered one-line rules, all battle-tested
    docs/semantics-recipes.md   typography→role tables; first-contact designs
    docs/image-remediation.md   image policy: ladder, fidelity, rubric,
                        attempt protocol (§5: bounded attempts, never loop)
    docs/comfyui-ops.md ComfyUI plan + validate-on-arrival checklist
    books/              TEMPLATE/ (start here), canary/ (fixture)
    images/             rubrics/ (7 classes), workflows/, storage.md
    vendor/checker-src/ README of checker-source URLs (reference, not vendored)
    tools/ venv/ work/   local install state & scratch (unversioned)

## You were handed scans and told to process them. Start here.

1. `./bin/selftest.sh` — must print ALL OK before you trust anything here.
2. Read the user's brief for WHERE the scans are and any per-job wishes.
   Formulate NO assumptions about the document's content, structure or
   genre from this repo — nothing here describes it, deliberately.
3. `cp -r books/TEMPLATE books/<job-id>/`; record scan provenance (file +
   page crop box, in px) per page inside `pages/pNNN.json` under a
   `"source"` key; name files `pNNN` in READING order (folio field carries
   the printed number; `"side": "v|r"` drives mirror margins).
4. Run the playbook. P0 measurement → P1 crops → P2 transcription (per
   page; the parallelizable step) → P3 CROSS-PAGE PASSES (heading census,
   style/pattern census, figure classification, note pairing — this is
   where meaning that spans pages gets decided; do not skip or defer) →
   P4 config → P5 build+validate → P6 visual QA.
5. Every uncertain reading → ISSUES.md row with the crop path; open rows
   BLOCK the final build — ask the user, attaching the crop. Every image →
   IMAGES.md ledger per docs/image-remediation.md. Never guess glyphs,
   never accept an unviewed generated image, never "fix" source typos
   silently.
6. Ship only when: validate_pdf PASS + veraPDF profile PASS + qpdf clean +
   roundtrip exact + montage visual pass + ISSUES.md has no un-asked rows.

## Non-negotiable gates

1. `bin/selftest.sh` ALL OK after every `lib/` or `bin/` edit. Approved
   engine-output changes only: inspect diff, `./bin/selftest.sh
   --update-goldens`, say WHY in the commit. Never re-seize to silence
   unexplained drift.
2. Page JSON self-respects: engine asserts joined line-table == text
   (soft vs real EOL hyphens are declared, not inferred — `hard_hyphen_lines`).
3. Layout collisions abort builds by design: fix the MODEL (widths,
   indents, band, order), never the guard.
4. Structure semantics are CONTEXTUAL decisions (heading levels from the
   whole-document census; Em vs Strong vs quoted-title from function),
   recorded in the book's STYLE-GUIDE.md as you go — that file is the
   anti-drift contract for multi-session jobs.

## Image work in one breath (full policy: docs/image-remediation.md)

- Ladder: live text > vector > restored raster (diffusion OK) > faithful
  crop. Restoration must be justifiable against the source crop; palette
  from measurement; no invented content; handwriting/scan damage excluded.
- Engine figures: `kind:"figure"` blocks (band | floating | artifact),
  images embedded with `/Figure /Alt /Lang /Placement /BBox`; wrap =
  per-line `widths`/`indents` in the transcription.
- Generation loop: ≤4 seeds × ≤3 rounds, escalate technique not luck;
  review EVERY candidate (contact sheet + native crops) against
  `images/rubrics/<class>.json` gates+weights; accept ≥1.6 + clean gates
  else best-of + ISSUES row; ledger every decision.
- WCAG wins ties: `imgctl contrast` audits text-over-art ≥4.5:1; adjust
  the art zone, never the requirement.
- ComfyUI machine arrives separately: follow docs/comfyui-ops.md
  validate-on-arrival checklist BEFORE trusting any planned pipeline;
  record findings in its PROVEN LOG; respect the 150 GB cap + storage.md.

## Proven facts that must not drift (full list: docs/pitfalls.md)

- Root `Document` element `/P` → StructTreeRoot; flat marked sequences
  (greenfield loses content association on nesting); one sequence per line
  per element by convention.
- UA identity via `pdfuaid` (part 2 also needs `rev=2024` + `%PDF-2.0`);
  `Em`/`Strong` are PDF 2.0 STRUCTURE ROLES and each element needs its own
  `/NS` → shared indirect `<</NS (http://iso.org/pdf2/ssn)>>`.
- `E`/`ActualText`/`Alt` are direct StructElem keys; soft EOL hyphens =
  `/Span` + `ActualText U+00AD`; ToUnicode includes space.
- UA-2 wants structure destinations for bookmarks; artifacts need
  `/Type /Pagination /Subtype /PageHeader /BBox /Attached`.
- Numbers in PDF objects are numbers (not strings); Image XObject names
  normalized with `/` in Resources AND `Do`; subset fonts with
  retain_gids + zeroed head timestamps.

## Session log (tooling only — append one line per meaningful change; NO
## per-document content, findings or job details go here: those live in the
## unversioned book directories)

- 2026-10-13: de-priming pass — committed docs scrubbed of every example
  drawn from real books (recipes/playbook/template now use neutral
  placeholders); playbook gained explicit per-page "source" provenance
  field; AGENTS is generic by construction: it tells a session HOW to
  start, never WHAT to expect.
- 2026-10-12 engine extraction byte-verified vs prior build; canary
  synthetic fixture + negative collision test anchor selftest.sh;
  setup_env.sh reproduces the toolchain from this repo alone.
- 2026-10-12 figure/wrap/hard-hyphen engine paths verified against veraPDF
  ua2+ua1 on the fixture; rubrics for 7 image classes checked in; ComfyUI
  ops plan committed as DESIGN (its HTTP paths and pipelines are explicitly
  UNTESTED — validate on arrival).

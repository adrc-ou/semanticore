# Remediation playbook — phases, artifacts, gates

Scope: scanned book → single accessible PDF (UA-2 + UA-1 variant), faithful
visual recreation, no artifacts of scanning. Scales from one spread to full
textbooks; the process and gates are identical. Commands assume cwd
`/workspace/pds`. This repo contains NO information about any particular
document; every structural decision is made from ITS scans during P2/P3.

## Page model (data contract)

`books/<id>/pages/pNNN.json`:

    {
      "folio": "17",                    // printed page number (or "")
      "side": "v" | "r",                // verso / recto (margin mirror)
      "running_head": "...",            // printed header text or null
      "source": {                       // provenance, always record:
        "scan": "<file>", "page_box": [x, y, w, h]   // px in the scan
      "blocks": [
        { "id": "p017-main",  "kind": "para", "indent": true,
          "text": "logical text with markers",
          "lines": ["ORIGINAL visual line 1-", "line 2 ..."] },
        { "id": "...", "kind": "runin-heading", "heading": "Label.",
          "indent": true, "text": "{BI|Label.} ...", "lines": [...] },
        { "id": "...", "kind": "list",
          "items": [ { "text": "...", "lines": ["...", "..."] }, ... ] }
      ]
    }

Markers: `{B|x}` `{I|x}` `{BI|x}` style-only; `{EM|x}` italic + Em role
(contrastive stress); `{STR|x}` bold + Strong role (formal names/strong
importance); `{E|x|expansion}` abbreviation. Line ending `-` = synthetic
soft hyphen (typesetter asserts consistency; never guess — see P2).
Figure block (IMPLEMENTED + regression-tested via books/figtest):
    { "id":"fig-7a", "kind":"figure",
      "src":"assets/fig-7a.png",           // book-dir or PDS-root relative
      "bbox":[x, top, w, h],               // pt; x/top relative to current grid row
      "alt":"…", "lang":"en-US",           // required unless artifact:true
      "band":true,                          // true: consumes ceil(h/pitch) rows;
                                            // false: floats (text must clear it)
      "artifact":false }                    // true: decorative, NOT in tree
Text blocks accept "widths":[pt|null,...] and "indents":[pt|null,...] per
line for wrap-around figures. The engine HARD-FAILS on any text/art or
art/art overlap ("LAYOUT COLLISION") — fix the model (widths/indents/
band/order), never the guard. Draft wrap numbers: bin/imgctl wrapmap;
confirm visually against strips (P2/P6 gates).

Kinds still queued for first contact (designs in semantics-recipes.md):
`table`, `sidebar`, note pairing (footnote/endnote).

## Phases

P0 Intake (once/book)
    venv/bin/python bin/scanctl.py meta SCAN [--single]
    Decide: page size/dpi (pitfalls #21), margins, pitch; write book.json
    (books/canary/book.json values are a proven starting point); record in
    books/<id>/STYLE-GUIDE.md §Geometry.
    Gate: render one page later at 300dpi → column edges within ~5% of scan.

P1 Crop (per spread)
    bin/scanctl.py strips SCAN --page N --rows <expected lines> --out work/...
    (use --rows for skewed scans, pitfalls #23)

P2 Transcribe (per page; PARALLELIZABLE — read-only)
    Read native-res crops/regions (ReadMediaFile region= on the ORIGINAL
    scan file — old handles die, pitfalls #25). Produce page JSON: verbatim
    text, original line breaks, markers per semantics-recipes decision
    table, ambiguous readings → ISSUES.md row {page, crop-path, question,
    status:open}. Gate: page with open ISSUES rows cannot enter P5.
    Confidence rule: anything below high confidence after a native-res
    second look → question, never a guess.

P3 Cross-page passes (serial; the "don't drift" phase)
    - Heading census: classify every heading (chapter opener, section,
      run-in, TOC); assign levels; FIRST H1 is the chapter title if present,
      else the topmost visible class; record template (size/weight/style →
      level) in STYLE-GUIDE.md. Fix earlier pages' marker kinds here.
    - Figure pass: classify every figure (rubric class), decide band vs
      float from printed geometry, write alt drafts (verify against restored
      art later), start IMAGES.md ledger rows.
- Provenance pass: every page JSON carries its "source" scan + box.
    - Pattern census: a "quirk" seen ≥2× with same function becomes a
      STYLE-GUIDE convention (e.g. run-in labels, drawn-bullet lists,
      folio placement, em-dash-at-EOL rule, degraded-comma rule).
    - Note pairing: collect endnote/footnote markers ↔ note texts
      (recipes §notes); verify counts match before build.
    - Page-break model: each page's block sequence must end exactly where
      the scan breaks (cross-page paragraph = two blocks, one per page).
    Gate: STYLE-GUIDE.md updated; contradictions between pages resolved.

P4 Typeset config (per book)
    book.json geometry + fonts (usually = demo's). Body size auto-calibrates
    from the line table; check the printed `body=` line is plausible
    (7.5–10.5 pt for this format).

P5 Build + validate (per book; SERIAL)
    venv/bin/python books/<id>/build.py            # UA_PART=2 default
    UA_PART=1 venv/bin/python books/<id>/build.py
    venv/bin/python bin/validate_pdf.py out/X.pdf --profile 2 --expect \
        Em=N --expect Strong=N --expect H1=N --expect-soft-hyphens N \
        --book books/<id>
    export PATH=$PWD/tools/jdk-17.0.20.1+1-jre/bin:$PATH
    java -jar tools/vp/bin/cli-1.30.3.jar -f ua2 --format text out/X.pdf
    venv/bin/python -c "import pikepdf;
      print(pikepdf.Job(['qpdf','--check','out/X.pdf']).run())"   # None=ok
    Gate: all PASS; roundtrip exact; counts match model.

P6 Visual QA (per book)
    bin/scanctl.py render out/X.pdf --page N --out work/pN.png (each page,
    or montage script) → compare against scan halves; line breaks, indents,
    furniture, emphasis weight. Fix models, not pixels.
    Escalate residual differences that are scan distortions (skew, bow,
    ink gain) — documented in ISSUES.md as accepted deviations.

## Scaling rules (hundreds of pages)

- P2 is embarrassingly parallel: spawn transcriber sub-agents per spread
  with {scan path, page range, STYLE-GUIDE.md, page-schema above}. They
  write pages/*.json + ISSUES rows; they never edit lib/ or shared files.
- P3/P5/P6 are single-writer. Run P3 every ~20 pages (pattern drift is the
  enemy), not once at the end; heading/note passes are diff-based re-checks.
- Keep per-page JSON validated at write time:
  `venv/bin/python -m json.tool` + typeset's built-in line/text assert
  (runs at load; a bad page fails fast with its id).
- Long books: build once; do NOT split-and-merge PDFs (tree merge is where
  accessibility goes to die).
- If engine work is needed mid-book: every lib/ edit must keep
  `bin/selftest.sh` green (golden streams), plus a new golden for the
  book when its first validated build exists.
- Recovery: lost model vs existing PDF → bin/pdf_probe.py decodes tree +
  text per page (rebuild JSON skeleton, then re-verify against scans).

## Tooling notes log (this file documents PROCESS; keep it document-agnostic —
book findings belong in the book's unversioned STYLE-GUIDE.md/ISSUES.md)

- 2026-10-12: process forged end-to-end on a real 2-page sample (result:
  full gates work; goldens + canary now anchor the tools instead).

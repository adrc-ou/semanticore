# Remediation playbook — phases, artifacts, gates

Scope: scanned book → one accessible PDF (PDF/UA-2; the only shipped
profile — the engine retains a UA-1 path for the canary fixture alone),
faithful visual recreation, no artifacts of scanning. Scales from one
spread to full textbooks; the process and gates are identical. WHEN output is
trusted is governed by docs/verification-protocol.md (claims, swarm
consensus, final sweep) — phases below describe the work, not the
authority. Commands assume cwd = the repo root. This repo contains NO information about any particular
document; every structural decision is made from ITS scans during P2/P3.

## Page model (data contract)

`books/<id>/pages/pNNN.json`:

    {
      "folio": "17",                    // printed page number (or "")
      "side": "v" | "r",                // verso / recto (margin mirror)
      "running_head": "...",            // printed header text or null
      "source": {                       // provenance, always record:
        "scan": "<file>", "page_box": [x, y, w, h]   // px in the scan
      },
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
importance); `{E|x|expansion}` abbreviation; `{REF|n}` note-reference mark
(superscript; pairs with a note block whose `note_anchor` is n, emits the
bidirectional link + /Ref); `{XREF|target|display}` inline cross-reference
to the block declaring `"xref_anchor":"target"` (forward-only link; wording
via `"xref_phrase"`). Line ending `-` = synthetic soft hyphen (typesetter
asserts consistency; never guess — see P2).
Figure block (IMPLEMENTED + regression-tested via books/canary):
    { "id":"fig-7a", "kind":"figure",
      "src":"assets/fig-7a.png",           // book-dir or PDS-root relative
      "bbox":[x, top, w, h],               // pt; x/top relative to current grid row
      "alt":"…", "lang":"en-US",           // required unless artifact:true
      "band":true,                          // true: consumes ceil(h/pitch) rows;
                                            // false: floats (text must clear it)
      "artifact":false }                    // true: decorative, NOT in tree
Text blocks accept "widths":[pt|null,...] and "indents":[pt|null,...] per
line for wrap-around figures.
Other live keys (engine surface — semantics-recipes.md has the design notes):
    para: "role":"Note" + "note_anchor":"n" + "note_kind":"Endnote|footnote";
          "align":"center|left"; "pitch":pt (block-local line pitch);
          "row_gap":grid-rows before block; "x_off":pt; "width":pt;
          "rule":"above|below" (+ "rule_lift":pt, "rule_span":[dx,w]);
          per-line "gaps":{"<li>":[pt,...]} declared inter-word widths.
    heading: "level":1-6, "size":pt, "lead":pt, "align", "indents":[pt,...]
          per line (hanging numerals), "gaps", per-line style markers.
    list: "numbering":"arabic"|null; "marker":null for undecorated lists
          (ListNumbering None); "numbering_start":n (continuation across a
          page break); "item_style":"b" etc.; "bullet_em","tab_em",
          "wrap_em" (measure per book, never inherit); "pitch":pt;
          "item_gap":rows.
    table: "cols":[pt,...]; "rows":[[{ "text","lines",  cell keys:
          "th":true + "scope":"col|row", "cid":"id", "cheaders":["id",...] }]];
          "cell_size","cell_pitch","cell_vpad","cell_hpad" (defaults
          7.6/9.2/2.6/3.2 — MEASURE); "caption":{"text","lines"};
          "xref_anchor"; "grid_rows":n; "rules":true|false.
    columns: "colw":[pt,...], "gap":pt; sub-blocks = mini paras (own
          "text"/"lines"/"size"/"pitch"/"align"/"space_before").
    page: "folio_place":"bottom-center" (display pages, no running head).
    book.json: "trim_edge_blanks" (default true — category 7); geometry keys incl.
          "list_wrap_em","list_bullet_em","bullet_tight","indent_em",
          "body_max","body_min"; "output" as plain path (one ship file) or
          dict keyed by UA part (fixture use). Root-relative shared assets
          resolve under books/_x/.
"pattern":"<id>" is VALIDATOR-only (engine ignores it): tag every instance of
a recurring construct so validate_pdf --book aborts if styling diverges
across pages. Body auto-fit flags `hscale_min` is legacy/ignored (category 4). The engine HARD-FAILS on any text/art or
art/art overlap ("LAYOUT COLLISION") — fix the model (widths/indents/
band/order), never the guard. Draft wrap numbers: bin/imgctl wrapmap;
confirm visually against strips (P2/P6 gates).

Kinds shipped with proven designs (semantics-recipes.md): `table`,
notes (FENote/Reference//Ref), undecorated lists, cross-references
(`{XREF}`). Still queued for first contact: `sidebar`.

## Phases

P0 Intake (once/book)
    venv/bin/python bin/scanctl.py meta SCAN [--single]
    Decide: page size/dpi (pitfalls #21), margins, pitch from the SCAN;
    write book.json with those measurements (template/canary numbers are
    PLACEHOLDERS — re-measure, never inherit); record in
    books/<id>/STYLE-GUIDE.md §Geometry.
    Gate: render one page later at 300dpi → column edges within ~5% of scan.

P1 Crop (per spread)
    bin/scanctl.py strips SCAN --page N --rows <expected lines> --out work/...
    (use --rows for skewed scans, pitfalls #23)
    Strips are P6-QA/zoom aids, NOT the P2 reading substrate (pitfall #39).

P2 Transcribe (per page; main lane; one pass per page)
    Look at the PAGE, not the line: ReadMediaFile the full page box of the
    ORIGINAL scan as 2–4 native-res horizontal bands (~12–20 lines each;
    old handles die, pitfalls #25) and transcribe the whole page in ONE
    pass straight into pages/pNNN.json. Never one image-read per printed
    line; never scratch ledgers (/tmp TSVs, state files) to track reading
    progress — the page JSON is the only state (pitfall #39).
    One uncertain word: zoom THAT region once; still unclear → best reading
    + ISSUES.md row {page, crop-path, question, status:open}. Never
    transcribe from notes/summaries — only from pixels (pitfall #25).
    Verification is the MACHINE step, run once after the write:
    venv/bin/python -c "import sys,json;sys.path.insert(0,'lib');from
    typeset import Block;[Block(b,0) for b in
    json.load(open('<pagefile>'))['blocks']]"  — fix, assert OK, move on
    (pitfall #40: no agent-side state-re-checking rituals).
    Gate: page with open ISSUES rows cannot enter P5.
    Confidence rule: anything below high confidence after a native-res
    second look → question, never a guess.
    Delegation: vision work is NEVER delegated (operator rule 2026-10-13)
    — subagent windows cannot hold page images (pitfall #39). P2 runs in
    the main agent, one page per pass. Swarms only for image-free work
    (code, validation, prose passes over existing text).

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
    - List recognition: scan for undecorated list CONTENT (author/credit
      stacks, address blocks, parallel series) → lift to L/LI with
      ListNumbering None, geometry preserved via list pitch/row_gap
      (category 5; recipes "Undecorated lists"). Mark cross-references
      ("See Figure X, p. N") for `{XREF}` wiring at the target block.
      (recipes §notes / §cross-references); verify marker↔text counts match
      before build.
    - Page-break model: each page's block sequence must end exactly where
      the scan breaks (cross-page paragraph = two blocks, one per page).
    Gate: STYLE-GUIDE.md updated; contradictions between pages resolved.

P4 Typeset config (per book)
    book.json geometry + fonts — MEASURED in P0 (the template ships
    plausible PLACEHOLDER numbers, not a book's answers to trust). Body size
    auto-calibrates from the line table; sanity-check the printed `body=`
    line against the scan's apparent type size.

P5 Build + validate (per book; SERIAL)
    venv/bin/python books/<id>/build.py            # UA_PART=2 (the only ship profile)
    venv/bin/python bin/validate_pdf.py out/X.pdf --profile 2 --expect \
        Em=N --expect Strong=N --expect H1=N --expect-soft-hyphens N \
        --book books/<id>
    export PATH=$PWD/tools/jdk-17.0.20.1+1-jre/bin:$PATH
    java -jar tools/vp/bin/cli-1.30.3.jar -f ua2 --format text out/X.pdf
    venv/bin/python -c "import pikepdf;
      print(pikepdf.Job(['qpdf','--check','out/X.pdf']).run())"   # None=ok
    Gate: all PASS; STRICT roundtrip exact (--book decode: real spaces,
    ActualText substitution, no layout heuristics); counts match model.

P6-L Layout verification (per book; SHIPS ONLY IF COMPLETE)
    Measured, every page — montages are for spotting gross errors, never
    for sign-off. Procedure per page:
    0. Automated parity probe (first pass, all pages):
       `bin/pagecmp.py SCAN --box x,y,w,h --pdf out/X.pdf --page N`
       aligns the scan's row-ink profile to the render's (scale+shift fit)
       and flags pitch drift / local leading collapse / block offsets
       numerically. REVIEW verdicts → steps 1-6 investigate that page; a
       pagecmp PASS does NOT replace the visual pass, it prioritizes it.
    1. Extract the SOURCE line grid: ink-row profile of the scan page box
       → per line: y-center, ink x-extent, band height (type-size proxy);
       group into blocks; note EMPTY grid rows between blocks (the blank
       budget — `bin/scanctl.py meta SCAN`).
    2. Extract the RENDER line positions: text spans from the built PDF
       (page + y + x-start + size — `bin/pdf_probe.py PDF --page N --text`).
    3. Diff block-by-block: line count, first/last baseline, inter-block
       gaps (grid rows), left edge (indent vs centered vs flush), size
       ratios, rule/divider presence. Tolerance: baselines ±3pt, gaps
       ±0.5 rows, block height ±5%, alignment per census.
    4. Fix the MODEL (gap:, size:, lead:, align:, rule:, indents:) — never
       pixels; rebuild; re-diff until in tolerance. Engine aborts on any
       two-block rect overlap (pitfall #42): zero overlaps allowed.
    5. Record per-page coverage ("L-passed date, max delta") in
       STYLE-GUIDE. Text-on-text overlap = WCAG 1.4.3 failure, not just
       ugly — veraPDF cannot see it (pitfall #42/#43).
    6. True-size visual review: render EVERY page at >=150dpi and view it
       against its source half (fine detail via native-resolution crops);
       check alignment, size, leading, gaps, rules, emphasis spans and
       occlusion per page. Sign-off only through this review — a
       downsampled full-sheet montage hides exactly the errors that
       matter (rules crossing text, wrong italics, collapsed leading).
       Distortion is never a fix: widen measures/cells/blocks instead;
       type inside one table keeps ONE size and shape; display word-
       spacing gaps are reproduced with measured per-space widths.

P6.5 V-pass — verbatim verification (per book; SHIPS ONLY IF COMPLETE)
    Independent word-for-word audit of every content page: re-read the
    SOURCE SCAN (fresh bands, same method as P2) with the page JSON text
    in hand; diff word by word. Efficiency: to re-check a flagged line,
    pull its narrow strip (page_box + line offset) and text-compare,
    citing the line's quote as anchor; full-page re-reads for first pass
    and fix-touched pages only. Disagreements become REVIEW.md claims. Resolve every difference in favor of the
    scan (fix JSON; keep source typos/sic — only justified-spacing
    normalization may stand, and must be listed in STYLE-GUIDE). Table
    cells, captions, footnotes and small print are the usual drift
    magnets — no block is exempt. Log coverage per page in STYLE-GUIDE
    ("V-passed YYYY-MM-DD"). Engine asserts DO NOT cover this: they only
    check internal consistency of a transcription that may itself be
    wrong. Rebuild + full validation after any fix.

## Scaling rules (hundreds of pages)

- P2 transcription is MAIN-AGENT VISION WORK: page by page, in-session —
  never a swarm (subagent windows fold page images; folded vision agents
  livelock — pitfall #39 + AGENTS ground rule). Trust the model's
  perception: read each page image whole and transcribe it in one pass
  (band crops only to settle genuinely ambiguous glyphs), then run the
  line/text assert and move on. Grinding line-by-line with per-line
  state-verification loops is the failure mode to avoid.
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

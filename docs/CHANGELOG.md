# Tooling changelog (formerly the AGENTS.md session log)

One line per meaningful tooling change. NO per-document content,
findings or job details here — those live in the unversioned book
directories. Newest first.

- 2026-10-16 AGENT-FIRST restructure (operator directive): the project
  states plainly that the agentic model is the driver and instruments
  only produce evidence; NEW docs/verification-protocol.md — swarm
  consensus loops (verify-claims → fix → verify-fixes → converge →
  final-sweep grants DONE), text-only verifiers that RE-RUN
  instruments instead of seeing images (no subagent image channel,
  crops included — folded-context livelock + selection bias);
  P2/P6.5 transcription+re-read v2 (source-line strips; verbatim
  re-reads quote-anchored, full pages only by exception); AGENTS.md
  rewritten ~400→~120 lines (gates→defect categories; session log
  moved out here; one-deliverable UA-2); TEMPLATE gains REVIEW.md
  claim ledger + per-line "source" quote format in the page model;
  pitfalls #39 amended (strip-first rationale includes fold-safety),
  new #57. Pilot book not yet retrofitted with quote blocks — until
  then its verbatim re-reads fall back to whole-page passes.
- 2026-10-16 reproducibility/generality audit: swept tracked files for
  pilot-book leaks (title strings, page numbers, per-book measurements
  in docs + session log) and scrubbed — de-priming had regressed; fixed
  stale doc references (nonexistent lint.py/check_demo.sh/books/figtest/
  images/ledger/absolute paths — P6-L now names scanctl/pdf_probe/the
  new tool); UA-1-as-deliverable language removed everywhere (one UA-2
  file; canary keeps the ua1 path as engine coverage only); NEW
  bin/pagecmp.py numeric scan-vs-render layout-parity probe wired into
  P6-L step 0 and gate 6(c); engine fixes — the sentence-period
  punctuation guard was dead code (indented under `continue`) and is
  now live + unit-tested, block-kind whitelist fails fast, table-cell
  lines==text join assert added, dead remap removed, misleading
  Tz/bootstrap docstrings corrected; canary extended with a
  heading+table+columns+FENote-pair+XREF coverage page (was the biggest
  regression gap — gates 8/11 had zero fixture); live-but-undocumented
  JSON keys written into the playbook schema; pitfalls de-duplicated
  (#32 collision -> Images 50-56).
- 2026-10-15 round 5 (Acrobat findings + fidelity): FENote marker Link
  no longer wrapped in Lbl (Acrobat restricts Lbl/LBody to LI — a
  WTPDF-legal structure Acrobat still rejects; pitfall #48 + standing
  external-finding promotion rule); validate_pdf gained list-nesting and
  pattern-drift gates (both neg-tested); recurring constructs now carry
  "pattern" ids with canonical STYLE-GUIDE param sets, enforced equal at
  validation (pitfall #49) — list/note geometry re-measured from scans
  per book (the fix procedure, not the values, is the tooling lesson);
  ONE deliverable per book: UA-2 only, ua1 variant dropped from book
  pipelines (canary keeps it as engine regression coverage).
- 2026-10-15 notes/xref/list round: note model rewritten to WTPDF
  (FENote+NoteType via /A owner dict, Lbl+P children, reciprocal /Ref
  both sides, /Alt removed from containers — the Alt was exactly
  Acrobat's "nested alternate text" defect; UA-1 keeps Annot-minus-Alt);
  new `{XREF|target|display}` markup → inline Reference+Link forward-
  only to a table's `xref_anchor`; undecorated lists (author credits) —
  list renderer gained block `pitch`, fractional `row_gap` and optional
  label (canary paths byte-identical); validate_pdf gates: nested-alt
  scan, FENote/NoteType//Ref reciprocity (all neg-tested by tampering);
  gates 5/8 extended, gate 11 (cross-refs) added; pitfalls #44–#47
  (spaces/nested-Alt//A-owner/page_box).
- 2026-10-15 EXTRACTION-FIDELITY fix: word/line joins were positioned,
  not shown — strict text extraction collapsed every heading/table/
  caption ("TITLEWORDSRUNTOGETHER"). Every render path (headings,
  paragraph line-final words + end-of-block span, columns, table cells,
  captions, arabic list labels) now emits a real U+0020 glyph at each
  join, following the split_lines contract (no space after EOL '-'/—);
  ActualText is now serialized into BDC property lists (StructElem-only
  was invisible to extraction consumers). validate_pdf --book roundtrip
  REBUILT as strict spec-level decode (ToUnicode-in-content-order, AT
  substitution, artifacts skipped, spaces compared) — MuPDF gap
  inference was masking the defect; canary goldens re-seized for the
  added spaces. Gate 4 extended ("spaces are copy"); pitfall #44.
- 2026-10-14 engine first-contact for navigable notes + fidelity guards:
  heading blocks take per-line indents/gaps/style slices (hanging
  chapter numerals); table cells wrap with header (bold) metrics and a
  hard per-line width guard aborts on any overflow; decimal numbered
  lists (`numbering:"arabic"`, outdented labels); footnote/endnote pairs
  ship as Reference>Link marks + Annot note blocks + bidirectional GoTo
  annotations with /Contents, UA-2 /SD struct dests alongside /D
  (veraPDF reads only /SD, MuPDF follows only /D); link StructElems ride
  EXTRA ParentTree number-tree keys — page mcid stays 0-based (1-based
  broke 216 checks); book.json `trim_edge_blanks` drops leading/
  trailing blank pages, interior blanks preserved. Gates 7-9 added
  (overflow, notes, trim); occlusion renumbered 10.
- 2026-10-13 gate 6 (layout fidelity) + gate 7 (no occlusion) added;
  engine: per-line horizontal scale (Tz) replaces size-shrink for width
  fit, blank-row gap/rule/heading primitives, every drawn rect
  registers for collision (occluded text = WCAG 1.4.3, invisible to
  veraPDF — rendering checks are part of the a11y program). canary path
  kept byte-exact via legacy branch when hscale_min>=1.0.
- 2026-10-13 engine first-contacts proven on a real book: block kinds
  heading/table/columns (+grid rules, TH/TD Scope + ID/Headers in /A),
  per-block size/pitch/align, figure grid_rows+btop offset,
  chapter-open folio placement, OFF-PAGE guard, multi-run PageLabels
  (r prelim + D numbered); validate_pdf taught table/columns extraction;
  UA-1 tables REQUIRE /A attribute-object Headers (direct keys are
  invisible to veraPDF).
- 2026-10-13 gate 4 added (operator): verbatim fidelity is absolute —
  named V-pass (independent page-by-page re-read vs source) is a ship
  gate; engine asserts do not cover it. playbook P6 updated.
- 2026-10-13 operator ground rules added: plain-English reporting (no
  internal process jargon to the operator) + vision work never delegated
  (playbook P2 + pitfall #39 amended to match).
- 2026-10-13 P2 protocol v2: page-band one-pass transcription in main
  lane replaces line-strip grinding; scratch ledgers + agent-side verify
  rituals banned (pitfalls #39/#40, playbook P2 rewritten). Trigger: a
  17-page strip-swarm livelocked for hours and shipped 2 assert-
  failures + 3 from-memory transcriptions.
- 2026-10-13: standing operator rule added: always maximize
  accessibility — real structure beats visual mimicry (engine <Table>
  chosen over raster for text tables on first contact; rasterizing text
  forbidden), UA-2 + per-SC WCAG 2.2 AA are co-equal ship gates.
- 2026-10-14 layout-parity engine round: Tz/horizontal-scale machinery
  REMOVED (glyph distortion forbidden; gate 6 rewritten); new engine
  capabilities: {REF|n} superscript Reference spans, punctuation guard
  (fused/speck punctuation aborts builds), rules register occlusion
  rects + rule_lift/rule_span, columns x_off + per-line style slices
  (kills mid-word italic flips), tables re-wrap at one cell size
  (widen, never squeeze), paragraph x_off/width/align:left/gaps/
  spread_lines, list item_gap; canary selftest stays ALL OK (legacy
  path intact). Playbook: P2 parallel-transcription scaling rule
  REVERSED (vision work is main-agent-only; see ground rules), P6-L
  gains true-size visual review + no-distortion clauses; AGENTS ground
  rules gain the perfectionism standard; gate 4 gains the
  speck-punctuation ruling.
- 2026-10-13: de-priming pass — committed docs scrubbed of every example
  drawn from real books (recipes/playbook/template now use neutral
  placeholders); playbook gained explicit per-page "source" provenance
  field; AGENTS is generic by construction: it tells a session HOW to
  start, never WHAT to expect.
- 2026-10-12 engine extraction byte-verified vs prior build; canary
  synthetic fixture + negative collision test anchor selftest.sh;
  setup_env.sh reproduces the toolchain from this repo alone.
- 2026-10-12 figure/wrap/hard-hyphen engine paths verified against
  veraPDF ua2+ua1 on the fixture; rubrics for 7 image classes checked
  in; ComfyUI ops plan committed as DESIGN (its HTTP paths and
  pipelines are explicitly UNTESTED — validate on arrival).

# Semantics recipes — typography → structure, and queued constructs

## Proven on real pages (implement as-is)

### Emphasis decision table (contextual, never mechanical)
| Observed | Question to answer | → Marker / role |
|---|---|---|
| run-in bold/italic label opening a passage; its words name the passage's topic | is it a heading? | `{BI|label}` + `kind:"runin-heading"` (+ re-level in P3 census) |
| italic on a word/phrase mid-sentence that the prose stresses when read aloud | contrastive stress? | `{EM|word}` → `Em` (+ /NS auto-attached) |
| italic defining/introducing a term at first use | term/defined-word? | `Em` for now; if a *defined term* convention recurs, note in STYLE-GUIDE (no standard "term" role; Em is the accepted proxy) |
| bold used for the formal NAME of a defined thing (section subject, product, coined entity) inside prose | naming emphasis | `{STR|Name}` → `Strong` |
| phrase in quotation marks used as a name/title of something | citation/title | keep quotes as plain text; NO role (no standard PDF role fits; avoid inventing stress) |
| small-caps / all-caps headers, folios | page furniture | artifact (see furniture) |
| abbreviation (N.E.A., i.e., cf.) | expansion known? | `{E|abbr|expansion}` → Span+/E |

Rules: one decision per RUN, recorded in the book STYLE-GUIDE.md table
(`pattern → class → role → first page seen`). A pattern seen ≥2× with the
same function MUST be promoted to a convention (guards drift + later
re-discovery). Em/Strong spanning a line break: engine splits into
per-line fragments automatically (contiguity-safe); do not nest.

### Furniture / artifacts
- Folio + running head → one `/Artifact PageHeader` per page,
  `/Attached [/Top]`, correct BBox; never in the tree; folio value also
  drives `/PageLabels` (decimal start = first page's folio).
- Decorative rules, page numbers in footers: PageFooter variant.
- Judgment: running heads are NOT headings even when they duplicate a
  section title (repeated furniture = noise for AT).

### Lists
- Drawn bullet → `Lbl` owns glyph+space; `L /A << /O /List /ListNumbering
  /Disc >>`; continuation indent from scan (this book: 2.6em wrap, 3.35em
  bullet — typist-driven, keep per-book).
- Numbered/roman lists: ListNumbering /Decimal /UpperRoman etc.

### Soft hyphens / dashes
- EOL `-` splitting a word → synthetic, `{ActualText U+00AD}`, glyph in the
  word's font (italic word → italic hyphen).
- A line-final '-' is SYNTHETIC (soft) by default; when the source breaks a
  compound AT ITS OWN HYPHEN, declare the line index in
  `hard_hyphen_lines:[...]` so the hyphen survives into the logical text
  with no space. The join assert catches either mistake at build time.
- Em dash at EOL (typewriter style `word—`) joins with NO space.

## PROVEN in engine (books/canary regression)
- Band figures, floating figures with wrap (`widths`/`indents`), decorative
  artifact figures, `/Figure` + `/Alt` `/Lang` `/Placement /Block` `/BBox`
  direct keys — pass veraPDF ua2 AND ua1 + qpdf + own validator; overlap
  guard verified by negative test. Long descriptions for data figures:
  place as ordinary `P` blocks after the figure in the SAME grid flow
  (tree order follows content order automatically).

## Queued — first-contact protocol (design ready; verify, then pin here)

When the construct first appears: build minimal page → probe → veraPDF →
adjust → write result into this file + book STYLE-GUIDE, then continue.
Never ship a guessed treatment unverified.

### Chapter / section headings (P3 heading census)
1. Census every candidate (class by size/weight/position/centering).
2. The document's own top-level opener (chapter number/title etc., if it
   appears in the batch) = `H1`; other classes get levels by measured
   nesting depth, not by guess.
3. Run-ins whose words merely label paragraphs rank BELOW the openers.
4. No skipped levels; first heading in the tree = H1; single-level batches
   are legitimately flat.
5. Typesetter currently hardwires run-ins to H1 → generalize
   `heading_level` on the block when this lands (engine change gated by
   check_demo.sh + demo re-leveling expectation).

### Footnotes / endnotes
- Marker: superscript digits run → element role `Reference` (PDF 2.0)
  (fallback UA-1: `Span`) with `/ActualText "endnote N"` / `"footnote N"`.
  Superscript style: `Sup` role exists in 2.0 — prefer
  Reference(+ActualText) over bare Sup (semantics > appearance).
- Note text: end-of-chapter list → each note = `Endnote` element; page
  footnotes = `FENote` elements in a page-bottom container; both live in
  the tree AFTER the page body (document-order reading = conventional
  and legal).
- Pairing: (a) structure `/C` (associated elements) on marker ↔ note
  elements, both directions; (b) invisible `/Link` annotation GoTo for
  mouse/keyboard: dest = structure destination (UA-2) / page+coords (UA-1);
  reverse link from note → marker. Verify greenfield accepts /C + annots;
  if /C unmodeled, annotations alone suffice; record findings here.
- Line numbers per page MUST accommodate note bands (measure; don't guess).

### Tables
- Re-typeset real text (never an image of a table).
- Tree: `Table` > `THead`?/`TBody` > `TR` > `TH`(`/Scope /Row|/Col`)/`TD`;
  header cells only where the scan shows header semantics; caption from
  scan = `Caption` child of `Table`.
- Merged cells: content-property dict `/Td` on `Table` (RowSpans/ColSpans
  arrays aligned with the TR stream) — verify against checker on first use.
- Engine: needs a column-grid line model: block kind `table` with
  `cols: [widths]`, `rows: [[{text, spans...}]]`; per-cell lines keep the
  source's wraps but WITHOUT justification (ragged like typewritten cells).

### Figures / photos / charts / infographics
- Embed the scan region itself as an image (PIL crop → FlateDecode RGB;
  never redraw art). `/Figure` element: `/Alt` concise (<~150 chars),
  `/Lang en-US`, `Placement /Block`, `BBox` in props; sits in tree at its
  reading position.
- Charts/infographics: Alt = what+form ("Bar chart of X by year, 1960–70");
  the full data/logic goes into an adjacent `Caption`/`P` "long
  description" (visible if the book has one; else a tree-adjacent `Sect`
  with `ActualText`? NO — prefer a real visible "Description:" paragraph
  only if source-consistent; else long desc inside Alt is acceptable —
  decide on first occurrence and pin here).
- Decorative art: `/Artifact /Type /Layout /Subtype /Watermark`? — for
  inline decoration use an `Artefact`-marked image sequence (no tree node).
- Grader/uncertain identification (chart types, labels inside art) →
  ISSUES.md, ask user; attach crop.

### Sidebars / boxes / quotations from other works
- Sidebar: `Aside` (2.0 role; UA-1: `Sect` + note in STYLE-GUIDE).
- Epigraph/poem quotes: `BlockQuote`; line breaks preserved via same
  line-table machinery; attribution = plain `P` inside the BlockQuote.

## Roundtrip & text rules (unchanged)
- Extraction equality is asserted against the page JSONs (`--book` flag:
  markers stripped, list items prefixed "•", artifacts removed, all
  whitespace + hyphens normalized away).
- Never "fix" source typos silently: keep + record in ISSUES.md
  `[sic-policy]` (e.g., degraded commas ARE commas per pitfalls #24 —
  that's an established reading, not a fix).

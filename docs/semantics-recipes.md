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
  /Disc >>`; continuation indent from scan — MEASURE it per book (bullet_em,
  tab_em, wrap_em); never inherit another book's numbers.
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
  direct keys — pass veraPDF ua2 (ua1 path via canary) + qpdf + validator; overlap
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
   bin/selftest.sh canary goldens).

### Footnotes / endnotes (verified shipping pattern, UA-1 + UA-2)
Best practice = notes are *navigable structures*, not just text: a
screen-reader user hits the mark, hears what it is, jumps to the note,
and jumps back. Ship all six layers (WTPDF-conformant; every element
verified against veraPDF's UA-2 model internals):
- Marker in body: role `Reference` (standard in both PDF 1.7 and 2.0 —
  no ActualText needed) wrapping a child `Link` StructElem. The `Link`
  element is REQUIRED: an untagged annotation fails UA 7.18.5.
- Note block, UA-2: role `FENote` (PDF 2.0 type → `/NS` ssn; the raw
  `Note` type is FORBIDDEN by WTPDF), children `Link` (marker, carries
  the back-link) + `P` (text). NO `Lbl` wrapper — Acrobat restricts
  Lbl/LBody to children of `LI` and flags Lbl-in-FENote even though
  WTPDF permits it (we hold to Acrobat's stricter rule; validate_pdf
  list-nesting gate enforces). NoteType rides the standard-attributes
  mechanism: `/A << /O /FENote /NoteType /Endnote|/Footnote >>` (Name
  values) — a direct /NoteType key is invisible to checkers (verified:
  AttributeHelper reads it by owner from /A). UA-1 build: role `Annot`,
  no wrapper P.
- NEVER /Alt on a note container: Alt REPLACES the subtree for AT and
  any ActualText/Alt trapped below it is Acrobat's "nested alternate
  text" failure. Note identity = role + NoteType + Lbl + link
  /Contents. Same rule generalizes: alt-bearing elements must have
  alt-free descendants (validate_pdf gate).
- Association: reciprocal `/Ref` arrays — `Reference./Ref [FENote]` and
  `FENote./Ref [Reference,…]` (WTPDF 8.2.5.14; veraPDF computes
  orphanRefs/ghostRefs from these). /Ref is a PDF 2.0 key → UA-1 build
  omits it (links still carry the pairing).
- Bidirectional link annotations: forward (mark → note) and backward
  (note Lbl marker → mark), each GoTo, each with `/Contents`
  ("Go to endnote 3" / "Return to text"). Missing pairs abort the
  build (every reference needs a target and vice versa).
- Destinations: UA-2 gets structure destinations via `/SD` named dest
  (veraPDF clause 8.8 accepts ONLY /SD); also emit page/XYZ `/D` on the
  same action because MuPDF and many viewers follow only /D. Both, always.
- ParentTree: link StructElems get EXTRA number-tree entries under their
  own mcid keys (keys allocated above the page range); pages stay 0-based
  mcid — do not renumber pages for annotations.
- Line numbers per page MUST accommodate note bands (measure; don't guess).
Intentionally NOT used: `/C` associated-elements (superseded by /Ref),
ActualText on markers (announced via role + Contents).

### Cross-page pattern consistency (mechanism)
Any construct that recurs — a numbered list continued across pages, the
note blocks, captions, display quotations — is tagged with a
`"pattern": "<id>"` on EVERY block that is an instance. The canonical
parameter set (bullet_em/tab_em/wrap_em/item_style/size/pitch/align/
role/note_kind/…) is recorded once in STYLE-GUIDE.md and MUST be byte-
identical across instances; `validate_pdf --book` groups blocks by
pattern id and ABORTS on drift (numbering_start excluded — it legitimately
increments). The rule this enforces: a construct is styled ONCE from
measurement, then applied everywhere; per-occurrence fiddling is the root
of inconsistency. When P3 finds a recurring quirk, mint the pattern id and
retrofit every earlier instance.

### Undecorated lists (semantic lift)
A vertical sequence of parallel items — author credits, editorial staff
blocks, addresses — is `L`/`LI` + `LBody`, `ListNumbering None`, even
when the source prints no bullets/numbers. AT then announces item counts
and lets users navigate item-by-item; plain paragraphs read as one run-on
sentence. Visual parity is mandatory (category 4): list blocks support
`pitch` and fractional `row_gap` so lifted lists keep the measured grid.
Decide from the document census, list every lift in the STYLE-GUIDE,
never change text or add punctuation between items.

### In-text cross-references ("See Figure X, p. N.")
- The referenced label renders as a NON-superscript `Reference` (inline
  size) wrapping a `Link`, with a FORWARD-only GoTo annotation onto the
  target block (`xref_anchor` on the Table/Figure block; missing
  target or unused anchor aborts the build). `/Ref` pairs
  Reference↔target in the UA-2 tree. /Contents: "Go to Figure 1".
- No back-link: a table can be referenced from many places and has no
  single point of departure; AT "previous location"/reading-order nav
  returns the user (note markers are the one case that gets explicit
  return links).
- Tables/figures stay inline at their source position in the structure
  tree — reading order = physical order. Whether the AT announces
  "table, 4 rows…" or lets linear reading skip it is the AT's decision,
  enabled by correct Table/Caption/TH tagging; never reorder content to
  guess at it.

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

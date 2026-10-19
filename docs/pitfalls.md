# Pitfalls — verified facts. Read before coding. Each cost real time.

## A. Engine / pikepdf mechanics
1. `pikepdf.Pdf()` has no ctor → `pikepdf.new()`.
2. Numbers in PDF objects: pikepdf turns Python `str` into PDF *String*.
   `/W`, `/W` arrays, BBox etc. must be int/float, never pre-formatted strings.
   (Symptom: overlapping repeated glyphs `ff→f`, extraction dedups them.)
3. Text strings: `String(("\ufeff"+s).encode("utf-16-be"))`; `String(s,
   encoding=...)` and `new_from_string` do not exist in pikepdf 10.
4. `docinfo.clear()` fails (dict, not array) → delete keys one by one.
5. GC gotcha: `pikepdf.open(f).pages[i]` chained across statements raises
   "cannot get key on object of type destroyed" — keep the `Pdf` bound.
6. Raw python dicts nested in Arrays can serialize as `/QPDFFakeN` keys —
   build `Dictionary()` explicitly for `/PageLabels` etc.
7. Byte-reproducible builds: `save(static_id=True, ...)` (`deterministic_id`
   is NOT it), `object_stream_mode=disable`, `fix_metadata_version=False`,
   and zero `head.created/modified` in fontTools (else font bytes drift).
8. `getBestCmap()` maps codepoint→glyph NAME; GIDs need
   `getReverseGlyphMap()`. Subsetter: `retain_gids=True`, populate from the
   sorted used-char set.
9. Identity-H recipe that works: Type0 + CIDFontType2, `/CIDToGIDMap
   /Identity`, `/W [gid [w]...]`, FontFile2 (Flate, `/Length1` raw len),
   descriptor flags Serif|NonSymbolic(|Italic), `ItalicAngle =
   -post.italicAngle` (sign flips between TT and PDF).
10. ToUnicode MUST include the space glyph (else extraction inserts junk
    for word separators).

## B. Tagging / structure
11. Root `Document` element: `/P` = the StructTreeRoot object (ISO
    32000-1 Table 344). Missing it fails veraPDF UA-1 7.1.3 on EVERY page
    item (their `isTaggedContent` walks `/P` until StructTreeRoot) and makes
    MuPDF report `PDF_STRUCT_FIXED`.
12. Marked content: FLAT sequences. `/Span` nested inside an open `/P`
    passes qpdf but greenfield warns "Nested MCID" and then treats content
    as untagged (932 false failures). Convention here: one sequence per
    line per element; element `/K` mixes ints + child refs in stream order.
13. Pages need `/StructParents` (= page index) AND `ParentTree/Nums` +
    `/ParentTreeNextKey = npages`, one slot per mcid, no holes.
14. PDF 2.0 semantic emphasis = standard ROLES `Em`, `Strong`, `Sub`, `Sup`,
    `Aside` (NOT /Style dictionaries). 1.7 has none → UA-1 build falls back
    to neutral `Span`.
15. Standard-type resolution does NOT inherit namespaces: EVERY `Em`/
    `Strong` element needs its own `/NS` → shared indirect dict
    `<</NS (http://iso.org/pdf2/ssn)>>` or UA-2 8.2.4.1 fails
    ("non-standard type not mapped").
16. `E` (abbreviation expansion) is an ATTRIBUTE on `Span`, not a role.
    Same for `ActualText`, `Alt`, `Lang` — direct StructElem keys work in
    1.7; `/A`+ClassMap machinery is only needed for `ListNumbering` etc.
17. Drawn-bullet lists: `Lbl` element owns the "•" glyph; put
    `/A <</O /List /ListNumbering /Disc>>` on `L` — UA-2 8.2.5.25 requires
    ListNumbering when `Lbl` exists.
18. Artifacts: `/Artifact <</Type /Pagination /Subtype /PageHeader
    /BBox [...] /Attached [/Top]>> BDC ... EMC` — no MCID. Folio + running
    head can share one sequence. Running heads are artifacts, NOT headings;
    content headings live where the content has them.
19. UA-2 8.8: in-document destinations must be STRUCTURE destinations:
    `/Dest [ <StructElem dict ref> /XYZ x y null ]`. UA-1 keeps page-dest
    `[ <Page> /XYZ ... ]`. Identities are mutually exclusive → profile
    switch in the build (`UA_PART=1|2`), never both claims in one file.
20. Identity XMP: `pdfuaid` = `http://www.aiim.org/pdfua/ns/id/` with
    `part` (+`rev=2024` iff part 2). `pdfaid` is the PDF/A schema — UA-1
    5.1 fails if you use it for UA.
44. Spaces must be SHOWN, not positioned: a gap that exists only as a
    Tm/x jump extracts as nothing in strict consumers ("TITLEWORDS…").
    MuPDF get_text() infers spaces from gaps and HIDES the defect —
    extraction QA must use validate_pdf --book (STRICT ToUnicode decode,
    ActualText substitution, spaces compared). A shipped book once pasted as
    run-together words: every render path now emits real U+0020 at every join,
    and ActualText rides the BDC
    property list (extraction) as well as the StructElem (tree).
45. NEVER /Alt on an element that has readable descendants: Alt REPLACES
    the subtree for AT, and nested Alt/ActualText under it is Acrobat's
    "nested alternate text" failure (the endnote Alt trapped 11 soft-
    hyphen ActualText spans this way). Note identity = FENote role +
    NoteType + Link marker + link /Contents (NO Lbl — see #48).
    validate_pdf walks the tree for it.
46. Standard structure attributes (NoteType, ListNumbering, Scope…) are
    read from `/A` attribute objects matched by `/O` owner — a direct
    key of the same name is invisible to checkers (verified against
    veraPDF AttributeHelper). /Ref targets must be the same indirect
    objects both ways (orphan/ghost pairing check).

## C. Scans / transcription
21. Confirm scan dpi by aspect: 1650×2550 halves = 5.5×8.5" @300dpi.
22. Never assume the face class: check ink-gap histograms + autocorrelation
    BEFORE believing "typewriter = monospace" (the reference sample looked
    like Courier but measured proportional). Choose by rendering the same
    line across candidates and zoom-comparing glyphs. Photocopy ink gain ≠
    true weight — Medium often matches better than Regular (canary default:
    Gelasio Medium; re-decide per book).
23. Skew kills band detection over full width: measure with narrow x-window
    or fixed `--rows` grid; verify geometry numbers by READING native-res
    crops, not trusting profiles.
24. Degraded commas print as bare dots when the next word is lowercase and
    sibling commas on the same line show tails → comma. Line-final em-dash
    (`combinations of—`) joins WITHOUT space; hard hyphen inside words is
    never line-final; trailing line hyphen = synthetic (soft).
25. Old crop handles die when context folds; the ORIGINAL scan file path
    stays valid — re-read regions from it. Never re-transcribe from memory
    (this project once hallucinated a nonexistent quote block from book
    priors; native crops disproved it).
26. Keep exact original line breaks per block (`lines` table). Typesetter
    asserts joined logical text == text; justification distributes residual
    width into word gaps only.
39. Transcribe by PAGE BANDS (2–4 native-res reads/page), never line-strip
    loops. Per-line image grinding guarantees mid-task compaction; compacted
    agents then either re-transcribe from notes (#25) or livelock
    re-checking scratch state (/tmp ledgers). An N-agent strip-swarm is an
    N-fold context-loss multiplier, not a speedup. ZERO images in any
    subagent context, crops included (#57); vision is main-agent work.
40. Verification is a machine gate (the Block assert, build gates), not an
    agent ritual. A brief heavy with "verify/sanity-check" produces agents
    that verify forever and transcribe nothing; say "assert once after the
    write" instead.
41. Roundtrip asserts check JSON-vs-JSON, never JSON-vs-scan. Transcription
    drift (silently "smoothed" words, reassembled line order, modernized
    spelling) is only caught by the P6.5 V-pass: a fresh source re-read,
    word by word, per page, before ship. Band-reassembly from memory after
    image trimming is a known drift vector — re-read pixels, not notes.
47. `"source"."page_box"` provenance is `[x, y, W, H]`, NOT a corner pair:
    composites/crops must compute crop=(x, y, x+W, y+H). Read as corners it
    silently yields sliver strips (recto boxes end at x0+W = image width);
    a "cropped" composite is a script bug to verify before suspecting the
    data (the engine never reads page_box — PDF layout is unaffected).
42. Collision guards must register EVERY drawn rect (text lines, headings,
    tables, figures), not just floating figures — text-over-table and
    text-over-text overlaps are invisible to float-only checks and to
    every structure validator; occluded text is also a WCAG 1.4.3 contrast
    failure. Guard aborts: fix block gaps/rows in the model.
43. Vertical fidelity = the blank-row budget. Source pages interleave
    empty grid rows between display elements (titles, subheads, lists,
    note zones); transcribing only inked lines silently collapses the
    rhythm. Extract the source line grid (ink-band profile) per page and
    model inter-block gaps explicitly; measure deltas against the render,
    don't eyeball montages.

## D. Validators / external sources
27. pdfa.org wp-content PDFs: Cloudflare 403. The same content: GitHub
    `pdf-association/techniques-for-accessible-pdf` (clone) lists every
    role's version (`Em: 2.0`, `Strong: 2.0`...) — that file is the
    authority for role-vs-1.7 decisions.
28. veraPDF community bundle: `https://software.verapdf.org/releases/
    verapdf-installer.zip` (izpack) → headless:
    `java -DINSTALL_PATH=... -jar verapdf-izpack-*.jar -auto`; run
    `java -jar tools/vp/bin/cli-*.jar -f ua2 --format text|xml FILE`.
    UA-2 profile ≈ 1728 rules; UA-1 ≈ 106. `--format xml` + parsing
    `<rule status="failed">` is how you read exact predicates.
29. When a validator's message is cryptic, fetch the checker's Java/C
    source (URLs listed in `vendor/checker-src/README.md`, not vendored): `TaggedPDFConstants.java` /
    `TaggedPDFHelper.java` / `PDDestination.java` / MuPDF `name-table.h`
    settled namespace URIs, struct-dest rules, and PDF-2.0 name existence.
30. Regression lock: content-stream sha256 goldens (`bin/selftest.sh`) on
    the SYNTHETIC canary fixture (books/canary — invented text, generated
    placeholder art; no document content is versioned). Engine edits must
    reproduce canary streams byte-equal; caught the `ensure_p` port bug.
    Approved changes only: selftest.sh --update-goldens + reason in commit.
31. Determinism reality: ALL decoded streams/objects are identical across
    rebuilds, but qpdf's Flate encoder state (and hence raw file bytes and
    file size) can differ run-to-run. Goldens therefore hash DECODED
    streams; never gate on whole-file hashes.
32. Refactor proof pattern: extract engine → rebuild → compare stream
    hashes vs pre-refactor snapshot → bisect by difflib on decoded streams.
    Save snapshots OUTSIDE the tree you clean: a restructure once deleted a
    source file mid-cleanup; recovery was verifiable only because golden
    hashes of the shipped artifact existed.

## E. Images / figures (ComfyUI items marked *)
50. /Figure element: direct StructElem keys /Alt /Lang /Placement /BBox
    pass veraPDF ua1+ua2; BBox in PDF points, page space, y-up.
51. Image XObject: raw RGB + FlateDecode + DeviceRGB + BitsPerComponent 8;
    resource keys need the leading slash normalized in BOTH places
    (Resources dict AND `Do` operand) — mismatch = invisible image, valid file.
52. Layout collisions are MODEL bugs: the engine guard aborts the build on
    any text×float or float×float overlap; fix widths/indents/band/order.
    Transcription line tables must clear figure x-spans for every row the
    figure touches (band figure: rows consumed; float: rows = ceil(h/pitch)).
    A line whose '-' is a REAL hyphen (compound broken at the hyphen) needs
    `hard_hyphen_lines:[idx]` or the engine treats it as synthetic.
53. Alts are structure metadata, NOT drawn glyphs — exclude figure/block alts
    from the font subset census (subset blew up when they were included).
54. Contrast tool samples region luma percentiles; a "fail" over dark art
    under dark text is CORRECT behavior — remediate per ladder (lighten
    art zone / artifact backing), don't tune the sampler to pass.
55. * Diffusion outputs are guilty until seen: every candidate gets personal
    native-res review + contact sheet + objective pre-score before rubric
    verdict; the tools (imgctl) are evidence, never the acceptance.
56. * Comfy workflow reproducibility = (API-format workflow JSON, seed,
    inputs) triple; keep workflow files in images/workflows/, record the
    triple in the book IMAGES.md row every accept.
48. Checkers DIVERGE: Acrobat enforces rules WTPDF/veraPDF permit (it
    restricts Lbl/LBody to LI children — an Lbl-in-FENote passed veraPDF
    and failed Acrobat; its nested-alternate-text check is broader than
    any vera clause). Ship standard = Acrobat-clean too. Standing
    promotion rule: whenever an external checker (Acrobat/PAC/other)
    reports a finding our gauntlet missed, encode that check as a
    validate_pdf gate the same session and negative-test it by planting
    the defect in a copy. Proprietary checkers cannot run headless here
    — our gates ARE the approximation; they only improve when a finding
    is fed back.
49. Recurring constructs drift when styled per-occurrence (a list spanning
    a page break had its first item outdented while continuations were not;
    note blocks on successive pages carried different line pitch). Mechanism:
    "pattern":"<id>" on every instance block + canonical parameter set in
    STYLE-GUIDE + validate_pdf --book groups by pattern and ABORTS on any
    styling-key difference (numbering_start exempt). Mint the id during
    the P3 census, retrofit earlier instances, measure once.
57. Trust moves to RE-RUNNABLE TEXT, never to pixels in someone else's
    window. Swarm verifiers get file paths + claim text and independently
    re-run the instruments (pagecmp, validate_pdf, probes); a claim with no
    re-runnable evidence pointer is a hunch (log it, don't fix on it).
    Subagent image load — even one small crop — re-enables the fold→
    distrust-state→re-verify→livelock cycle that ate hours in the pilot,
    and crops inherit the primary's framing bias. Verification fan-out is
    safe BECAUSE verifiers are text-only, stateless, one-shot, and capped
    (docs/verification-protocol.md).
58. * Environment facts are harness-owned, repo-hostile. A hand-written
    ComfyUI client that baked in a host, a port and a scheme went stale the
    moment the integration moved behind a declared endpoint with bearer
    auth, and the repo then actively misinformed the next session (it also
    asserted a machine spec nobody had). Rule: never commit an endpoint,
    token, helper-tool path, host name, or capacity number — read them from
    the harness at run time and record only the *verdict* of
    `bin/comfy_probe.py`. Docs that restate an integration become a second
    source of truth, and the second source is always the stale one.
59. * "ComfyUI is not available here" is a supported configuration, not an
    error to route around. The gate answers ABSENT → the ladder stops at the
    non-diffusion rungs, the verdict goes in IMAGES.md, and any figure that
    genuinely needed restoration gets an ISSUES.md row. Never guess a
    localhost port, install a server, or start a second stack to make the
    rung exist (same trap as #58 in the other direction).
60. * `PARTIAL: no models installed` is the agent's own to-do, not a blocker.
    ComfyUI rescans weight folders when a loader is queried, so a file placed
    in the right class subfolder is selectable within seconds with no restart
    — while custom-node CODE loads only at startup, and packages for the
    server's own Python environment are usually outside an agent's reach
    entirely. Classify every gap as self-fixable (§4.1), request-once (§0), or
    route-around (§6) instead of reporting it and stopping.
61. * Do not assume a mapped directory in the workspace belongs to the running
    deployment — prove it by writing and observing from the server's side
    (upload via API → look; drop a file → query a loader). A mount that maps
    input/output but not models, or a deployment whose folders live elsewhere,
    changes the plan and must be re-proven per environment
    (docs/comfyui-ops.md §4.1).
62. * A pack whose files are on disk is not a pack that loaded. Node code that
    raises on import is swallowed into a startup log line, and a shim that
    catches its own missing module quietly is worse. Prove loading from the
    server's side — marker node present in `GET /object_info/<Class>`, control
    route answering, startup log clean — and confirm which directory the server
    actually imports from, because a mapped `custom_nodes/` in the workspace is
    not evidence it is on that path (docs/comfyui-ops.md §13).

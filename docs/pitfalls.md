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
    source (kept in `vendor/checker-src/`): `TaggedPDFConstants.java` /
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

## E. Images / figures (engine-proven 2026-10-12; ComfyUI items marked *)
32. /Figure element: direct StructElem keys /Alt /Lang /Placement /BBox
    pass veraPDF ua1+ua2; BBox in PDF points, page space, y-up.
33. Image XObject: raw RGB + FlateDecode + DeviceRGB + BitsPerComponent 8;
    resource keys need the leading slash normalized in BOTH places
    (Resources dict AND `Do` operand) — mismatch = invisible image, valid file.
34. Layout collisions are MODEL bugs: the engine guard aborts the build on
    any text×float or float×float overlap; fix widths/indents/band/order.
    Transcription line tables must clear figure x-spans for every row the
    figure touches (band figure: rows consumed; float: rows = ceil(h/pitch)).
    A line whose '-' is a REAL hyphen (compound broken at the hyphen) needs
    `hard_hyphen_lines:[idx]` or the engine treats it as synthetic.
35. Alts are structure metadata, NOT drawn glyphs — exclude figure/block alts
    from the font subset census (subset blew up when they were included).
36. Contrast tool samples region luma percentiles; a "fail" over dark art
    under dark text is CORRECT behavior — remediate per ladder (lighten
    art zone / artifact backing), don't tune the sampler to pass.
37. * Diffusion outputs are guilty until seen: every candidate gets personal
    native-res review + contact sheet + objective pre-score before rubric
    verdict; the tools (imgctl) are evidence, never the acceptance.
38. * Comfy workflow reproducibility = (API-format workflow JSON, seed,
    inputs) triple; keep workflow files in images/workflows/, record the
    triple in the book IMAGES.md row every accept.

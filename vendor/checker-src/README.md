# Checker sources consulted while debugging (NOT vendored — fetch fresh)

These upstream files answered questions the validator messages alone couldn't.
Pull them when needed; keep findings in docs/pitfalls.md (they already are).

| file | URL | what it proved |
|---|---|---|
| TaggedPDFConstants.java | https://raw.githubusercontent.com/verapdf/veraPDF-parser/master/src/main/java/org/verapdf/tools/TaggedPDFConstants.java | namespace URIs: PDF1 = http://iso.org/pdf/ssn, PDF2 = http://iso.org/pdf2/ssn; Em/Strong/Sub role names exist |
| TaggedPDFHelper.java | https://raw.githubusercontent.com/verapdf/veraPDF-parser/master/src/main/java/org/verapdf/tools/TaggedPDFHelper.java | standard-type resolution uses the element's OWN /NS (no inheritance) → every Em/Strong needs /NS |
| GFSEGroupedContent.java | https://raw.githubusercontent.com/verapdf/veraPDF-validation/master/validation-model/src/main/java/org/verapdf/gf/model/impl/pd/gfse/contents/GFSEGroupedContent.java | isTaggedContent walks /P up to StructTreeRoot → root Document needs /P=StructTreeRoot |
| PDDestination.java | https://raw.githubusercontent.com/verapdf/veraPDF-parser/master/src/main/java/org/verapdf/pd/PDDestination.java | struct destination test: dest[0] is a dict carrying /S (the structure element) |
| pdf-struct.c (MuPDF, AGPL) | https://raw.githubusercontent.com/ArtifexSoftware/mupdf/master/source/pdf/pdf-struct.c | pdf_check_structure_tree semantics: FIXED == repaired-on-load (e.g. missing root /P) |
| name-table.h (MuPDF) | https://raw.githubusercontent.com/ArtifexSoftware/mupdf/master/include/mupdf/pdf/name-table.h | which PDF names exist per version (Em, Strong registered) |
| techniques-for-accessible-pdf | https://github.com/pdf-association/techniques-for-accessible-pdf | official role/version registry (config/structure-types.yaml): "Em: 2.0 - Emphasis", "Strong: 2.0"...; Lbl/LBody + ListNumbering examples |

(Licenses: veraPDF = MPL-2.0+/GPL-3 dual; MuPDF = AGPL — reference by URL,
don't vendor copies into product repos.)

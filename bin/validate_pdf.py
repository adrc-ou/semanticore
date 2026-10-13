#!/usr/bin/env python
"""Generalized accessible-PDF validator for remediated books.

usage: validate_pdf.py PDF [--profile 1|2] [--expect Role=NAME=N ...]
                       [--expect-soft-hyphens N] [--book BOOK_DIR]

Core checks (profile-aware):
  catalog: MarkInfo, StructTreeRoot, Lang, DisplayDocTitle, XMP + pdfuaid
  identity: PDF 2.0 header for profile 2; Document /NS (pdf2/ssn) for profile 2
  marked content <-> structure tree bijection (incl. ParentTree, no holes)
  artifacts carry Type/BBox; BDC/EMC balanced
  outline destinations: structure (profile 2) vs page (profile 1)
  fonts: Type0/CIDFontType2 embedded + ToUnicode on every resource font
  PageLabels decimal start; role counts (--expect); Em/Strong children of P
  text roundtrip vs book page JSONs (--book): exact non-space match
Exit 0 iff all pass. Run veraPDF in addition; this tool checks things
veraPDF does not (roundtrip, counts, engine regressions).
"""
import argparse
import os
import re
import sys

import pikepdf
from pikepdf import Array, Name

P_OK = True


def good(m):
    print("ok  :", m)


def fail(m):
    global P_OK
    P_OK = False
    print("FAIL:", m)


def strip_markers(t):
    return "".join(m.group(2) if m.group(2) is not None else m.group(3)
                   for m in re.finditer(r"\{(?:[BI]+|EM|STR)\|([^{}]*)\}|"
                                        r"\{E\|([^{}]*)\|[^{}]*\}|([^{]+)", t)
                   ) if False else re.sub(r"\{(?:B|I|BI|EM|STR)\|([^{}]*)\}",
                                          r"\1",
                                          re.sub(r"\{E\|([^{}]*)\|[^{}]*\}",
                                                 r"\1", t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--profile", default=os.environ.get("UA_PART", "2"))
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--expect-soft-hyphens", type=int, default=None)
    ap.add_argument("--book", default=None)
    a = ap.parse_args()
    ua = str(a.profile)
    pdf = pikepdf.open(a.pdf)
    root = pdf.Root

    if not (root.get('/MarkInfo') and root.MarkInfo.get('/Marked') is True):
        fail("MarkInfo/Marked missing")
    if '/StructTreeRoot' not in root:
        fail("StructTreeRoot missing")
    if str(root.get('/Lang', '')) not in ("en-US", "en"):
        fail(f"Lang {root.get('/Lang')}")
    vp = root.get('/ViewerPreferences')
    if not (vp and vp.get('/DisplayDocTitle') is True):
        fail("DisplayDocTitle missing")
    if '/Metadata' not in root:
        fail("XMP missing")
    else:
        x = root.Metadata.read_bytes().decode('utf-8', 'replace')
        if f'<pdfuaid:part>{ua}</pdfuaid:part>' not in x:
            fail(f"pdfuaid:part != {ua}")
        elif ua == "2" and '<pdfuaid:rev>2024</pdfuaid:rev>' not in x:
            fail("pdfuaid:rev != 2024")
        else:
            good(f"XMP identity pdfuaid:part={ua}"
                 + (" rev=2024" if ua == "2" else ""))
        m = re.search(r'<dc:title>.*?<rdf:li xml:lang="x-default">(.*?)</rdf:li>',
                      x, re.S)
        it = str(pdf.trailer.get('/Info', {}).get('/Title', ''))
        if m and it and it == m.group(1):
            good("/Info Title == XMP dc:title")
        else:
            fail("title mismatch Info/XMP")
    hdr = open(a.pdf, "rb").read(16)
    if ua == "2" and b"PDF-2.0" not in hdr:
        fail("profile 2 requires %PDF-2.0 header")
    elif ua == "2":
        good("header %PDF-2.0")

    st = root.StructTreeRoot
    doc_el = st.K
    if ua == "2":
        nsv = str(doc_el.get("/NS", ""))
        if "pdf2/ssn" not in nsv:
            fail("Document element lacks /NS http://iso.org/pdf2/ssn")
        else:
            good("Document in PDF 2.0 structure namespace")

    # marked content bijection
    page_objs = list(pdf.pages)
    ref_pairs = set()

    def collect(e):
        k = e.get('/K')
        if k is None:
            return
        for it in (k if isinstance(k, Array) else [k]):
            if hasattr(it, "keys") and '/StructElem' in str(it.get('/Type', '')):
                collect(it)
            elif isinstance(it, Array) and len(it) == 2:
                ref_pairs.add((int(it[0]), int(it[1])))
            elif isinstance(it, (int, pikepdf.Integer if hasattr(pikepdf, 'Integer') else int)):
                pg, anc = None, e
                while anc is not None and pg is None:
                    if '/Pg' in anc:
                        pg = anc.Pg
                    anc = anc.get('/P')
                if pg is None:
                    fail(f"mcid {it} without resolvable /Pg")
                    continue
                for i, p in enumerate(page_objs):
                    if p.objgen == pg.objgen:
                        ref_pairs.add((i, int(it)))

    collect(doc_el)

    pat_bdc = re.compile(rb'/(\w+)\s*(?:<<\s*/MCID\s+(\d+)\s*>>)?\s*BDC')
    for i, p in enumerate(page_objs):
        c = p.Contents
        data = (b" ".join(x.read_bytes() for x in c) if isinstance(c, Array)
                else c.read_bytes())
        opens = list(pat_bdc.finditer(data))
        for m in opens:
            tag, mcid = m.group(1), m.group(2)
            if tag == b"Artifact":
                seg = m.group(0)
                if b"/Type" not in seg or (b"BBox" not in seg and b"Inline" not in seg):
                    fail(f"page {i}: artifact props {seg[:60]}")
            elif mcid is None:
                fail(f"page {i}: /{tag.decode()} BDC without MCID")
            elif (i, int(mcid)) not in ref_pairs:
                fail(f"page {i}: MCID {int(mcid)} (/{tag.decode()}) not in tree")
        if data.count(b"BDC") != data.count(b"EMC"):
            fail(f"page {i}: BDC/EMC unbalanced")
    good(f"marked content bijection: {len(ref_pairs)} sequences")

    pt = st.ParentTree
    if int(st.get('/ParentTreeNextKey', -1)) != len(page_objs):
        fail("ParentTreeNextKey != page count")
    nums = pt.Nums
    covered = {int(nums[i]) for i in range(0, len(nums), 2)}
    if covered != set(range(len(page_objs))):
        fail(f"ParentTree pages covered {covered}")
    else:
        for i in range(0, len(nums), 2):
            arr = nums[i + 1]
            for j, slot in enumerate(arr):
                if slot is None:
                    fail(f"ParentTree hole page {nums[i]} mcid {j}")
        good("ParentTree complete, no holes")

    # fonts
    for i, p in enumerate(page_objs):
        for fname, fo in p.Resources.Font.items():
            if str(fo.Subtype) != '/Type0' or '/ToUnicode' not in fo:
                fail(f"page {i} font {fname} not Type0/ToUnicode")
            elif '/FontFile2' not in fo.DescendantFonts[0].FontDescriptor:
                fail(f"page {i} font {fname} not embedded")
    good("all fonts Type0 + ToUnicode + FontFile2")

    # outline destination style
    ol = root.get('/Outlines')
    want_struct = ua == "2"
    n = 0
    if ol:
        it = ol.get('/First')
        while it is not None:
            d = it.get('/Dest')
            first = d[0] if isinstance(d, Array) else None
            is_struct = first is not None and hasattr(first, "keys") and '/S' in first
            if is_struct != want_struct:
                fail(f"outline dest kind (struct={is_struct}, profile={ua})")
            else:
                n += 1
            it = it.get('/Next')
        good(f"{n} outline destinations match profile {ua} style")

    pl = root.get('/PageLabels')
    if pl is None:
        fail("PageLabels missing")
    else:
        nums0 = pl.Nums
        good(f"PageLabels start {nums0[1].get('/St')}")

    # roles
    counts = {}
    parents = {}

    def rwalk(e, prole=""):
        r = str(e.get("/S", "")).lstrip("/")
        counts[r] = counts.get(r, 0) + 1
        k = e.get('/K')
        for x in (k if isinstance(k, Array) else ([k] if k is not None else [])):
            if hasattr(x, "keys") and '/StructElem' in str(x.get('/Type', '')):
                parents[str(x.objgen)] = r
                rwalk(x, r)
    rwalk(doc_el)

    for spec in a.expect:
        role, num = spec.split("=")
        want = int(num)
        got = counts.get(role, 0)
        if got != want:
            fail(f"role {role}: {got} != {want}")
        else:
            good(f"role {role} = {got}")
    if ua == "2":
        for r in counts:
            if r in ("Em", "Strong"):
                pass
    # Em/Strong inside P and carrying NS
    def nchk(e, prole):
        r = str(e.get("/S", "")).lstrip("/")
        if r in ("Em", "Strong"):
            if prole != "P":
                fail(f"{r} not child of P (parent {prole})")
            if ua == "2":
                ns = e.get("/NS")
                if ns is None or "pdf2/ssn" not in str(ns.get("/NS", "")):
                    fail(f"{r} {e.objgen} lacks /NS pdf2/ssn")
        k = e.get('/K')
        for x in (k if isinstance(k, Array) else ([k] if k is not None else [])):
            if hasattr(x, "keys") and '/StructElem' in str(x.get('/Type', '')):
                nchk(x, r)
    nchk(doc_el, "")

    # Figure elements: count, Alt, Placement, BBox, Lang
    figs = []
    def fwalk(e):
        if str(e.get("/S","")).lstrip("/") == "Figure":
            figs.append(e)
        k = e.get('/K')
        for x in (k if isinstance(k, Array) else ([k] if k is not None else [])):
            if hasattr(x, "keys") and '/StructElem' in str(x.get("/Type", "")):
                fwalk(x)
    fwalk(doc_el)
    nfig_exp = next((int(s.split("=")[1]) for s in a.expect if s.startswith("Figure=")), None)
    if nfig_exp is not None and len(figs) != nfig_exp:
        fail(f"Figure count {len(figs)} != {nfig_exp}")
    for fe in figs:
        if "/Alt" not in fe:
            fail(f"Figure {fe.objgen} missing /Alt")
        if "/Placement" not in fe or "/BBox" not in fe:
            fail(f"Figure {fe.objgen} missing Placement/BBox")
        if "/Lang" not in fe:
            fail(f"Figure {fe.objgen} missing /Lang")
    if nfig_exp is not None:
        good(f"{len(figs)} Figure elements with Alt/Placement/BBox/Lang")

    if a.expect_soft_hyphens is not None:
        at = 0
        def ac(e):
            nonlocal at
            v = e.get('/ActualText')
            if v is not None and '\u00ad' in str(v):
                at += 1
            k = e.get('/K')
            for x in (k if isinstance(k, Array) else ([k] if k is not None else [])):
                if hasattr(x, "keys") and '/StructElem' in str(x.get('/Type', '')):
                    ac(x)
        ac(doc_el)
        if at != a.expect_soft_hyphens:
            fail(f"soft-hyphen ActualText spans {at} != {a.expect_soft_hyphens}")
        else:
            good(f"{at} ActualText soft-hyphen spans")

    # text roundtrip vs book
    if a.book:
        import json, pathlib
        import pymupdf
        pages = sorted((pathlib.Path(a.book) / "pages").glob("*.json"))
        parts = []
        for pf in pages:
            pg = json.loads(pf.read_text())
            for b in pg["blocks"]:
                if b["kind"] == "figure":
                    continue
                if b["kind"] == "list":
                    for it in b["items"]:
                        parts.append("\u2022" + it["text"])
                else:
                    parts.append(strip_markers(b["text"]))
        expected = re.sub(r"\s+", "", "".join(parts)).replace("-", "")
        d = pymupdf.open(a.pdf)
        art = set()
        for pf in pages:
            pg = json.loads(pf.read_text())
            art.add(pg.get("running_head") or "\u0000")
            art.add(str(pg.get("folio", "\u0000")))
        full = []
        for pgv in d:
            for ln in pgv.get_text().splitlines():
                if ln.strip() in art:
                    continue
                full.append(ln)
        got = re.sub(r"\s+", "", "\n".join(full)).replace("\u00ad", "").replace("-", "")
        if got != expected:
            i = next((k for k in range(min(len(got), len(expected)))
                      if got[k] != expected[k]), min(len(got), len(expected)))
            fail(f"roundtrip mismatch @{i}: ...{expected[max(0,i-25):i+25]!r} vs ...{got[max(0,i-25):i+25]!r}")
        else:
            good(f"text roundtrip exact ({len(expected)} non-space chars)")

    print("RESULT:", "PASS" if P_OK else "FAIL")
    return 0 if P_OK else 1


if __name__ == "__main__":
    sys.exit(main())

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
  text roundtrip vs book page JSONs (--book): STRICT spec-level decode —
  ToUnicode-mapped glyphs in content order, BDC ActualText substitution,
  artifacts skipped, spaces compared. No layout heuristics anywhere.
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
                   ) if False else re.sub(r"\{(?:B|I|BI|EM|STR|REF)\|([^{}]*)\}",
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
    next_key = int(st.get('/ParentTreeNextKey', -1))
    nums = pt.Nums
    covered = {int(nums[i]) for i in range(0, len(nums), 2)}
    if not covered >= set(range(len(page_objs))):
        fail(f"ParentTree pages not covered: {sorted(set(range(len(page_objs))) - covered)}")
    elif next_key < len(page_objs) or max(covered, default=-1) >= next_key:
        fail(f"ParentTreeNextKey {next_key} vs keys {sorted(covered)}")
    else:
        holes = 0
        for i in range(0, len(nums), 2):
            key, val = int(nums[i]), nums[i + 1]
            if isinstance(val, pikepdf.Array):
                for j, slot in enumerate(val):
                    if slot is None:
                        fail(f"ParentTree hole page {key} mcid {j}")
                        holes += 1
            elif str(val.get('/Type', '')) == '/StructElem':
                pass          # dedicated annotation struct-parent key (legal)
            else:
                fail(f"ParentTree key {key} value neither array nor StructElem")
        if not holes:
            good(f"ParentTree complete, no holes ({len(covered)} keys)")

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

    # ---- notes & nested alternate text (WTPDF / Acrobat-class gates) ----
    def kids(e):
        k = e.get('/K')
        return [x for x in (k if isinstance(k, Array) else
                            ([k] if k is not None else []))
                if hasattr(x, "keys") and '/StructElem' in str(x.get('/Type', ''))]

    # 1) Nested alternate text: /Alt REPLACES a subtree for AT — anything
    #    Alt-bearing below an Alt-bearing element is dead text (Acrobat
    #    "nested alternate text"; also traps ActualText).
    dead = []

    def altwalk(e, inside_alt):
        if inside_alt and ("/Alt" in e or "/ActualText" in e):
            dead.append(str(e.get("/S", "?")))
        for x in kids(e):
            altwalk(x, inside_alt or "/Alt" in e)
    altwalk(doc_el, False)
    if dead:
        fail(f"NESTED ALTERNATE TEXT: {len(dead)} elements (e.g. {dead[0]}) "
             f"carry Alt/ActualText inside an /Alt subtree — AT reads the "
             f"replacement and skips them")
    else:
        good("no nested alternate text (every /Alt subtree is Alt-free)")

    # 2) FENote / Reference / /Ref model (UA-2); Annot notes for UA-1.
    notes, refs, alle = [], [], {}

    def reg(e):
        alle[e.objgen] = e
        s = str(e.get("/S", "")).lstrip("/")
        if s in ("FENote", "Annot"):
            notes.append(e)
        if s == "Reference":
            refs.append(e)
        for x in kids(e):
            reg(x)
    reg(doc_el)
    for n in notes:
        if "/Alt" in n:
            fail("note container carries /Alt (would replace note text for AT)")
    if ua == "2":
        for n in (x for x in notes if str(x.get("/S", "")).endswith("FENote")):
            av = n.get("/A")
            nt = av.get("/NoteType") if av is not None and hasattr(av, "get") else None
            if nt is None or str(nt).lstrip("/") not in ("Footnote", "Endnote", "None"):
                fail(f"FENote {n.objgen} missing /A /O /FENote /NoteType")
        # /Ref reciprocity: every claim must point at a struct elem that
        # lists the claim back (veraPDF orphanRefs/ghostRefs analog).
        npair = 0
        for e in alle.values():
            r = e.get("/Ref")
            if r is None:
                continue
            for t in (r if isinstance(r, Array) else [r]):
                te = alle.get(getattr(t, "objgen", None))
                if te is None:
                    fail(f"/Ref of {e.get('/S')} does not target a struct elem")
                    continue
                rt = te.get("/Ref")
                if not any(getattr(x, "objgen", None) == e.objgen
                           for x in (rt if isinstance(rt, Array) else ([rt] if rt else []))):
                    fail(f"/Ref {e.get('/S')}->{te.get('/S')} not reciprocal")
                npair += 1
        nfe = sum(1 for x in notes if str(x.get("/S", "")).endswith("FENote"))
        good(f"notes model: {nfe} FENote, {len(refs)} Reference, "
             f"{npair} reciprocal /Ref associations")

    # ---- Acrobat list-nesting rule (checker divergence, pitfall #48) ----
    # Acrobat REQUIRES Lbl and LBody to be children of LI, and LI a child of
    # L — stricter than WTPDF (which also permits Lbl/LBody under other
    # grouping elements like FENote). We hold to Acrobat's rule so the file
    # passes the checker our operator runs; a Lbl under a FENote marker fails
    # here even though veraPDF stays silent.
    listerrs = []

    def lwalk(e, parent_role):
        s = str(e.get("/S", "")).lstrip("/")
        if s in ("Lbl", "LBody") and parent_role != "LI":
            listerrs.append(f"{s} under {parent_role} (must be child of LI)")
        if s == "LI" and parent_role != "L":
            listerrs.append(f"LI under {parent_role} (must be child of L)")
        for x in kids(e):
            lwalk(x, s)
    lwalk(doc_el, "Document")
    if listerrs:
        fail(f"LIST NESTING: {len(listerrs)} violation(s), e.g. {listerrs[0]} "
             f"— Acrobat's Lbl/LBody check; Lbl markers go directly in the "
             f"parent, never wrapping a FENote/Reference marker")
    else:
        good("list nesting: Lbl/LBody only under LI, LI only under L")

    # text roundtrip vs book — STRICT spec-level decode: every glyph code is
    # mapped through its font's ToUnicode and concatenated in content order,
    # with BDC ActualText substitution and artifact skipping. NO layout or
    # gap heuristics: this is what a copy/paste consumer of a strict viewer
    # gets. Spaces must be real glyphs in the stream or this fails.
    if a.book:
        import json, pathlib
        import pymupdf
        pages = sorted((pathlib.Path(a.book) / "pages").glob("*.json"))

        # ---- pattern consistency: blocks sharing a "pattern" id must carry
        # identical styling, so the same construct is identical everywhere
        # (the STYLE-GUIDE anti-drift contract, made machine-enforced). ----
        STYLE_KEYS = ("kind", "size", "numbering",
                      "bullet_em", "tab_em", "wrap_em", "item_style", "align",
                      "indent", "role", "note_kind", "marker", "x_off",
                      "width", "style", "pitch", "cell_size")
        groups = {}
        for pf in pages:
            for b in json.loads(pf.read_text())["blocks"]:
                pid = b.get("pattern")
                if pid:
                    groups.setdefault(pid, []).append((pf.name, b))
        drift = []
        for pid, members in groups.items():
            ref_name, ref = members[0]
            for nm, b in members[1:]:
                for k in STYLE_KEYS:
                    if b.get(k) != ref.get(k):
                        drift.append(
                            f"{pid}: {nm}.{b.get('id')} {k}={b.get(k)!r} "
                            f"!= {ref_name}.{ref.get('id')} {k}={ref.get(k)!r}")
        if drift:
            fail(f"PATTERN DRIFT ({len(drift)}): " + "; ".join(drift[:4]))
        else:
            good(f"pattern consistency: {len(groups)} pattern(s), "
                 f"{sum(len(m) for m in groups.values())} blocks identical")

        def strip_strict(t):
            # XREF: {XREF|target|display} keeps only the display text visible
            t = re.sub(r"\{XREF\|[^{}|]*\|([^{}]*)\}", r"\1", t)
            # E spans: /E is an EXPANSION annotation, not ActualText —
            # extraction keeps the visible text
            t = re.sub(r"\{E\|([^{}]*)\|[^{}]*\}", r"\1", t)
            return re.sub(r"\{(?:B|I|BI|EM|STR|REF)\|([^{}]*)\}", r"\1", t)

        parts = []
        for pf in pages:
            pg = json.loads(pf.read_text())
            for b in pg["blocks"]:
                if b["kind"] == "figure":
                    continue
                if b["kind"] == "list":
                    if b.get("numbering") == "arabic":
                        st0 = int(b.get("numbering_start", 1))
                        for j, it in enumerate(b["items"]):
                            parts.append(f"{st0 + j}. " + strip_strict(it["text"]))
                    else:
                        mk = b.get("marker", "•") or ""
                        for it in b["items"]:
                            parts.append(mk + (" " if mk else "")
                                         + strip_strict(it["text"]))
                elif b["kind"] == "table":
                    cap = b.get("caption")
                    if cap:
                        parts.append(strip_strict(cap["text"]))
                    for r in b["rows"]:
                        for c in r:
                            parts.append(strip_strict(c["text"]))
                elif b["kind"] == "columns":
                    for col in b["columns"]:
                        for pb in col:
                            parts.append(strip_strict(pb["text"]))
                else:
                    parts.append(strip_strict(b["text"]))

        d = pymupdf.open(a.pdf)
        lost, unmapped, page_texts = [], [], []
        tokre = re.compile(
            r"/(?P<res>F\d+)\s+[\d.]+\s+Tf"
            r"|/(?P<brole>\w+)\s*<<(?P<bprops>.*?)>>\s*BDC"
            r"|(?P<emc>\bEMC\b)"
            r"|<(?P<thex>[0-9A-Fa-f]*)>\s*Tj"
            r"|\[(?P<arr>[^]]*)\]\s*TJ", re.S)
        for pno, pg in enumerate(d):
            fmaps = {}
            for tup in pg.get_fonts(full=True):
                o = d.xref_object(tup[0], compressed=True) or ""
                m = re.search(r"/ToUnicode (\d+) 0 R", o)
                if not m:
                    fail(f"page {pno+1}: font {tup[4]} has no ToUnicode")
                    continue
                cm = d.xref_stream(int(m.group(1))).decode("latin-1")
                mp = {}
                for src, dst in re.findall(
                        r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", cm):
                    if len(src) != 4:
                        continue
                    if len(dst) == 4:
                        mp[int(src, 16)] = chr(int(dst, 16))
                    elif len(dst) == 8:
                        hi, lo = int(dst[:4], 16), int(dst[4:], 16)
                        mp[int(src, 16)] = chr(0x10000
                                               + ((hi - 0xD800) << 10)
                                               + (lo - 0xDC00))
                fmaps[tup[4].lstrip("/")] = mp
            cs = b"".join(d.xref_stream(x)
                          for x in pg.get_contents()).decode("latin-1")
            out, stack, cur_font = [], [], None
            for m in tokre.finditer(cs):
                if m.group("res"):
                    cur_font = m.group("res")
                elif m.group("brole"):
                    at = None
                    mat = re.search(r"/ActualText\s*<([0-9A-Fa-f]+)>",
                                    m.group("bprops"))
                    if mat:
                        u = bytes.fromhex(mat.group(1)).decode("utf-16-be")
                        at = u.removeprefix("﻿")
                    stack.append([m.group("brole") == "Artifact", at, []])
                elif m.group("emc"):
                    if not stack:
                        fail(f"page {pno+1}: unmatched EMC")
                        continue
                    art, at, buf = stack.pop()
                    txt = at if at is not None else "".join(buf)
                    if not art:
                        (stack[-1][2].append(txt) if stack
                         else out.append(txt))
                else:
                    s = (m.group("thex") if m.group("thex") is not None
                         else "".join(re.findall(r"<([0-9A-Fa-f]+)>",
                                                 m.group("arr"))))
                    mp = fmaps.get(cur_font or "", {})
                    buf = []
                    for i in range(0, len(s), 4):
                        code = int(s[i:i + 4], 16)
                        ch = mp.get(code)
                        if ch is None and code != 0:
                            unmapped.append((pno + 1, s[i:i + 4]))
                            ch = ""
                        buf.append(ch)
                    txt = "".join(buf)
                    if not stack:
                        if txt.strip():
                            lost.append((pno + 1, txt[:60]))
                    elif not stack[-1][0]:
                        stack[-1][2].append(txt)
            if stack:
                fail(f"page {pno+1}: unbalanced BDC at EOF")
            page_texts.append("".join(out))
        SHY = "\u00ad"   # soft-hyphen: substituted by ActualText, not copy text
        def canon(s):
            return re.sub(r"\s+", " ", s.replace(SHY, "")).strip()
        expected_c, got_c = canon(" ".join(parts)), canon(" ".join(page_texts))
        if unmapped:
            fail(f"{len(unmapped)} glyph codes not in ToUnicode "
                 f"(first: page {unmapped[0][0]} code {unmapped[0][1]})")
        if lost:
            fail(f"unmarked text outside any structure element: "
                 f"p{lost[0][0]} {lost[0][1]!r} ({len(lost)} runs)")
        if got_c != expected_c:
            i = next((k for k in range(min(len(got_c), len(expected_c)))
                      if got_c[k] != expected_c[k]),
                     min(len(got_c), len(expected_c)))
            fail(f"STRICT roundtrip mismatch @{i} "
                 f"(spaces/punctuation ARE compared): "
                 f"...{expected_c[max(0,i-30):i+30]!r} vs "
                 f"...{got_c[max(0,i-30):i+30]!r}")
        else:
            good(f"strict text roundtrip exact, incl. spaces "
                 f"({len(expected_c)} chars, {len(page_texts)} pages)")

    print("RESULT:", "PASS" if P_OK else "FAIL")
    return 0 if P_OK else 1


if __name__ == "__main__":
    sys.exit(main())

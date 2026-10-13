#!/usr/bin/env python
"""pdf_probe.py — decode a tagged PDF's structure + marked content for QA.

usage: pdf_probe.py PDF [--page N] [--text]

Prints, per page: the marked-sequence spine (role, mcid, font/size, baseline y,
decoded text) and the matching structure-element outline. Use when output and
page model disagree, or to inspect a build you did not create.
"""
import re
import sys
import pikepdf
from pikepdf import Array


def tounicode_map(tustream):
    txt = tustream.read_bytes().decode("latin-1")
    pairs = re.findall(r"<([0-9A-Fa-f]{4})>\s*<([0-9A-Fa-f]{4})>", txt)
    return {int(a, 16): chr(int(b, 16)) for a, b in pairs}


def main():
    path = sys.argv[1]
    only = None
    show_text = "--text" in sys.argv
    if "--page" in sys.argv:
        only = int(sys.argv[sys.argv.index("--page") + 1]) - 1
    pdf = pikepdf.open(path)
    fonts = {}

    def fdecode(key, fontobj, hexstr):
        if key not in fonts:
            fonts[key] = tounicode_map(fontobj.ToUnicode)
        m = fonts[key]
        return "".join(m.get(int(hexstr[i:i + 4], 16), "?")
                       for i in range(0, len(hexstr), 4))

    pat = re.compile(
        r"/(\w+)\s*(?:<<\s*/MCID\s+(\d+)\s*>>)?\s*BDC\b"
        r"|BT\s+(/\w+)\s+([\d.]+)\s+Tf\s+1 0 0 1\s+([\d.-]+)\s+([\d.-]+)\s+Tm\s+"
        r"\s*(?:<([0-9A-Fa-f]+)>\s*Tj|\[([^\]]*)\]\s*TJ)", re.S)
    tj_pat = re.compile(r"<([0-9A-Fa-f]+)>|(-?[\d.]+)")

    tree = {}

    def walk(e):
        k = e.get("/K")
        r = str(e.get("/S", "")).lstrip("/")
        attrs = " ".join(a for a in ("/ActualText", "/E", "/NS", "/Alt")
                         if e.get(a) is not None)
        mc = []
        if k is not None:
            for it in (k if isinstance(k, Array) else [k]):
                if isinstance(it, Array) and len(it) == 2:
                    mc.append((int(it[0]), int(it[1])))
                elif isinstance(it, int):
                    mc.append(("?", it))
                elif hasattr(it, "keys") and str(it.get("/Type", "")) == "/StructElem":
                    walk(it)
        for pg, m in mc:
            tree[(str(pg), m)] = f"{r}{' ' + attrs if attrs else ''}"

    if "/StructTreeRoot" in pdf.Root:
        walk(pdf.Root.StructTreeRoot.K)

    for i, page in enumerate(pdf.pages):
        if only is not None and i != only:
            continue
        c = page.Contents
        data = (b" ".join(x.read_bytes() for x in c) if isinstance(c, Array)
                else c.read_bytes()).decode("latin-1")
        print(f"===== page {i+1} =====")
        cur_role = cur_mc = None
        for m in pat.finditer(data):
            if m.group(1):
                cur_role, cur_mc = m.group(1), m.group(2)
                tag = tree.get(("?", int(cur_mc))) or tree.get((str(i), int(cur_mc))) or ""
                print(f"[BDC] /{cur_role} MCID {cur_mc}  «{tag}»")
            else:
                fkey = m.group(3)
                fref = page.Resources.Font[fkey]
                hexs = m.group(7)
                txt = ""
                if hexs:
                    txt = fdecode(fkey, fref, hexs)
                elif m.group(8):
                    parts = []
                    for hx, num in tj_pat.findall(m.group(8)):
                        if hx:
                            parts.append(fdecode(fkey, fref, hx))
                        elif float(num) < -120:
                            parts.append(" ")
                    txt = "".join(parts)
                if show_text or cur_role == "Artifact":
                    print(f"      {m.group(3)}@{m.group(4)} "
                          f"y={m.group(6)} x={m.group(5)}: {txt[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

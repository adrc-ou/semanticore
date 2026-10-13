#!/usr/bin/env python
"""Scan measurement & crop helpers for remediation.

subcommands
  meta    <scan>                      page-size/dpi/pitch/column geometry (JSON)
  strips  <scan> --page N --out DIR   crop each detected text line -> PNG (OCR/vision aid)
  half    <scan> --page N --out FILE  single page crop
  render  <pdf> --page N --out FILE   rasterize one PDF page (for side-by-side QA)
  diffcols <pdfA> <pdfB>              compare page content-stream hashes

`meta` assumes an evenly-lit two-page spread unless --single. Geometry it
reports is advisory; final numbers are chosen by a human reading the strips.
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert("L")).astype(np.int32)


def page_boxes(a, single):
    H, W = a.shape
    if single:
        return [(0, W)]
    mid = W // 2
    # gutter = darkest continuous vertical valley near the middle
    colsum = (a < 115).sum(axis=0)
    lo, hi = int(W * 0.42), int(W * 0.58)
    g = lo + int(np.argmin(colsum[lo:hi]))
    return [(0, g), (g, W)]


def line_bands(prof, min_ink, gap=8):
    idx = np.nonzero(prof >= min_ink)[0]
    if not len(idx):
        return []
    out, cur = [], [idx[0]]
    for v in idx[1:]:
        if v - cur[-1] <= gap:
            cur.append(v)
        else:
            out.append((cur[0], cur[-1])); cur = [v]
    out.append((cur[0], cur[-1]))
    return out


def meta(a, single):
    H, W = a.shape
    dark = a < 115
    pages = []
    for (x0, x1) in page_boxes(a, single):
        col = dark[:, x0:x1]
        # narrow central window to dodge gutter shadow & outer bleed
        wx0, wx1 = int((x1 - x0) * 0.30), int((x1 - x0) * 0.72)
        prof = col[:, wx0:wx1].sum(axis=1)
        bands = line_bands(prof, 2)
        body = [b for b in bands if b[0] > H * 0.06]
        tops = np.array([b[0] for b in body])
        pitch = float(np.median(np.diff(tops))) if len(tops) > 2 else None
        # column x extent from body rows only
        if len(body) > 4:
            bt, bb = body[3][0], body[-1][1]
            cs = dark[bt:bb, x0:x1].sum(axis=0)
            nz = np.nonzero(cs >= 2)[0]
            left, right = int(nz.min()), int(nz.max())
        else:
            left = right = None
        pages.append(dict(
            x=[int(x0), int(x1)],
            first_line_top=int(tops[0]) if len(tops) else None,
            last_line_bottom=int(body[-1][1]) if body else None,
            n_line_bands=len(body), pitch_px=round(pitch, 1) if pitch else None,
            col_x0=left, col_x1=right))
    return dict(width=int(W), height=int(H), pages=pages)


def cmd_meta(a, args):
    print(json.dumps(meta(a, args.single), indent=1))


def cmd_strips(a, args):
    H, W = a.shape
    pages = page_boxes(a, args.single)
    x0, x1 = pages[args.page - 1] if args.page else pages[0]
    prof = (a[:, x0:x1] < 115).sum(axis=1)
    if args.rows:
        m = meta(a, args.single)["pages"]
        pi = args.page - 1 if args.page else 0
        top = m[pi]["first_line_top"] or int(H * 0.06)
        bot = m[pi]["last_line_bottom"] or int(H * 0.97)
        step = (bot - top) / args.rows
        bands = [(int(top + k * step), int(top + (k + 1) * step)) for k in range(args.rows)]
    else:
        bands = [b for b in line_bands(prof, 2) if b[0] > H * 0.05]
    os.makedirs(args.out, exist_ok=True)
    img = Image.fromarray(a.astype('uint8'))
    for i, (t, b) in enumerate(bands):
        pad = int(args.pad)
        crop = img.crop((max(0, x0 + 4), max(0, t - pad),
                         min(W, x1 - 4), min(H, b + pad)))
        crop.save(os.path.join(args.out, f"line{i:03d}.png"))
    print(f"{len(bands)} line strips -> {args.out}")


def cmd_half(a, args):
    x0, x1 = page_boxes(a, args.single)[args.page - 1]
    Image.fromarray(a.astype('uint8')).crop((x0, 0, x1, a.shape[0])).save(args.out)
    print("wrote", args.out)


def cmd_render(args):
    import pymupdf
    d = pymupdf.open(args.pdf)
    d[args.page - 1].get_pixmap(dpi=args.dpi).save(args.out)
    print("wrote", args.out)


def cmd_diff(a, b):
    import pikepdf, hashlib
    pa, pb = pikepdf.open(a), pikepdf.open(b)
    if len(pa.pages) != len(pb.pages):
        print(f"DIFFERS page count {len(pa.pages)} vs {len(pb.pages)}"); return 1
    same = True
    for i in range(len(pa.pages)):
        ha = hashlib.sha256(pa.pages[i].Contents.read_bytes()).hexdigest()
        hb = hashlib.sha256(pb.pages[i].Contents.read_bytes()).hexdigest()
        if ha != hb:
            same = False; print(f"page {i+1}: DIFFERS")
    print("IDENTICAL content streams" if same else "DIFFERENT")
    return 0 if same else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("meta");   m.add_argument("scan"); m.add_argument("--single", action="store_true")
    s = sub.add_parser("strips"); s.add_argument("scan"); s.add_argument("--page", type=int, default=1)
    s.add_argument("--out", required=True); s.add_argument("--pad", type=int, default=6); s.add_argument("--single", action="store_true")
    s.add_argument("--rows", type=int, default=None,
                   help="ignore band detection; split body evenly into N rows "
                        "(robust to skewed scans; one row per printed line)")
    h = sub.add_parser("half");   h.add_argument("scan"); h.add_argument("--page", type=int, default=1)
    h.add_argument("--out", required=True); h.add_argument("--single", action="store_true")
    r = sub.add_parser("render"); r.add_argument("pdf"); r.add_argument("--page", type=int, default=1)
    r.add_argument("--out", required=True); r.add_argument("--dpi", type=int, default=300)
    dc = sub.add_parser("diffcols"); dc.add_argument("a"); dc.add_argument("b")
    args = ap.parse_args()
    if args.cmd == "render":    return cmd_render(args)
    if args.cmd == "diffcols":  return cmd_diff(args.a, args.b)
    a = load(args.scan)
    return {"meta": cmd_meta, "strips": cmd_strips, "half": cmd_half}[args.cmd](a, args)


if __name__ == "__main__":
    sys.exit(main() or 0)

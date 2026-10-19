#!/usr/bin/env python
"""pagecmp.py — numeric layout parity between a scan page and its PDF page.

usage: pagecmp.py SCAN --box X,Y,W,H --pdf PDF --page N
                     [--tol 2.0] [--regions 10] [--max-report 12] [--no-x]

Crops the scan to its page_box, renders the PDF page at the same pixel
size, then aligns the two ROW-INK profiles with a scale+shift fit:
  * scale mismatch (a != 1)  => line pitch / leading drift across the page
  * shift (b)                => origin offset (registration, informational)
  * per-region residual      => LOCAL collapse or spread (the class eyeball
                               checks miss: one paragraph's spacing eaten)
Optionally the same fit on COLUMN profiles (left-margin fidelity): reported
informationally (per-line left edges vary legitimately with indent/center).
Exit 1 if the pitch scale drifts > 3.5% or a confidently-matched
region (corr > 0.55) is displaced by more than --tol pt.

Geometry-only — it never reads text. --box is the page provenance
page_box [x, y, w, h]. Advisory by design: flags are starting points for
the P6-L visual pass, not automatic re-build orders.
"""
import argparse
import os
import pathlib
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def row_profile(dark):
    """ink count per row, vertical artifacts (gutter/bleed) masked first"""
    colink = dark.mean(axis=0)
    art = colink > 0.30
    if art.any():
        dark = dark.copy()
        dark[:, art] = False
    return dark.sum(axis=1).astype(float)


def smooth(p, k=9):
    if len(p) < k:
        return p
    ker = np.ones(k) / k
    return np.convolve(p, ker, mode="same")


def align(ref, tgt, a_lo=0.9, a_hi=1.1, a_steps=41):
    """find scale a, shift b maximizing normalized cross-correlation of
    ref(y) against tgt(a*y + b). Both profiles same pixel length."""
    n = len(ref)
    y = np.arange(n)
    best = (-2.0, 1.0, 0.0)
    rn = ref - ref.mean()
    rstd = rn.std() or 1.0
    for a in np.linspace(a_lo, a_hi, a_steps):
        # coarse shift search +-6% of page
        yy = np.clip((y * a).astype(int), 0, n - 1)
        for b in range(-int(0.06 * n), int(0.06 * n) + 1, 3):
            tj = np.clip(yy + b, 0, n - 1)
            tv = tgt[tj]
            tv = tv - tv.mean()
            den = (tv.std() or 1.0) * rstd * n
            c = float((rn * tv).sum() / den)
            if c > best[0]:
                best = (c, a, b)
    # refine shift at 1px
    c0, a, b0 = best
    for b in range(b0 - 3, b0 + 4):
        yy = np.clip((y * a).astype(int), 0, n - 1)
        tj = np.clip(yy + b, 0, n - 1)
        tv = tgt[tj]
        tv = tv - tv.mean()
        den = ((tv.std() or 1.0) * rstd * n)
        c = float((rn * tv).sum() / den)
        if c > c0:
            c0, b = c, b
    return c0, a, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan")
    ap.add_argument("--box", required=True, help="x,y,w,h (page_box)")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, required=True, help="1-based")
    ap.add_argument("--tol", type=float, default=2.0,
                    help="max region residual, pt")
    ap.add_argument("--regions", type=int, default=10)
    ap.add_argument("--max-report", type=int, default=12)
    ap.add_argument("--no-x", action="store_true", help="skip margin fit")
    a = ap.parse_args()

    root = pathlib.Path(os.environ.get("SEMANTICORE_HOME", "") or ".").resolve()
    sys.path.insert(0, str(root / "lib"))
    import pymupdf

    x, y, w, h = (int(v) for v in a.box.split(","))
    src = np.asarray(Image.open(a.scan).convert("L").crop((x, y, x + w, y + h)))
    if src.shape[0] < 200 or src.min() > 200:
        sys.exit("scan crop looks blank/wrong — check --box")
    p50 = float(np.percentile(src, 50))
    thr = max(60.0, min(115.0, 0.5 * (p50 + 40.0)))
    dark_s = src.astype(np.int32) < thr

    d = pymupdf.open(a.pdf)
    pg = d[a.page - 1]
    ph_pt = pg.rect.height
    s = h / ph_pt
    px = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), colorspace=pymupdf.csGRAY)
    rn = np.asarray(Image.frombytes("L", (px.width, px.height), px.samples))
    H = min(dark_s.shape[0], rn.shape[0])
    W = min(dark_s.shape[1], rn.shape[1])
    dark_s = dark_s[:H, :W]
    dark_r = rn[:H, :W] < 128
    ppp = ph_pt / H

    ps = smooth(row_profile(dark_s))
    pr = smooth(row_profile(dark_r))
    corr, scale, shift = align(ps, pr)
    ptx = ppp * shift                     # origin offset, pt (informational)
    pitch_err = abs(scale - 1.0)

    # region residuals: local shift of pdf vs the global fit
    bad_regions, rep = 0, []
    edges = np.linspace(0, H, a.regions + 1).astype(int)
    yy = np.arange(H)
    warp = np.clip((yy * scale + shift).astype(int), 0, H - 1)
    for i in range(a.regions):
        e0, e1 = edges[i], edges[i + 1]
        if e1 - e0 < 12:
            continue
        seg_s = ps[e0:e1]
        if seg_s.max() < 10:              # blank zone both sides expected
            continue
        best = None
        for dloc in range(-int(0.02 * H), int(0.02 * H) + 1, 1):
            tj = np.clip(warp[e0:e1] + dloc, 0, H - 1)
            seg_r = pr[tj]
            sn = seg_s - seg_s.mean()
            rv = seg_r - seg_r.mean()
            den = (sn.std() * rv.std() * len(sn)) or 1.0
            c = float((sn * rv).sum() / den)
            if c > 0.55 and (best is None or c > best[0]):
                best = (c, dloc)
        if best:
            res_pt = best[1] * ppp
            over = abs(res_pt) > a.tol
            bad_regions += over
            rep.append((e0 * ppp, e1 * ppp, res_pt, best[0], over))

    x_msg = ""
    if not a.no_x:
        cs = smooth(row_profile(dark_s.T))
        cr = smooth(row_profile(dark_r.T))
        cx, sx, bx = align(cs, cr, 0.95, 1.05, 21)
        x_msg = (f" | margin fit: scale {sx:.3f} shift {bx * ppp:+.1f}pt "
                 f"(info)")

    print(f"page {a.page}: profile corr {corr:.3f}, pitch scale "
          f"{scale:.4f} ({(scale - 1) * 100:+.1f}%), origin {ptx:+.1f}pt"
          f"{x_msg}")
    print(f"{'y0':>6} {'y1':>6} {'resid':>6} {'corr':>5}")
    shown = [r for r in rep if r[4]][:a.max_report] or rep[:a.max_report]
    for (y0, y1, res_pt, c, over) in shown:
        print(f"{y0:6.0f} {y1:6.0f} {res_pt:6.1f} {c:5.2f}"
              + ("  <== DRIFT" if over else ""))
    # a low-correlation fit (sparse/display pages: covers, image pages) is
    # not trustworthy for the page-level pitch claim — downgrade it to info.
    confident = corr >= 0.35
    pitch_flag = confident and pitch_err > 0.035
    fail = pitch_flag or bad_regions > 0
    pitch_msg = ("pitch n/a (low corr)" if not confident
                 else ("pitch off" if pitch_flag else "pitch ok"))
    print(f"verdict: {'REVIEW' if fail else 'parity ok'} "
          f"({bad_regions}/{len(rep)} regions over {a.tol}pt; {pitch_msg})")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()

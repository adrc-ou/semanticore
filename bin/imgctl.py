#!/usr/bin/env python
"""imgctl.py — image remediation toolkit (PIL+numpy only; works with no ComfyUI).

Subcommands
  measure  IMG                       palette, tonal stats, edge/screen hints (JSON)
  crop     SCAN --x --y --w --h --out NAME   native-res source crop (page coords, pt)
  contact  --src SRC --cand A B C... --rub CLASS --out SHEET --dpi 150
                                     labelled contact sheet for own visual scoring
  score    SRC CAND [CAND...]        objective pre-scores per candidate (JSON):
                                     aspect delta, downscale-SSIM, edge overlap,
                                     histogram distance, Laplacian sharpness ratio
  diffmap  SRC CAND --out            per-region abs-diff PNG (locate failing areas)
  contrast IMG --box x,y,w,h --text-hex RGB   min WCAG ratio of text over region
                                     (samples region luminance; flags <4.5 / <3)
  wrapmap  SCAN --page-box x0,y0,w,h --colx --colw --rows N --out
                                     prints per-line available width by ink-probing
                                     each row (draft wrap numbers to hand-tune)
  ledger   --book DIR --figure ID --class C --chosen F --rounds N --scores JSON
                                     append/refresh IMAGES.md row + storage tally

All numbers are evidence for a human/agent decision made from the contact
sheet; they never auto-accept. See docs/image-remediation.md §5-6.
"""
import argparse, json, os, sys, math
import numpy as np
from PIL import Image


def _lum(img):                      # Rec.709 luma 0..1
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _gray(img):
    return _lum(img)


def _ssim_small(a_img, b_img, win=8):
    """coarse global SSIM-ish on matched-size grayscale (0..1)."""
    a = _gray(a_img); b = _gray(b_img)
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    a = a[:h, :w]; b = b[:h, :w]
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    s1 = (2 * mu_a * mu_b + c1) / (mu_a ** 2 + mu_b ** 2 + c1)
    s2 = (2 * cov + c2) / (va + vb + c2)
    return float(s1 * s2)


def _hist_dist(a_img, b_img):
    ha = np.asarray(a_img.convert("L").resize((256, 256)).histogram(), np.float32)
    hb = np.asarray(b_img.convert("L").resize((256, 256)).histogram(), np.float32)
    ha /= ha.sum() + 1e-9; hb /= hb.sum() + 1e-9
    return float(np.abs(np.cumsum(ha) - np.cumsum(hb)).mean())  # EMD-lite


def _sobel_edge_energy(gray):
    gx = np.zeros_like(gray); gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.hypot(gx, gy)


def _edge_overlap(a_img, b_img, thr=0.18):
    ea = _sobel_edge_energy(_gray(a_img)) > thr * 255
    eb = _sobel_edge_energy(_gray(b_img)) > thr * 255
    h = min(ea.shape[0], eb.shape[0]); w = min(ea.shape[1], eb.shape[1])
    ea = ea[:h, :w]; eb = eb[:h, :w]
    inter = (ea & eb).sum(); union = (ea | eb).sum()
    return float(inter / union) if union else 1.0


def _lap_sharp(gray):
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], np.float32)
    from numpy.lib.stride_tricks import sliding_window_view as swv
    g = (gray * 255.0)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    windows = swv(g, (3, 3))
    resp = (windows * k).sum(axis=(-1, -2))
    return float(resp.var())


def measure(img_path):
    im = Image.open(img_path).convert("RGB")
    g = _gray(im)
    small = im.resize((min(64, im.width), min(64, im.height)))
    q = small.quantize(colors=8, method=2)
    pal = q.getpalette() or []
    counts = q.getcolors(maxcolors=1 << 16) or []
    cols = [tuple(pal[c[1] * 3:c[1] * 3 + 3]) for c in
            sorted(counts, reverse=True)[:8]]
    edges = _sobel_edge_energy(g)
    return dict(size=[im.width, im.height],
                mean_luma=round(float(g.mean()), 3),
                luma_p=[int(np.percentile(g * 255, q)) for q in (5, 50, 95)],
                edge_frac=round(float((edges > 0.18 * 255).mean()), 3),
                palette8=cols[:8])


def cmd_measure(a):
    print(json.dumps(measure(a.img), indent=1))


def cmd_crop(a):
    im = Image.open(a.scan)
    box = (int(a.x), int(a.y), int(a.x + a.w), int(a.y + a.h))
    im.crop(box).save(a.out)
    print("wrote", a.out, box)


def cmd_contact(a):
    pad, labelh = 8, 18
    cands = [a.src] + list(a.cand)
    ims = [Image.open(p).convert("RGB") for p in cands]
    th = a.thumbs
    ims = [im.resize((th, max(1, int(im.height * th / im.width)))) for im in ims]
    W = sum(im.width for im in ims) + pad * (len(ims) + 1)
    H = max(im.height for im in ims) + labelh + 2 * pad
    sheet = Image.new("RGB", (W, H), (30, 30, 30))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    x = pad
    labels = ["SRC"] + [os.path.basename(p)[:14] for p in a.cand]
    for im, lab in zip(ims, labels):
        sheet.paste(im, (x, pad + labelh))
        d.text((x + 2, pad), lab, fill=(230, 230, 120))
        x += im.width + pad
    d.text((pad, H - 16), f"rubric={a.rub}", fill=(150, 220, 150))
    sheet.save(a.out)
    print("contact sheet ->", a.out, sheet.size)


def score(src_path, cand_path):
    src = Image.open(src_path).convert("RGB")
    cand = Image.open(cand_path).convert("RGB")
    ar_s = src.width / src.height
    ar_c = cand.width / cand.height
    cand_rs = cand.resize((src.width, src.height)) if (cand.size != src.size) else cand
    return dict(candidate=os.path.basename(cand_path),
                aspect_delta=round(abs(ar_s - ar_c) / ar_s, 4),
                ssim=round(_ssim_small(src, cand_rs), 4),
                edge_overlap=round(_edge_overlap(src, cand_rs), 4),
                hist_dist=round(_hist_dist(src, cand_rs), 4),
                sharpness_ratio=round(_lap_sharp(_gray(cand_rs)) /
                                      max(_lap_sharp(_gray(src)), 1e-6), 3))


def cmd_score(a):
    print(json.dumps(dict(source=a.src,
                          candidates=[score(a.src, c) for c in a.cand]), indent=1))


def cmd_diffmap(a):
    src = Image.open(a.src).convert("L")
    cand = Image.open(a.cand).convert("L")
    if cand.size != src.size:
        cand = cand.resize(src.size)
    d = np.abs(np.asarray(src, np.int16) - np.asarray(cand, np.int16))
    d = np.clip(d * 3, 0, 255).astype("uint8")
    Image.fromarray(d).save(a.out)
    print("diffmap ->", a.out, "mean abs diff:", round(float(d.mean()), 1))


def cmd_contrast(a):
    im = Image.open(a.img).convert("RGB")
    x, y, w, h = [int(v) for v in a.box.split(",")]
    reg = np.asarray(im.crop((x, y, x + w, y + h)), np.float32) / 255.0
    lum = 0.2126 * reg[..., 0] + 0.7152 * reg[..., 1] + 0.0722 * reg[..., 2]

    def chan_l(c):
        c = max(0.0, min(1.0, c))
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    tx = a.text_hex.lstrip("#")
    tr, tg, tb = (int(tx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    Ltext = chan_l(tr) * .2126 + chan_l(tg) * .7152 + chan_l(tb) * .0722
    worst = 21.0
    for q in (5, 50, 95):
        Lbg = chan_l(float(np.percentile(lum, q)))
        hi, lo = max(Ltext, Lbg), min(Ltext, Lbg)
        worst = min(worst, (hi + .05) / (lo + .05))
    print(json.dumps(dict(min_ratio_over_luma_percentiles=round(worst, 2),
                          AA_body_pass=worst >= 4.5, AA_large_pass=worst >= 3.0,
                          note="sampled bg percentiles; true worst-glyph audit is "
                               "visual (P6). Accessibility wins ties.")))


def cmd_wrapmap(a):
    im = Image.open(a.scan).convert("L")
    a2 = np.asarray(im).astype(np.int32) < 115
    x0, y0, w, h = [int(v) for v in a.page_box.split(",")]
    colx, colw, rows = float(a.colx), float(a.colw), int(a.rows)
    step = h / rows
    out = []
    for r in range(rows):
        ry0 = int(y0 + r * step) + 4
        ry1 = int(y0 + (r + 1) * step) - 4
        band = a2[ry0:ry1, x0:x0 + w]
        cs = band.sum(axis=0)
        nz = np.nonzero(cs >= 1)[0]
        if len(nz) == 0:
            out.append(None); continue
        # widest left ink run => available text width before a right-side figure
        right_text_end = x0 + int(nz.max())
        avail = max(0.0, min(colw, right_text_end - colx))
        out.append(round(avail, 1))
    print(json.dumps(out))


def cmd_ledger(a):
    d = os.path.join(a.book, "IMAGES.md")
    new = not os.path.exists(d)
    with open(d, "a") as f:
        if new:
            f.write("# IMAGE ledger\n\n| figure | class | rounds | chosen | "
                    "scores | storage_kB | notes |\n|---|---|---|---|---|---|---|\n")
        try:
            size = round(os.path.getsize(a.chosen) / 1024) if a.chosen and \
                os.path.exists(a.chosen) else "-"
        except Exception:
            size = "-"
        f.write(f"| {a.figure} | {a.cls} | {a.rounds} | {os.path.basename(a.chosen or '')} | "
                f"{a.scores or ''} | {size} | {(a.notes or '').replace('|','/')} |\n")
    print("ledger row appended ->", d)


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="c", required=True)
    m = sub.add_parser("measure"); m.add_argument("img")
    cr = sub.add_parser("crop"); cr.add_argument("scan"); cr.add_argument("--x",type=int,required=True)
    cr.add_argument("--y",type=int,required=True); cr.add_argument("--w",type=int,required=True)
    cr.add_argument("--h",type=int,required=True); cr.add_argument("--out",required=True)
    ct = sub.add_parser("contact"); ct.add_argument("--src",required=True)
    ct.add_argument("--cand",nargs="+",required=True); ct.add_argument("--rub",default="base")
    ct.add_argument("--out",required=True); ct.add_argument("--thumbs",type=int,default=256)
    sc = sub.add_parser("score"); sc.add_argument("src"); sc.add_argument("cand",nargs="+")
    dm = sub.add_parser("diffmap"); dm.add_argument("src"); dm.add_argument("cand"); dm.add_argument("--out",required=True)
    co = sub.add_parser("contrast"); co.add_argument("img"); co.add_argument("--box",required=True)
    co.add_argument("--text-hex",default="#000000")
    wm = sub.add_parser("wrapmap"); wm.add_argument("scan"); wm.add_argument("--page-box",required=True)
    wm.add_argument("--colx",required=True); wm.add_argument("--colw",required=True); wm.add_argument("--rows",required=True)
    lg = sub.add_parser("ledger"); lg.add_argument("--book",required=True); lg.add_argument("--figure",required=True)
    lg.add_argument("--class",dest="cls",required=True); lg.add_argument("--rounds",default="1")
    lg.add_argument("--chosen"); lg.add_argument("--scores"); lg.add_argument("--notes")
    a = ap.parse_args()
    return {"measure": cmd_measure, "crop": cmd_crop, "contact": cmd_contact,
            "score": cmd_score, "diffmap": cmd_diffmap, "contrast": cmd_contrast,
            "wrapmap": cmd_wrapmap, "ledger": cmd_ledger}[a.c](a)


if __name__ == "__main__":
    sys.exit(main() or 0)

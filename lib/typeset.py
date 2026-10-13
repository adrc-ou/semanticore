"""Reusable forced-line typesetting + tagging engine.

A "book" is a directory:
    book.json           geometry, profile, fonts, output names, first folio
    pages/pNNN.json     {"folio","running_head","side","blocks":[...]}
    out/                built PDFs land here

Block kinds: "para" | "runin-heading" | "list"
Inline markers in block text:
    {B|x} {I|x} {BI|x}      visual style only
    {EM|x}                  italic + PDF 2.0 `Em` role (contrastive stress)
    {STR|x}                 bold + PDF 2.0 `Strong` role (strong importance)
    {E|x|expansion}         Span with /E abbreviation-expansion attribute
`lines` must hold the ORIGINAL visual line breaks; a line ending in "-"
carries a synthetic end-of-line (soft) hyphen.  Assembly asserts that the
logical text and the line table agree, character for character.

Only the calling code decides WHICH marker a run gets (contextual inference
lives in the transcription, not here).
"""
import json
import os
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pdfwriter import Writer, EmbedFont, Elem  # noqa: E402
import pds_bootstrap  # noqa: E402

MARK = re.compile(r"\{(B|I|BI|EM|STR)\|([^{}]*)\}|\{E\|([^{}]*)\|([^{}]*)\}")
STYLE_OF = {"B": "b", "I": "i", "BI": "bi", "EM": "i", "STR": "b"}
ROLE_OF = {"EM": "Em", "STR": "Strong"}
NO_JOIN_END = ("-", "\u2014")     # no space re-added after these at line end


# ----------------------------------------------------------------- parsing
def parse_markup(text):
    """-> (stripped, per-char styles, espans[(a,b,exp)], rspecs[(a,b,role)])"""
    espans, rspecs, out, styled = [], [], [], []
    pos = 0
    for m in MARK.finditer(text):
        if m.start() > pos:
            seg = text[pos:m.start()]
            s0 = sum(map(len, out))
            out.append(seg)
            styled.append(("r", s0, s0 + len(seg)))
        if m.group(2) is not None:
            kind, frag = m.group(1), m.group(2)
            style = STYLE_OF[kind]
            s0 = sum(map(len, out))
            out.append(frag)
            if style != "r":
                styled.append((style, s0, s0 + len(frag)))
            if kind in ROLE_OF:
                rspecs.append((s0, s0 + len(frag), ROLE_OF[kind], {}))
        else:
            frag, exp = m.group(3), m.group(4)
            s0 = sum(map(len, out))
            out.append(frag)
            espans.append((s0, s0 + len(frag), exp))
        pos = m.end()
    if pos < len(text):
        out.append(text[pos:])
    stripped = "".join(out)
    st = ["r"] * len(stripped)
    for style, a, b in styled:
        for i in range(a, min(b, len(st))):
            st[i] = style
    return stripped, st, espans, rspecs


def style_at(st, i):
    return st[i] if 0 <= i < len(st) else "r"


def split_lines(visual, hard=()):
    """visual lines -> (logical lines, soft flags). Re-adds the line-end
    space the original break dropped; strips synthetic hyphens.
    `hard` = line indices whose trailing '-' is a REAL hyphen (compound
    broken at the hyphen): the hyphen stays in the text, no space re-added."""
    logical, soft = [], []
    for li, ln in enumerate(visual):
        last = li == len(visual) - 1
        sf = (not last) and ln.endswith("-") and li not in hard
        core = ln[:-1] if sf else ln
        no_join = (li in hard and ln.endswith("-")) or core.endswith(NO_JOIN_END)
        if not last and not sf and not no_join:
            core += " "
        logical.append(core)
        soft.append(sf)
    return logical, soft


class Block:
    def __init__(self, b, page_idx):
        self.raw = b
        self.id = b.get("id", f"p{page_idx}-blk")
        self.kind = b["kind"]
        self.page = page_idx
        self.heading = b.get("heading")
        self.indent = bool(b.get("indent"))
        if self.kind == "figure":
            for k in ("bbox", "alt", "src"):
                assert k in b, f"{self.id}: figure needs {k}"
            self.bbox = b["bbox"]              # [x, top, w, h] in pt, column-rel
            self.src = b["src"]
            self.alt = b["alt"]
            self.lang = b.get("lang", "en-US")
            self.band = bool(b.get("band", True))   # consume rows? (false=floating side)
            self.artifact = bool(b.get("artifact", False))  # decorative-only
            return
        if self.kind == "list":
            self.items = []
            for it in b["items"]:
                logical, soft = split_lines(it["lines"],
                                            it.get("hard_hyphen_lines", ()))
                assert "".join(logical) == it["text"], self.id
                assert not any(soft), f"hyphen break inside list: {self.id}"
                self.items.append({"visual": it["lines"], "logical": logical})
            return
        visual = b["lines"]
        stripped, st, espans, rspecs = parse_markup(b["text"])
        logical, soft = split_lines(visual, b.get("hard_hyphen_lines", ()))
        off, pos = [], 0
        for lg in logical:
            off.append(pos)
            pos += len(lg)
        joined = "".join(logical)
        if joined != stripped:
            i = 0
            while i < min(len(joined), len(stripped)) and joined[i] == stripped[i]:
                i += 1
            raise SystemExit(
                f"block {self.id}: line table != text at char {i}\n"
                f"  LOGICAL: {joined[max(0, i - 30):i + 40]!r}\n"
                f"  TEXT   : {stripped[max(0, i - 30):i + 40]!r}")
        self.stripped, self.st = stripped, st
        self.ispans = sorted(
            [(a, bb, "E", {"E": exp}) for (a, bb, exp) in espans] +
            [(a, bb, role, attrs) for (a, bb, role, attrs) in rspecs])
        self.visual, self.logical, self.soft, self.off = visual, logical, soft, off
        n = len(visual)
        def _pad(key):
            v = b.get(key)
            return (list(v) + [None] * n)[:n] if v else None
        self.widths = _pad("widths")      # per-line available width (pt) or null
        self.indents = _pad("indents")    # per-line extra left indent (pt) or null
        if self.heading and not visual[0].startswith(self.heading):
            raise SystemExit(f"{self.id}: heading not at line start")


def load_pages(book_dir):
    d = pathlib.Path(book_dir) / "pages"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]


# ------------------------------------------------------------------ engine
class Typesetter:
    def __init__(self, book_dir):
        self.dir = pathlib.Path(book_dir)
        self.book = json.loads((self.dir / "book.json").read_text())
        self.ua_part = int(os.environ.get("UA_PART", self.book.get("profile", 2)))
        g = self.book["geom"]
        self.g = dict(
            PW=float(g.get("pw", 396)), PH=float(g.get("ph", 612)),
            COL=float(g["col"]), V_COLX=float(g["v_colx"]), R_COLX=float(g["r_colx"]),
            HDR_BASE=float(g["hdr_base"]), BODY_BASE0=float(g["body_base0"]),
            PITCH=float(g["pitch"]), INDENT_EM=float(g.get("indent_em", 1.0)),
            BODY_MAX=float(g.get("body_max", 11.6)), BODY_MIN=float(g.get("body_min", 9.0)),
            LIST_WRAP_EM=float(g.get("list_wrap_em", 2.6)),
            LIST_BULLET_EM=float(g.get("list_bullet_em", 3.35)),
            BULLET_TIGHT=float(g.get("bullet_tight", 0.12)))
        try:
            self.root = pds_bootstrap.find_root()
        except SystemExit:
            self.root = None
        self.pages = load_pages(self.dir)
        self.blocks = [Block(b, i) for i, pg in enumerate(self.pages)
                       for b in pg["blocks"]]
        self.w = Writer()
        self.fonts = {}
        self.pages_used_img = set()

    # ---- fonts ----------------------------------------------------------
    def _collect_chars(self):
        chars = set()
        for b in self.blocks:
            if b.kind == "list":
                for it in b.items:
                    chars |= set("".join(it["visual"]))
            elif b.kind == "figure":
                continue          # alts are metadata, not drawn glyphs
            else:
                chars |= set("".join(b.visual))
        for pg in self.pages:
            chars |= set(str(pg.get("folio", ""))) | set(pg.get("running_head") or "")
        chars |= set("\u2022- ")
        return {c for c in chars if ord(c) >= 32}

    def load_fonts(self):
        chars = sorted(self._collect_chars())
        RES = {"r": "/F1", "b": "/F2", "i": "/F3", "bi": "/F4"}
        self.RES = RES
        try:
            wr = pds_bootstrap.find_root()
        except SystemExit:
            wr = None
        for st_key, rel in self.book["fonts"].items():
            p1 = (self.dir / rel).resolve()
            if not p1.exists() and wr is not None:
                p1 = (wr / "books" / "_x" / rel).resolve()   # root-relative fallback
            self.fonts[st_key] = EmbedFont(self.w.pdf, str(p1), RES[st_key][1:], chars)

    def tw(self, text, sty, size):
        return sum(self.fonts[sty].w(c) for c in text) * size / 1000.0

    def line_nat(self, blk, li, size):
        s = blk.off[li]
        e = s + len(blk.logical[li])
        adv = sum(self.fonts[style_at(blk.st, k)].w(blk.stripped[k])
                  for k in range(s, e))
        if blk.soft[li]:
            adv += self.fonts["r"].w("-")
        return adv * size / 1000.0

    def list_line_used(self, li, size):
        g = self.g
        if li == 0:
            return (g["LIST_BULLET_EM"] * size + self.tw("\u2022", "r", size)
                    + g["BULLET_TIGHT"] * size)
        return g["LIST_WRAP_EM"] * size

    # ---- calibration ------------------------------------------------------
    def calibrate(self):
        g = self.g
        size = g["BODY_MAX"]
        for blk in self.blocks:
            if blk.kind == "figure":
                continue
            if blk.kind == "list":
                for it in blk.items:
                    for li, ln in enumerate(it["logical"]):
                        used = self.list_line_used(li, size)
                        nat = self.tw(ln, "r", size)
                        if nat > g["COL"] - used:
                            size = min(size, (g["COL"] - used) / nat * size)
                continue
            for li in range(len(blk.logical)):
                indent = g["INDENT_EM"] * size if (li == 0 and blk.indent) else 0.0
                nat = self.line_nat(blk, li, size)
                if nat > g["COL"] - indent:
                    size = min(size, (g["COL"] - indent) / nat * size)
        size = int(size * 100) / 100.0
        if size < g["BODY_MIN"]:
            raise SystemExit(f"calibration too small: {size}")
        self.size = size
        return size

    # ---- rendering --------------------------------------------------------
    def render(self):
        g = self.g
        self.doc = Elem("Document")
        idx = [self.w.new_page(g["PW"], g["PH"]) for _ in self.pages]
        for pi in idx:
            for st_key in self.fonts:
                self.w.use_font(pi, self.fonts[st_key])
        self.outline_items = []
        self.line_ptr = {pi: 0 for pi in idx}
        self.idx = idx
        self.float_rects = {pi: [] for pi in idx}   # (x0,y0,x1,y1,blk_id) pt, pdf coords
        self._render_headers()          # artifacts first, like the source engine
        for blk in self.blocks:
            pi = idx[blk.page]
            colx = g["V_COLX"] if self.pages[blk.page].get("side", "v") == "v" \
                else g["R_COLX"]
            blk_colx = colx
            if blk.kind in ("para", "runin-heading"):
                self._render_paragraph(blk, pi, blk_colx)
            elif blk.kind == "list":
                self._render_list(blk, pi, blk_colx)
            elif blk.kind == "figure":
                self._render_figure(blk, pi, blk_colx)
            else:
                raise SystemExit(f"block kind not implemented yet: {blk.kind}")
        return self.doc

    def _render_paragraph(self, blk, pi, colx):
        g, RES, SIZE = self.g, self.RES, self.size
        w, fonts, doc = self.w, self.fonts, self.doc
        lines, stripped, st = blk.logical, blk.stripped, blk.st
        spans = blk.ispans
        heading, first = blk.heading, self.line_ptr[pi]
        hw = 0.0
        if heading:
            he = Elem("H1")
            doc.add(he)
            y0 = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"])
            x0 = colx + g["INDENT_EM"] * SIZE
            w.begin(pi, he)
            hw = self.tw(heading + " ", "bi", SIZE)
            w.show(pi, RES["bi"], SIZE, x0, y0, [(heading + " ", 0.0)])
            w.end(pi)
            self.outline_items.append((heading.rstrip("."), he, pi, x0, y0))

        pe = Elem("P")
        doc.add(pe)
        p_state = {"open": False}

        def ensure_p():
            if not p_state["open"]:
                w.begin(pi, pe)
                p_state["open"] = True

        def close_p():
            if p_state["open"]:
                w.end(pi)
                p_state["open"] = False

        for li in range(len(lines)):
            yy = g["PH"] - (g["BODY_BASE0"] + (first + li) * g["PITCH"])
            seg_s = blk.off[li]
            seg_e = seg_s + len(lines[li])
            extra_ind = (blk.indents[li] if blk.indents else 0.0) or 0.0
            indent = (g["INDENT_EM"] * SIZE if (li == 0 and blk.indent) else 0.0) + extra_ind
            x = colx + indent
            i = seg_s
            if li == 0 and heading:
                x += hw
                i = seg_s + len(heading)
                while i < seg_e and stripped[i] == " ":
                    x += fonts["bi"].w(" ") * SIZE / 1000.0
                    i += 1
            rem = stripped[i:seg_e]
            gaps = rem.count(" ")
            nat = sum(fonts[style_at(st, k)].w(stripped[k])
                      for k in range(i, seg_e)) * SIZE / 1000.0
            if blk.soft[li]:
                nat += fonts["r"].w("-") * SIZE / 1000.0
            avail = g["COL"] - indent - (hw if (li == 0 and heading) else 0.0)
            if blk.widths and blk.widths[li]:
                avail = min(avail, blk.widths[li] - extra_ind)
            line_rect = (colx + indent - 1,
                         g["PH"] - (g["BODY_BASE0"] + (first + li) * g["PITCH"]) - 4.5,
                         colx + indent + avail + 1,
                         g["PH"] - (g["BODY_BASE0"] + (first + li) * g["PITCH"]) + 5.5,
                         blk.id)
            self._check_rect(pi, line_rect, blk.id)
            justified = (li != len(lines) - 1) and gaps > 0
            extra_per = max(0.0, (avail - nat) / gaps) if justified else 0.0

            state = {"pieces": [], "font": None, "x0": x}

            def emit_run():
                if state["pieces"]:
                    w.show(pi, state["font"], SIZE, state["x0"], yy, state["pieces"])
                    state["pieces"] = []

            k2 = i
            while k2 < seg_e or (blk.soft[li] and k2 == seg_e):
                if k2 == seg_e:                  # synthetic soft hyphen
                    emit_run()
                    close_p()
                    hsty = style_at(st, k2 - 1) if k2 > seg_s else "r"
                    she = Elem("Span", attrs={"ActualText": "\u00ad"})
                    pe.add(she)
                    w.begin(pi, she)
                    w.show(pi, RES[hsty], SIZE, x, yy, [("-", 0.0)])
                    w.end(pi)
                    x += fonts[hsty].w("-") * SIZE / 1000.0
                    break
                sty = style_at(st, k2)
                fnt = RES[sty]
                sp = next((s0 for s0 in spans
                           if s0[0] <= k2 < s0[1] and (k2 == s0[0] or k2 == seg_s)),
                          None)
                if sp:
                    emit_run()
                    close_p()
                    a, b, kind, attrs = sp
                    if kind == "E":
                        role, ea = "Span", dict(attrs)
                    elif self.ua_part >= 2:
                        role, ea = kind, {"PDF2NS": True}
                    else:
                        role, ea = "Span", {}
                    se = Elem(role, attrs=ea)
                    pe.add(se)
                    frag_end = min(b, seg_e)
                    tx = stripped[k2:frag_end]
                    esty = style_at(st, k2)
                    w.begin(pi, se)
                    w.show(pi, RES[esty], SIZE, x, yy, [(tx, 0.0)])
                    w.end(pi)
                    x += self.tw(tx, esty, SIZE)
                    k2 = frag_end
                    continue
                if stripped[k2] == " ":          # gap left at a span boundary
                    x += fonts[sty].w(" ") * SIZE / 1000.0 + extra_per
                    k2 += 1
                    continue
                b_starts = [s0[0] for s0 in spans if s0[0] > k2]
                stop_at = min(b_starts + [seg_e])
                j = k2
                while j < seg_e and stripped[j] != " " and j < stop_at:
                    j += 1
                word = stripped[k2:j]
                trailing = j < seg_e and stripped[j] == " "
                if trailing:
                    word += " "
                wlen = sum(fonts[style_at(st, q)].w(stripped[q])
                           for q in range(k2, j)) * SIZE / 1000.0
                sp_w = fonts[sty].w(" ") * SIZE / 1000.0 if trailing else 0.0
                if state["font"] is None:
                    ensure_p()
                    state["font"], state["x0"] = fnt, x
                elif state["font"] != fnt:
                    emit_run()
                    state["font"], state["x0"] = fnt, x
                state["pieces"].append((word, 0.0))
                x += wlen + sp_w + (extra_per if trailing else 0.0)
                if trailing:
                    emit_run()
                    state["font"] = None
                if j == k2:
                    raise SystemExit(f"no progress: {lines[li]!r} @{k2}")
                k2 = j if not trailing else j + 1
            emit_run()
            close_p()          # one marked sequence per line (matches engine of record)
        close_p()
        self.line_ptr[pi] = first + len(lines)

    @staticmethod
    def _hit(a, b, tol=0.75):
        return (min(a[2], b[2]) - max(a[0], b[0]) > tol and
                min(a[3], b[3]) - max(a[1], b[1]) > tol)

    def _check_rect(self, pi, rect, who, ignore_live=False):
        for fr in self.float_rects[pi]:
            if fr[4] == who:
                continue
            if self._hit(rect, fr):
                raise SystemExit(
                    f"LAYOUT COLLISION: {who} overlaps {fr[4]} on page {pi+1} "
                    f"(x {max(rect[0], fr[0]):.0f}-{min(rect[2], fr[2]):.0f}pt). "
                    f"Fix the page model: per-line widths/indents must clear "
                    f"floating figures, or move the block.")

    def _render_figure(self, blk, pi, colx):
        import io
        from PIL import Image as PILImage
        g, SIZE = self.g, self.size
        w = self.w
        bx, btop, bw, bh = blk.bbox
        path = (self.dir / blk.src) if not blk.src.startswith("/") else pathlib.Path(blk.src)
        if not path.exists() and self.root is not None:
            alt = (self.root / "books" / "_x" / blk.src).resolve()
            if alt.exists():
                path = alt
            elif (self.root / blk.src).exists():
                path = self.root / blk.src
        im = PILImage.open(path).convert("RGB")
        raw = im.tobytes()
        name = "/Im%d" % (len(self.pages_used_img))
        self.pages_used_img.add((pi, name))
        w.add_image(pi, name[1:], raw, im.width, im.height)
        first = self.line_ptr[pi]
        y1 = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"]) + 2.5
        y0 = y1 - bh
        x0 = colx + bx
        rect = (x0, y0, x0 + bw, y1, blk.id)
        self._check_rect(pi, rect, blk.id)
        if not blk.band:
            self.float_rects[pi].append(rect)
        if blk.artifact:
            w.begin(pi, None, artifact=dict(Type="Layout", Subtype="Decoration",
                                            BBox=[x0, y0, x0 + bw, y1]))
            w.show_image(pi, name[1:], x0, y0, bw, bh)
            w.end(pi)
        else:
            fe = Elem("Figure", attrs={"Alt": blk.alt, "Lang": blk.lang,
                                       "Placement": "Block",
                                       "BBox": [x0, y0, x0 + bw, y1]})
            self.doc.add(fe)
            w.begin(pi, fe)
            w.show_image(pi, name[1:], x0, y0, bw, bh)
            w.end(pi)
        rows = -(-(bh + 4.0) // g["PITCH"]) if blk.band else 0
        self.line_ptr[pi] = first + rows

    def _render_list(self, blk, pi, colx):
        g, RES, SIZE = self.g, self.RES, self.size
        w, doc = self.w, self.doc
        le = Elem("L", attrs={"A": {"O": "List", "ListNumbering": "Disc"}})
        doc.add(le)
        for it in blk.items:
            logical = it["logical"]
            lie = Elem("LI")
            le.add(lie)
            first = self.line_ptr[pi]
            y = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"])
            x_lbl = colx + g["INDENT_EM"] * SIZE if g.get("list_from_indent") \
                else colx + g["LIST_BULLET_EM"] * SIZE
            lb = Elem("Lbl")
            lie.add(lb)
            w.begin(pi, lb)
            w.show(pi, RES["r"], SIZE, x_lbl, y, [("\u2022", 0.0)])
            w.show(pi, RES["r"], SIZE, x_lbl + self.tw("\u2022", "r", SIZE), y,
                   [(" ", 0.0)])
            text_x = x_lbl + self.tw("\u2022", "r", SIZE) + g["BULLET_TIGHT"] * SIZE
            w.end(pi)
            lbody = Elem("LBody")
            lie.add(lbody)
            pe = Elem("P")
            lbody.add(pe)
            w.begin(pi, pe)
            for li, ln in enumerate(logical):
                yy = g["PH"] - (g["BODY_BASE0"] + (first + li) * g["PITCH"])
                indent = (text_x - colx) if li == 0 else g["LIST_WRAP_EM"] * SIZE
                gaps = ln.count(" ")
                nat = self.tw(ln, "r", SIZE)
                avail = g["COL"] - indent
                extra_per = max(0.0, (avail - nat) / gaps) \
                    if (li != len(logical) - 1 and gaps) else 0.0
                xx = colx + indent
                parts = ln.split(" ")
                for n, word in enumerate(parts):
                    tok = word + (" " if n < len(parts) - 1 else "")
                    w.show(pi, RES["r"], SIZE, xx, yy, [(tok, 0.0)])
                    xx += self.tw(tok, "r", SIZE) + (extra_per if tok.endswith(" ") else 0.0)
            w.end(pi)
            self.line_ptr[pi] = first + len(logical)

    def _render_headers(self):
        g, RES, SIZE = self.g, self.RES, self.size
        w = self.w
        hdr_size = min(SIZE * 0.88,
                       (g["COL"] - 18) * 1000.0 /
                       sum(self.fonts["b"].w(c) for c in
                           max((pg.get("running_head") or "" for pg in self.pages),
                               key=len) or " "))
        for n, pg in enumerate(self.pages):
            title, folio = pg.get("running_head"), str(pg.get("folio", ""))
            if not (title or folio):
                continue
            pi = self.idx[n]
            colx = g["V_COLX"] if pg.get("side", "v") == "v" else g["R_COLX"]
            y = g["PH"] - g["HDR_BASE"]
            x0 = colx
            twt = 0.0
            if title:
                twt = self.tw(title, "b", hdr_size)
                x0 = colx + (g["COL"] - twt) / 2.0
            fw = self.tw(folio, "b", hdr_size)
            fx0 = colx if pg.get("side", "v") == "v" else colx + g["COL"] - fw
            fx1 = fx0 + fw
            bbox = [min(x0, fx0) - 4, g["PH"] - g["HDR_BASE"] - hdr_size * 0.8,
                    max(x0 + twt, fx1) + 4, g["PH"] - g["HDR_BASE"] + hdr_size * 0.3]
            w.begin(pi, None, artifact=dict(Type="Pagination",
                                            Subtype="PageHeader",
                                            BBox=bbox, Attached=["Top"]))
            if title:
                w.show(pi, RES["b"], hdr_size, x0, y, [(title, 0.0)])
            if folio:
                w.show(pi, RES["b"], hdr_size, fx0, y, [(folio, 0.0)])
            w.end(pi)

    # ---- save ---------------------------------------------------------------
    def save(self):
        b = self.book
        out_rel = b["output"][str(self.ua_part)] if isinstance(b["output"], dict) \
            else b["output"]
        out = self.dir / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        first_folio = str(self.pages[0].get("folio", "1"))
        labels = None
        if first_folio.isdigit():
            labels = [0, {"S": "D", "St": int(first_folio)}]
        self.w.finalize(str(out), self.doc, b["title"], lang=b.get("lang", "en-US"),
                        producer=b.get("producer", "pds tagged-pdf engine"),
                        creator=b.get("creator", ""),
                        page_labels=labels,
                        outlines=self.outline_items, ua_part=self.ua_part)
        return out


def build_book(book_dir):
    ts = Typesetter(book_dir)
    ts.load_fonts()
    size = ts.calibrate()
    ts.render()
    out = ts.save()
    print(f"[{os.path.basename(str(book_dir))}] ua_part={ts.ua_part} "
          f"body={size:.2f}pt -> {out}")
    return ts


if __name__ == "__main__":
    build_book(sys.argv[1] if len(sys.argv) > 1 else ".")

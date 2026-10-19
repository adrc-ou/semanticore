"""Reusable forced-line typesetting + tagging engine.

A "book" is a directory:
    book.json           geometry, profile, fonts, output names, first folio
    pages/pNNN.json     {"folio","running_head","side","blocks":[...]}
    out/                built PDFs land here

Block kinds: para | runin-heading | heading | list | table |
   columns | figure
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

MARK = re.compile(r"\{(B|I|BI|EM|STR|REF)\|([^{}]*)\}"
                  r"|\{XREF\|([^{}|]*)\|([^{}]*)\}"
                  r"|\{E\|([^{}]*)\|([^{}]*)\}")
STYLE_OF = {"B": "b", "I": "i", "BI": "bi", "EM": "i", "STR": "b", "REF": "r"}
ROLE_OF = {"EM": "Em", "STR": "Strong", "REF": "Reference"}
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
        elif m.group(3) is not None:          # XREF|target|display text
            frag = m.group(4)
            s0 = sum(map(len, out))
            out.append(frag)
            rspecs.append((s0, s0 + len(frag), "Reference",
                           {"xref": m.group(3)}))
        else:
            frag, exp = m.group(5), m.group(6)
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


_ABBR = re.compile(
    r"(?i)\b(?:i\.e|e\.g|cf|vs|etc|pp|vol|no|mr|mrs|dr|st|jr|sr|u\.s|n\.e\.a|"
    r"d\.c|inc|ltd|prof)\.\s+[a-z]")


def _punct_guard(text, bid):
    """Punctuation stuck to a word (',but') can only be a transcription
    artifact; a sentence period before a lowercase word is either a
    grammar-breaking misread or must match the abbreviation list. Both
    abort the build so they are RESOLVED, not shipped (operator ruling
    2026-10-13)."""
    m = re.search(r"[A-Za-z0-9][,;:!?](?=[A-Za-z0-9])", text)
    if m:
        raise SystemExit(
            f"{bid}: punctuation with no following space: "
            f"...{text[max(0, m.start()-18):m.end()+14]!r} — a printed "
            f"comma never fuses to the next word; resolve the speck per "
            f"grammar (usually just a space).")
    for m in re.finditer(r"[A-Za-z]\.(\s+)([a-z])", text):
        lo = max(0, m.start() - 12)
        if re.search(r"(?:[A-Z]\.){1,}[A-Z]\.?$", text[:m.end() - 1].strip()
                     ) or _ABBR.search(text[lo:m.end() + 6]):
            continue        # initialism (T.V., U.S., N.E.A.) or known abbr
        raise SystemExit(
            f"{bid}: sentence-period before lowercase: "
            f"...{text[max(0, m.start()-18):m.end()+16]!r} — verify "
            f"against source: typewriter comma tails degrade to dots; "
            f"grammar usually means ','.")


class Block:
    def __init__(self, b, page_idx):
        self.raw = b
        self.id = b.get("id", f"p{page_idx}-blk")
        self.kind = b["kind"]
        self.page = page_idx
        self.heading = b.get("heading")
        self.indent = bool(b.get("indent"))
        self.size_pt = None
        self.fit = None
        self.tz = 1.0
        if self.kind not in ("para", "runin-heading",
                              "heading", "list", "table", "columns",
                              "figure"):
            raise SystemExit(f"{self.id}: unknown block kind {self.kind!r}"
                             f" (typo? not implemented?)")
        if self.kind == "figure":
            for k in ("bbox", "alt", "src"):
                assert k in b, f"{self.id}: figure needs {k}"
            self.bbox = b["bbox"]              # [x, top, w, h] in pt, column-rel
            self.src = b["src"]
            self.alt = b["alt"]
            self.lang = b.get("lang", "en-US")
            self.band = bool(b.get("band", True))   # consume rows? (false=floating side)
            self.artifact = bool(b.get("artifact", False))  # decorative-only
            self.rows = b.get("grid_rows")     # explicit grid rows consumed
            self.fig_style = b.get("style", "r")
            return
        if self.kind == "heading":
            self.level = int(b.get("level", 1))
            assert 1 <= self.level <= 6, f"{self.id}: heading level 1-6"
            self.style = b.get("style", "b")
            self.align = b.get("align", "left")
            self.size_pt = b.get("size")
            self.lead = b.get("lead")           # per-line baseline pitch pt
            self.rows = b.get("rows")           # explicit grid rows consumed
            stripped, st, espans, rspecs = parse_markup(b["text"])
            if " ".join(b["lines"]) != stripped:
                raise SystemExit(f"{self.id}: heading lines != text")
            self.lines, self.st = b["lines"], st
            pos, lst = 0, []
            for ln in self.lines:
                lst.append(st[pos:pos + len(ln)])
                pos += len(ln) + 1
            self.line_st = lst
            self.heading_text = stripped
            _punct_guard(b["text"], self.id)
            return
        if self.kind == "table":
            for k in ("cols", "rows"):
                assert k in b, f"{self.id}: table needs {k}"
            self.cols = [float(c) for c in b["cols"]]
            self.tsize = float(b.get("cell_size", 7.6))
            self.tpitch = float(b.get("cell_pitch", 9.2))
            self.vpad = float(b.get("cell_vpad", 2.6))
            self.hpad = float(b.get("cell_hpad", 3.2))
            cap = b.get("caption")
            self.cap_lines, self.cap_text = [], None
            if cap:
                stripped, _ = parse_markup(cap["text"])[:2]
                if " ".join(cap["lines"]) != stripped:
                    raise SystemExit(f"{self.id}: caption lines != text")
                self.cap_lines, self.cap_text = cap["lines"], stripped
            self.rows_data = b["rows"]
            self.cell_strip, self.cell_st = [], []
            for ri, r in enumerate(self.rows_data):
                assert len(r) == len(self.cols), f"{self.id}: ragged row"
                sr, st_r = [], []
                for ci, c in enumerate(r):
                    _punct_guard(c["text"], f"{self.id}.r{ri}c{ci}")
                    stripped, st, _, _ = parse_markup(c["text"])
                    if c.get("lines") and " ".join(c["lines"]) != stripped:
                        raise SystemExit(
                            f"{self.id}.r{ri}c{ci}: cell lines != text")
                    sr.append(stripped)
                    st_r.append(st)
                self.cell_strip.append(sr)
                self.cell_st.append(st_r)
            return
        if self.kind == "columns":
            self.colw = [float(v) for v in b["colw"]]
            self.gap = float(b.get("gap", 12.0))
            self.columns = []
            for colblocks in b["columns"]:
                col = []
                for pb in colblocks:
                    _punct_guard(pb["text"], f"{self.id}/{pb.get('id')}")
                    stripped, st, _, _ = parse_markup(pb["text"])
                    if " ".join(pb["lines"]) != stripped:
                        raise SystemExit(f"{self.id}/{pb.get('id')}: lines != text")
                    col.append((pb, stripped, st))
                self.columns.append(col)
            return
        if self.kind == "list":
            self.items = []
            for it in b["items"]:
                logical, soft = split_lines(it["lines"],
                                            it.get("hard_hyphen_lines", ()))
                assert "".join(logical) == it["text"], self.id
                assert not any(soft), f"hyphen break inside list: {self.id}"
                self.items.append({"visual": it["lines"], "logical": logical,
                                   "widths": it.get("widths")})
            self.size_pt = b.get("size")
            return
        visual = b["lines"]
        _punct_guard(b["text"], self.id)
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
        self.gaps = b.get("gaps")         # {line: [space widths pt]} for display lines
        self.indents = _pad("indents")    # per-line extra left indent (pt) or null
        self.size_pt = b.get("size")      # fixed face size (notes, small print)
        self.fit = None                   # resolved at calibration
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
            BULLET_TIGHT=float(g.get("bullet_tight", 0.12)),
            hscale_min=float(g.get("hscale_min", 0.88)))  # legacy key: ignored, Tz forbidden
        try:
            self.root = pds_bootstrap.find_root()
        except SystemExit:
            self.root = None
        self.pages = load_pages(self.dir)
        # global rule: trim leading/trailing blank (block-less) pages from
        # the output; interior blanks are intentional and stay.
        if self.book.get("trim_edge_blanks", True):
            i0 = 0
            while i0 < len(self.pages) - 1 and not self.pages[i0].get("blocks"):
                i0 += 1
            i1 = len(self.pages)
            while i1 > i0 + 1 and not self.pages[i1 - 1].get("blocks"):
                i1 -= 1
            if i0 or i1 < len(self.pages):
                keep = list(range(i0, i1))
                self.pages = [self.pages[i] for i in keep]
        self.note_anchors = {}      # label -> (pi, rect, nlink, elem, back?)
        self.note_kinds = {}        # label -> "footnote"/"endnote"/xref phrase
        self.ref_locs = []          # (label, pi, rect)
        self.xref_labels = set()    # forward-only cross-reference targets
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
            elif b.kind == "heading":
                chars |= set(b.heading_text)
            elif b.kind == "table":
                for r in b.rows_data:
                    for c in r:
                        chars |= set("".join(c["lines"]))
                chars |= set("".join(b.cap_lines))
            elif b.kind == "columns":
                for col in b.columns:
                    for pb, _s, _t in col:
                        chars |= set("".join(pb["lines"]))
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

    def list_line_used(self, blk, li, size):
        g = self.g
        if li == 0:
            if blk.raw.get("numbering") == "arabic":
                if blk.raw.get("tab_em") is not None:
                    return blk.raw["tab_em"] * size
                lbl = "%d." % int(blk.raw.get("numbering_start", 1))
                return (blk.raw.get("bullet_em", g["LIST_BULLET_EM"]) * size
                        + self.tw(lbl, blk.raw.get("item_style", "r"), size)
                        + g["BULLET_TIGHT"] * size)
            marker = blk.raw.get("marker", "\u2022") or ""
            return (blk.raw.get("bullet_em", g["LIST_BULLET_EM"]) * size
                    + self.tw(marker, "r", size)
                    + blk.raw.get("tight", g["BULLET_TIGHT"]) * size)
        return blk.raw.get("wrap_em", g["LIST_WRAP_EM"]) * size

    # ---- calibration ------------------------------------------------------
    def _fit_ratio(self, blk, size):
        """min over lines of avail/natural-width (>=1 means no squeeze)."""
        g = self.g
        worst = float("inf")
        for li in range(len(blk.logical)):
            indent = (g["INDENT_EM"] * size if (li == 0 and blk.indent) else 0.0)
            extra = (blk.indents[li] if blk.indents else 0.0) or 0.0
            avail = g["COL"] - indent - extra
            if blk.widths and blk.widths[li]:
                avail = min(avail, blk.widths[li] - extra)
            nat1 = self.line_nat(blk, li, 1.0)
            if nat1 > 0:
                worst = min(worst, avail / (nat1 * size))
        return worst

    def _calibrate_legacy(self):
        """Original per-line sequential sizing — kept byte-exact for the
        canary fixture. Uniform shrink-to-fit; Tz forcing is forbidden."""
        g = self.g
        size = g["BODY_MAX"]
        for blk in self.blocks:
            if blk.kind in ("figure", "heading", "table", "columns"):
                continue
            if blk.kind == "list":
                isty = blk.raw.get("item_style", "r")
                if blk.size_pt:
                    fit = float(blk.size_pt)
                    for it in blk.items:
                        for li, ln in enumerate(it["logical"]):
                            used = self.list_line_used(blk, li, fit)
                            nat = self.tw(ln, isty, fit)
                            if nat > g["COL"] - used:
                                fit = min(fit, (g["COL"] - used) / nat * fit)
                    blk.fit = int(fit * 100) / 100.0
                    continue
                for it in blk.items:
                    for li, ln in enumerate(it["logical"]):
                        used = self.list_line_used(blk, li, size)
                        nat = self.tw(ln, isty, size)
                        if nat > g["COL"] - used:
                            size = min(size, (g["COL"] - used) / nat * size)
                continue
            if blk.size_pt:
                fit = float(blk.size_pt)
                for li in range(len(blk.logical)):
                    indent = (g["INDENT_EM"] * fit
                              if (li == 0 and blk.indent) else 0.0)
                    extra = (blk.indents[li] if blk.indents else 0.0) or 0.0
                    avail = g["COL"] - indent - extra
                    if blk.widths and blk.widths[li]:
                        avail = min(avail, blk.widths[li] - extra)
                    nat = self.line_nat(blk, li, fit)
                    if nat > avail:
                        fit = min(fit, (avail / nat) * fit)
                blk.fit = int(fit * 100) / 100.0
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

    def calibrate(self):
        # Uniform body size = the largest size at which EVERY line fits its
        # measure at natural glyph width. Horizontal glyph distortion (Tz) to
        # force fit is FORBIDDEN (operator ruling 2026-10-13): adapt measures,
        # never letterforms.
        return self._calibrate_legacy()

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
            elif blk.kind == "heading":
                self._render_heading(blk, pi, blk_colx)
            elif blk.kind == "table":
                self._render_table(blk, pi, blk_colx)
            elif blk.kind == "columns":
                self._render_columns(blk, pi, blk_colx)
            elif blk.kind == "list":
                self._render_list(blk, pi, blk_colx)
            elif blk.kind == "figure":
                self._render_figure(blk, pi, blk_colx)
            else:
                raise SystemExit(f"block kind not implemented yet: {blk.kind}")
        self._emit_note_links()
        return self.doc

    def _rule(self, blk, pi, colx, where, ypt):
        w = self.w
        dx, wdt = blk.raw.get("rule_span", (0.0, self.g["COL"]))
        x0, x1 = colx + float(dx), colx + float(dx) + float(wdt)
        rid = f"{blk.id}#rule-{where}"
        self._check_rect(pi, (x0, ypt - 0.8, x1, ypt + 0.8, rid), rid)
        w.begin(pi, None, artifact=dict(
            Type="Layout", Subtype="Line",
            BBox=[x0, ypt - 1, x1, ypt + 1]))
        w.rule(pi, x0, ypt, x1, ypt, 0.6)
        w.end(pi)

    def _render_heading(self, blk, pi, colx):
        g, RES, SIZE = self.g, self.RES, self.size
        w, doc = self.w, self.doc
        size = float(blk.size_pt) if blk.size_pt \
            else min(SIZE * {1: 1.6, 2: 1.3, 3: 1.12}.get(blk.level, 1.0),
                     SIZE + 6.5)
        lead = float(blk.lead) if blk.lead else size * 1.30
        first = self.line_ptr[pi] + float(blk.raw.get("row_gap", 0))
        x_off = float(blk.raw.get("x_off", 0.0))
        colw_eff = float(blk.raw.get("width", g["COL"]))
        colx = colx + x_off
        he = Elem(f"H{blk.level}")
        doc.add(he)
        base = g["BODY_BASE0"] + first * g["PITCH"]
        if blk.raw.get("rule") == "above":
            lift = blk.raw.get("rule_lift")
            if lift is None:
                lift = (size * 0.8
                        + min(float(blk.raw.get("row_gap", 1.0)), 1.0)
                        * g["PITCH"] * 0.45)
            self._rule(blk, pi, colx, "above", g["PH"] - base + lift)
        for li, ln in enumerate(blk.lines):
            stl = blk.line_st[li]
            gline = (blk.raw.get("gaps") or {}).get(str(li))
            ind = float((blk.raw.get("indents") or [0] * len(blk.lines))[li])
            nat = sum(self.fonts[style_at(stl, k)].w(ch)
                      for k, ch in enumerate(ln)) * size / 1000.0
            if nat > colw_eff - ind + 0.5:
                raise SystemExit(
                    f"{blk.id}: heading line {li!r} too wide ({nat:.0f}pt > "
                    f"{colw_eff - ind:.0f}pt). Widen the measure or reduce the "
                    f"declared size — glyph distortion is forbidden.")
            x = colx + ind if blk.align != "center" \
                else colx + (colw_eff - nat) / 2.0
            ypt = base + li * lead
            yy = g["PH"] - ypt
            rect = (colx + ind - 1, yy - size * 0.33,
                    colx + colw_eff + 1, yy + size * 0.62, blk.id)
            self._check_rect(pi, rect, blk.id)
            w.begin(pi, he)
            gidx = 0
            pos = 0
            words = ln.split(" ")
            for n, word in enumerate(words):
                xx = x
                k = 0
                line_end = n == len(words) - 1
                tail_sp = not (line_end and word.endswith("-"))
                while k < len(word):
                    sty = style_at(stl, pos + k)
                    j = k
                    while j < len(word) and style_at(stl, pos + j) == sty:
                        j += 1
                    seg = word[k:j]
                    disp = seg + (" " if (j == len(word) and tail_sp) else "")
                    w.show(pi, RES[sty], size, xx, yy, [(disp, 0.0)])
                    xx += self.tw(seg, sty, size)
                    k = j
                pos += len(word)
                if n < len(words) - 1:      # the space
                    spw = (float(gline[gidx]) if gline and gidx < len(gline)
                           else self.fonts[style_at(stl, pos)].w(" ")
                           * size / 1000.0)
                    if gline and gidx < len(gline):
                        gidx += 1
                    pos += 1
                    x = xx + spw
            w.end(pi)
        rows = blk.rows if blk.rows else max(
            1, int((len(blk.lines) - 1) * lead / g["PITCH"] + 1.6))
        self.line_ptr[pi] = first + rows
        txt = blk.heading_text
        if blk.level <= 2:
            self.outline_items.append((txt, he, pi, colx, g["PH"] - base))

    def _wrap_cell(self, stripped, st, size, avail):
        """Greedy word-wrap at uniform size; returns [(start,end)] ranges.
        A single word wider than the column is an error, never a squeeze."""
        ranges, n = [], len(stripped)
        i = 0
        while i < n and stripped[i] == " ":
            i += 1
        start = i
        cur_end = i
        while i < n:
            j = i
            while j < n and stripped[j] != " ":
                j += 1
            w0, w1 = i, j
            while w1 < n and stripped[w1] == " ":
                w1 += 1
            width_upto = sum(self.fonts[style_at(st, k)].w(stripped[k])
                             for k in range(start, w0)) * size / 1000.0
            width_word = sum(self.fonts[style_at(st, k)].w(stripped[k])
                             for k in range(w0, w1)) * size / 1000.0
            if w0 == start or width_upto + width_word <= avail + 0.3:
                if width_word > avail + 0.3 and w0 == start:
                    raise SystemExit(
                        "table cell word too wide for column; widen the table")
                cur_end = w1
            else:
                ranges.append((start, cur_end))
                start = w0
                cur_end = w1
            i = max(w1, w0 + 1) if w1 > w0 else n
            if i >= n:
                break
            while i < n and stripped[i] == " ":
                i += 1
        ranges.append((start, cur_end))
        return ranges

    def _render_table(self, blk, pi, colx):
        g, RES = self.g, self.RES
        w, doc = self.w, self.doc
        ts, tp, vp, hp = blk.tsize, blk.tpitch, blk.vpad, blk.hpad
        x_off = float(blk.raw.get("x_off", 0.0))
        colx = colx + x_off
        tw = sum(blk.cols)
        first = self.line_ptr[pi] + float(blk.raw.get("row_gap", 0))
        top0 = g["BODY_BASE0"] + first * g["PITCH"]
        te = Elem("Table", attrs={"Lang": "en-US"})
        doc.add(te)
        y = top0
        if blk.cap_lines:
            ce = Elem("Caption")
            te.add(ce)
            for ln in blk.cap_lines:
                nat = self.tw(ln, "b", ts + 1.6)
                w.begin(pi, ce)
                w.show(pi, RES["b"], ts + 1.6, colx + (tw - nat) / 2.0,
                       g["PH"] - y,
                       [(ln if ln.endswith(" ") else ln + " ", 0.0)])
                w.end(pi)
                y += (ts + 1.6) * 1.5
            y += 2.0
        # pre-wrap every cell at the ONE table size; th cells measure bold
        pre = []
        for ri, r in enumerate(blk.rows_data):
            rowp = []
            for ci, cell in enumerate(r):
                stripped = blk.cell_strip[ri][ci]
                st = blk.cell_st[ri][ci]
                if cell.get("th"):
                    st = ["b"] * len(stripped)
                avail_c = blk.cols[ci] - 2 * hp
                ranges = self._wrap_cell(stripped, st, ts, avail_c)
                for (a, b) in ranges:      # hard overflow guard
                    lw = sum(self.fonts[style_at(st, k)].w(stripped[k])
                             for k in range(a, b)) * ts / 1000.0
                    if lw > avail_c + 0.5:
                        raise SystemExit(
                            f"{blk.id} r{ri}c{ci}: line "
                            f"{stripped[a:b]!r} is {lw:.1f}pt > cell "
                            f"{avail_c:.1f}pt — widen the column; "
                            f"overflow is an accessibility failure")
                rowp.append((ranges, st))
            pre.append(rowp)
        row_h = []
        for ri, r in enumerate(blk.rows_data):
            n = max(len(pre[ri][ci][0]) for ci in range(len(r)))
            row_h.append(n * tp + 2 * vp)
        cap_h = y - top0
        tab_h = sum(row_h)
        rect = (colx - 1, g["PH"] - (y + tab_h) - 1, colx + tw + 1,
                g["PH"] - top0 + 2, blk.id)
        self._check_rect(pi, rect, blk.id)
        xs = [colx]
        for cwv in blk.cols:
            xs.append(xs[-1] + cwv)
        ry = y
        head = any(c.get("th") for c in blk.rows_data[0]) if blk.rows_data else False
        thead = Elem("THead") if head else None
        tbody = Elem("TBody")
        if thead:
            te.add(thead)
        te.add(tbody)
        for ri, r in enumerate(blk.rows_data):
            tre = Elem("TR")
            (thead if (head and ri == 0) else tbody).add(tre)
            for ci, cell in enumerate(r):
                role = "TH" if cell.get("th") else "TD"
                scope = cell.get("scope") or cell.get("header_scope")
                attrs = {}
                if cell.get("th") and scope:
                    attrs["Scope"] = scope
                if cell.get("cid"):
                    attrs["ID"] = cell["cid"]
                if cell.get("cheaders"):
                    attrs["Headers"] = cell["cheaders"]
                ce = Elem(role, attrs=attrs)
                tre.add(ce)
                cx = xs[ci] + hp
                cy = ry + vp + tp * 0.80
                ranges, st_c = pre[ri][ci]
                bold = bool(cell.get("th"))
                w.begin(pi, ce)
                for (a, b) in ranges:
                    xx, k = cx, a
                    while k < b:
                        sty = "b" if bold else style_at(st_c, k)
                        j = k
                        while j < b and ("b" if bold else style_at(st_c, j)) == sty:
                            j += 1
                        seg = blk.cell_strip[ri][ci][k:j]
                        if (j == b and not seg.endswith((" ", "-"))):
                            seg += " "      # real join char for extraction
                        w.show(pi, RES[sty], ts, xx, g["PH"] - cy,
                               [(seg, 0.0)])
                        xx += sum(self.fonts[sty].w(ch)
                                  for ch in seg) * ts / 1000.0
                        k = j
                    cy += tp
                w.end(pi)
            ry += row_h[ri]
        if blk.raw.get("rules", True):
            t0, t1 = y, y + tab_h
            w.begin(pi, None, artifact=dict(
                Type="Layout", Subtype="Decoration",
                BBox=[xs[0] - 1, g["PH"] - t1 - 1, xs[-1] + 1, g["PH"] - t0 + 1]))
            for x in xs:
                w.rule(pi, x, g["PH"] - t1, x, g["PH"] - t0, 0.6)
            w.rule(pi, xs[0], g["PH"] - t0, xs[-1], g["PH"] - t0, 0.6)
            yc = t0
            for hgt in row_h[:-1]:
                yc += hgt
                w.rule(pi, xs[0], g["PH"] - yc, xs[-1], g["PH"] - yc, 0.6)
            w.rule(pi, xs[0], g["PH"] - t1, xs[-1], g["PH"] - t1, 0.6)
            w.end(pi)
        rows = blk.raw.get("grid_rows") or max(
            1, int(-(-(cap_h + tab_h + 6) // g["PITCH"])))
        self.line_ptr[pi] = first + rows
        xa = blk.raw.get("xref_anchor")
        if xa:                       # whole table is a cross-reference target
            phrase = blk.raw.get("xref_phrase", "the table")
            self.note_kinds[xa] = phrase
            self.xref_labels.add(xa)
            t1 = y + tab_h
            self.note_anchors[xa] = (
                pi, (xs[0], g["PH"] - t1, xs[-1], g["PH"] - y),
                None, te, False)     # back=None: forward-only xref

    def _render_paragraph(self, blk, pi, colx):
        w, fonts, doc = self.w, self.fonts, self.doc
        SIZE = blk.fit if getattr(blk, "fit", None) else self.size
        tz = 1.0
        g, RES = self.g, self.RES
        lines, stripped, st = blk.logical, blk.stripped, blk.st
        spans = blk.ispans
        heading = blk.heading
        first = self.line_ptr[pi] + float(blk.raw.get("row_gap", 0))
        x_off = float(blk.raw.get("x_off", 0.0))
        colw_eff = float(blk.raw.get("width", g["COL"]))
        colx = colx + x_off
        hw = 0.0
        if heading:
            he = Elem(f"H{blk.raw.get('level', 1)}")
            doc.add(he)
            y0 = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"])
            x0 = colx + g["INDENT_EM"] * SIZE
            w.begin(pi, he)
            hw = self.tw(heading + " ", "bi", SIZE) * tz
            w.show(pi, RES["bi"], SIZE, x0, y0, [(heading + " ", 0.0)], tz=tz)
            w.end(pi)
            self.outline_items.append((heading.rstrip("."), he, pi, x0, y0))

        if blk.raw.get("rule") == "above":
            lift = blk.raw.get("rule_lift")
            if lift is None:
                gap = float(blk.raw.get("row_gap", 1.0))
                lift = (SIZE * 0.8
                        + min(gap, 1.0) * g["PITCH"] * 0.45)
            self._rule(blk, pi, colx, "above",
                       g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"])
                       + lift)
        role = blk.raw.get("role", "P")
        na = blk.raw.get("note_anchor")
        note_outer = None
        if role == "Note":
            # UA-2/WTPDF: notes are FENote (NoteType=Footnote|Endnote) with
            # Lbl + P children; the raw Note type is forbidden in PDF 2.0.
            # NO /Alt on the container: Alt REPLACES the note text for AT,
            # and Acrobat flags the nested ActualText it traps ("nested
            # alternate text"). Identity comes from role + Lbl + links.
            kind = blk.raw.get("note_kind", "Endnote")
            if self.ua_part >= 2:
                note_outer = Elem("FENote", attrs={
                    "A": {"O": "FENote",
                          "NoteType": "Footnote"
                          if kind.lower().startswith("f") else "Endnote"},
                    "PDF2NS": True})
                pe = Elem("P")      # attached after Lbl in the marker branch
            else:
                # UA-1: Annot is standard in 1.7; keep the simple container
                note_outer = pe = Elem("Annot")
        else:
            pe = Elem(role)
        doc.add(note_outer if note_outer is not None else pe)
        if note_outer is not None and self.ua_part >= 2 and not na:
            note_outer.add(pe)   # with a marker, Lbl+P are attached there
        if na:
            self.note_kinds[na] = blk.raw.get("note_kind", "endnote")
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
            pitch_ = blk.raw.get("pitch", g["PITCH"])
            yy = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"] + li * pitch_)
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
            if na and li == 0:
                seg0 = lines[0]
                if seg0.startswith(str(na) + "."):
                    mword = str(na) + "."
                elif seg0.startswith(str(na)):
                    mword = str(na)
                else:
                    mword = seg0.split(" ", 1)[0]
                nlink = Elem("Link")
                dest_e = pe
                if na and note_outer is not None and self.ua_part >= 2:
                    # marker Link attaches directly to FENote (NO Lbl wrapper:
                    # Acrobat requires Lbl/LBody be children of LI and flags
                    # Lbl-in-FENote). FENote -> Link + P is WTPDF-valid.
                    note_outer.add(nlink)
                    note_outer.add(pe)
                    dest_e = note_outer
                else:
                    pe.add(nlink)
                w.begin(pi, nlink)
                w.show(pi, RES[style_at(st, seg_s)], SIZE, x, yy,
                       [(mword, 0.0)])
                w.end(pi)
                x0n = x
                x += self.tw(mword, style_at(st, seg_s), SIZE)
                self.note_anchors[na] = (
                    pi, (x0n, yy - 3, x + 1.0, yy + SIZE * 0.75),
                    nlink, dest_e, True)
                i += len(mword)
            rem = stripped[i:seg_e]
            gaps = rem.count(" ")
            ref_rng = [(a, b) for (a, b, kd, at) in spans
                       if kd == "Reference" and "xref" not in at]
            nat = sum(
                fonts[style_at(st, k)].w(stripped[k])
                * (0.62 if any(a <= k < b for a, b in ref_rng) else 1.0)
                for k in range(i, seg_e)) * SIZE / 1000.0 * tz
            if blk.soft[li]:
                nat += fonts["r"].w("-") * SIZE / 1000.0 * tz
            avail = colw_eff - indent - (hw if (li == 0 and heading) else 0.0)
            if blk.widths and blk.widths[li]:
                avail = min(avail, blk.widths[li] - extra_ind)
            if blk.raw.get("align") == "center":
                x += max(0.0, (avail - nat) / 2.0)
            line_rect = (x + indent - 1 if False else colx + indent - 1,
                         yy - 4.5,
                         colx + indent + avail + 1,
                         yy + 5.5,
                         blk.id)
            self._check_rect(pi, line_rect, blk.id)
            spread = li in set(blk.raw.get("spread_lines", ()))
            gline = (getattr(blk, "gaps", None) or {}).get(str(li))
            justified = ((li != len(lines) - 1 or spread) and gaps > 0
                         and blk.raw.get("align") not in ("center", "left")
                         and gline is None)
            extra_per = max(0.0, (avail - nat) / gaps) if justified else 0.0
            gidx = 0

            state = {"pieces": [], "font": None, "x0": x}

            def emit_run():
                if state["pieces"]:
                    w.show(pi, state["font"], SIZE, state["x0"], yy,
                           state["pieces"], tz=tz)
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
                    w.show(pi, RES[hsty], SIZE, x, yy, [("-", 0.0)], tz=tz)
                    w.end(pi)
                    x += fonts[hsty].w("-") * SIZE / 1000.0 * tz
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
                    elif kind == "Reference":
                        role, ea = "Reference", {}   # standard 1.x type, both profiles
                    elif self.ua_part >= 2:
                        role, ea = kind, {"PDF2NS": True}
                    else:
                        role, ea = "Span", {}
                    se = Elem(role, attrs=ea)
                    pe.add(se)
                    frag_end = min(b, seg_e)
                    tx = stripped[k2:frag_end]
                    # a block-final span needs the real join toward next block
                    tx_disp = tx + (" " if (frag_end == seg_e
                                            and li == len(lines) - 1) else "")
                    esty = style_at(st, k2)
                    sup = kind == "Reference" and "xref" not in attrs
                    r_size, r_rise = (SIZE * 0.62, SIZE * 0.42) \
                        if sup else (SIZE, 0.0)
                    if kind == "Reference":
                        link_e = Elem("Link")
                        se.add(link_e)
                        w.begin(pi, link_e)
                        self._ref_links(pi, attrs.get("xref", tx), x,
                                        yy + r_rise,
                                        x + self.tw(tx, esty, r_size),
                                        yy + SIZE, se, link_e)
                    else:
                        w.begin(pi, se)
                    w.show(pi, RES[esty], r_size, x, yy + r_rise,
                           [(tx_disp, 0.0)], tz=tz)
                    w.end(pi)
                    x += self.tw(tx, esty, r_size) * tz
                    state["font"] = None     # forces reopen inside P mark
                    k2 = frag_end
                    continue
                if stripped[k2] == " ":          # gap left at a span boundary
                    ensure_p()
                    w.show(pi, RES[sty], SIZE, x, yy, [(" ", 0.0)], tz=tz)
                    x += fonts[sty].w(" ") * SIZE / 1000.0 * tz + extra_per
                    k2 += 1
                    continue
                b_starts = [s0[0] for s0 in spans if s0[0] > k2]
                stop_at = min(b_starts + [seg_e])
                j = k2
                while j < seg_e and stripped[j] != " " and j < stop_at:
                    j += 1
                word = stripped[k2:j]
                trailing = j < seg_e and stripped[j] == " "
                # mid-line joins are real chars (split_lines contract); a
                # block-final line needs a real join toward the next block
                if trailing or (j == seg_e and li == len(lines) - 1):
                    word += " "
                wlen = sum(fonts[style_at(st, q)].w(stripped[q])
                           for q in range(k2, j)) * SIZE / 1000.0 * tz
                sp_w = (fonts[sty].w(" ") * SIZE / 1000.0 * tz
                        if trailing else 0.0)
                if (gline is not None and trailing and gidx < len(gline)
                        and not (na and li == 0 and gidx == 0)):
                    sp_w = float(gline[gidx]); gidx += 1
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
        pitch_ = blk.raw.get("pitch", g["PITCH"])
        if blk.raw.get("rule") == "below":
            self._rule(blk, pi, colx, "below",
                       g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"]
                                  + len(lines) * pitch_) - 3.0)
        if pitch_ == g["PITCH"]:
            self.line_ptr[pi] = first + len(lines)
        else:
            self.line_ptr[pi] = first + len(lines) * pitch_ / g["PITCH"]

    def _ref_links(self, pi, label, x0, y0, x1, y1, ref_e=None, link_e=None):
        self.ref_locs.append((label, pi, (x0, y0 - 1, x1 + 0.5, y1),
                              ref_e, link_e))

    def _note_words(self, label):
        kind = self.note_kinds.get(label, "note")
        if label in getattr(self, "xref_labels", ()):
            return f"Go to {kind}", ""
        return f"Go to {kind} {label}", f"Return to text for {kind} {label}"

    def _emit_note_links(self):
        """Pair {REF|n} marks with their note anchors: forward GoTo on
        each reference, backward GoTo on the note's leading marker —
        the standard accessible footnote navigation pattern (WTPDF:
        Reference <-> FENote, /Ref associations both ways, tagged
        Link annotations with /Contents). {XREF|...} marks link forward
        only (AT "previous location" is the convention for returning
        from a cross-referenced object; note markers get explicit back
        links)."""
        for (label, pi, rect, ref_e, link_e) in self.ref_locs:
            if label not in self.note_anchors:
                raise SystemExit(f"reference {label!r} has no anchor target")
            (npi, nrect, nlink_e, note_e, back) = self.note_anchors[label]
            fwd, backw = self._note_words(label)
            self.w.struct_link(pi, rect, link_e, note_e, npi,
                               nrect[0], nrect[3],
                               label=f"fnref-{label}", contents=fwd)
            if back:
                self.w.struct_link(npi, nrect, nlink_e, ref_e, pi,
                                   rect[0], rect[3],
                                   label=f"fnback-{label}", contents=backw)
            if self.ua_part >= 2:      # WTPDF: Ref entries on both partners
                ref_e.refs.append(note_e)
                note_e.refs.append(ref_e)
        used = {lbl for (lbl, *_rest) in self.ref_locs}
        missing = set(self.note_anchors) - used
        if missing:
            raise SystemExit(f"note anchors with no reference: {missing}")

    @staticmethod
    def _hit(a, b, tol=0.75):
        return (min(a[2], b[2]) - max(a[0], b[0]) > tol and
                min(a[3], b[3]) - max(a[1], b[1]) > tol)

    def _check_rect(self, pi, rect, who, ignore_live=False):
        if rect[1] < 2.0 or rect[3] > self.g["PH"] - 2.0 \
                or rect[0] < -20.0 or rect[2] > self.g["PW"] + 20.0:
            raise SystemExit(
                f"OFF-PAGE: {who} line/box at y {rect[1]:.0f}-{rect[3]:.0f} "
                f"x {rect[0]:.0f}-{rect[2]:.0f} leaves the page; fix the page "
                f"model (block pitch/size), not the guard.")
        for fr in self.float_rects[pi]:          # ALL drawn rects register here
            if fr[4] == who:
                continue
            if self._hit(rect, fr):
                raise SystemExit(
                    f"LAYOUT COLLISION: {who} overlaps {fr[4]} on page {pi+1} "
                    f"(x {max(rect[0], fr[0]):.0f}-{min(rect[2], fr[2]):.0f}pt, "
                    f"y {max(rect[1], fr[1]):.0f}-{min(rect[3], fr[3]):.0f}pt). "
                    f"Occluded text also fails WCAG 1.4.3. Fix the page model: "
                    f"gaps/rows/widths/indents, or move the block.")
        self.float_rects[pi].append(rect)        # register every checked rect

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
        self.line_ptr[pi] += int(float(blk.raw.get("row_gap", 0)))
        im = PILImage.open(path).convert("RGB")
        raw = im.tobytes()
        name = "/Im%d" % (len(self.pages_used_img))
        self.pages_used_img.add((pi, name))
        w.add_image(pi, name[1:], raw, im.width, im.height)
        first = self.line_ptr[pi]
        top = min(btop or 0, 0)   # bbox[1] <0 lifts above flow start; positive
                                  # values stay legacy-ignored (canary bytes)
        y1 = g["PH"] - (g["BODY_BASE0"] + first * g["PITCH"] + top) + 2.5
        y0 = y1 - bh
        x0 = colx + bx
        rect = (x0, y0, x0 + bw, y1, blk.id)
        self._check_rect(pi, rect, blk.id)
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
        if not blk.band:
            rows = 0
        elif blk.rows is not None:
            rows = int(blk.rows)
        else:
            rows = -(-(bh + max(top, 0) + 4.0) // g["PITCH"])
        self.line_ptr[pi] = first + rows

    def _render_columns(self, blk, pi, colx):
        g, RES = self.g, self.RES
        w, doc = self.w, self.doc
        first = self.line_ptr[pi] + int(float(blk.raw.get("row_gap", 0)))
        base_y = g["BODY_BASE0"] + first * g["PITCH"]
        maxh, x = 0.0, colx + float(blk.raw.get("x_off", 0.0))
        for ci, col in enumerate(blk.columns):
            wdt = blk.colw[ci]
            yoff = 0.0
            for pb, para_stripped, para_st in col:
                size = float(pb.get("size", 8.8))
                pitch = float(pb.get("pitch", 9.9))
                pe = Elem("P")
                doc.add(pe)
                if pb.get("space_before"):
                    yoff += pb["space_before"]
                # split para-level style array into per-line arrays using the
                # " ".join mapping that Block validated, so italic spans are
                # correct WITHIN each drawn line (no mid-word flips).
                pos, line_st = 0, []
                for ln in pb["lines"]:
                    line_st.append(para_st[pos:pos + len(ln)])
                    pos += len(ln) + 1
                for li, ln in enumerate(pb["lines"]):
                    stl = line_st[li]
                    yy = g["PH"] - (base_y + yoff)
                    indent = (g["INDENT_EM"] * size
                              if (li == 0 and pb.get("indent")) else 0.0)
                    nat = sum(self.fonts[style_at(stl, k)].w(ch)
                              for k, ch in enumerate(ln)) * size / 1000.0
                    if nat > wdt - indent + 0.5:
                        raise SystemExit(
                            f"{blk.id} line {li!r} too wide for column; widen "
                            f"the column — distortion is forbidden")
                    if pb.get("align") == "center":
                        indent += max(0.0, (wdt - indent - nat) / 2.0)
                    rect = (x + indent - 1, yy - 4.5, x + wdt + 1, yy + 5.5,
                            f"{blk.id}/{pb.get('id','c')}")
                    self._check_rect(pi, rect, f"{blk.id}/{pb.get('id','c')}")
                    w.begin(pi, pe)
                    xx, k = x + indent, 0
                    while k < len(ln):
                        sty = style_at(stl, k)
                        j = k
                        while j < len(ln) and style_at(stl, j) == sty:
                            j += 1
                        run = ln[k:j]
                        if j == len(ln) and not run.endswith((" ", "-")):
                            run += " "      # real join char for extraction
                        w.show(pi, RES[sty], size, xx, yy, [(run, 0.0)])
                        xx += sum(self.fonts[sty].w(ch)
                                  for ch in run) * size / 1000.0
                        k = j
                    w.end(pi)
                    yoff += pitch
            maxh = max(maxh, yoff)
            x += wdt + blk.gap
        self.line_ptr[pi] = first + max(1, int(-(-(maxh + 2.0) // g["PITCH"])))

    def _render_list(self, blk, pi, colx):
        g, RES = self.g, self.RES
        SIZE = blk.fit if getattr(blk, "fit", None) else self.size
        w, doc = self.w, self.doc
        arabic = blk.raw.get("numbering") == "arabic"
        marker = None if arabic else blk.raw.get("marker", "\u2022")
        numbering = "Decimal" if arabic else (
            "Disc" if marker == "\u2022" else ("None" if not marker else "Disc"))
        isty = blk.raw.get("item_style", "r")
        tab = blk.raw.get("tab_em")
        start = int(blk.raw.get("numbering_start", 1))
        # block-local line pitch (default grid pitch) + fractional row_gap
        pitch_ = float(blk.raw.get("pitch", g["PITCH"]))
        rstart = self.line_ptr[pi] + float(blk.raw.get("row_gap", 0))
        self.line_ptr[pi] = rstart
        le = Elem("L", attrs={"A": {"O": "List", "ListNumbering": numbering}})
        doc.add(le)
        offs = 0.0
        for ii, it in enumerate(blk.items):
            logical = it["logical"]
            lie = Elem("LI")
            le.add(lie)
            y0 = g["BODY_BASE0"] + rstart * g["PITCH"] + offs * pitch_
            y = g["PH"] - y0
            b_em = blk.raw.get("bullet_em", g["LIST_BULLET_EM"])
            x_lbl = (colx + g["INDENT_EM"] * SIZE if g.get("list_from_indent")
                     else colx + b_em * SIZE)
            label = f"{start + ii}." if arabic else marker
            if label:
                lb = Elem("Lbl")
                lie.add(lb)
                w.begin(pi, lb)
                if arabic:
                    w.show(pi, RES[isty], SIZE, x_lbl, y, [(label + " ", 0.0)])
                    if tab is not None:
                        text_x = colx + float(tab) * SIZE
                    else:
                        text_x = (x_lbl + self.tw(label, isty, SIZE)
                                  + g["BULLET_TIGHT"] * SIZE)
                else:
                    w.show(pi, RES["r"], SIZE, x_lbl, y, [(marker, 0.0)])
                    w.show(pi, RES["r"], SIZE,
                           x_lbl + self.tw(marker, "r", SIZE),
                           y, [(" ", 0.0)])
                    text_x = (x_lbl + self.tw(marker, "r", SIZE)
                              + g["BULLET_TIGHT"] * SIZE)
                w.end(pi)
            else:
                text_x = x_lbl
            lbody = Elem("LBody")
            lie.add(lbody)
            pe = Elem("P")
            lbody.add(pe)
            w.begin(pi, pe)
            for li, ln in enumerate(logical):
                yy = g["PH"] - (y0 + li * pitch_)
                indent = (text_x - colx) if li == 0 else \
                    blk.raw.get("wrap_em", g["LIST_WRAP_EM"]) * SIZE
                gaps = ln.count(" ")
                nat = self.tw(ln, isty, SIZE)
                avail = g["COL"] - indent
                wi = (it.get("widths") or [None] * len(logical))[li]
                if wi:
                    avail = min(avail, wi)
                if nat > avail + 0.5 and (arabic or marker is None):
                    raise SystemExit(
                        f"{blk.id} item {ii} line {li!r} too wide "
                        f"({nat:.1f} > {avail:.1f}pt) — overflow forbidden")
                extra_per = max(0.0, (avail - nat) / gaps) \
                    if (li != len(logical) - 1 and gaps) else 0.0
                xx = colx + indent
                parts = ln.split(" ")
                for n, word in enumerate(parts):
                    last = n == len(parts) - 1
                    if (last and li < len(logical) - 1
                            and word.endswith(NO_JOIN_END)):
                        tok = word          # hyphen/em-dash join within item
                    else:
                        tok = word + " "
                    w.show(pi, RES[isty], SIZE, xx, yy, [(tok, 0.0)])
                    xx += self.tw(tok, isty, SIZE) + (extra_per if not last else 0.0)  # noqa: E501
            w.end(pi)
            offs += len(logical) + (
                float(blk.raw.get("item_gap", 0))
                if it is not blk.items[-1] else 0.0)
        self.line_ptr[pi] = rstart + offs * pitch_ / g["PITCH"]

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
            if pg.get("folio_place") == "bottom-center" and not title:
                pi = self.idx[n]
                colx = g["V_COLX"] if pg.get("side", "v") == "v" else g["R_COLX"]
                fw = self.tw(folio, "i", hdr_size)
                fx = colx + (g["COL"] - fw) / 2.0
                fy = 18.0
                w.begin(pi, None, artifact=dict(Type="Pagination",
                                                Subtype="PageFooter",
                                                BBox=[fx - 4, fy - hdr_size,
                                                      fx + fw + 4, fy + hdr_size],
                                                Attached=["Bottom"]))
                w.show(pi, RES["i"], hdr_size, fx, fy, [(folio, 0.0)])
                w.end(pi)
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
        labels = None
        runs, prev, unum = [], None, 0
        for i, pg in enumerate(self.pages):
            folio = str(pg.get("folio", ""))
            style = "D" if folio.isdigit() else "r"
            if style != prev:
                runs += [i, {"S": style,
                             "St": int(folio) if style == "D" else unum + 1}]
                prev = style
            if style == "r":
                unum += 1
        if runs:
            labels = runs
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

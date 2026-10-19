"""Minimal hand-built tagged-PDF writer (strict ISO 32000-1, PDF/UA-1 profile)
on top of pikepdf.  The caller composes marked content and a structure tree;
this module embeds fonts, serializes objects and finalizes metadata.
"""
import zlib
import pikepdf
from pikepdf import Dictionary, Array, Name, String, Integer
from fontTools.ttLib import TTFont as FT
from fontTools import subset as ftsubset
from io import BytesIO

NULL = lambda: pikepdf.Object.parse(b"null")


def pdf_text(s: str):
    return String(("\ufeff" + s).encode("utf-16-be"))


def num(v):
    """numeric value for PDF objects: pikepdf serializes int/float natively;
    for content-stream f-strings str(num(x)) is used."""
    v = round(float(v), 3)
    if v == int(v):
        return int(v)
    return v


def hexstr(codes):
    return "<" + "".join(f"{c & 0xFFFF:04X}" for c in codes) + ">"


# ---------------------------------------------------------------- fonts
class EmbedFont:
    """Embed a TTF as Identity-H CIDFontType2 + ToUnicode (subset, GIDs kept)."""

    def __init__(self, pdf, path, res_name, used_chars):
        f = FT(path)
        upem = f["head"].unitsPerEm
        cmap = {chr(u): f.getReverseGlyphMap()[g]
                for u, g in f.getBestCmap().items()}
        miss = sorted(c for c in used_chars if ord(c) > 32 and c not in cmap)
        if miss:
            raise SystemExit(f"{path}: no glyph for {miss!r}")

        opts = ftsubset.Options(retain_gids=True, notdef_outline=True,
                                recalc_bounds=True, glyph_names=False)
        ss = ftsubset.Subsetter(opts)
        ss.populate(text="".join(sorted(used_chars)) + " ")
        ss.subset(f)
        try:
            f["head"].created = f["head"].modified = 0
        except Exception:
            pass
        buf = BytesIO(); f.save(buf, reorderTables=False)
        raw = buf.getvalue()

        order = f.getGlyphOrder()
        metrics = f["hmtx"].metrics
        self.gid = {ch: cmap.get(ch, 0) for ch in used_chars}
        self.adv = {}
        for ch in set(list(self.gid) + [" "] + list(used_chars)):
            g = cmap.get(ch, 0)
            self.adv[ch] = metrics.get(order[g], (0, 0))[0] * 1000.0 / upem

        head, os2, post = f["head"], f["OS/2"], f["post"]
        asc = os2.sTypoAscender or head.ascender
        desc = os2.sTypoDescender or head.descender
        cap = getattr(os2, "sCapHeight", 0) or int(asc * 0.72)
        xh = getattr(os2, "sxHeight", 0) or int(cap * 0.68)
        ita = -float(getattr(post, "italicAngle", 0.0))
        flags = 2 | 32 | (64 if ita else 0)

        ff = pdf.make_stream(zlib.compress(raw, 9))
        ff.Length1 = len(raw)
        ff.Filter = Name("/FlateDecode")

        used_gids = sorted({cmap.get(c, 0) for c in used_chars} | {0})
        warr = Array()
        for g in used_gids:
            warr.append(g)
            warr.append(Array([num(metrics.get(order[g], (0, 0))[0] * 1000.0 / upem)]))

        base = "PDS" + res_name.lstrip("/").upper().replace("-", "") + "+" + \
               str(f["name"].getDebugName(4)).replace(" ", "")
        fd = pdf.make_indirect(Dictionary(
            Type=Name("/FontDescriptor"), FontName=Name("/" + base), Flags=flags,
            FontBBox=Array([num(head.xMin * 1000 / upem), num(head.yMin * 1000 / upem),
                            num(head.xMax * 1000 / upem), num(head.yMax * 1000 / upem)]),
            ItalicAngle=num(ita), Ascent=num(asc * 1000 / upem),
            Descent=num(desc * 1000 / upem), CapHeight=num(cap * 1000 / upem),
            XHeight=num(xh * 1000 / upem), StemV=120 if "bold" in base.lower() else 85,
            FontFile2=ff))
        codes = {}
        for ch in used_chars:
            codes.setdefault(self.gid[ch], ch)
        tus = pdf.make_stream(self._tounicode(codes))
        cid = pdf.make_indirect(Dictionary(
            Type=Name("/Font"), Subtype=Name("/CIDFontType2"), BaseFont=Name("/" + base),
            CIDSystemInfo=Dictionary(Registry="Adobe", Ordering="Identity", Supplement=0),
            FontDescriptor=fd, CIDToGIDMap=Name("/Identity"), DW=500, W=warr))
        self.obj = pdf.make_indirect(Dictionary(
            Type=Name("/Font"), Subtype=Name("/Type0"), BaseFont=Name("/" + base),
            Encoding=Name("/Identity-H"), DescendantFonts=Array([cid]),
            ToUnicode=tus))
        self.res_name = res_name if res_name.startswith("/") else "/" + res_name

    @staticmethod
    def _tounicode(pairs):
        items = sorted((g, ch) for g, ch in pairs.items() if ch != "\x00")
        out = ["/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
               "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
               "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
               "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"]
        for i in range(0, len(items), 90):
            chunk = items[i:i + 90]
            out.append(f"{len(chunk)} beginbfchar\n")
            for g, ch in chunk:
                u = ord(ch)
                if u > 0xFFFF:
                    u1 = 0xD800 + ((u - 0x10000) >> 10)
                    u2 = 0xDC00 + ((u - 0x10000) & 0x3FF)
                    out.append(f"<{g:04X}> <{u1:04X}{u2:04X}>\n")
                else:
                    out.append(f"<{g:04X}> <{u:04X}>\n")
            out.append("endbfchar\n")
        out.append("endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n")
        return "".join(out).encode("ascii")

    def w(self, ch):      # advance in thousandths of em
        return self.adv.get(ch, 0)


# ------------------------------------------------------------- structure
class Elem:
    def __init__(self, role, attrs=None):
        self.role = role
        self.attrs = dict(attrs or {})
        self.k = []          # ordered: Elem children or mcid ints or (page, mcid)
        self.refs = []       # PDF 2.0 /Ref: related structure elements
        self.obj = None
        self.mcid = None

    def add(self, elem):
        self.k.append(elem)

    def mark(self, mcid, page=None):
        self.k.append((page, mcid) if page is not None else mcid)
        self.mcid = mcid


# ---------------------------------------------------------------- writer
class Writer:
    def __init__(self):
        self.pdf = pikepdf.new()
        self.pages = []
        self.all_fonts = []

    def new_page(self, w, h):
        self.pages.append(dict(w=w, h=h, cs=[], fonts={}, images={}, mcid=0,
                               by_mcid={}))
        return len(self.pages) - 1

    def add_image(self, page_idx, name, rgb_bytes, width, height):
        """Embed raw RGB bytes as FlateDecode Image XObject; returns obj."""
        import zlib as _z
        stream = self.pdf.make_stream(_z.compress(rgb_bytes, 9))
        stream.Type = Name("/XObject")
        stream.Subtype = Name("/Image")
        stream.Width = width
        stream.Height = height
        stream.ColorSpace = Name("/DeviceRGB")
        stream.BitsPerComponent = 8
        stream.Filter = Name("/FlateDecode")
        self.pages[page_idx]["images"][name] = stream
        return stream

    def show_image(self, page_idx, name, x, y, w, h):
        """name: bare key as passed to add_image (no slash)."""
        nm = name if name.startswith("/") else "/" + name
        self.pages[page_idx]["cs"].append(
            f"q {num(w)} 0 0 {num(h)} {num(x)} {num(y)} cm {nm} Do Q\n")

    def rule(self, page_idx, x0, y0, x1, y1, width=0.6):
        """Straight stroke in the content stream (table rules, dividers)."""
        self.pages[page_idx]["cs"].append(
            f"{num(width)} w {num(x0)} {num(y0)} m {num(x1)} {num(y1)} l S\n")

    # ---- link annotations (materialized at finalize) ----
    def struct_link(self, page_idx, rect, link_elem, dest_elem, dest_pi,
                    dest_x, dest_y, label=None, contents=None):
        """Register a GoTo link whose visible span is the marked content of
        link_elem (a /Link StructElem, required for PDF/UA link tagging);
        the destination targets dest_elem (structure destination under
        UA-2, page/XYZ under UA-1)."""
        self.pages[page_idx].setdefault("links", []).append(
            (rect, link_elem, dest_elem, dest_pi, dest_x, dest_y,
             label, contents))

    def use_font(self, page_idx, font: EmbedFont):
        self.pages[page_idx]["fonts"][font.res_name] = font
        if font not in self.all_fonts:
            self.all_fonts.append(font)

    # ---- marked content ----
    def begin(self, page_idx, elem=None, role=None, artifact=None):
        p = self.pages[page_idx]
        if artifact is not None:
            parts = ["<<"]
            for key in ("Type", "Subtype"):
                if key in artifact:
                    parts.append(f"/{key} /{artifact[key]}")
            if "BBox" in artifact:
                parts.append("/BBox [" + " ".join(str(num(v)) for v in artifact["BBox"]) + "]")
            if "Attached" in artifact:
                parts.append("/Attached [" + " ".join("/" + a for a in artifact["Attached"]) + "]")
            parts.append(">>")
            p["cs"].append("/Artifact " + "".join(parts) + " BDC\n")
            return None
        role = role or elem.role
        m = p["mcid"]; p["mcid"] += 1
        p["by_mcid"][m] = elem
        elem.mark(m, page_idx)
        props = f"/MCID {m}"
        if "ActualText" in elem.attrs:
            # extraction consumers (copy/paste, reflow) substitute from the
            # BDC property list; StructElem-only is invisible to them.
            at = elem.attrs["ActualText"]
            props += " /ActualText <FEFF" + \
                     "".join(f"{ord(c):04X}" for c in at) + ">"
        p["cs"].append(f"/{role} <<{props}>> BDC\n")
        return m

    def end(self, page_idx):
        self.pages[page_idx]["cs"].append("EMC\n")

    # ---- text ----
    def show(self, page_idx, res_name, size, x, y, pieces, tz=1.0):
        """pieces: list of (text, extra_shift_pt_before) — same font run.
        tz: horizontal text-space scale. Inert in this workshop: gate 6
        forbids glyph distortion, so callers pass 1.0 and no Tz operator
        is ever emitted. Kept as a generic writer arg only."""
        p = self.pages[page_idx]
        font = p["fonts"][res_name]
        items = []
        for sub, sh in pieces:
            if sh:
                items.append(str(num(-sh * 1000.0 / (size * tz))))
            items.append(hexstr([font.gid.get(c, 0) for c in sub]))
        body = ("[" + " ".join(items) + "] TJ") if len(items) > 1 \
            else (items[0] + " Tj")
        tzop = "" if tz == 1.0 else f"{num(tz * 100.0)} Tz "
        p["cs"].append(
            f"BT {font.res_name} {num(size)} Tf {tzop}1 0 0 1 {num(x)} {num(y)} Tm {body} ET\n")

    # ---- finalize ----
    def finalize(self, path, doc_root, title, lang="en-US",
                 producer="pds tagged-pdf builder", creator="",
                 date="D:20261012120000Z", date_x="2026-10-12T12:00:00Z",
                 page_labels=None, outlines=None, ua_part=1):
        pdf = self.pdf
        page_objs = []
        for i, p in enumerate(self.pages):
            fdict = Dictionary()
            for fname, font in p["fonts"].items():
                fdict[Name(fname)] = font.obj

            cs = "".join(p["cs"]).encode("latin-1")
            stream = pdf.make_stream(zlib.compress(cs, 9))
            stream.Filter = Name("/FlateDecode")
            pg = pdf.make_indirect(Dictionary(
                Type=Name("/Page"),
                MediaBox=[0, 0, num(p["w"]), num(p["h"])],
                Resources=Dictionary(Font=pdf.make_indirect(fdict)),
                Tabs=Name("/S"),
                StructParents=i,
                Contents=stream))
            if p["images"]:
                xo = Dictionary()
                for nm, ob in p["images"].items():
                    xo[Name(nm if nm.startswith("/") else "/" + nm)] = ob
                pg.Resources.XObject = pdf.make_indirect(xo)
            p["obj"] = pg
            page_objs.append(pg)



        # ---- structure tree: post-order serialize ----
        pdf2_ns = None
        if ua_part >= 2:
            pdf2_ns = pdf.make_indirect(Dictionary(NS=String(b"http://iso.org/pdf2/ssn")))

        def serialize(e):
            k_arr = Array()
            for item in e.k:
                if isinstance(item, Elem):
                    serialize(item)
                    k_arr.append(item.obj)
                elif isinstance(item, tuple):
                    k_arr.append(Array([item[0], item[1]]))
                else:
                    k_arr.append(item)
            d = Dictionary(Type=Name("/StructElem"), S=Name("/" + e.role))
            child_pg = None
            for item in e.k:
                if isinstance(item, Elem) and item.obj is not None and "/Pg" in item.obj:
                    child_pg = item.obj.Pg
                    break
            if len(e.k) == 1:
                item = e.k[0]
                if isinstance(item, Elem):
                    d.K = item.obj
                elif isinstance(item, tuple):
                    d.K = item[1]                      # plain MCID
                    d.Pg = page_objs[item[0]]
                else:
                    d.K = item
            elif len(e.k) > 1:
                k_arr = Array()
                pages_seen = set()
                for item in e.k:
                    if isinstance(item, Elem):
                        k_arr.append(item.obj)
                    elif isinstance(item, tuple):
                        pages_seen.add(item[0])
                        k_arr.append(item[1] if len(pages_seen) <= 1 else Array([item[0], item[1]]))
                    else:
                        k_arr.append(item)
                d.K = k_arr
                if len(pages_seen) == 1:
                    d.Pg = page_objs[next(iter(pages_seen))]
            if "/Pg" not in d and child_pg is not None and e.role != "Document":
                d.Pg = child_pg
            if e.attrs.get("PDF2NS"):
                d.NS = pdf2_ns
            a_attrs = {}
            for key, val in e.attrs.items():
                if key in ("ActualText", "Alt", "E", "T"):
                    d[Name("/" + key)] = pdf_text(val)
                elif key == "Lang":
                    d.Lang = String(val.encode("ascii"))
                elif key in ("PDF2NS",):
                    pass
                elif key == "Placement":
                    d.Placement = Name("/" + val)
                elif key == "BBox":
                    d.BBox = Array([num(v) for v in val])
                elif key == "ID":
                    d.ID = pdf_text(val)
                elif key == "Summary":
                    d.Summary = pdf_text(val)
                elif key == "Scope":
                    a_attrs["Scope"] = Name("/" + {"col": "Column", "row": "Row",
                                                   "both": "Both", "none": "None"}[val])
                elif key == "Headers":
                    a_attrs["Headers"] = Array([pdf_text(h) for h in val])
                elif key == "A" and isinstance(val, dict):
                    for ak, av in val.items():
                        a_attrs[ak] = (Name("/" + av) if isinstance(av, str)
                                       and not av[0].isdigit() else av)
            if a_attrs:
                a = Dictionary()
                for ak, av in a_attrs.items():
                    a[Name("/" + ak)] = av
                if ("Scope" in a_attrs or "Headers" in a_attrs) and "O" not in a_attrs:
                    a.O = Name("/Table")
                d.A = pdf.make_indirect(a)
            e.obj = pdf.make_indirect(d)
            if e.refs:
                refs_pending.append((d, list(e.refs)))
            for item in e.k:
                if isinstance(item, Elem):
                    item.obj.P = e.obj

        refs_pending = []
        serialize(doc_root)
        for d, targets in refs_pending:   # /Ref after the whole tree exists
            arr = Array()
            for t in targets:
                arr.append(t.obj)
            d.Ref = arr

        # ---- link annotations (need serialized elems + page objs) ----
        next_struct_key = len(self.pages)
        extra_nums = Array()
        for i, p in enumerate(self.pages):
            if not p.get("links"):
                continue
            arr = Array()
            for spec in p["links"]:
                (rect, link_e, dest_e, dpi, dx, dy, label, contents) = spec
                act = Dictionary(
                    S=Name("/GoTo"),
                    D=Array([page_objs[dpi], Name("/XYZ"), num(dx),
                             num(dy), NULL()]))
                if ua_part >= 2:
                    # ISO 14289-2 8.8 requires a structure destination (/SD);
                    # keep /D too so every viewer can follow the jump.
                    act.SD = Array([dest_e.obj, Name("/XYZ"), num(dx),
                                    num(dy), NULL()])
                if link_e.obj is not None:
                    link_e.obj.A = act      # /Link StructElem carries /A
                d = Dictionary(Type=Name("/Annot"), Subtype=Name("/Link"),
                               Rect=[num(v) for v in rect],
                               Border=Array([0, 0, 0]), A=act)
                if link_e.obj is not None:
                    # dedicated ParentTree key resolving straight to the
                    # /Link StructElem (veraPDF/PDFUA annotation lookups)
                    extra_nums.append(Integer(next_struct_key))
                    extra_nums.append(link_e.obj)
                    d[Name("/StructParent")] = Integer(next_struct_key)
                    next_struct_key += 1
                if label:
                    d[Name("/NM")] = String(label)
                if contents:
                    d[Name("/Contents")] = String(contents)
                arr.append(pdf.make_indirect(d))
            p["obj"].Annots = arr

        nums = Array()
        for i, p in enumerate(self.pages):
            arr = Array()
            for m in range(p["mcid"]):
                el = p["by_mcid"].get(m)
                arr.append(el.obj if el else NULL())
            nums.append(i)
            nums.append(arr)
        for k in extra_nums:      # annotation struct keys (sorted after pages)
            nums.append(k)
        parent_tree = Dictionary(Nums=nums)
        stru = pdf.make_indirect(Dictionary(
            Type=Name("/StructTreeRoot"), K=doc_root.obj,
            ParentTree=pdf.make_indirect(parent_tree),
            ParentTreeNextKey=next_struct_key))
        # ISO 32000-1 Table 344: the /P of the root element of the hierarchy
        # shall be the structure tree root object itself.
        if doc_root.obj is not None:
            doc_root.obj.P = stru
        # ISO 32000-2 14.7.4 / ISO 14289-2 8.2.5.2: the Document element
        # carries the PDF 2.0 default structure namespace (indirect dict).
        if ua_part >= 2 and doc_root.obj is not None:
            nsd = pdf.make_indirect(Dictionary(
                NS=String(b"http://iso.org/pdf2/ssn")))
            doc_root.obj.NS = nsd

        # ---- pages tree ----
        pages = pdf.make_indirect(Dictionary(
            Type=Name("/Pages"),
            MediaBox=[0, 0, num(self.pages[0]["w"]), num(self.pages[0]["h"])],
            Kids=Array(page_objs), Count=len(page_objs)))
        for pg in page_objs:
            pg.Parent = pages

        catalog = pdf.Root
        catalog.Type = Name("/Catalog")
        catalog.Pages = pages
        catalog.MarkInfo = Dictionary(Marked=True)
        catalog.StructTreeRoot = stru
        catalog.Lang = String(lang.encode("ascii"))
        catalog.ViewerPreferences = Dictionary(DisplayDocTitle=True)
        if page_labels:
            conv = Array()
            for item in page_labels:
                if isinstance(item, dict):
                    d2 = Dictionary()
                    for k, v in item.items():
                        kn = k if k.startswith("/") else "/" + k
                        if k in ("S",):
                            d2[Name(kn)] = Name(v if v.startswith("/") else "/" + v)
                        else:
                            d2[Name(kn)] = v
                    item = d2
                conv.append(item)
            catalog.PageLabels = Dictionary(Nums=conv)
        if outlines:
            objs = []
            ol = pdf.make_indirect(Dictionary(Type=Name("/Outlines"), Count=len(outlines)))
            # outline entries: (title, Elem, page_idx, x, y)
            for t, elem, pg_idx, x, y in outlines:
                if ua_part >= 2:
                    # ISO 14289-2 8.8: destinations inside the document shall
                    # be structure destinations: [ <StructElem> /XYZ ... ]
                    target = elem.obj
                else:
                    target = page_objs[pg_idx]
                o = pdf.make_indirect(Dictionary(
                    Title=pdf_text(t), Parent=ol, Dest=Array(
                        [target, Name("/XYZ"), num(x), num(y), NULL()])))
                objs.append(o)
            for i, o in enumerate(objs):
                if i:
                    o.Prev = objs[i - 1]
                if i < len(objs) - 1:
                    o.Next = objs[i + 1]
            ol.First = objs[0]
            ol.Last = objs[-1]
            catalog.Outlines = ol

        # ---- document metadata ----
        di = pdf.docinfo
        for k in list(di.keys()):
            del di[k]
        di.Title = pdf_text(title)
        di.Producer = String(producer.encode("ascii"))
        if creator:
            di.Creator = String(creator.encode("ascii"))
        di.CreationDate = String(date.encode("ascii"))
        di.ModDate = String(date.encode("ascii"))
        xmp = self._xmp(title, lang, producer, date_x, ua_part)
        ms = pdf.make_stream(xmp.encode("utf-8"))
        ms.Type = Name("/Metadata")
        ms.Subtype = Name("/XML")
        catalog.Metadata = ms
        if ua_part >= 2:
            # PDF 2.0 deprecates the legacy date format; XMP is canonical
            iso = date_x
            di.CreationDate = String(iso.encode("ascii"))
            di.ModDate = String(iso.encode("ascii"))
            pdf.save(path, static_id=True, force_version="2.0",
                     object_stream_mode=pikepdf.ObjectStreamMode.disable,
                     fix_metadata_version=False)
        else:
            pdf.save(path, static_id=True,
                     object_stream_mode=pikepdf.ObjectStreamMode.disable,
                     fix_metadata_version=False)

    @staticmethod
    def _xmp(title, lang, producer, mddate, ua_part=1):
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t, pr = esc(title), esc(producer)
        return (
            '<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n <rdf:RDF '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '  <rdf:Description rdf:about="" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">' + t +
            '</rdf:li><rdf:li xml:lang="en-US">' + t + '</rdf:li></rdf:Alt></dc:title>\n'
            '   <dc:language><rdf:Seq><rdf:li>' + lang +
            '</rdf:li></rdf:Seq></dc:language>\n'
            '  </rdf:Description>\n'
            '  <rdf:Description rdf:about="" '
            'xmlns:pdf="http://ns.adobe.com/pdf/1.3/">\n'
            '   <pdf:Producer>' + pr + '</pdf:Producer>\n'
            '   <pdf:Version>' + ('2.0' if ua_part >= 2 else '1.7') + '</pdf:Version>\n'
            '  </rdf:Description>\n'
            '  <rdf:Description rdf:about="" '
            'xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">\n'
            '   <pdfuaid:part>' + str(ua_part) + '</pdfuaid:part>\n' +
            ('   <pdfuaid:rev>2024</pdfuaid:rev>\n' if ua_part >= 2 else '') +
            '  </rdf:Description>\n' +
            '  <rdf:Description rdf:about="" '
            'xmlns:xmp="http://ns.adobe.com/xap/1.0/">\n'
            '   <xmp:MetadataDate>' + mddate + '</xmp:MetadataDate>\n'
            '   <xmp:ModifyDate>' + mddate + '</xmp:ModifyDate>\n'
            '  </rdf:Description>\n'
            ' </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end="w"?>')

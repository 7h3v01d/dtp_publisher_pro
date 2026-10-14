# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""OpenDocument Drawing (.odg) → Document.

LibreOffice reads Publisher files (via libmspub) and writes them as ODG; this
module rebuilds editable pages from that: text frames with their fonts and
paragraph formatting, pictures (including old WMF/EMF ones), vector shapes,
lines, groups and page backgrounds.

libmspub has one big quirk: every box of a linked Publisher story is given the
*whole* story.  Boxes that carry identical text are therefore re-linked into a
real chain, so the story flows instead of repeating.
"""

from __future__ import annotations

import math
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QPainterPath, QTextBlockFormat,
                         QTextCharFormat, QTextCursor, QTextListFormat, QTransform)

from .. import limits
from ..document import Document
from ..geometry import Geo, normalize_angle, rotate_vec
from ..items import BaseItem, GroupItem, ImageItem, PathItem, ShapeItem, TextItem
from ..items.image import encode_image, prepare_image_bytes
from ..items.path import parse_svg_path, path_to_svg
from .metafile import metafile_to_image

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "loext": "urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0",
}
_REV = {v: k for k, v in NS.items()}
MAX_DEPTH = 64
MAX_LENGTH_PT = 100_000.0          # about 35 m: far beyond any page


def q(name: str) -> str:
    p, n = name.split(":")
    return "{%s}%s" % (NS[p], n)


def short(tag: str) -> str:
    if tag.startswith("{"):
        ns, local = tag[1:].split("}")
        return f"{_REV.get(ns, ns)}:{local}"
    return tag


_LEN = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(cm|mm|in|pt|pc|px|%)?\s*$")
_UNIT = {"cm": 72 / 2.54, "mm": 72 / 25.4, "in": 72.0, "pt": 1.0, "pc": 12.0, "px": 0.75,
         None: 1.0}


def length(v: Optional[str]) -> Optional[float]:
    if not v:
        return None
    m = _LEN.match(v)
    if not m or m.group(2) == "%":
        return None
    x = float(m.group(1)) * _UNIT[m.group(2)]
    if not math.isfinite(x):
        return None
    return max(-MAX_LENGTH_PT, min(x, MAX_LENGTH_PT))     # 1e30mm must not reach Qt


def percent(v: Optional[str]) -> Optional[float]:
    if v and v.strip().endswith("%"):
        try:
            return float(v.strip()[:-1]) / 100.0
        except ValueError:
            return None
    return None


def angle_deg(v: str) -> float:
    """ODF angles: '30deg', '0.5rad', '33grad', or a bare number in tenths of a degree."""
    m = re.match(r"^\s*([-+]?\d*\.?\d+)\s*(deg|rad|grad)?\s*$", v or "")
    if not m:
        return 0.0
    x = float(m.group(1))
    unit = m.group(2)
    if unit == "rad":
        return math.degrees(x)
    if unit == "grad":
        return x * 0.9
    if unit == "deg":
        return x
    return x / 10.0


def color(v: Optional[str]) -> Optional[QColor]:
    if not v or v == "transparent":
        return None
    c = QColor(v)
    return c if c.isValid() else None


class _CountingBuilder(ET.TreeBuilder):
    def __init__(self, limit: int):
        super().__init__()
        self.limit, self.n = limit, 0

    def start(self, tag, attrs):
        self.n += 1
        if self.n > self.limit:
            raise limits.TooBig("The publication has too many parts to open.")
        return super().start(tag, attrs)


# ═════════════════════════════════════════════════════════════════════════════
class Styles:
    def __init__(self, roots: List[ET.Element]):
        self.styles: Dict[Tuple[str, str], ET.Element] = {}
        self.defaults: Dict[str, ET.Element] = {}
        self.fonts: Dict[str, str] = {}
        self.fill_images: Dict[str, str] = {}
        self.gradients: Dict[str, dict] = {}
        self.layouts: Dict[str, Tuple[float, float]] = {}
        self.masters: Dict[str, Tuple[str, ET.Element]] = {}
        self.list_styles: Dict[str, str] = {}
        self.opacities: Dict[str, float] = {}
        for root in roots:
            for e in root.iter():
                t = short(e.tag)
                if t == "style:style":
                    self.styles[(e.get(q("style:family"), ""), e.get(q("style:name"), ""))] = e
                elif t == "style:default-style":
                    self.defaults[e.get(q("style:family"), "")] = e
                elif t == "style:font-face":
                    fam = (e.get(q("svg:font-family")) or e.get(q("style:name")) or "")
                    self.fonts[e.get(q("style:name"), "")] = fam.strip("'\"")
                elif t == "draw:fill-image":
                    self.fill_images[e.get(q("draw:name"), "")] = e.get(q("xlink:href"), "")
                elif t == "draw:gradient":
                        self.gradients[e.get(q("draw:name"), "")] = {
                        "start": e.get(q("draw:start-color")), "end": e.get(q("draw:end-color")),
                        "angle": angle_deg(e.get(q("draw:angle"), "0")),
                        "style": e.get(q("draw:style"), "linear")}
                elif t == "draw:opacity":
                    a = percent(e.get(q("draw:start"))) or 1.0
                    b = percent(e.get(q("draw:end"))) or 1.0
                    self.opacities[e.get(q("draw:name"), "")] = (a + b) / 2
                elif t == "style:page-layout":
                    pp = e.find(q("style:page-layout-properties"))
                    if pp is not None:
                        w, h = length(pp.get(q("fo:page-width"))), length(pp.get(q("fo:page-height")))
                        if w and h:
                            self.layouts[e.get(q("style:name"), "")] = (w, h)
                elif t == "style:master-page":
                    self.masters[e.get(q("style:name"), "")] = (
                        e.get(q("style:page-layout-name"), ""), e)
                elif t == "text:list-style":
                    numbered = e.find(q("text:list-level-style-number")) is not None
                    bullet = e.find(q("text:list-level-style-bullet")) is not None
                    self.list_styles[e.get(q("style:name"), "")] = (
                        "number" if numbered and not bullet else "bullet")

    def props(self, family: str, name: Optional[str], kind: str) -> Dict[str, str]:
        """Merged attributes of ``kind`` (e.g. 'style:text-properties') with inheritance."""
        chain = []
        seen = set()
        while name and (family, name) in self.styles and name not in seen:
            seen.add(name)
            e = self.styles[(family, name)]
            chain.append(e)
            name = e.get(q("style:parent-style-name"))
        out: Dict[str, str] = {}
        d = self.defaults.get(family)
        if d is not None:
            pe = d.find(q(kind))
            if pe is not None:
                out.update({short(k): v for k, v in pe.attrib.items()})
        for e in reversed(chain):
            pe = e.find(q(kind))
            if pe is not None:
                out.update({short(k): v for k, v in pe.attrib.items()})
        return out


# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class ImportReport:
    pages: int = 0
    texts: int = 0
    pictures: int = 0
    shapes: int = 0
    stories: int = 0
    warnings: List[str] = field(default_factory=list)

    def warn(self, msg: str):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def summary(self) -> str:
        parts = [f"{self.pages} page{'s' * (self.pages != 1)}",
                 f"{self.texts} text box{'es' * (self.texts != 1)}",
                 f"{self.pictures} picture{'s' * (self.pictures != 1)}",
                 f"{self.shapes} shape{'s' * (self.shapes != 1)}"]
        s = ", ".join(parts)
        if self.stories:
            s += (f"; {self.stories} linked stor{'ies' if self.stories != 1 else 'y'} "
                  "re-connected so the text flows from box to box")
        return s


class OdgImporter:
    def __init__(self, odg_path: str, report: Optional[ImportReport] = None):
        self.report = report or ImportReport()
        self.zip = zipfile.ZipFile(odg_path)
        if len(self.zip.infolist()) > limits.MAX_ODG_ENTRIES:
            raise limits.TooBig("The converted file has too many parts to open.")
        self._picture_bytes = 0          # uncompressed bytes read so far (budget)
        self._page_path_chars = 0        # drawing detail on the current page (budget)
        self._objects = 0
        self.content = self._xml("content.xml")
        styles_root = self._xml("styles.xml", required=False)
        roots = [r for r in (styles_root, self.content) if r is not None]
        self.styles = Styles(roots)
        self._images: Dict[str, Optional[Tuple[bytes, str, QImage]]] = {}
        self._frames: List[Tuple[TextItem, int, float, float]] = []

    def _xml(self, name: str, required: bool = True) -> Optional[ET.Element]:
        try:
            info = self.zip.getinfo(name)
        except KeyError:
            if required:
                raise ValueError(f"The converted file has no {name}.")
            return None
        if info.file_size > limits.MAX_ODG_XML_BYTES:
            raise limits.TooBig("The publication is too large to open.")
        # streamed into a counting tree builder, so an element limit stops a runaway
        # file before the tree gets big; the size is re-checked as bytes arrive
        parser = ET.XMLParser(target=_CountingBuilder(limits.MAX_XML_ELEMENTS))
        got = 0
        with self.zip.open(info) as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                got += len(chunk)
                if got > limits.MAX_ODG_XML_BYTES:
                    raise limits.TooBig("The publication is too large to open.")
                parser.feed(chunk)
        return parser.close()

    def _read_member(self, name: str) -> bytes:
        """Read an embedded file within the per-picture and whole-file budgets."""
        info = self.zip.getinfo(name)              # KeyError if missing
        left = limits.MAX_ODG_TOTAL_PICTURE_BYTES - self._picture_bytes
        cap = min(limits.MAX_ODG_PICTURE_BYTES, left)
        if info.file_size > cap:
            raise limits.TooBig(name)
        out = bytearray()
        with self.zip.open(info) as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                out += chunk
                if len(out) > cap:                 # a header that under-states its size
                    raise limits.TooBig(name)
        self._picture_bytes += len(out)
        return bytes(out)

    # ── document ─────────────────────────────────────────────────────────────
    def build(self) -> Document:
        doc = Document()
        body = self.content.find(q("office:body"))
        drawing = body.find(q("office:drawing")) if body is not None else None
        pages = list(drawing.iter(q("draw:page"))) if drawing is not None else []
        if len(pages) > limits.MAX_PAGES:
            raise limits.TooBig(f"This publication has {len(pages):,} pages; DTP Publisher "
                                f"can open up to {limits.MAX_PAGES:,}.")
        for i, page in enumerate(pages):
            master = page.get(q("draw:master-page-name"), "")
            layout = self.styles.masters.get(master, ("", None))[0]
            w, h = self.styles.layouts.get(layout, (595.276, 841.89))
            sc = doc.make_page(w, h, margins=[min(36.0, w / 10, h / 10)] * 4)
            bg = self._page_background(page)
            if bg is not None:
                st = sc.setup_state()
                st["background"] = bg.name(QColor.NameFormat.HexArgb)
                sc.apply_setup(st)
            doc.add_page(sc)
            self._page_path_chars = 0
            z = 1.0
            master_el = self.styles.masters.get(master, ("", None))[1]
            sources = ([(c, True) for c in master_el] if master_el is not None else []) + \
                      [(c, False) for c in page]
            for child, from_master in sources:
                item = self._element(child, i, 0)
                if item is None:
                    continue
                if from_master:
                    item.name = item.name or "Background (from master page)"
                    item.set_prop("locked", True)
                item.setZValue(z)
                z += 1
                sc.addItem(item)
        if not doc.pages:
            doc.add_page(doc.make_page())
        from ..items.path import limit_page_drawings
        blocked = sum(limit_page_drawings(sc.all_design_items()) for sc in doc.pages)
        if blocked:
            self.report.warn(f"{blocked} very detailed drawing(s) are shown as boxes, "
                             "because drawing them would make the program very slow.")
        self.report.pages = len(doc.pages)
        for sc in doc.pages:
            self._set_wrapping(sc)
        self._relink_stories()
        self.zip.close()
        return doc

    @staticmethod
    def _set_wrapping(sc) -> None:
        """Publisher flows text round pictures and text boxes in front of it.  The
        wrap settings don't survive LibreOffice's conversion, so: pictures and text
        boxes wrap ("Square") unless they mostly cover a text box behind them (then
        they were decoration, set to "None" in Publisher), and anything from the
        master page never wraps."""
        from PyQt6.QtCore import Qt as _Qt
        order = {id(i): n for n, i in enumerate(sc.items(_Qt.SortOrder.DescendingOrder))}
        items = [i for i in sc.all_design_items() if i.KIND in ("image", "text")]
        texts = [i for i in items if i.KIND == "text"]
        for it in items:
            if it.locked:                      # master-page background
                it.wrap = "none"
                continue
            box = it.scene_box()
            covers = False
            for t in texts:
                if t is it or order.get(id(t), 0) <= order.get(id(it), 0):
                    continue                    # only boxes *behind* this one count
                tb = t.scene_box()
                inter = box.intersected(tb)
                area = max(tb.width() * tb.height(), 1e-6)
                if inter.width() * inter.height() > 0.6 * area:
                    covers = True
                    break
            it.wrap = "none" if covers else "square"

    def _page_background(self, page: ET.Element) -> Optional[QColor]:
        gp = self.styles.props("drawing-page", page.get(q("draw:style-name")),
                               "style:drawing-page-properties")
        if gp.get("draw:fill") == "solid":
            return color(gp.get("draw:fill-color"))
        return None

    # ── elements ─────────────────────────────────────────────────────────────
    def _element(self, e: ET.Element, page_idx: int, depth: int) -> Optional[BaseItem]:
        if depth > MAX_DEPTH:
            return None
        self._objects += 1
        if self._objects > limits.MAX_OBJECTS:
            raise limits.TooBig(f"This publication has more than {limits.MAX_OBJECTS:,} "
                                "objects, which is more than DTP Publisher can safely open.")
        t = short(e.tag)
        try:
            if t == "draw:g":
                return self._group(e, page_idx, depth)
            if t == "draw:frame":
                return self._frame(e, page_idx)
            if t in ("draw:polygon", "draw:polyline", "draw:path", "draw:rect",
                     "draw:ellipse", "draw:circle", "draw:line", "draw:connector",
                     "draw:custom-shape"):
                return self._shape(e, t)
        except limits.TooBig:
            raise
        except (ValueError, TypeError, ZeroDivisionError) as ex:
            self.report.warn(f"Skipped an object that could not be read ({t}: {ex}).")
            return None
        if t not in ("office:forms", "draw:layer-set", "presentation:notes", "svg:title",
                     "svg:desc", "office:event-listeners", "loext:theme"):
            self.report.warn(f"Skipped an unsupported object ({t}).")
        return None

    def _group(self, e, page_idx, depth) -> Optional[BaseItem]:
        kids = [k for k in (self._element(c, page_idx, depth + 1) for c in e) if k is not None]
        if not kids:
            return None
        if len(kids) == 1:
            return kids[0]
        for z, k in enumerate(kids):
            k.setZValue(z + 1)
        g = GroupItem()
        g.adopt(kids)
        return g

    def _geo(self, e) -> Tuple[float, float, float, float, float]:
        """x, y, w, h, rotation (our convention: clockwise degrees about the centre)."""
        w = max(length(e.get(q("svg:width"))) or 0.0, 0.0)
        h = max(length(e.get(q("svg:height"))) or 0.0, 0.0)
        x = length(e.get(q("svg:x"))) or 0.0
        y = length(e.get(q("svg:y"))) or 0.0
        tr = e.get(q("draw:transform"))
        rot = 0.0
        if tr:
            ang, tx, ty = 0.0, 0.0, 0.0
            m = re.search(r"rotate\s*\(\s*([-+0-9.eE]+)\s*\)", tr)
            if m:
                ang = float(m.group(1))
            m = re.search(r"translate\s*\(\s*([^ )]+)\s+([^ )]+)\s*\)", tr)
            if m:
                tx, ty = length(m.group(1)) or 0.0, length(m.group(2)) or 0.0
            # ODF: rotate(a) is counter-clockwise on the page, about the shape's
            # top-left, then translated.  Our items rotate clockwise about the centre.
            deg = -math.degrees(ang)
            cx, cy = rotate_vec(w / 2 + x, h / 2 + y, deg)
            cx, cy = cx + tx, cy + ty
            x, y, rot = cx - w / 2, cy - h / 2, normalize_angle(deg)
        return x, y, w, h, rot

    # graphic style → fill / stroke
    def _graphic(self, e) -> Dict[str, str]:
        return self.styles.props("graphic", e.get(q("draw:style-name")),
                                 "style:graphic-properties")

    def _apply_line_fill(self, it: BaseItem, gp: Dict[str, str], closed: bool = True):
        fill = gp.get("draw:fill", "none") if closed else "none"
        op = percent(gp.get("draw:opacity"))
        if op is None and gp.get("draw:opacity-name") in self.styles.opacities:
            op = self.styles.opacities[gp["draw:opacity-name"]]
        if fill == "solid":
            c = color(gp.get("draw:fill-color")) or QColor("#729fcf")
            if op is not None:
                c.setAlphaF(max(0.0, min(op, 1.0)))
            it.fill = c
        elif fill == "gradient":
            g = self.styles.gradients.get(gp.get("draw:fill-gradient-name", ""), {})
            c1 = color(g.get("start")) or QColor("#ffffff")
            c2 = color(g.get("end")) or QColor("#cccccc")
            if op is not None:
                c1.setAlphaF(max(0.0, min(op, 1.0)))
                c2.setAlphaF(max(0.0, min(op, 1.0)))
            it.fill = c1
            if isinstance(it, PathItem):
                it.fill2 = c2
                # ODF: angle 0 runs top → bottom, increasing counter-clockwise
                it.grad_angle = g.get("angle", 0.0) - 90.0
            else:
                # solid stand-in halfway between the two colours
                it.fill = QColor((c1.red() + c2.red()) // 2, (c1.green() + c2.green()) // 2,
                                 (c1.blue() + c2.blue()) // 2, c1.alpha())
        elif fill == "hatch":
            it.fill = color(gp.get("draw:fill-color")) or QColor(0, 0, 0, 0)
        else:
            it.fill = QColor(0, 0, 0, 0)
        stroke = gp.get("draw:stroke", "solid")
        if stroke == "none":
            it.stroke_width = 0.0
        else:
            it.stroke = color(gp.get("svg:stroke-color")) or QColor("#000000")
            sop = percent(gp.get("svg:stroke-opacity"))
            if sop is not None:
                it.stroke.setAlphaF(max(0.0, min(sop, 1.0)))
            sw = length(gp.get("svg:stroke-width"))
            it.stroke_width = sw if sw and sw > 0 else 0.5      # 0 = hairline
            it.stroke_style = "dash" if stroke == "dash" else "solid"

    # ── shapes ───────────────────────────────────────────────────────────────
    def _shape(self, e, t: str) -> Optional[BaseItem]:
        gp = self._graphic(e)
        if t in ("draw:line", "draw:connector"):
            x1, y1 = length(e.get(q("svg:x1"))) or 0.0, length(e.get(q("svg:y1"))) or 0.0
            x2, y2 = length(e.get(q("svg:x2"))) or 0.0, length(e.get(q("svg:y2"))) or 0.0
            box = QRectF(min(x1, x2), min(y1, y2), max(abs(x2 - x1), 0.01), max(abs(y2 - y1), 0.01))
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
            return self._path_item(path, box, gp, closed=False, rot=0.0)
        x, y, w, h, rot = self._geo(e)
        if w <= 0 and h <= 0:
            return None
        w, h = max(w, 0.01), max(h, 0.01)
        if gp.get("draw:fill") == "bitmap":
            return self._bitmap_fill(e, gp, x, y, w, h, rot)
        if t in ("draw:rect", "draw:ellipse", "draw:circle") and gp.get("draw:fill") == "gradient":
            path = QPainterPath()
            if t == "draw:rect":
                path.addRect(QRectF(0, 0, 1, 1))
            else:
                path.addEllipse(QRectF(0, 0, 1, 1))
            it = PathItem(w, h, path_to_svg(path))
            self._apply_line_fill(it, gp)
            it.set_geometry(Geo(x, y, w, h, rot))
            self.report.shapes += 1
            return it
        if t in ("draw:rect", "draw:ellipse", "draw:circle"):
            kind = "rect" if t == "draw:rect" else "ellipse"
            radius = length(e.get(q("draw:corner-radius"))) or 0.0
            s = ShapeItem(w, h, "rounded" if radius > 0 else kind)
            s.radius = radius
            self._apply_line_fill(s, gp)
            s.set_geometry(Geo(x, y, w, h, rot))
            self.report.shapes += 1
            return s
        if t == "draw:custom-shape":
            return self._custom_shape(e, gp, x, y, w, h, rot)
        vb = [float(v) for v in (e.get(q("svg:viewBox")) or f"0 0 {w} {h}").split()[:4]]
        if len(vb) < 4 or vb[2] == 0 or vb[3] == 0:
            vb = [0.0, 0.0, max(vb[2] if len(vb) > 2 else 1.0, 1.0),
                  max(vb[3] if len(vb) > 3 else 1.0, 1.0)]
        path = QPainterPath()
        closed = t != "draw:polyline"
        if t in ("draw:polygon", "draw:polyline"):
            pts = []
            for pair in (e.get(q("draw:points")) or "").split():
                a, _, b = pair.partition(",")
                pts.append(QPointF(float(a), float(b)))
            if not pts:
                return None
            if (t == "draw:polygon" and self._is_box(pts, vb)
                    and gp.get("draw:fill") != "gradient"):
                s = ShapeItem(w, h, "rect")
                self._apply_line_fill(s, gp)
                s.set_geometry(Geo(x, y, w, h, rot))
                self.report.shapes += 1
                return s
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            if closed:
                path.closeSubpath()
        else:
            path = parse_svg_path(e.get(q("svg:d")) or "")
            if path.isEmpty():
                return None
            closed = any(c in (e.get(q("svg:d")) or "") for c in "zZ")
        # viewBox → unit box
        tr = QTransform()
        tr.scale(1 / vb[2], 1 / vb[3])
        tr.translate(-vb[0], -vb[1])
        it = PathItem(w, h, path_to_svg(tr.map(path)))
        it.closed = closed
        self._apply_line_fill(it, gp, closed)
        it.set_geometry(Geo(x, y, w, h, rot))
        self.report.shapes += 1
        return it

    @staticmethod
    def _is_box(pts: List[QPointF], vb: List[float]) -> bool:
        if len(pts) not in (4, 5):
            return False
        xs = sorted({round(p.x(), 3) for p in pts})
        ys = sorted({round(p.y(), 3) for p in pts})
        return len(xs) == 2 and len(ys) == 2

    def _path_item(self, path: QPainterPath, box: QRectF, gp, closed: bool,
                   rot: float) -> PathItem:
        tr = QTransform()
        tr.scale(1 / box.width(), 1 / box.height())
        tr.translate(-box.left(), -box.top())
        d = path_to_svg(tr.map(path))
        if (len(d) > limits.MAX_PATH_CHARS
                or self._page_path_chars + len(d) > limits.MAX_PAGE_PATH_CHARS):
            raise limits.TooBig("a drawing too detailed to show")
        self._page_path_chars += len(d)
        it = PathItem(box.width(), box.height(), d)
        it.closed = closed
        self._apply_line_fill(it, gp, closed)
        it.set_geometry(Geo(box.left(), box.top(), box.width(), box.height(), rot))
        self.report.shapes += 1
        return it

    _CUSTOM = {"rectangle": "rect", "round-rectangle": "rounded", "ellipse": "ellipse",
               "circle": "ellipse", "isosceles-triangle": "triangle", "diamond": "diamond",
               "pentagon": "pentagon", "hexagon": "hexagon", "star5": "star",
               "right-arrow": "arrow", "heart": "heart"}

    def _custom_shape(self, e, gp, x, y, w, h, rot) -> Optional[BaseItem]:
        geom = e.find(q("draw:enhanced-geometry"))
        typ = geom.get(q("draw:type"), "") if geom is not None else ""
        kind = self._CUSTOM.get(typ)
        if kind is None:
            self.report.warn("Some decorative shapes were simplified to rectangles.")
            kind = "rect"
        s = ShapeItem(w, h, kind)
        self._apply_line_fill(s, gp)
        s.set_geometry(Geo(x, y, w, h, rot))
        self.report.shapes += 1
        text = "".join(e.itertext()).strip()
        if text:
            t = TextItem(w, h)
            t.document.clear()
            self._fill_text(t, e, e.get(q("draw:style-name")))
            t.valign = "middle"
            t.set_geometry(Geo(x, y, w, h, rot))
            g = GroupItem()
            s.setZValue(1)
            t.setZValue(2)
            g.adopt([s, t])
            self.report.texts += 1
            return g
        return s

    # ── pictures ─────────────────────────────────────────────────────────────
    def _picture(self, href: str) -> Optional[Tuple[bytes, str, QImage]]:
        if href in self._images:
            return self._images[href]
        res = None
        try:
            raw = self._read_member(href.lstrip("./"))
        except KeyError:
            raw = b""
        except limits.TooBig:
            raw = b""
            self.report.warn("Some pictures were too big to open; empty picture frames "
                             "were left in their place.")
        if raw:
            ext = os.path.splitext(href)[1].lower()
            if ext in (".wmf", ".emf", ".svm") or raw[:4] in (b"\xd7\xcd\xc6\x9a",
                                                              b"\x01\x00\x00\x00"):
                img, kind = metafile_to_image(raw)
                if img is not None:
                    data, fmt = encode_image(img)
                    res = prepare_image_bytes(data) or (data, fmt, img)
                else:
                    self.report.warn("Some drawings in an old picture format could not be "
                                     "converted; empty picture frames were left in their place.")
            else:
                res = prepare_image_bytes(raw)
                if res is None:
                    self.report.warn("Some pictures could not be read; empty picture frames "
                                     "were left in their place.")
        self._images[href] = res
        return res

    def _image_item(self, href: str, x, y, w, h, rot) -> ImageItem:
        im = ImageItem(w, h)
        im.fit_mode = "stretch"
        res = self._picture(href)
        if res is not None:
            data, fmt, img = res
            im.set_image_data(data, fmt, os.path.basename(href), img)
        im.set_geometry(Geo(x, y, w, h, rot))
        self.report.pictures += 1
        return im

    def _bitmap_fill(self, e, gp, x, y, w, h, rot) -> ImageItem:
        href = self.styles.fill_images.get(gp.get("draw:fill-image-name", ""), "")
        im = self._image_item(href, x, y, w, h, rot)
        if gp.get("draw:stroke", "none") != "none":
            sw = length(gp.get("svg:stroke-width"))
            im.stroke = color(gp.get("svg:stroke-color")) or QColor("#000000")
            im.stroke_width = sw if sw and sw > 0 else 0.5
        return im

    # ── frames (text / image / object) ──────────────────────────────────────
    def _frame(self, e, page_idx: int) -> Optional[BaseItem]:
        x, y, w, h, rot = self._geo(e)
        gp = self._graphic(e)
        tb = e.find(q("draw:text-box"))
        if tb is not None:
            minh = length(gp.get("fo:min-height")) or length(tb.get(q("fo:min-height")))
            t = TextItem(max(w, 1.0), max(h, 1.0))
            t.document.clear()
            t.padding = min(length(gp.get("fo:padding-left") or gp.get("fo:padding")) or 0.0,
                            30.0)
            t.valign = {"middle": "middle", "bottom": "bottom"}.get(
                gp.get("draw:textarea-vertical-align", "top"), "top")
            self._apply_line_fill(t, gp)
            if t.stroke_width > 0 and gp.get("draw:stroke", "none") == "none":
                t.stroke_width = 0.0
            self._fill_text(t, tb, e.get(q("draw:style-name")))
            t.fit = "none"
            t.set_geometry(Geo(x, y, max(w, 1.0), max(h, 1.0), rot))
            # LibreOffice grows boxes to fit their text (for linked boxes, the whole
            # duplicated story); Publisher's real box size is the minimum height,
            # which is restored for boxes that turn out to be linked
            t._publisher_h = minh if minh and 0 < minh < h else None
            self._frames.append((t, page_idx, x, y))
            self.report.texts += 1
            return t
        img = e.find(q("draw:image"))
        if img is not None and img.get(q("xlink:href")):
            return self._image_item(img.get(q("xlink:href")), x, y, w, h, rot)
        for tag in ("draw:object", "draw:object-ole"):
            if e.find(q(tag)) is not None:
                self.report.warn("An embedded object could not be imported.")
                return None
        return None

    # ── text ─────────────────────────────────────────────────────────────────
    def _char_format(self, props: Dict[str, str], base: QTextCharFormat) -> QTextCharFormat:
        f = QTextCharFormat(base)
        fam = None
        if props.get("style:font-name"):
            fam = self.styles.fonts.get(props["style:font-name"], props["style:font-name"])
        elif props.get("fo:font-family"):
            fam = props["fo:font-family"].split(",")[0].strip("'\" ")
        if fam:
            f.setFontFamilies([fam])
        fs = props.get("fo:font-size")
        if fs:
            pc = percent(fs)
            cur = base.fontPointSize() or 12.0
            size = cur * pc if pc is not None else length(fs)
            if size and size > 0:
                f.setFontPointSize(max(1.0, min(size, 1600.0)))
        fw = props.get("fo:font-weight")
        if fw:
            if fw == "bold":
                f.setFontWeight(QFont.Weight.Bold.value)
            elif fw == "normal":
                f.setFontWeight(QFont.Weight.Normal.value)
            elif fw.isdigit():
                f.setFontWeight(max(100, min(int(fw), 900)))
        if props.get("fo:font-style"):
            f.setFontItalic(props["fo:font-style"] in ("italic", "oblique"))
        if props.get("style:text-underline-style"):
            f.setFontUnderline(props["style:text-underline-style"] != "none")
        if props.get("style:text-line-through-style"):
            f.setFontStrikeOut(props["style:text-line-through-style"] != "none")
        c = color(props.get("fo:color"))
        if c is not None and props.get("style:use-window-font-color") != "true":
            f.setForeground(QBrush(c))
        elif props.get("style:use-window-font-color") == "true" and c is None:
            f.setForeground(QBrush(QColor("#000000")))
        bg = color(props.get("fo:background-color"))
        if bg is not None:
            f.setBackground(QBrush(bg))
        pos = props.get("style:text-position", "")
        if pos.startswith("super") or pos.startswith("33%"):
            f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        elif pos.startswith("sub") or pos.startswith("-33%"):
            f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
        if props.get("fo:text-transform") == "uppercase":
            f.setFontCapitalization(QFont.Capitalization.AllUppercase)
        elif props.get("fo:font-variant") == "small-caps":
            f.setFontCapitalization(QFont.Capitalization.SmallCaps)
        ls = length(props.get("fo:letter-spacing"))
        if ls:
            f.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
            f.setFontLetterSpacing(ls)
        return f

    def _block_format(self, props: Dict[str, str]) -> QTextBlockFormat:
        bf = QTextBlockFormat()
        al = props.get("fo:text-align", "start")
        bf.setAlignment({"center": Qt.AlignmentFlag.AlignHCenter,
                         "end": Qt.AlignmentFlag.AlignRight,
                         "right": Qt.AlignmentFlag.AlignRight,
                         "justify": Qt.AlignmentFlag.AlignJustify}.get(al, Qt.AlignmentFlag.AlignLeft))
        for key, setter in (("fo:margin-top", bf.setTopMargin),
                            ("fo:margin-bottom", bf.setBottomMargin),
                            ("fo:margin-left", bf.setLeftMargin),
                            ("fo:margin-right", bf.setRightMargin),
                            ("fo:text-indent", bf.setTextIndent)):
            v = length(props.get(key))
            if v:
                setter(round(v))              # Qt HTML stores whole units
        lh = props.get("fo:line-height")
        pc = percent(lh)
        if pc is not None:
            bf.setLineHeight(pc * 100, 1)      # proportional
        elif length(lh):
            bf.setLineHeight(length(lh), 2)    # fixed
        elif length(props.get("style:line-height-at-least")):
            bf.setLineHeight(length(props["style:line-height-at-least"]), 3)
        elif length(props.get("style:line-spacing")):
            bf.setLineHeight(length(props["style:line-spacing"]), 4)
        bg = color(props.get("fo:background-color"))
        if bg is not None:
            bf.setBackground(QBrush(bg))
        return bf

    def _fill_text(self, t: TextItem, container: ET.Element, style_name: Optional[str]):
        base = QTextCharFormat()
        base.setFontPointSize(12.0)
        base.setForeground(QBrush(QColor("#000000")))
        # text in a shape inherits the shape's graphic style text properties
        frame_text = self.styles.props("graphic", style_name, "style:text-properties")
        base = self._char_format(frame_text, base)
        doc = t.document
        cur = QTextCursor(doc)
        state = {"first": True}

        def paragraph(p: ET.Element, list_kind: Optional[str]):
            sname = p.get(q("text:style-name"))
            pprops = self.styles.props("paragraph", sname, "style:paragraph-properties")
            tprops = self.styles.props("paragraph", sname, "style:text-properties")
            cf = self._char_format(tprops, base)
            bf = self._block_format(pprops)
            if state["first"]:
                cur.setBlockFormat(bf)
                cur.setBlockCharFormat(cf)
                state["first"] = False
            else:
                cur.insertBlock(bf, cf)
            if list_kind:
                lf = QTextListFormat()
                lf.setStyle(QTextListFormat.Style.ListDecimal if list_kind == "number"
                            else QTextListFormat.Style.ListDisc)
                lf.setIndent(1)
                cur.createList(lf)
            inline(p, cf, 0)

        def inline(el: ET.Element, cf: QTextCharFormat, depth: int):
            if depth > MAX_DEPTH:
                return
            if el.text:
                cur.insertText(el.text, cf)
            for c in el:
                tag = short(c.tag)
                if tag == "text:span":
                    props = self.styles.props("text", c.get(q("text:style-name")),
                                              "style:text-properties")
                    inline(c, self._char_format(props, cf), depth + 1)
                elif tag == "text:s":
                    try:
                        n = max(1, min(int(c.get(q("text:c"), "1")), 200))
                    except ValueError:
                        n = 1
                    cur.insertText(" " * n, cf)
                elif tag == "text:tab":
                    cur.insertText("\t", cf)
                elif tag == "text:line-break":
                    cur.insertText(" ", cf)
                elif tag in ("text:a", "text:bookmark", "text:span"):
                    inline(c, cf, depth + 1)
                elif tag in ("text:page-number",):
                    cur.insertText(c.text or "#", cf)
                elif tag.startswith("text:") and (c.text or len(c)):
                    inline(c, cf, depth + 1)
                if c.tail:
                    cur.insertText(c.tail, cf)

        def walk(el: ET.Element, list_kind: Optional[str], depth: int):
            if depth > MAX_DEPTH:
                return
            for c in el:
                tag = short(c.tag)
                if tag in ("text:p", "text:h"):
                    paragraph(c, list_kind)
                elif tag == "text:list":
                    kind = self.styles.list_styles.get(c.get(q("text:style-name"), ""),
                                                       list_kind or "bullet")
                    walk(c, kind, depth + 1)
                elif tag in ("text:list-item", "text:list-header", "text:section"):
                    walk(c, list_kind, depth + 1)

        walk(container, None, 0)
        # drop the empty trailing paragraphs Publisher leaves at the end of stories
        while doc.blockCount() > 1 and not doc.lastBlock().text().strip():
            c = QTextCursor(doc.lastBlock())
            c.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
            c.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()

    # ── linked stories ───────────────────────────────────────────────────────
    def _relink_stories(self):
        from ..textflow import deferred_layout
        with deferred_layout(lambda: [t for t, *_ in self._frames]):
            self._relink_stories_now()

    def _relink_stories_now(self):
        from ..textflow import connect
        groups: Dict[str, List[Tuple[TextItem, int, float, float]]] = {}
        for entry in self._frames:
            text = entry[0].plain_text().strip()
            if len(text) >= 20:
                groups.setdefault(text, []).append(entry)
        chains: List[List[Tuple[TextItem, int, float, float]]] = []
        singles: List[Tuple[TextItem, int, float, float]] = []
        for frames in groups.values():
            if len(frames) < 2:
                singles.extend(frames)
                continue
            # reading order: page, then column (left to right), then top to bottom
            frames.sort(key=self._reading_key)
            prev = frames[0][0]
            for t, *_ in frames[1:]:
                t.document.clear()
                connect(prev, t, merge_text=False)
                prev = t
            chains.append(frames)
            self.report.stories += 1
        self._join_continuations(chains, singles)
        for frames in chains:
            for t, *_ in frames:
                ph = getattr(t, "_publisher_h", None)
                if ph:
                    g = t.geometry()
                    t.set_geometry(g._replace(h=ph))

    @staticmethod
    def _reading_key(f):
        return (f[1], round(f[2] / 28.35), f[3])

    def _join_continuations(self, chains, singles):
        """A story that stops mid-sentence and a box on the same page that starts
        mid-sentence, after it in reading order, are one story (libmspub sometimes
        splits a linked story like this)."""
        from ..textflow import connect
        stories = chains + [[s] for s in singles]
        used = set()
        enders = ('.', '!', '?', '"', '\u201d', "'", ')', ':')
        for story in sorted(stories, key=lambda st: self._reading_key(st[0])):
            head = story[0][0]
            if id(head) in used:
                continue
            text = head.document.toPlainText().rstrip()
            if len(text) < 150 or text.endswith(enders):
                continue
            last = story[-1]
            best = None
            for cand in singles:
                t = cand[0]
                if t is head or id(t) in used or t.link_prev is not None or t.is_linked():
                    continue
                first = t.plain_text().lstrip()[:1]
                if not first.islower() or cand[1] != last[1]:
                    continue
                if abs(t.w - last[0].w) > 0.1 * max(t.w, last[0].w):   # same column width
                    continue
                if self._reading_key(cand) <= self._reading_key(last):
                    continue
                if best is None or self._reading_key(cand) < self._reading_key(best):
                    best = cand
            if best is None:
                continue
            t = best[0]
            c = QTextCursor(head.document)
            c.movePosition(QTextCursor.MoveOperation.End)
            frag = QTextCursor(t.document)
            frag.select(QTextCursor.SelectionType.Document)
            c.insertFragment(frag.selection())        # same paragraph: mid-sentence
            t.document.clear()
            connect(last[0], t, merge_text=False)
            used.add(id(t))
            was_single = len(story) == 1
            story.append(best)
            if was_single:
                chains.append(story)
                self.report.stories += 1


def import_odg(path: str) -> Tuple[Document, ImportReport]:
    rep = ImportReport()
    doc = OdgImporter(path, rep).build()
    return doc, rep

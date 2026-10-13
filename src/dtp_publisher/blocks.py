# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Building blocks: ready-made headers, footers, quotes, coupons, fields…"""

from __future__ import annotations

from typing import List

from PyQt6.QtGui import QColor

from .geometry import Geo
from .items import BaseItem, ShapeItem, TextItem
from .scene import PageScene
from .units import mm

BLOCKS = {
    "header": "Heading Band",
    "footer": "Footer",
    "story": "Heading and story",
    "quote": "Pull quote",
    "sidebar": "Sidebar box",
    "coupon": "Coupon",
    "pagenum": "Page number",
    "date": "Today's date",
}

ACCENT = QColor("#1f3864")
GROUPED = {"coupon": "Coupon"}      # blocks inserted as a single group


def _text(w, h, text, size=12.0, bold=False, italic=False, color="#201f1e", align="left",
          family="Calibri", fit="none", valign="top") -> TextItem:
    t = TextItem(w, h)
    t.set_text(text, family, size, bold, italic, QColor(color), align)
    t.fit, t.valign = fit, valign
    t.refit()
    return t


def make_block(kind: str, sc: PageScene) -> List[BaseItem]:
    """Create (not yet added) items for a building block, placed on ``sc``."""
    pw, ph = sc.page_w, sc.page_h
    m = sc.margin_rect()
    if kind == "header":
        band = ShapeItem(pw, mm(24), "rect")
        band.fill, band.stroke_width = QColor(ACCENT), 0
        band.set_geometry(Geo(0, 0, pw, mm(24)))
        t = _text(m.width(), mm(16), "Your Heading Here", 26, True, color="#ffffff",
                  family="Georgia", fit="shrink", valign="middle")
        t.set_geometry(Geo(m.left(), mm(4), m.width(), mm(16)))
        return [band, t]
    if kind == "footer":
        line = ShapeItem(m.width(), 4, "line")
        line.stroke, line.stroke_width = QColor("#bfbfbf"), 0.75
        y = ph - m.top() * 0.5 - mm(8)
        line.set_geometry(Geo(m.left(), y - 2, m.width(), 4))
        left = _text(m.width() * 0.6, mm(7), "Publication name", 9, color="#7f7f7f")
        left.set_geometry(Geo(m.left(), y + mm(1), m.width() * 0.6, mm(7)))
        right = _text(m.width() * 0.4, mm(7), "", 9, color="#7f7f7f", align="right")
        right.auto = "page_of"
        right.set_geometry(Geo(m.right() - m.width() * 0.4, y + mm(1), m.width() * 0.4, mm(7)))
        return [line, left, right]
    if kind == "story":
        t = TextItem(min(m.width(), mm(120)), mm(70))
        t.set_text("Story heading", "Georgia", 18, True, False, QColor(ACCENT))
        t.add_paragraphs("Type your story here. Double-click to start typing.", "Calibri", 11,
                         line_height=1.15)
        t.set_geometry(Geo(m.left(), m.top() + mm(30), min(m.width(), mm(120)), mm(70)))
        return [t]
    if kind == "quote":
        w = min(m.width(), mm(110))
        bar = ShapeItem(mm(2), mm(30), "rect")
        bar.fill, bar.stroke_width = QColor("#c55a11"), 0
        t = _text(w - mm(6), mm(30), "“A memorable line from your story, in big "
                  "friendly letters.”", 16, italic=True, color=ACCENT.name(),
                  family="Georgia", fit="shrink", valign="middle")
        x, y = m.left() + (m.width() - w) / 2, m.top() + m.height() / 3
        bar.set_geometry(Geo(x, y, mm(2), mm(30)))
        t.set_geometry(Geo(x + mm(6), y, w - mm(6), mm(30)))
        return [bar, t]
    if kind == "sidebar":
        w = min(mm(60), m.width() / 3)
        t = TextItem(w, mm(110))
        t.fill = QColor("#eef3fa")
        t.padding = mm(4)
        t.set_text("Did you know?", "Georgia", 14, True, False, QColor(ACCENT))
        t.add_paragraphs("Add a tip, a list of dates or a little extra information here.",
                         "Calibri", 11, line_height=1.2)
        t.set_geometry(Geo(m.right() - w, m.top() + mm(30), w, mm(110)))
        return [t]
    if kind == "coupon":
        w, h = mm(90), mm(45)
        x, y = m.left() + (m.width() - w) / 2, m.top() + (m.height() - h) / 2
        box = ShapeItem(w, h, "rounded")
        box.fill, box.stroke = QColor("#fffbe6"), QColor("#7f6000")
        box.stroke_width, box.stroke_style, box.radius = 1.5, "dash", mm(3)
        box.set_geometry(Geo(x, y, w, h))
        big = _text(w - mm(8), mm(18), "SAVE 20%", 30, True, color="#7f6000", align="center",
                    family="Arial Black", fit="shrink", valign="middle")
        big.set_geometry(Geo(x + mm(4), y + mm(4), w - mm(8), mm(18)))
        small = _text(w - mm(8), mm(18), "On your next visit. Bring this coupon.\n"
                      "Expires 31 December.", 10, color="#5c4a00", align="center")
        small.set_geometry(Geo(x + mm(4), y + mm(24), w - mm(8), mm(18)))
        return [box, big, small]
    if kind in ("pagenum", "date"):
        w = mm(50)
        t = _text(w, mm(8), "", 10, color="#595959", align="center")
        t.auto = "page" if kind == "pagenum" else "date"
        y = ph - m.top() / 2 - mm(4) if kind == "pagenum" else m.top() / 2 - mm(4)
        t.set_geometry(Geo((pw - w) / 2, max(y, 0.0), w, mm(8)))
        return [t]
    raise KeyError(kind)

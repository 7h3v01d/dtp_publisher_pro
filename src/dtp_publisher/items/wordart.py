# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""WordArtItem — decorative headline text drawn as a vector outline.

The text stretches to fill its box (like Publisher WordArt) and can be warped
(arch, wave, bulge), outlined, gradient-filled and shadowed.
"""

from __future__ import annotations

import math
from typing import Any, Dict

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                         QPolygonF, QTransform)

from .base import BaseItem, color_from, color_to_str, num

WARPS = {"none": "Straight", "arch_up": "Arch up", "arch_down": "Arch down",
         "wave": "Wave", "bulge": "Bulge"}
WARP_K = 0.32


def _subdivide(poly: QPolygonF, step: float) -> QPolygonF:
    out = QPolygonF()
    n = poly.count()
    for i in range(n):
        a = poly.at(i)
        out.append(a)
        if i + 1 < n:
            b = poly.at(i + 1)
            d = math.hypot(b.x() - a.x(), b.y() - a.y())
            k = int(d / step)
            for j in range(1, k):
                t = j / k
                out.append(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    return out


def _warp_pt(u: float, v: float, warp: str) -> tuple[float, float]:
    k = WARP_K
    x = 2 * u - 1
    if warp == "arch_up":
        return u, v * (1 - k) + k * x * x
    if warp == "arch_down":
        return u, v * (1 - k) + k * (1 - x * x)
    if warp == "wave":
        return u, v * (1 - k) + k * (0.5 - 0.5 * math.sin(2 * math.pi * u))
    if warp == "bulge":
        s = 1 - k + k * (1 - x * x)
        return u, 0.5 + (v - 0.5) * s
    return u, v


def wordart_path(text: str, font: QFont, warp: str, w: float, h: float) -> QPainterPath:
    raw = QPainterPath()
    f = QFont(font)
    f.setPointSizeF(100)
    raw.addText(0, 0, f, text or " ")
    br = raw.boundingRect()
    if br.width() <= 0 or br.height() <= 0:
        return QPainterPath()
    # normalise into the unit square
    t = QTransform()
    t.scale(1 / br.width(), 1 / br.height())
    t.translate(-br.left(), -br.top())
    unit = t.map(raw)
    out = QPainterPath()
    out.setFillRule(Qt.FillRule.WindingFill)
    for poly in unit.toSubpathPolygons():
        poly = _subdivide(poly, 0.01) if warp != "none" else poly
        pts = []
        for i in range(poly.count()):
            p = poly.at(i)
            u, v = _warp_pt(p.x(), p.y(), warp)
            pts.append(QPointF(u * w, v * h))
        out.addPolygon(QPolygonF(pts))
        out.closeSubpath()
    return out


class WordArtItem(BaseItem):
    KIND = "wordart"
    DISPLAY = "WordArt"
    MIN_W = 20.0
    MIN_H = 12.0

    def __init__(self, w: float = 360, h: float = 90, text: str = "Your Text Here"):
        super().__init__(w, h)
        self.text = text
        self.font_family = "Arial Black"
        self.bold = True
        self.italic = False
        self.warp = "none"
        self.fill = QColor("#1f5fbf")
        self.fill2 = QColor("#7fb2ff")
        self.gradient = True
        self.stroke = QColor("#0b2a5c")
        self.stroke_width = 1.5
        self.shadow = True
        self.shadow_color = QColor(0, 0, 0, 90)
        self._cache_key = None
        self._cache = QPainterPath()

    def display_name(self) -> str:
        return self.name or f"WordArt — {self.text[:24]}"

    def font(self) -> QFont:
        f = QFont(self.font_family)
        f.setBold(self.bold)
        f.setItalic(self.italic)
        return f

    def path(self) -> QPainterPath:
        key = (self.text, self.font_family, self.bold, self.italic, self.warp,
               round(self._w, 2), round(self._h, 2))
        if key != self._cache_key:
            self._cache = wordart_path(self.text, self.font(), self.warp, self._w, self._h)
            self._cache_key = key
        return self._cache

    def paint_content(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = self.path()
        if self.shadow:
            off = max(2.0, self._h * 0.04)
            p.fillPath(path.translated(off, off), self.shadow_color)
        if self.gradient:
            g = QLinearGradient(0, 0, 0, self._h)
            g.setColorAt(0, self.fill2)
            g.setColorAt(1, self.fill)
            brush = QBrush(g)
        else:
            brush = QBrush(self.fill)
        p.setPen(self.make_pen())
        p.setBrush(brush)
        p.drawPath(path)

    def on_double_click(self, e):
        sc = self.page_scene()
        if sc is not None:
            sc.itemActivated.emit(self)

    # whole WordArt style as one undoable value
    def get_prop(self, key: str):
        if key == "wordart":
            return self.wordart_state()
        return super().get_prop(key)

    def set_prop(self, key: str, value):
        if key == "wordart":
            self.apply_wordart_state(value)
            self.update()
            return
        super().set_prop(key, value)

    def wordart_state(self) -> Dict[str, Any]:
        return {"text": self.text, "font_family": self.font_family, "bold": self.bold,
                "italic": self.italic, "warp": self.warp, "gradient": self.gradient,
                "shadow": self.shadow, "fill": color_to_str(self.fill),
                "fill2": color_to_str(self.fill2), "stroke": color_to_str(self.stroke),
                "stroke_width": self.stroke_width}

    def apply_wordart_state(self, d: Dict[str, Any]):
        self.text = str(d.get("text", self.text))[:500]
        self.font_family = str(d.get("font_family", self.font_family))[:100]
        self.bold = bool(d.get("bold", self.bold))
        self.italic = bool(d.get("italic", self.italic))
        w = d.get("warp", self.warp)
        self.warp = w if w in WARPS else "none"
        self.gradient = bool(d.get("gradient", self.gradient))
        self.shadow = bool(d.get("shadow", self.shadow))
        self.fill = color_from(d.get("fill"), self.fill)
        self.fill2 = color_from(d.get("fill2"), self.fill2)
        self.stroke = color_from(d.get("stroke"), self.stroke)
        self.stroke_width = num(d, "stroke_width", self.stroke_width, 0, 50)

    def extra_to_dict(self) -> Dict[str, Any]:
        d = self.wordart_state()
        d.pop("fill"), d.pop("stroke"), d.pop("stroke_width")   # saved by the base
        d["shadow_color"] = color_to_str(self.shadow_color)
        return d

    def apply_extra(self, d: Dict[str, Any]):
        st = {k: v for k, v in d.items() if k not in ("fill", "stroke", "stroke_width")}
        self.apply_wordart_state(st)
        self.shadow_color = color_from(d.get("shadow_color"), self.shadow_color)

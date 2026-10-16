# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""ShapeItem — basic vector shapes."""

from __future__ import annotations

import math
from typing import Any, Dict

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPolygonF

from .base import BaseItem, num

SHAPES = {
    "rect": "Rectangle",
    "rounded": "Rounded rectangle",
    "ellipse": "Oval",
    "triangle": "Triangle",
    "diamond": "Diamond",
    "pentagon": "Pentagon",
    "hexagon": "Hexagon",
    "star": "Star",
    "arrow": "Arrow",
    "heart": "Heart",
    "line": "Line",
}


def _regular(r: QRectF, n: int, start: float = -90.0) -> QPolygonF:
    cx, cy = r.center().x(), r.center().y()
    rx, ry = r.width() / 2, r.height() / 2
    pts = []
    for i in range(n):
        a = math.radians(start + i * 360.0 / n)
        pts.append(QPointF(cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return QPolygonF(pts)


def shape_path(kind: str, r: QRectF, radius: float = 12.0) -> QPainterPath:
    p = QPainterPath()
    w, h = r.width(), r.height()
    if kind == "ellipse":
        p.addEllipse(r)
    elif kind == "rounded":
        rad = max(0.0, min(radius, w / 2, h / 2))
        p.addRoundedRect(r, rad, rad)
    elif kind == "triangle":
        p.addPolygon(QPolygonF([QPointF(r.center().x(), r.top()), r.bottomRight(), r.bottomLeft()]))
        p.closeSubpath()
    elif kind == "diamond":
        c = r.center()
        p.addPolygon(QPolygonF([QPointF(c.x(), r.top()), QPointF(r.right(), c.y()),
                                QPointF(c.x(), r.bottom()), QPointF(r.left(), c.y())]))
        p.closeSubpath()
    elif kind == "pentagon":
        p.addPolygon(_regular(r, 5))
        p.closeSubpath()
    elif kind == "hexagon":
        p.addPolygon(_regular(r, 6, 0))
        p.closeSubpath()
    elif kind == "star":
        cx, cy = r.center().x(), r.center().y()
        pts = []
        for i in range(10):
            a = math.radians(-90 + i * 36)
            k = 1.0 if i % 2 == 0 else 0.42
            pts.append(QPointF(cx + w / 2 * k * math.cos(a), cy + h / 2 * k * math.sin(a)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif kind == "arrow":
        head = min(w * 0.45, h * 1.0)
        t, b = r.top() + h * 0.28, r.bottom() - h * 0.28
        p.addPolygon(QPolygonF([
            QPointF(r.left(), t), QPointF(r.right() - head, t), QPointF(r.right() - head, r.top()),
            QPointF(r.right(), r.center().y()), QPointF(r.right() - head, r.bottom()),
            QPointF(r.right() - head, b), QPointF(r.left(), b)]))
        p.closeSubpath()
    elif kind == "heart":
        x, y = r.left(), r.top()
        p.moveTo(x + w * .5, y + h * .25)
        p.cubicTo(x + w * .5, y + h * .05, x + w * .2, y, x + w * .1, y + h * .12)
        p.cubicTo(x - w * .05, y + h * .3, x + w * .05, y + h * .55, x + w * .5, y + h)
        p.cubicTo(x + w * .95, y + h * .55, x + w * 1.05, y + h * .3, x + w * .9, y + h * .12)
        p.cubicTo(x + w * .8, y, x + w * .5, y + h * .05, x + w * .5, y + h * .25)
        p.closeSubpath()
    elif kind == "line":
        p.moveTo(r.left(), r.center().y())
        p.lineTo(r.right(), r.center().y())
    else:
        p.addRect(r)
    return p


class ShapeItem(BaseItem):
    KIND = "shape"
    DISPLAY = "Shape"

    def __init__(self, w: float = 150, h: float = 100, shape: str = "rect"):
        super().__init__(w, h)
        self.shape_kind = shape if shape in SHAPES else "rect"
        self.radius = 14.0
        self.fill = QColor("#5b9bd5")
        self.stroke = QColor("#2e5c8a")
        self.stroke_width = 1.0
        if self.shape_kind == "line":
            self.fill = QColor(0, 0, 0, 0)
            self.stroke = QColor("#1f1f1f")
            self.stroke_width = 2.0

    def display_name(self) -> str:
        return self.name or SHAPES.get(self.shape_kind, "Shape")

    @property
    def MIN_H(self):  # type: ignore[override]
        return 1.0 if self.shape_kind == "line" else 6.0

    def path(self) -> QPainterPath:
        return shape_path(self.shape_kind, self.rect(), self.radius)

    def hit_path(self) -> QPainterPath:
        if self.shape_kind == "line":
            s = QPainterPathStroker()
            s.setWidth(max(self.stroke_width, 10 / self._zoom()))
            return s.createStroke(self.path())
        return self.path()

    def paint_content(self, p):
        p.setRenderHint(p.RenderHint.Antialiasing, True)
        p.setPen(self.make_pen())
        p.setBrush(self.fill if self.shape_kind != "line" else Qt.BrushStyle.NoBrush)
        p.drawPath(self.path())

    def extra_to_dict(self) -> Dict[str, Any]:
        return {"shape": self.shape_kind, "radius": self.radius}

    def apply_extra(self, d: Dict[str, Any]):
        k = d.get("shape", "rect")
        self.shape_kind = k if k in SHAPES else "rect"
        self.radius = num(d, "radius", 14.0, 0, 10000)

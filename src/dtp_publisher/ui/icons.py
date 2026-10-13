# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Vector icons drawn with QPainter, so they recolour with the theme and stay
crisp at any UI scale (no image files to ship)."""

from __future__ import annotations

import math
from typing import Callable, Dict, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from .. import theme

_cache: Dict[Tuple[str, str, int], QIcon] = {}


class _P:
    """Tiny drawing helper on a 24×24 grid."""

    def __init__(self, p: QPainter, fg: QColor, ac: QColor):
        self.p, self.fg, self.ac = p, fg, ac
        self.pen(fg)

    def pen(self, c: QColor, w: float = 1.7):
        pen = QPen(c, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.p.setPen(pen)
        self.p.setBrush(Qt.BrushStyle.NoBrush)

    def fill(self, c: QColor):
        self.p.setBrush(c)

    def nofill(self):
        self.p.setBrush(Qt.BrushStyle.NoBrush)

    def rect(self, x, y, w, h, fill=None):
        if fill is not None:
            self.p.setBrush(fill)
        self.p.drawRect(QRectF(x, y, w, h))
        self.nofill()

    def rrect(self, x, y, w, h, r=2, fill=None):
        if fill is not None:
            self.p.setBrush(fill)
        self.p.drawRoundedRect(QRectF(x, y, w, h), r, r)
        self.nofill()

    def line(self, *pts):
        """Separate segments: line(x1, y1, x2, y2, x3, y3, x4, y4, ...)."""
        for i in range(0, len(pts) - 3, 4):
            self.p.drawLine(QPointF(pts[i], pts[i + 1]), QPointF(pts[i + 2], pts[i + 3]))

    def poly(self, pts, fill=None, close=True):
        poly = QPolygonF([QPointF(x, y) for x, y in pts])
        if fill is not None:
            self.p.setBrush(fill)
        if close:
            self.p.drawPolygon(poly)
        else:
            self.p.drawPolyline(poly)
        self.nofill()

    def circle(self, cx, cy, r, fill=None):
        if fill is not None:
            self.p.setBrush(fill)
        self.p.drawEllipse(QPointF(cx, cy), r, r)
        self.nofill()

    def text(self, x, y, w, h, s, size=13, bold=True, italic=False, underline=False, color=None):
        f = QFont("Georgia" if italic else "Arial")
        f.setPixelSize(size)
        f.setBold(bold)
        f.setItalic(italic)
        f.setUnderline(underline)
        self.p.setFont(f)
        old = self.p.pen()
        self.p.setPen(color or self.fg)
        self.p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, s)
        self.p.setPen(old)

    def arrow(self, x1, y1, x2, y2, head=3.5):
        self.line(x1, y1, x2, y2)
        a = math.atan2(y2 - y1, x2 - x1)
        for d in (2.5, -2.5):
            self.line(x2, y2, x2 - head * math.cos(a + d * .3), y2 - head * math.sin(a + d * .3))

    def page(self, x=5, y=2.5, w=14, h=19, fold=4, fill=None):
        self.poly([(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)],
                  fill=fill)
        self.poly([(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], close=False)

    def lines(self, x, y, w, n=3, gap=3.2, last=0.6):
        for i in range(n):
            ww = w * (last if i == n - 1 and n > 1 else 1)
            self.line(x, y + i * gap, x + ww, y + i * gap)


def _soft(c: QColor, a: int = 60) -> QColor:
    c = QColor(c)
    c.setAlpha(a)
    return c


# ── icon definitions ─────────────────────────────────────────────────────────
def _new(d):
    d.page(fill=_soft(d.ac, 40))
    d.pen(d.ac, 2)
    d.line(12, 10, 12, 18, 8, 14, 16, 14)


def _open(d):
    d.poly([(2.5, 6), (9, 6), (11, 8), (19, 8), (19, 11)], close=False)
    d.poly([(2.5, 6), (2.5, 19), (18, 19), (21.5, 11), (6, 11), (2.5, 19)], fill=_soft(d.ac, 70))


def _save(d):
    d.rrect(3.5, 3.5, 17, 17, 1.5)
    d.rect(7, 3.5, 9, 5.5, fill=_soft(d.ac, 90))
    d.rect(6.5, 12.5, 11, 8)
    d.pen(d.ac)
    d.line(9, 15.5, 15, 15.5, 9, 18, 13, 18)


def _save_as(d):
    _save(d)
    d.pen(d.ac, 2)
    d.line(15, 21, 21.5, 14.5)


def _pdf(d):
    d.page(fill=_soft(d.ac, 30))
    d.text(4, 11, 16, 9, "PDF", 7, color=d.ac)


def _picture_export(d):
    _picture(d)
    d.pen(d.ac, 2)
    d.arrow(15, 20, 21.5, 20, 3)


def _print(d):
    d.rect(7, 3, 10, 6)
    d.rrect(3, 9, 18, 8, 1.5, fill=_soft(d.ac, 60))
    d.rect(7, 14, 10, 7, fill=QColor("white"))
    d.lines(9, 16.5, 6, 2, 2.4, 1)


def _undo(d):
    p = QPainterPath()
    p.moveTo(6, 10)
    p.cubicTo(10, 5, 19, 6, 19.5, 13)
    p.cubicTo(19.8, 17, 16, 19.5, 12.5, 19.5)
    d.p.drawPath(p)
    d.poly([(3.5, 5), (4, 12), (10.5, 10.5)], fill=d.fg)


def _redo(d):
    d.p.save()
    d.p.translate(24, 0)
    d.p.scale(-1, 1)
    _undo(d)
    d.p.restore()


def _cut(d):
    d.circle(7, 17.5, 3)
    d.circle(17, 17.5, 3)
    d.line(9, 15.5, 17, 3, 15, 15.5, 7, 3)


def _copy(d):
    d.rrect(8, 7.5, 12, 14, 1.5, fill=_soft(d.ac, 50))
    d.poly([(5, 17), (4, 17), (4, 3), (15, 3), (15, 5)], close=False)


def _paste(d):
    d.rrect(4, 4.5, 14, 17, 1.5)
    d.rect(8, 2.5, 6, 4, fill=d.fg)
    d.rrect(10, 10, 11, 12, 1.2, fill=QColor("white"))
    d.pen(d.ac)
    d.lines(12.5, 13.5, 6, 3, 2.6)


def _duplicate(d):
    d.rrect(3, 3, 12, 12, 1.5)
    d.rrect(9, 9, 12, 12, 1.5, fill=_soft(d.ac, 80))


def _delete(d):
    d.line(4, 6.5, 20, 6.5)
    d.poly([(9, 6.5), (9, 4), (15, 4), (15, 6.5)], close=False)
    d.poly([(6, 6.5), (7, 21), (17, 21), (18, 6.5)], fill=_soft(d.ac, 40))
    d.line(10, 10, 10, 17.5, 14, 10, 14, 17.5)


def _select_all(d):
    d.pen(d.fg, 1.4)
    d.p.setPen(QPen(d.fg, 1.4, Qt.PenStyle.DashLine))
    d.rect(3, 3, 18, 18)
    d.pen(d.ac)
    d.rect(7, 7, 10, 10, fill=_soft(d.ac, 80))


def _text(d):
    d.rect(3, 3, 18, 18)
    d.text(3, 3, 18, 18, "A", 14, color=d.ac)


def _picture(d):
    d.rrect(3, 4.5, 18, 15, 1.5, fill=_soft(d.ac, 25))
    d.poly([(3.5, 19), (9, 11), (13, 16), (16, 13), (20.5, 19)], fill=_soft(d.ac, 120))
    d.circle(16.5, 8.5, 1.8, fill=d.ac)


def _placeholder(d):
    d.p.setPen(QPen(d.fg, 1.5, Qt.PenStyle.DashLine))
    d.rect(3, 4.5, 18, 15)
    d.pen(d.ac, 2)
    d.line(12, 8.5, 12, 15.5, 8.5, 12, 15.5, 12)


def _shapes(d):
    d.rect(3, 10, 10, 10, fill=_soft(d.ac, 90))
    d.circle(15.5, 8.5, 5.5, fill=_soft(d.fg, 40))


def _rect(d):
    d.rect(3.5, 6, 17, 12, fill=_soft(d.ac, 90))


def _ellipse(d):
    d.p.setBrush(_soft(d.ac, 90))
    d.p.drawEllipse(QRectF(3, 5.5, 18, 13))
    d.nofill()


def _line(d):
    d.pen(d.fg, 2)
    d.line(4, 19, 20, 5)


def _star(d):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = 9 if i % 2 == 0 else 4
        pts.append((12 + r * math.cos(a), 12.5 + r * math.sin(a)))
    d.poly(pts, fill=_soft(d.ac, 110))


def _table(d):
    d.rect(3, 4, 18, 16)
    d.rect(3, 4, 18, 4.5, fill=_soft(d.ac, 140))
    d.line(3, 13, 21, 13, 9, 4, 9, 20, 15, 4, 15, 20)


def _wordart(d):
    d.text(1, 2, 22, 20, "A", 21, color=d.ac)
    d.pen(d.fg, 1.2)
    p = QPainterPath()
    p.moveTo(3, 21)
    p.quadTo(12, 15, 21, 21)
    d.p.drawPath(p)


def _header(d):
    d.page()
    d.rect(5, 2.5, 14, 5, fill=_soft(d.ac, 160))


def _footer(d):
    d.page()
    d.rect(5, 16.5, 14, 5, fill=_soft(d.ac, 160))


def _quote(d):
    d.text(2, 0, 20, 20, "“", 26, color=d.ac)
    d.lines(5, 17, 14, 2, 3, 0.7)


def _sidebar(d):
    d.page()
    d.rect(12.5, 6, 5, 13, fill=_soft(d.ac, 120))
    d.lines(7, 8, 4, 4, 3, 1)


def _story(d):
    d.page()
    d.pen(d.ac, 2.2)
    d.line(7, 7, 15, 7)
    d.pen(d.fg, 1.3)
    d.lines(7, 10.5, 10, 4, 2.6)


def _coupon(d):
    d.p.setPen(QPen(d.fg, 1.5, Qt.PenStyle.DashLine))
    d.rect(2.5, 5.5, 19, 13)
    d.text(3, 6, 18, 12, "%", 11, color=d.ac)


def _pagenum(d):
    d.page()
    d.text(5, 11, 14, 10, "#", 10, color=d.ac)


def _date(d):
    d.rrect(3.5, 5, 17, 15.5, 1.5)
    d.rect(3.5, 5, 17, 4.5, fill=_soft(d.ac, 150))
    d.line(8, 3, 8, 6.5, 16, 3, 16, 6.5)
    d.text(3.5, 9.5, 17, 11, "31", 9)


def _page_add(d):
    d.page()
    d.pen(d.ac, 2)
    d.line(12, 9, 12, 17, 8, 13, 16, 13)


def _page_dup(d):
    d.page(3, 2, 12, 16, 3)
    d.page(9, 6, 12, 16, 3, fill=_soft(d.ac, 70))


def _page_del(d):
    d.page()
    d.pen(d.ac, 2)
    d.line(9, 10, 15, 16, 15, 10, 9, 16)


def _page_setup(d):
    d.page()
    d.pen(d.ac, 1.6)
    d.arrow(7, 21, 7, 5, 2.5)
    d.arrow(7, 21, 17, 21, 2.5)


def _margins(d):
    d.page()
    d.p.setPen(QPen(d.ac, 1.3, Qt.PenStyle.DashLine))
    d.rect(7.5, 6, 9, 13)


def _orientation(d):
    d.rect(3, 9, 18, 11, fill=_soft(d.ac, 70))
    d.rect(6, 3, 8, 11)


def _background(d):
    d.page(fill=_soft(d.ac, 120))


def _columns(d):
    d.page()
    d.pen(d.ac, 1.3)
    d.lines(7, 7, 4, 4, 3, 1)
    d.lines(13, 7, 4, 4, 3, 1)


def _group(d):
    d.p.setPen(QPen(d.fg, 1.3, Qt.PenStyle.DashLine))
    d.rect(2.5, 2.5, 19, 19)
    d.pen(d.fg)
    d.rect(5, 5, 8, 7, fill=_soft(d.ac, 120))
    d.circle(15, 15, 4, fill=_soft(d.ac, 60))


def _ungroup(d):
    d.rect(3, 3, 9, 8, fill=_soft(d.ac, 120))
    d.circle(16, 16, 5, fill=_soft(d.ac, 60))


def _front(d):
    d.rect(3, 3, 10, 10)
    d.rect(11, 11, 10, 10)
    d.rect(7, 7, 10, 10, fill=d.ac)


def _back(d):
    d.rect(7, 7, 10, 10, fill=d.ac)
    d.rect(3, 3, 10, 10, fill=QColor("white"))
    d.rect(11, 11, 10, 10, fill=QColor("white"))


def _forward(d):
    d.rect(3, 9, 12, 12)
    d.rect(9, 3, 12, 12, fill=d.ac)


def _backward(d):
    d.rect(9, 3, 12, 12, fill=d.ac)
    d.rect(3, 9, 12, 12, fill=QColor("white"))


def _align(kind):
    def f(d):
        d.pen(d.fg, 1.6)
        if kind in ("left", "hcenter", "right"):
            x = {"left": 3.5, "hcenter": 12, "right": 20.5}[kind]
            d.line(x, 2, x, 22)
            for y, w in ((5, 14), (13, 9)):
                xx = {"left": 3.5, "hcenter": 12 - w / 2, "right": 20.5 - w}[kind]
                d.rect(xx, y, w, 5.5, fill=_soft(d.ac, 140))
        else:
            y = {"top": 3.5, "vcenter": 12, "bottom": 20.5}[kind]
            d.line(2, y, 22, y)
            for x, h in ((5, 14), (13, 9)):
                yy = {"top": 3.5, "vcenter": 12 - h / 2, "bottom": 20.5 - h}[kind]
                d.rect(x, yy, 5.5, h, fill=_soft(d.ac, 140))
    return f


def _dist(axis):
    def f(d):
        if axis == "h":
            d.line(2.5, 3, 2.5, 21, 21.5, 3, 21.5, 21)
            d.rect(5.5, 7, 4, 10, fill=_soft(d.ac, 140))
            d.rect(14.5, 7, 4, 10, fill=_soft(d.ac, 140))
        else:
            d.line(3, 2.5, 21, 2.5, 3, 21.5, 21, 21.5)
            d.rect(7, 5.5, 10, 4, fill=_soft(d.ac, 140))
            d.rect(7, 14.5, 10, 4, fill=_soft(d.ac, 140))
    return f


def _rotate(direction):
    def f(d):
        p = QPainterPath()
        if direction == "right":
            p.moveTo(6, 15)
            p.cubicTo(5, 8, 11, 4, 17, 7)
            d.p.drawPath(p)
            d.poly([(19, 3), (19.5, 10), (13, 8)], fill=d.fg)
        else:
            p.moveTo(18, 15)
            p.cubicTo(19, 8, 13, 4, 7, 7)
            d.p.drawPath(p)
            d.poly([(5, 3), (4.5, 10), (11, 8)], fill=d.fg)
        d.rect(8, 13, 8, 8, fill=_soft(d.ac, 120))
    return f


def _flip(axis):
    def f(d):
        d.p.setPen(QPen(d.ac, 1.3, Qt.PenStyle.DashLine))
        if axis == "h":
            d.line(12, 2, 12, 22)
            d.pen(d.fg)
            d.poly([(10, 5), (10, 19), (3, 19)], fill=_soft(d.ac, 140))
            d.poly([(14, 5), (14, 19), (21, 19)])
        else:
            d.line(2, 12, 22, 12)
            d.pen(d.fg)
            d.poly([(5, 10), (19, 10), (19, 3)], fill=_soft(d.ac, 140))
            d.poly([(5, 14), (19, 14), (19, 21)])
    return f


def _lock(d):
    d.rrect(5, 11, 14, 10, 1.5, fill=_soft(d.ac, 120))
    p = QPainterPath()
    p.moveTo(8, 11)
    p.lineTo(8, 8)
    p.cubicTo(8, 2.5, 16, 2.5, 16, 8)
    p.lineTo(16, 11)
    d.p.drawPath(p)


def _zoom(kind):
    def f(d):
        d.circle(10, 10, 6.5)
        d.pen(d.fg, 2.4)
        d.line(15, 15, 21, 21)
        d.pen(d.ac, 1.8)
        if kind in ("in", "out"):
            d.line(7, 10, 13, 10)
            if kind == "in":
                d.line(10, 7, 10, 13)
        elif kind == "100":
            d.text(4, 4, 12, 12, "1:1", 6)
        else:
            d.rect(7, 7.5, 6, 5)
    return f


def _grid(d):
    d.pen(d.fg, 1.2)
    for i in range(5):
        v = 3 + i * 4.5
        d.line(v, 3, v, 21, 3, v, 21, v)


def _guides(d):
    d.rect(3, 3, 18, 18)
    d.p.setPen(QPen(d.ac, 1.5, Qt.PenStyle.DashLine))
    d.line(9, 3, 9, 21, 3, 15, 21, 15)


def _boundaries(d):
    d.p.setPen(QPen(d.fg, 1.4, Qt.PenStyle.DotLine))
    d.rect(3, 4, 18, 16)
    d.pen(d.ac)
    d.lines(6, 9, 12, 3, 3.5)


def _snap(d):
    p = QPainterPath()
    p.moveTo(6, 4)
    p.lineTo(6, 13)
    p.cubicTo(6, 21, 18, 21, 18, 13)
    p.lineTo(18, 4)
    d.pen(d.fg, 2.6)
    d.p.drawPath(p)
    d.pen(d.ac, 2.8)
    d.line(4.5, 6, 7.5, 6, 16.5, 6, 19.5, 6)


def _theme(d):
    d.circle(12, 12, 8.5)
    p = QPainterPath()
    p.moveTo(12, 3.5)
    p.arcTo(QRectF(3.5, 3.5, 17, 17), 90, 180)
    p.closeSubpath()
    d.p.fillPath(p, d.fg)


def _settings(d):
    d.circle(12, 12, 3)
    for i in range(8):
        a = math.radians(i * 45)
        d.line(12 + 5.5 * math.cos(a), 12 + 5.5 * math.sin(a),
               12 + 8.5 * math.cos(a), 12 + 8.5 * math.sin(a))
    d.circle(12, 12, 6)


def _help(d):
    d.circle(12, 12, 9)
    d.text(3, 3, 18, 18, "?", 13, color=d.ac)


def _templates(d):
    d.rect(3, 3, 8, 8, fill=_soft(d.ac, 120))
    d.rect(13, 3, 8, 8)
    d.rect(3, 13, 8, 8)
    d.rect(13, 13, 8, 8, fill=_soft(d.ac, 60))


def _recent(d):
    d.circle(12, 12, 8.5)
    d.pen(d.ac, 2)
    d.poly([(12, 6.5), (12, 12), (16, 14)], close=False)


def _close(d):
    d.pen(d.fg, 2)
    d.line(6, 6, 18, 18, 18, 6, 6, 18)


def _fill_page(d):
    d.page(3, 2, 18, 20, 3)
    for r in range(3):
        for c in range(2):
            d.rect(5.5 + c * 7, 6 + r * 5, 5.5, 3.5, fill=_soft(d.ac, 140))


def _fmt(label, **kw):
    def f(d):
        d.text(2, 2, 20, 20, label, 15, **kw)
    return f


def _talign(kind):
    def f(d):
        for i, w in enumerate((16, 11, 16, 9)):
            if kind == "justify":
                w = 16
            x = {"left": 4, "center": 12 - w / 2, "right": 20 - w, "justify": 4}[kind]
            d.line(x, 5 + i * 4.5, x + w, 5 + i * 4.5)
    return f


def _bullets(d):
    for i in range(3):
        d.circle(5, 6 + i * 6, 1.4, fill=d.fg)
        d.line(9, 6 + i * 6, 20, 6 + i * 6)


def _numbering(d):
    for i in range(3):
        d.text(1, 1.5 + i * 6, 7, 9, str(i + 1), 7)
        d.line(9, 6 + i * 6, 20, 6 + i * 6)


def _textcolor(d):
    d.text(2, 0, 20, 18, "A", 15)
    d.rect(3, 18.5, 18, 3.5, fill=d.ac)


def _linespacing(d):
    d.arrow(5, 12, 5, 3.5, 2.5)
    d.arrow(5, 12, 5, 20.5, 2.5)
    d.lines(10, 5, 10, 4, 4.5, 1)


def _grow(sign):
    def f(d):
        d.text(1, 3, 16, 18, "A", 15 if sign == "+" else 11)
        d.text(13, 1, 10, 10, sign, 11, color=d.ac)
    return f


def _crop(d):
    d.poly([(6, 2), (6, 18), (22, 18)], close=False)
    d.poly([(2, 6), (18, 6), (18, 22)], close=False)
    d.pen(d.ac)
    d.rect(8, 8, 8, 8, fill=_soft(d.ac, 70))


def _edit(d):
    d.poly([(5, 19), (6, 15), (16, 5), (19, 8), (9, 18)], fill=_soft(d.ac, 90))
    d.line(4.5, 19.5, 6, 15)


def _move(up):
    def f(d):
        d.page(3, 4, 11, 15, 3)
        d.pen(d.ac, 2.2)
        if up:
            d.arrow(18.5, 20, 18.5, 4, 3.5)
        else:
            d.arrow(18.5, 4, 18.5, 20, 3.5)
    return f


def _rename(d):
    d.rrect(2.5, 7, 19, 10, 1.5)
    d.pen(d.ac, 1.8)
    d.line(13, 5, 13, 19, 11, 5, 15, 5, 11, 19, 15, 19)
    d.pen(d.fg, 1.4)
    d.line(5, 12, 10, 12)


ICONS: Dict[str, Callable] = {
    "move_up": _move(True), "move_down": _move(False), "rename": _rename,
    "new": _new, "open": _open, "save": _save, "save_as": _save_as, "pdf": _pdf,
    "picture_export": _picture_export, "print": _print, "undo": _undo, "redo": _redo,
    "cut": _cut, "copy": _copy, "paste": _paste, "duplicate": _duplicate, "delete": _delete,
    "select_all": _select_all, "text": _text, "picture": _picture, "placeholder": _placeholder,
    "shapes": _shapes, "rect": _rect, "ellipse": _ellipse, "line": _line, "star": _star,
    "table": _table, "wordart": _wordart, "header": _header, "footer": _footer,
    "quote": _quote, "sidebar": _sidebar, "story": _story, "coupon": _coupon,
    "pagenum": _pagenum, "date": _date, "page_add": _page_add, "page_dup": _page_dup,
    "page_del": _page_del, "page_setup": _page_setup, "margins": _margins,
    "orientation": _orientation, "background": _background, "columns": _columns,
    "group": _group, "ungroup": _ungroup, "front": _front, "back": _back,
    "forward": _forward, "backward": _backward,
    "align_left": _align("left"), "align_hcenter": _align("hcenter"),
    "align_right": _align("right"), "align_top": _align("top"),
    "align_vcenter": _align("vcenter"), "align_bottom": _align("bottom"),
    "dist_h": _dist("h"), "dist_v": _dist("v"), "rotate_left": _rotate("left"),
    "rotate_right": _rotate("right"), "flip_h": _flip("h"), "flip_v": _flip("v"),
    "lock": _lock, "zoom_in": _zoom("in"), "zoom_out": _zoom("out"),
    "zoom_fit": _zoom("fit"), "zoom_100": _zoom("100"), "grid": _grid, "guides": _guides,
    "boundaries": _boundaries, "snap": _snap, "theme": _theme, "settings": _settings,
    "help": _help, "templates": _templates, "recent": _recent, "close": _close,
    "fill_page": _fill_page, "bold": _fmt("B"), "italic": _fmt("I", bold=False, italic=True),
    "underline": _fmt("U", bold=False, underline=True), "talign_left": _talign("left"),
    "talign_center": _talign("center"), "talign_right": _talign("right"),
    "talign_justify": _talign("justify"), "bullets": _bullets, "numbering": _numbering,
    "text_color": _textcolor, "line_spacing": _linespacing, "font_grow": _grow("+"),
    "font_shrink": _grow("−"), "crop": _crop, "edit": _edit,
}


def icon(name: str, size: int = 32) -> QIcon:
    t = theme.tokens()
    key = (name, theme.current_name(), size)
    if key in _cache:
        return _cache[key]
    fn = ICONS.get(name)
    ic = QIcon()
    if fn is not None:
        for scale in (1, 2):
            px = QPixmap(size * scale, size * scale)
            px.setDevicePixelRatio(scale)
            px.fill(Qt.GlobalColor.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.scale(size / 24.0, size / 24.0)
            fn(_P(p, QColor(t["text"]), QColor(t["accent"])))
            p.end()
            ic.addPixmap(px, QIcon.Mode.Normal)
            dim = QPixmap(px)
            dp = QPainter(dim)
            dp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            dp.fillRect(dim.rect(), QColor(0, 0, 0, 90))
            dp.end()
            ic.addPixmap(dim, QIcon.Mode.Disabled)
    _cache[key] = ic
    return ic


def clear_cache():
    _cache.clear()

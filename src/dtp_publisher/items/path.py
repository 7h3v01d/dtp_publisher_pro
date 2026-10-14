# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""PathItem — a free-form vector shape (imported lines, borders, clip-art).

The outline is stored as an SVG-style path in a unit box (0..1 × 0..1) so it
scales with the frame like every other object.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                         QPainterPathStroker, QPen, QTransform)

from .base import BaseItem, color_from, color_to_str, num

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
MAX_TOKENS = 400_000


def _arc_points(p0: QPointF, rx: float, ry: float, phi: float, large: bool, sweep: bool,
                p1: QPointF, segs: int = 24) -> List[QPointF]:
    """Endpoint-parameterised SVG arc → polyline (SVG spec F.6.5)."""
    if rx == 0 or ry == 0:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (p0.x() - p1.x()) / 2, (p0.y() - p1.y()) / 2
    x1 = c * dx + s * dy
    y1 = -s * dx + c * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num_ = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(num_ / den, 0)) if den else 0.0
    if large == sweep:
        k = -k
    cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = c * cx1 - s * cy1 + (p0.x() + p1.x()) / 2
    cy = s * cx1 + c * cy1 + (p0.y() + p1.y()) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    out = []
    for i in range(1, segs + 1):
        t = t1 + dt * i / segs
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append(QPointF(c * x - s * y + cx, s * x + c * y + cy))
    return out


def parse_svg_path(d: str) -> QPainterPath:
    """Parse SVG path data (all commands; arcs are flattened)."""
    toks = _TOKEN.findall(d or "")[:MAX_TOKENS]
    path = QPainterPath()
    i, cmd = 0, ""
    cur = QPointF(0, 0)
    start = QPointF(0, 0)
    last_ctrl = None
    last_cmd = ""

    def nums(n):
        nonlocal i
        vals = []
        for _ in range(n):
            if i >= len(toks) or toks[i].isalpha():
                raise ValueError("short path")
            vals.append(float(toks[i]))
            i += 1
        return vals

    try:
        while i < len(toks):
            if toks[i].isalpha():
                cmd = toks[i]
                i += 1
                if cmd in "Zz":
                    path.closeSubpath()
                    cur = QPointF(start)
                    last_cmd = cmd
                    continue
            elif not cmd:
                break
            rel = cmd.islower()
            C = cmd.upper()
            base = cur if rel else QPointF(0, 0)
            if C == "M":
                x, y = nums(2)
                cur = QPointF(base.x() + x, base.y() + y)
                path.moveTo(cur)
                start = QPointF(cur)
                cmd = "l" if rel else "L"            # implicit lineto after moveto
                last_ctrl = None
            elif C == "L":
                x, y = nums(2)
                cur = QPointF(base.x() + x, base.y() + y)
                path.lineTo(cur)
                last_ctrl = None
            elif C == "H":
                (x,) = nums(1)
                cur = QPointF((cur.x() if rel else 0) + x, cur.y())
                path.lineTo(cur)
                last_ctrl = None
            elif C == "V":
                (y,) = nums(1)
                cur = QPointF(cur.x(), (cur.y() if rel else 0) + y)
                path.lineTo(cur)
                last_ctrl = None
            elif C == "C":
                x1, y1, x2, y2, x, y = nums(6)
                c1 = QPointF(base.x() + x1, base.y() + y1)
                c2 = QPointF(base.x() + x2, base.y() + y2)
                cur = QPointF(base.x() + x, base.y() + y)
                path.cubicTo(c1, c2, cur)
                last_ctrl = c2
            elif C == "S":
                x2, y2, x, y = nums(4)
                c1 = (QPointF(2 * cur.x() - last_ctrl.x(), 2 * cur.y() - last_ctrl.y())
                      if last_ctrl is not None and last_cmd.upper() in "CS" else QPointF(cur))
                c2 = QPointF(base.x() + x2, base.y() + y2)
                cur = QPointF(base.x() + x, base.y() + y)
                path.cubicTo(c1, c2, cur)
                last_ctrl = c2
            elif C == "Q":
                x1, y1, x, y = nums(4)
                c1 = QPointF(base.x() + x1, base.y() + y1)
                cur = QPointF(base.x() + x, base.y() + y)
                path.quadTo(c1, cur)
                last_ctrl = c1
            elif C == "T":
                x, y = nums(2)
                c1 = (QPointF(2 * cur.x() - last_ctrl.x(), 2 * cur.y() - last_ctrl.y())
                      if last_ctrl is not None and last_cmd.upper() in "QT" else QPointF(cur))
                cur = QPointF(base.x() + x, base.y() + y)
                path.quadTo(c1, cur)
                last_ctrl = c1
            elif C == "A":
                rx, ry, phi, la, sw, x, y = nums(7)
                end = QPointF(base.x() + x, base.y() + y)
                for pt in _arc_points(cur, rx, ry, phi, bool(la), bool(sw), end):
                    path.lineTo(pt)
                cur = end
                last_ctrl = None
            else:
                break
            last_cmd = C if not rel else C.lower()
    except (ValueError, IndexError):
        pass
    return path


def path_to_svg(path: QPainterPath, prec: int = 6) -> str:
    """Serialise a QPainterPath (unit box) back to compact SVG path data."""
    out: List[str] = []
    i, n = 0, path.elementCount()
    f = lambda v: f"{v:.{prec}g}"  # noqa: E731
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append(f"M{f(e.x)} {f(e.y)}")
            i += 1
        elif e.isLineTo():
            out.append(f"L{f(e.x)} {f(e.y)}")
            i += 1
        elif e.isCurveTo() and i + 2 < n:
            c2, p = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(f"C{f(e.x)} {f(e.y)} {f(c2.x)} {f(c2.y)} {f(p.x)} {f(p.y)}")
            i += 3
        else:
            i += 1
    return "".join(out)


class PathItem(BaseItem):
    KIND = "path"
    DISPLAY = "Drawing"
    MIN_W = 1.0
    MIN_H = 1.0

    def __init__(self, w: float = 100, h: float = 100, d: str = "M0 0L1 0L1 1L0 1Z"):
        super().__init__(w, h)
        self.d = d
        self.closed = True
        self.fill = QColor("#5b9bd5")
        self.stroke = QColor("#000000")
        self.stroke_width = 0.75
        self.fill2 = QColor(0, 0, 0, 0)     # gradient end colour (alpha 0 = solid fill)
        self.grad_angle = 90.0
        self._cache_key = None
        self._cache = QPainterPath()
        self._density = 0.0
        self.too_detailed = False       # set by limit_page_drawings (the page's budget)

    def unit_path(self) -> QPainterPath:
        if self._cache_key != self.d:
            self._cache = parse_svg_path(self.d)
            self._cache_key = self.d
            self._density = edge_density(self._cache)
        return self._cache

    def density(self) -> float:
        self.unit_path()
        return self._density

    def detail(self) -> str:
        """How this drawing is shown: 'smooth', 'plain' (no antialiasing) or 'box'.

        Qt's antialiased drawing costs roughly (edges crossed per row) × (rows), so
        a hostile outline can take minutes to draw.  Very dense outlines are drawn
        without smoothing, and beyond that as a labelled box; the drawing itself
        is kept unchanged in the file either way."""
        from .. import limits
        d = self.density()
        if self.too_detailed or d > limits.MAX_DRAW_DENSITY:
            return "box"
        if self.is_rendering():                   # printing / PDF: one-off, may take a while
            return "plain" if d > limits.MAX_SMOOTH_DENSITY else "smooth"
        return "smooth" if self in _screen_smooth_set(self.page_scene()) else "plain"

    def fills(self) -> bool:
        return self.closed and self.fill.alpha() > 0

    def path(self) -> QPainterPath:
        t = QTransform()
        t.scale(self._w, self._h)
        return t.map(self.unit_path())

    def hit_path(self) -> QPainterPath:
        if self.detail() == "box":
            p = QPainterPath()
            p.addRect(self.rect())
            return p
        p = self.path()
        if not self.fills():
            s = QPainterPathStroker()
            s.setWidth(max(self.stroke_width, 8 / self._zoom()))
            out = s.createStroke(p)
            if self.closed:
                out.addPath(p)
            return out
        return p

    def paint_content(self, p: QPainter):
        detail = self.detail()
        if detail == "box":
            self._paint_too_detailed(p)
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, detail == "smooth")
        path = self.path()
        if self.fills():
            if self.fill2.alpha():
                a = math.radians(self.grad_angle)
                c = QPointF(self._w / 2, self._h / 2)
                r = max(self._w, self._h) / 2
                g = QLinearGradient(c - QPointF(math.cos(a) * r, -math.sin(a) * r),
                                    c + QPointF(math.cos(a) * r, -math.sin(a) * r))
                g.setColorAt(0, self.fill)
                g.setColorAt(1, self.fill2)
                p.fillPath(path, QBrush(g))
            else:
                p.fillPath(path, self.fill)
        pen = self.make_pen()
        if pen.style() != Qt.PenStyle.NoPen:
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _paint_too_detailed(self, p: QPainter):
        r = self.rect()
        c = QColor(self.fill if self.fills() else self.stroke)
        c.setAlpha(60)
        p.fillRect(r, c)
        pen = QPen(QColor(120, 120, 120), 1.0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(r)
        if self.is_rendering():
            return
        f = QFont()
        f.setPointSizeF(max(min(9.0 / self._zoom(), r.height() / 5), 1.0))
        p.setFont(f)
        p.setPen(QColor(70, 70, 70))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   "Drawing too detailed to show")

    def on_prop_changed(self, key: str):
        if key == "d":
            self._cache_key = None

    def extra_to_dict(self) -> Dict[str, Any]:
        return {"d": self.d, "closed": self.closed, "fill2": color_to_str(self.fill2),
                "grad_angle": self.grad_angle}

    def apply_extra(self, d: Dict[str, Any]):
        from .. import limits
        self.d = str(d.get("d", self.d))[:limits.MAX_PATH_CHARS]
        self.closed = bool(d.get("closed", True))
        self.fill2 = color_from(d.get("fill2"), self.fill2)
        self.grad_angle = num(d, "grad_angle", 90.0, -360, 360)
        self._cache_key = None


def edge_density(path: QPainterPath) -> float:
    """Average number of edges a horizontal line crosses: what drawing costs.

    The sum of every edge's vertical extent over the height: a circle is 2, a
    line of text turned into outlines about 90, a zig-zag of 1,000 edges about
    1,000.  Curves are flattened first.
    """
    h = path.boundingRect().height()
    if h <= 0:
        return 0.0
    total = 0.0
    for poly in path.toSubpathPolygons():
        prev = None
        for i in range(poly.count()):
            y = poly[i].y()
            if prev is not None:
                total += abs(y - prev)
            prev = y
    return total / h


def _screen_smooth_set(scene) -> set:
    """The drawings on a page that are smoothed on screen at the current zoom.

    Smoothed drawing costs about density × zoom² (the pen widens too), so the page
    shares one allowance, given out from the back to the front.  Worked out once
    per zoom level and page contents."""
    from .. import limits
    if scene is None:
        return set()
    items = [i for i in scene.items() if isinstance(i, PathItem)]
    z = max(getattr(scene, "zoom", 1.0), 1.0)
    key = (round(z, 3), len(items), sum(id(i) for i in items))
    cached = getattr(scene, "_smooth_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    allowed, left = set(), limits.MAX_SCREEN_SMOOTH_WORK
    for it in sorted(items, key=lambda i: i.zValue()):
        if it.too_detailed or len(allowed) >= limits.MAX_SMOOTH_DRAWINGS_PER_PAGE:
            continue
        if it.density() <= limits.ALWAYS_SMOOTH_DENSITY:   # rectangles, circles, rings
            allowed.add(it)
            continue
        work = it.density() * z * z
        if it.density() <= limits.MAX_SMOOTH_DENSITY and work <= left:
            allowed.add(it)
            left -= work
    scene._smooth_cache = (key, allowed)
    return allowed


def limit_page_drawings(items) -> int:
    """Once a page's drawings add up to too much work, show the rest as boxes.

    Returns how many drawings are shown as boxes (their data is unchanged)."""
    from .. import limits
    budget = limits.MAX_PAGE_DENSITY
    boxed = 0
    for it in sorted((i for i in items if isinstance(i, PathItem)), key=lambda i: i.zValue()):
        it.too_detailed = False
        dens = it.density()
        if dens > limits.MAX_DRAW_DENSITY or dens > budget:
            it.too_detailed = True
            boxed += 1
        else:
            budget -= dens
        it.update()
    return boxed


def unit_path_from(path: QPainterPath, box: QRectF) -> Tuple[str, QRectF]:
    """Normalise ``path`` (in some coordinate space) into the unit box of ``box``."""
    w = box.width() if box.width() > 1e-9 else 1.0
    h = box.height() if box.height() > 1e-9 else 1.0
    t = QTransform()
    t.scale(1 / w, 1 / h)
    t.translate(-box.left(), -box.top())
    return path_to_svg(t.map(path)), box

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""BaseItem — common behaviour for every object on a page.

Geometry model (the old code's root cause for "objects move when reopened"):
the local rect is ALWAYS (0, 0, w, h); ``pos()`` is the unrotated top-left
corner; rotation is about the box centre.  ``Geo`` captures all of it, and
that is exactly what gets saved.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject

from .. import theme
from ..commands import GeometryCmd
from ..geometry import (Geo, geo_from_local_rect, normalize_angle, parent_to_local,
                        snap_angle)

HANDLE_PX = 11.0      # handle size in screen pixels (large for easier grabbing)
ROT_PX = 30.0         # distance of the rotate knob above the box, screen px

STROKE_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dash": Qt.PenStyle.DashLine,
    "dot": Qt.PenStyle.DotLine,
    "dashdot": Qt.PenStyle.DashDotLine,
}

_HANDLE_ANGLE = {"e": 0, "se": 45, "s": 90, "sw": 135, "w": 180, "nw": 225, "n": 270, "ne": 315}
_CURSOR_BUCKET = [Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeFDiagCursor,
                  Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeBDiagCursor]


def device_font(painter: QPainter, family: str, pt: float, bold: bool = False,
                italic: bool = False) -> QFont:
    """A font that is ``pt`` *scene points* tall whatever the painter's device DPI."""
    dev = painter.device()
    dpi = dev.logicalDpiY() if dev is not None else 72
    f = QFont(family)
    f.setPointSizeF(max(pt * 72.0 / max(dpi, 1), 0.1))
    f.setBold(bold)
    f.setItalic(italic)
    return f


def new_uid() -> str:
    return uuid.uuid4().hex[:12]


def color_to_str(c: QColor) -> str:
    return QColor(c).name(QColor.NameFormat.HexArgb)


def color_from(v: Any, default: QColor) -> QColor:
    if isinstance(v, QColor):
        return QColor(v)
    if isinstance(v, str):
        c = QColor(v)
        if c.isValid():
            return c
    return QColor(default)


def num(d: dict, key: str, default: float, lo: float = -1e7, hi: float = 1e7) -> float:
    try:
        v = float(d.get(key, default))
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(v):
        return float(default)
    return min(max(v, lo), hi)


@dataclass
class _Drag:
    kind: str                      # "move" | "resize" | "rotate"
    handle: str = ""
    start_geo: Optional[Geo] = None
    center: QPointF = field(default_factory=QPointF)
    reselect: bool = False


class BaseItem(QGraphicsObject):
    KIND = "base"
    DISPLAY = "Object"
    MIN_W = 6.0
    MIN_H = 6.0
    CAN_RESIZE = True
    CAN_ROTATE = True
    KEEP_ASPECT = False       # corner handles keep aspect by default (pictures)
    SHOW_BOUNDARY = False     # dotted outline when "Boundaries" is on

    geometryChanged = pyqtSignal()

    def __init__(self, w: float = 100.0, h: float = 100.0):
        super().__init__()
        self._w = max(float(w), 1.0)
        self._h = max(float(h), 1.0)
        self.uid = new_uid()
        self.name = ""
        self.fill = QColor(0, 0, 0, 0)
        self.stroke = QColor(0, 0, 0)
        self.stroke_width = 0.0
        self.stroke_style = "solid"
        self.locked = False
        self.hidden = False
        self.flip_h = False
        self.flip_v = False
        self._drag: Optional[_Drag] = None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(self._w / 2, self._h / 2)

    # ── identity ─────────────────────────────────────────────────────────────
    def display_name(self) -> str:
        return self.name or self.DISPLAY

    def page_scene(self):
        from ..scene import PageScene
        sc = self.scene()
        return sc if isinstance(sc, PageScene) else None

    def is_rendering(self) -> bool:
        sc = self.page_scene()
        return bool(sc and sc.rendering)

    def _zoom(self) -> float:
        sc = self.page_scene()
        return max(sc.zoom, 0.05) if sc else 1.0

    def in_group(self) -> bool:
        return isinstance(self.parentItem(), BaseItem)

    # ── geometry ─────────────────────────────────────────────────────────────
    @property
    def w(self) -> float:
        return self._w

    @property
    def h(self) -> float:
        return self._h

    def rect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def geometry(self) -> Geo:
        p = self.pos()
        return Geo(p.x(), p.y(), self._w, self._h, normalize_angle(self.rotation()))

    def set_geometry(self, g: Geo):
        self.prepareGeometryChange()
        self._w = max(float(g.w), 1.0)
        self._h = max(float(g.h), 1.0)
        self.setTransformOriginPoint(self._w / 2, self._h / 2)
        self.setPos(QPointF(g.x, g.y))
        self.setRotation(normalize_angle(g.rot))
        self.on_resized()
        self.update()
        self.geometryChanged.emit()

    def scene_box(self) -> QRectF:
        """Axis-aligned bounds of the object (without handles) in scene space."""
        return self.mapToScene(self.rect()).boundingRect()

    def on_resized(self):
        """Hook: content reflow after size change."""

    # ── properties (generic get/set used by undo commands and panels) ───────
    def get_prop(self, key: str) -> Any:
        if key == "geometry":
            return self.geometry()
        if key == "opacity":
            return self.opacity()
        v = getattr(self, key)
        return QColor(v) if isinstance(v, QColor) else v

    def set_prop(self, key: str, value: Any):
        if key == "locked":
            self.locked = bool(value)
            self.update()
            return
        if key == "hidden":
            self.hidden = bool(value)
            self.setVisible(not self.hidden)
            return
        if key == "opacity":
            self.setOpacity(min(max(float(value), 0.0), 1.0))
            return
        if key == "geometry":
            self.set_geometry(value)
            return
        if isinstance(getattr(self, key, None), QColor):
            value = QColor(value)
        setattr(self, key, value)
        self.on_prop_changed(key)
        self.update()

    def on_prop_changed(self, key: str):
        """Hook for subclasses."""

    @property
    def opacity_value(self) -> float:
        return self.opacity()

    # ── serialisation ────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        g = self.geometry()
        d = {
            "kind": self.KIND,
            "uid": self.uid,
            "name": self.name,
            "x": round(g.x, 4), "y": round(g.y, 4),
            "w": round(g.w, 4), "h": round(g.h, 4),
            "rot": round(g.rot, 4),
            "z": self.zValue(),
            "fill": color_to_str(self.fill),
            "stroke": color_to_str(self.stroke),
            "stroke_width": self.stroke_width,
            "stroke_style": self.stroke_style,
            "opacity": round(self.opacity(), 4),
            "locked": self.locked,
            "hidden": self.hidden,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
        }
        d.update(self.extra_to_dict())
        return d

    def extra_to_dict(self) -> Dict[str, Any]:
        return {}

    def apply_dict(self, d: Dict[str, Any]):
        self.uid = str(d.get("uid") or self.uid)[:64]
        self.name = str(d.get("name", ""))[:200]
        self.fill = color_from(d.get("fill"), self.fill)
        self.stroke = color_from(d.get("stroke"), self.stroke)
        self.stroke_width = num(d, "stroke_width", self.stroke_width, 0, 200)
        ss = d.get("stroke_style", "solid")
        self.stroke_style = ss if ss in STROKE_STYLES else "solid"
        self.setOpacity(num(d, "opacity", 1.0, 0.0, 1.0))
        self.flip_h = bool(d.get("flip_h", False))
        self.flip_v = bool(d.get("flip_v", False))
        self.setZValue(num(d, "z", 1.0))
        self.apply_extra(d)
        self.set_geometry(Geo(num(d, "x", 0), num(d, "y", 0),
                              num(d, "w", self._w, 1, 1e5), num(d, "h", self._h, 1, 1e5),
                              num(d, "rot", 0, -360, 360)))
        self.set_prop("locked", bool(d.get("locked", False)))
        self.set_prop("hidden", bool(d.get("hidden", False)))

    def apply_extra(self, d: Dict[str, Any]):
        """Hook: subclass-specific fields (called before geometry is set)."""

    # ── painting ────────────────────────────────────────────────────────────
    def make_pen(self) -> QPen:
        if self.stroke_width <= 0 or self.stroke.alpha() == 0:
            return QPen(Qt.PenStyle.NoPen)   # 0 used to draw a 1px hairline
        pen = QPen(self.stroke, self.stroke_width, STROKE_STYLES.get(self.stroke_style,
                                                                     Qt.PenStyle.SolidLine))
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def _hs(self) -> float:
        return HANDLE_PX / self._zoom()

    def boundingRect(self) -> QRectF:
        z = self._zoom()
        pad = HANDLE_PX / z + self.stroke_width / 2 + 2
        top = pad + (ROT_PX / z if self.CAN_ROTATE else 0)
        return self.rect().adjusted(-pad, -top, pad, pad)

    def hit_path(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(self.rect())
        return p

    def shape(self) -> QPainterPath:
        p = self.hit_path()
        if self.isSelected() and not self.locked and not self.is_rendering():
            for r in self._handle_rects().values():
                p.addRect(r)
            if self.CAN_ROTATE:
                p.addEllipse(self._rot_rect())
        return p

    CAN_FLIP = True

    def paint(self, p: QPainter, opt, widget=None):
        p.save()
        if self.CAN_FLIP and (self.flip_h or self.flip_v):
            p.translate(self._w if self.flip_h else 0, self._h if self.flip_v else 0)
            p.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
        self.paint_content(p)
        p.restore()
        if not self.is_rendering():
            self.paint_overlay(p)

    def paint_content(self, p: QPainter):
        """Subclasses draw the object here (in local coords)."""

    def paint_overlay(self, p: QPainter):
        sc = self.page_scene()
        p.save()
        if self.isSelected():
            self._paint_selection(p)
        elif (self.SHOW_BOUNDARY and sc is not None and sc.doc.view.show_boundaries
              and not self.in_group()):
            pen = QPen(theme.color("c_bounds"), 1, Qt.PenStyle.DotLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self.rect())
        p.restore()

    def _paint_selection(self, p: QPainter):
        sel = theme.color("c_select")
        pen = QPen(sel, 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect())
        if self.locked:
            self._paint_lock(p)
            return
        hp = QPen(sel, 1.5)
        hp.setCosmetic(True)
        if self.CAN_ROTATE:
            r = self._rot_rect()
            p.setPen(hp)
            p.drawLine(QPointF(self._w / 2, 0), QPointF(r.center().x(), r.bottom()))
            p.setBrush(theme.color("c_handle_fill"))
            p.drawEllipse(r)
            # little arrow arc inside the knob
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(r.adjusted(r.width() * .28, r.height() * .28, -r.width() * .28,
                                 -r.height() * .28), 30 * 16, 280 * 16)
        p.setPen(hp)
        p.setBrush(theme.color("c_handle_fill"))
        for k, r in self._handle_rects().items():
            if len(k) == 2:
                p.drawEllipse(r)
            else:
                p.drawRect(r)

    def _paint_lock(self, p: QPainter):
        s = 14 / self._zoom()
        x, y = self._w - s - 2 / self._zoom(), -s - 3 / self._zoom()
        col = theme.color("c_lock")
        pen = QPen(col, 2)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(col)
        p.drawRect(QRectF(x, y + s * .45, s, s * .55))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(x + s * .2, y, s * .6, s * .9), 0, 180 * 16)

    # ── handles ──────────────────────────────────────────────────────────────
    def _handle_rects(self) -> Dict[str, QRectF]:
        if not self.CAN_RESIZE:
            return {}
        hs = self._hs()
        w, h = self._w, self._h
        pts = {"nw": (0, 0), "n": (w / 2, 0), "ne": (w, 0), "e": (w, h / 2),
               "se": (w, h), "s": (w / 2, h), "sw": (0, h), "w": (0, h / 2)}
        # hide middle handles on very small boxes so corners stay grabbable
        if w * self._zoom() < 3 * HANDLE_PX:
            pts.pop("n"), pts.pop("s")
        if h * self._zoom() < 3 * HANDLE_PX:
            pts.pop("e"), pts.pop("w")
        return {k: QRectF(x - hs / 2, y - hs / 2, hs, hs) for k, (x, y) in pts.items()}

    def _rot_rect(self) -> QRectF:
        z = self._zoom()
        d = (HANDLE_PX + 3) / z
        return QRectF(self._w / 2 - d / 2, -ROT_PX / z - d / 2, d, d)

    def hit_handle(self, pos: QPointF) -> Optional[str]:
        if not self.isSelected() or self.locked or self.in_group():
            return None
        if self.CAN_ROTATE and self._rot_rect().adjusted(-2, -2, 2, 2).contains(pos):
            return "rot"
        grow = 2 / self._zoom()
        for k, r in self._handle_rects().items():
            if r.adjusted(-grow, -grow, grow, grow).contains(pos):
                return k
        return None

    def _cursor_for(self, handle: Optional[str]) -> Qt.CursorShape:
        if handle is None:
            return Qt.CursorShape.ForbiddenCursor if self.locked else Qt.CursorShape.SizeAllCursor
        if handle == "rot":
            return Qt.CursorShape.CrossCursor
        rot =math.degrees(math.atan2(self.sceneTransform().m12(), self.sceneTransform().m11()))
        ang = (_HANDLE_ANGLE[handle] + rot) % 180
        return _CURSOR_BUCKET[int(round(ang / 45.0)) % 4]

    # ── mouse ────────────────────────────────────────────────────────────────
    def hoverMoveEvent(self, e):
        if self.in_group():
            self.unsetCursor()
            return
        self.setCursor(self._cursor_for(self.hit_handle(e.pos())))
        super().hoverMoveEvent(e)

    def hoverLeaveEvent(self, e):
        self.unsetCursor()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        sc = self.page_scene()
        if self.in_group() or sc is None:
            e.ignore()     # the group handles clicks on its members
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.RightButton:
            if not self.isSelected():
                sc.clearSelection()
                self.setSelected(True)
            e.accept()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        mods = e.modifiers()
        handle = self.hit_handle(e.pos())
        if handle:
            self._drag = _Drag("rotate" if handle == "rot" else "resize", handle,
                               self.geometry(), self.mapToScene(self.rect().center()))
            self.on_drag_start()
            e.accept()
            return
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.setSelected(not self.isSelected())
            self._drag = None
            e.accept()
            return
        reselect = self.isSelected()
        if not self.isSelected():
            sc.clearSelection()
            self.setSelected(True)
        self._drag = _Drag("move", reselect=reselect) if sc.begin_move(e.scenePos()) else \
            _Drag("noop", reselect=reselect)
        e.accept()

    def mouseMoveEvent(self, e):
        d = self._drag
        sc = self.page_scene()
        if d is None or sc is None:
            return
        if d.kind == "move":
            sc.update_move(e.scenePos(), e.modifiers())
        elif d.kind == "resize":
            self._resize_to(e.scenePos(), e.modifiers())
        elif d.kind == "rotate":
            self._rotate_to(e.scenePos(), e.modifiers())
        e.accept()

    def mouseReleaseEvent(self, e):
        d, self._drag = self._drag, None
        sc = self.page_scene()
        if d is None or sc is None:
            e.accept()
            return
        if d.kind in ("move", "noop"):
            moved = sc.end_move() if d.kind == "move" else False
            if not moved and d.reselect and e.button() == Qt.MouseButton.LeftButton:
                sc.clearSelection()
                self.setSelected(True)
        else:
            sc.set_snap_lines([])
            new = self.geometry()
            if not new.close_to(d.start_geo):
                changes = {self: (d.start_geo, new)}
                changes.update(self.extra_geometry_changes())
                sc.push(GeometryCmd(sc, changes, "Rotate" if d.kind == "rotate" else "Resize"))
            self.on_drag_end()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if self.in_group() or self.locked:
            e.ignore()
            return
        self.on_double_click(e)
        e.accept()

    def on_double_click(self, e):
        """Hook: text edit, choose picture, edit table…"""

    # group hooks (GroupItem scales members while resizing)
    def on_drag_start(self):
        pass

    def on_live_resize(self, start: Geo, new: Geo):
        pass

    def extra_geometry_changes(self) -> Dict["BaseItem", tuple]:
        return {}

    def on_drag_end(self):
        pass

    # ── resize / rotate maths ───────────────────────────────────────────────
    def _to_parent(self, scene_pos: QPointF) -> QPointF:
        par = self.parentItem()
        return par.mapFromScene(scene_pos) if par is not None else QPointF(scene_pos)

    def _resize_to(self, scene_pos: QPointF, mods):
        d = self._drag
        g0 = d.start_geo
        sc = self.page_scene()
        lp = parent_to_local(g0, self._to_parent(scene_pos))
        h = d.handle
        x0, y0, x1, y1 = 0.0, 0.0, g0.w, g0.h
        if "w" in h:
            x0 = lp.x()
        if "e" in h:
            x1 = lp.x()
        if "n" in h:
            y0 = lp.y()
        if "s" in h:
            y1 = lp.y()
        lines = []
        if (abs(g0.rot) < 0.01 and self.parentItem() is None
                and not (mods & Qt.KeyboardModifier.AltModifier)):
            ex = {self}
            ex.update(self.childItems())
            for edge in ("w", "e", "n", "s"):
                if edge not in h:
                    continue
                if edge in "we":
                    cur = g0.x + (x0 if edge == "w" else x1)
                    v, ln = sc.snap_value(cur, "x", ex)
                    if edge == "w":
                        x0 = v - g0.x
                    else:
                        x1 = v - g0.x
                else:
                    cur = g0.y + (y0 if edge == "n" else y1)
                    v, ln = sc.snap_value(cur, "y", ex)
                    if edge == "n":
                        y0 = v - g0.y
                    else:
                        y1 = v - g0.y
                if ln is not None:
                    lines.append(ln)
        from_center = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if from_center:
            if "w" in h:
                x1 = g0.w - x0
            if "e" in h:
                x0 = g0.w - x1
            if "n" in h:
                y1 = g0.h - y0
            if "s" in h:
                y0 = g0.h - y1
        corner = len(h) == 2
        keep = corner and (self.KEEP_ASPECT != bool(mods & Qt.KeyboardModifier.ShiftModifier))
        if keep and g0.h > 0:
            ratio = g0.w / g0.h
            w, hh = abs(x1 - x0), abs(y1 - y0)
            if w / ratio >= hh:
                hh = w / ratio
            else:
                w = hh * ratio
            x0, x1 = self._anchor(x0, x1, w, "w" in h, from_center, g0.w)
            y0, y1 = self._anchor(y0, y1, hh, "n" in h, from_center, g0.h)
        mw, mh = self.MIN_W, self.MIN_H
        if x1 - x0 < mw:
            x0, x1 = self._anchor(x0, x1, mw, "w" in h, from_center, g0.w)
        if y1 - y0 < mh:
            y0, y1 = self._anchor(y0, y1, mh, "n" in h, from_center, g0.h)
        new = geo_from_local_rect(g0, QRectF(x0, y0, x1 - x0, y1 - y0))
        self.set_geometry(new)
        self.on_live_resize(g0, new)
        sc.set_snap_lines(lines)

    @staticmethod
    def _anchor(a: float, b: float, size: float, moving_low: bool, center: bool, full: float):
        if center:
            c = full / 2
            return c - size / 2, c + size / 2
        if moving_low:
            return b - size, b
        return a, a + size

    def _rotate_to(self, scene_pos: QPointF, mods):
        d = self._drag
        c = d.center
        ang = math.degrees(math.atan2(scene_pos.y() - c.y(), scene_pos.x() - c.x())) + 90.0
        par = self.parentItem()
        if par is not None:
            ang -= par.rotation()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            ang = snap_angle(ang, 15.0)
        else:
            ang = snap_angle(ang, 90.0, magnet=4.0)
        self.set_geometry(d.start_geo._replace(rot=normalize_angle(ang)))

    # ── misc ─────────────────────────────────────────────────────────────────
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()   # shape grows/shrinks by the handles
        return super().itemChange(change, value)

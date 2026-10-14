# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""GroupItem — members become Qt child items, so moving/rotating is exact."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsItem

from ..geometry import Geo, normalize_angle
from .base import BaseItem


class GroupItem(BaseItem):
    CAN_FLIP = False
    KIND = "group"
    DISPLAY = "Group"
    KEEP_ASPECT = True
    MIN_W = 4.0
    MIN_H = 4.0

    def __init__(self, w: float = 10, h: float = 10):
        super().__init__(w, h)
        self._snapshot: Dict[BaseItem, Geo] = {}

    def display_name(self) -> str:
        return self.name or f"Group ({len(self.members())} objects)"

    def affects_wrap(self) -> bool:
        return any(m.affects_wrap() for m in self.members())

    def _is_text_box(self) -> bool:
        return any(m._is_text_box() for m in self.members())

    def members(self) -> List[BaseItem]:
        return sorted((c for c in self.childItems() if isinstance(c, BaseItem)),
                      key=lambda c: c.zValue())

    def descendants(self) -> List[BaseItem]:
        out: List[BaseItem] = []
        for m in self.members():
            out.append(m)
            if isinstance(m, GroupItem):
                out.extend(m.descendants())
        return out

    # ── grouping ─────────────────────────────────────────────────────────────
    def adopt(self, items: Iterable[BaseItem]):
        items = sorted(items, key=lambda i: i.zValue())
        if not items:
            return
        bounds = items[0].scene_box()
        for it in items[1:]:
            bounds = bounds.united(it.scene_box())
        self.set_geometry(Geo(bounds.left(), bounds.top(), max(bounds.width(), 1.0),
                              max(bounds.height(), 1.0), 0.0))
        self.setZValue(items[-1].zValue())
        for rank, it in enumerate(items):
            centre = it.mapToScene(it.rect().center())
            scene_rot = it.rotation()          # members are top-level when adopted
            it.setSelected(False)
            it.setParentItem(self)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            lc = self.mapFromScene(centre)
            it.setPos(lc - QPointF(it.w / 2, it.h / 2))
            it.setRotation(normalize_angle(scene_rot - self.rotation()))
            it.setZValue(rank + 1)
        self.prepareGeometryChange()
        self.update()

    def snapshot(self) -> tuple:
        """Exact state (own frame + members' local geometry/z) for undo."""
        return (self.geometry(), self.zValue(),
                [(m, m.geometry(), m.zValue()) for m in self.members()])

    def restore(self, snap: tuple):
        """Re-attach members exactly as captured by ``snapshot``."""
        geo, z, members = snap
        self.set_geometry(geo)
        self.setZValue(z)
        for m, g, mz in members:
            m.setSelected(False)
            m.setParentItem(self)
            m.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            m.set_geometry(g)
            m.setZValue(mz)
        self.prepareGeometryChange()
        self.update()

    def release(self) -> List[BaseItem]:
        items = self.members()
        gz = self.zValue()
        grot = self.rotation()
        for rank, it in enumerate(items):
            centre = it.mapToScene(it.rect().center())
            rot = it.rotation() + grot
            it.setParentItem(None)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            it.setPos(centre - QPointF(it.w / 2, it.h / 2))
            it.setRotation(normalize_angle(rot))
            it.setZValue(gz + (rank + 1) * 0.001)
        self.prepareGeometryChange()
        return items

    # ── hit testing / painting ──────────────────────────────────────────────
    def hit_path(self) -> QPainterPath:
        p = QPainterPath()
        for m in self.members():
            p.addPath(m.mapToParent(m.hit_path()))
        if p.isEmpty():
            p.addRect(self.rect())
        return p

    def paint_content(self, p):
        pass

    def on_double_click(self, e):
        # double-click a member to work on it without ungrouping
        from .text import TextItem
        for it in sorted(self.descendants(), key=lambda m: -m.zValue()):
            if it.contains(it.mapFromScene(e.scenePos())) and it.hit_path().contains(
                    it.mapFromScene(e.scenePos())):
                if isinstance(it, TextItem):
                    it.begin_edit(e.scenePos())
                    return
                sc = self.page_scene()
                if sc is not None and hasattr(it, "on_double_click"):
                    sc.itemActivated.emit(it)
                return

    # ── resizing scales the members ──────────────────────────────────────────
    def on_drag_start(self):
        self._snapshot = {m: m.geometry() for m in self.descendants()}

    def on_live_resize(self, start: Geo, new: Geo):
        if not self._snapshot or start.w <= 0 or start.h <= 0:
            return
        sx, sy = new.w / start.w, new.h / start.h
        for m, g in self._snapshot.items():
            r = abs(normalize_angle(g.rot)) % 180
            if r < 1 or r > 179:
                fw, fh = sx, sy
            elif 89 < r < 91:
                fw, fh = sy, sx
            else:
                fw = fh = (sx * sy) ** 0.5
            c = g.center
            nw, nh = max(g.w * fw, 1.0), max(g.h * fh, 1.0)
            m.set_geometry(Geo(c.x() * sx - nw / 2, c.y() * sy - nh / 2, nw, nh, g.rot))

    def extra_geometry_changes(self) -> Dict[BaseItem, tuple]:
        return {m: (g, m.geometry()) for m, g in self._snapshot.items()
                if not g.close_to(m.geometry())}

    def on_drag_end(self):
        self._snapshot = {}

    # ── serialisation ────────────────────────────────────────────────────────
    def extra_to_dict(self) -> Dict[str, Any]:
        return {"children": [m.to_dict() for m in self.members()]}

    def apply_extra(self, d: Dict[str, Any]):
        pass  # children are attached by serialize.item_from_dict

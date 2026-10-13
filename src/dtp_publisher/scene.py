# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""PageScene (one per page), ruler guides, snapping and group moving."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set, Tuple

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsScene

from . import theme
from .commands import MoveGuideCmd, MoveItemsCmd, RemoveGuideCmd
from .units import mm

if TYPE_CHECKING:  # pragma: no cover
    from .document import Document
    from .items.base import BaseItem


# ═════════════════════════════════════════════════════════════════════════════
class GuideItem(QGraphicsObject):
    """A ruler guide.  'H' = horizontal line at y=position, 'V' = vertical at x."""

    def __init__(self, orient: str, position: float):
        super().__init__()
        if orient not in ("H", "V"):
            raise ValueError(orient)
        self.orient = orient
        self.setZValue(1_000_000)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SplitVCursor if orient == "H" else Qt.CursorShape.SplitHCursor)
        self._press: Optional[float] = None
        self.set_position(position)

    # position lives in pos(): x for 'V', y for 'H'
    @property
    def position(self) -> float:
        return self.pos().y() if self.orient == "H" else self.pos().x()

    def set_position(self, v: float):
        self.setPos(QPointF(0, v) if self.orient == "H" else QPointF(v, 0))
        sc = self.scene()
        if isinstance(sc, PageScene):
            sc.update()

    def _span(self) -> Tuple[float, float]:
        sc = self.scene()
        if isinstance(sc, PageScene):
            r = sc.sceneRect()
            return (r.left(), r.right()) if self.orient == "H" else (r.top(), r.bottom())
        return (-2000.0, 4000.0)

    def _thick(self) -> float:
        sc = self.scene()
        z = sc.zoom if isinstance(sc, PageScene) else 1.0
        return 7.0 / max(z, 0.05)

    def boundingRect(self) -> QRectF:
        a, b = self._span()
        t = self._thick()
        if self.orient == "H":
            return QRectF(a, -t / 2, b - a, t)
        return QRectF(-t / 2, a, t, b - a)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(self.boundingRect())
        return p

    def paint(self, p: QPainter, opt, w=None):
        sc = self.scene()
        if not isinstance(sc, PageScene) or sc.rendering or not sc.doc.view.show_guides:
            return
        pen = QPen(theme.color("c_guide"), 1.2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        a, b = self._span()
        if self.orient == "H":
            p.drawLine(QPointF(a, 0), QPointF(b, 0))
        else:
            p.drawLine(QPointF(0, a), QPointF(0, b))

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        self._press = self.position
        e.accept()

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        sp = e.scenePos()
        v = sp.y() if self.orient == "H" else sp.x()
        sc = self.scene()
        if isinstance(sc, PageScene) and not (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            v, _ = sc.snap_value(v, "y" if self.orient == "H" else "x", exclude=set(), guides=False)
        self.set_position(v)

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        old, self._press = self._press, None
        sc = self.scene()
        if not isinstance(sc, PageScene):
            return
        limit = sc.page_h if self.orient == "H" else sc.page_w
        if self.position < -4 or self.position > limit + 4:
            # dragged off the page: remove (like dragging back to the ruler)
            self.set_position(old)
            sc.push(RemoveGuideCmd(sc, [self]))
        elif abs(self.position - old) > 1e-6:
            sc.push(MoveGuideCmd(sc, self, old, self.position))

    def contextMenuEvent(self, e):
        sc = self.scene()
        if isinstance(sc, PageScene):
            from PyQt6.QtWidgets import QMenu
            m = QMenu()
            act = m.addAction("Delete guide")
            if m.exec(e.screenPos()) is act:
                sc.push(RemoveGuideCmd(sc, [self]))
        e.accept()


# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class _MoveState:
    start: QPointF
    items: List["BaseItem"]
    starts: Dict["BaseItem", QPointF]
    bounds: QRectF
    moved: bool = False
    exclude: Set[QGraphicsItem] = field(default_factory=set)


class PageScene(QGraphicsScene):
    PASTEBOARD = 300.0   # scratch area around the page, in points

    textEditingChanged = pyqtSignal(object)   # TextItem now editing, or None
    textFormatChanged = pyqtSignal(object)    # caret/format moved while editing
    itemActivated = pyqtSignal(object)        # double-click needing a dialog (picture/table)

    def __init__(self, doc: "Document", width: float, height: float):
        super().__init__(doc)
        self.doc = doc
        self.name = ""
        self.page_w = float(width)
        self.page_h = float(height)
        self.margins = [mm(12.7)] * 4          # left, top, right, bottom
        self.columns = 1
        self.rows = 1
        self.gutter = mm(5)
        self.background = QColor(255, 255, 255)
        self.rendering = False
        self.preview = False        # thumbnails: hide aids but still show empty photo frames
        self.zoom = 1.0
        self.guides: List[GuideItem] = []
        self._snap_lines: List[QLineF] = []
        self._move: Optional[_MoveState] = None
        self._update_rect()

    # ── basics ────────────────────────────────────────────────────────────────
    def page_rect(self) -> QRectF:
        return QRectF(0, 0, self.page_w, self.page_h)

    def margin_rect(self) -> QRectF:
        l, t, r, b = self.margins
        rect = QRectF(l, t, self.page_w - l - r, self.page_h - t - b)
        return rect if rect.width() > 0 and rect.height() > 0 else self.page_rect()

    def _update_rect(self):
        p = self.PASTEBOARD
        self.setSceneRect(-p, -p, self.page_w + 2 * p, self.page_h + 2 * p)

    def push(self, cmd):
        if self.doc is not None:
            self.doc.undo_stack.push(cmd)
        else:  # pragma: no cover - scenes are always owned by a Document
            cmd.redo()

    def content_changed(self):
        if self.doc is not None:
            self.doc.pageContentChanged.emit(self)

    def view_options_changed(self):
        show = self.doc.view.show_guides if self.doc is not None else True
        for g in self.guides:
            g.setVisible(show)          # hidden guides must not catch clicks either
            g.update()
        self.update()

    def set_zoom(self, z: float):
        if abs(z - self.zoom) < 1e-9:
            return
        self.zoom = z
        from .items.base import BaseItem
        for it in self.items():
            if isinstance(it, (BaseItem, GuideItem)):
                it.prepareGeometryChange()
        self.update()

    # ── page setup ──────────────────────────────────────────────────────────
    def setup_state(self) -> dict:
        return {
            "width": self.page_w,
            "height": self.page_h,
            "margins": list(self.margins),
            "columns": self.columns,
            "rows": self.rows,
            "gutter": self.gutter,
            "background": self.background.name(QColor.NameFormat.HexArgb),
        }

    def apply_setup(self, st: dict):
        self.page_w = max(18.0, float(st.get("width", self.page_w)))
        self.page_h = max(18.0, float(st.get("height", self.page_h)))
        m = st.get("margins", self.margins)
        if isinstance(m, (int, float)):
            m = [m] * 4
        self.margins = [max(0.0, float(v)) for v in list(m)[:4]] + [0.0] * (4 - len(list(m)[:4]))
        self.columns = max(1, min(24, int(st.get("columns", self.columns))))
        self.rows = max(1, min(60, int(st.get("rows", self.rows))))
        self.gutter = max(0.0, float(st.get("gutter", self.gutter)))
        bg = QColor(st.get("background", self.background.name(QColor.NameFormat.HexArgb)))
        self.background = bg if bg.isValid() else QColor("white")
        self._update_rect()
        for g in self.guides:
            g.prepareGeometryChange()
        self.update()

    # ── items ────────────────────────────────────────────────────────────────
    def top_items(self) -> List["BaseItem"]:
        from .items.base import BaseItem
        return sorted((i for i in self.items() if isinstance(i, BaseItem) and i.parentItem() is None),
                      key=lambda i: i.zValue())

    def all_design_items(self) -> List["BaseItem"]:
        from .items.base import BaseItem
        return [i for i in self.items() if isinstance(i, BaseItem)]

    def selected_top(self) -> List["BaseItem"]:
        from .items.base import BaseItem
        return sorted((i for i in self.selectedItems() if isinstance(i, BaseItem)
                       and i.parentItem() is None), key=lambda i: i.zValue())

    def next_z(self) -> float:
        tops = self.top_items()
        return (tops[-1].zValue() + 1) if tops else 1.0

    def find_uid(self, uid: str) -> Optional["BaseItem"]:
        for it in self.all_design_items():
            if it.uid == uid:
                return it
        return None

    # ── guides ──────────────────────────────────────────────────────────────
    def attach_guide(self, g: GuideItem):
        if g not in self.guides:
            self.guides.append(g)
        if g.scene() is not self:
            self.addItem(g)
        g.setVisible(self.doc.view.show_guides if self.doc is not None else True)
        self.update()

    def detach_guide(self, g: GuideItem):
        if g in self.guides:
            self.guides.remove(g)
        if g.scene() is self:
            self.removeItem(g)
        self.update()

    def guide_state(self) -> List[dict]:
        return [{"orient": g.orient, "pos": round(g.position, 4)} for g in self.guides]

    # ── layout guide lines (margins/columns/rows) ───────────────────────────
    def layout_lines(self) -> Tuple[List[float], List[float]]:
        inner = self.margin_rect()
        xs = [inner.left(), inner.right()]
        ys = [inner.top(), inner.bottom()]
        if self.columns > 1:
            cw = (inner.width() - self.gutter * (self.columns - 1)) / self.columns
            for i in range(1, self.columns):
                x = inner.left() + i * cw + (i - 1) * self.gutter
                xs += [x, x + self.gutter] if self.gutter > 0 else [x]
        if self.rows > 1:
            rh = (inner.height() - self.gutter * (self.rows - 1)) / self.rows
            for i in range(1, self.rows):
                y = inner.top() + i * rh + (i - 1) * self.gutter
                ys += [y, y + self.gutter] if self.gutter > 0 else [y]
        return xs, ys

    # ── painting ─────────────────────────────────────────────────────────────
    def drawBackground(self, p: QPainter, rect: QRectF):
        pr = self.page_rect()
        if not self.rendering:
            p.fillRect(rect, theme.color("canvas"))
            p.fillRect(pr.translated(4 / max(self.zoom, .05), 4 / max(self.zoom, .05)),
                       QColor(0, 0, 0, 60))
        p.fillRect(pr, self.background)
        if self.rendering:
            return
        v = self.doc.view
        if v.show_grid and v.grid_size >= 1:
            p.save()
            p.setClipRect(pr)
            pen = QPen(theme.color("c_grid"), 0)
            pen.setCosmetic(True)
            p.setPen(pen)
            gs = v.grid_size
            # thin out the grid when zoomed far out so it stays readable
            while gs * self.zoom < 6:
                gs *= 2
            x = 0.0
            while x <= pr.right():
                p.drawLine(QPointF(x, 0), QPointF(x, pr.bottom()))
                x += gs
            y = 0.0
            while y <= pr.bottom():
                p.drawLine(QPointF(0, y), QPointF(pr.right(), y))
                y += gs
            p.restore()
        if v.show_guides:
            p.save()
            pen = QPen(theme.color("c_margin"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            inner = self.margin_rect()
            p.drawRect(inner)
            xs, ys = self.layout_lines()
            for x in xs[2:]:
                p.drawLine(QPointF(x, inner.top()), QPointF(x, inner.bottom()))
            for y in ys[2:]:
                p.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y))
            p.restore()
        pen = QPen(QColor(0, 0, 0, 90), 0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(pr)

    def drawForeground(self, p: QPainter, rect: QRectF):
        if self.rendering or not self._snap_lines:
            return
        pen = QPen(theme.color("c_snap"), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        for ln in self._snap_lines:
            p.drawLine(ln)

    def set_snap_lines(self, lines: List[QLineF]):
        if lines or self._snap_lines:
            self._snap_lines = list(lines)
            self.update()

    # ── snapping ─────────────────────────────────────────────────────────────
    def snap_tolerance(self) -> float:
        return self.doc.view.snap_px / max(self.zoom, 0.05)

    def _candidates(self, exclude: Set[QGraphicsItem], guides: bool = True):
        v = self.doc.view
        pr = self.page_rect()
        xs = [pr.left(), pr.center().x(), pr.right()]
        ys = [pr.top(), pr.center().y(), pr.bottom()]
        lx, ly = self.layout_lines()
        xs += lx + [self.margin_rect().center().x()]
        ys += ly + [self.margin_rect().center().y()]
        if guides and v.snap_guides:
            for g in self.guides:
                (ys if g.orient == "H" else xs).append(g.position)
        if v.snap_objects:
            for it in self.top_items():
                if it in exclude or not it.isVisible():
                    continue
                r = it.scene_box()
                xs += [r.left(), r.center().x(), r.right()]
                ys += [r.top(), r.center().y(), r.bottom()]
        return xs, ys

    def _best(self, values: Iterable[float], cands: List[float], tol: float):
        best = None  # (abs, delta, target, is_grid)
        v = self.doc.view
        for val in values:
            for c in cands:
                d = c - val
                if abs(d) <= tol and (best is None or abs(d) < best[0] - 1e-9):
                    best = (abs(d), d, c, False)
            if v.snap_grid and v.grid_size >= 1:
                c = round(val / v.grid_size) * v.grid_size
                d = c - val
                if abs(d) <= tol and (best is None or abs(d) < best[0] - 1e-9):
                    best = (abs(d), d, c, True)
        return best

    def _line(self, axis: str, c: float) -> QLineF:
        r = self.sceneRect()
        if axis == "x":
            return QLineF(c, r.top(), c, r.bottom())
        return QLineF(r.left(), c, r.right(), c)

    def snap_rect(self, r: QRectF, exclude: Set[QGraphicsItem]) -> Tuple[float, float, List[QLineF]]:
        xs, ys = self._candidates(exclude)
        tol = self.snap_tolerance()
        bx = self._best([r.left(), r.center().x(), r.right()], xs, tol)
        by = self._best([r.top(), r.center().y(), r.bottom()], ys, tol)
        lines = []
        dx = dy = 0.0
        if bx:
            dx = bx[1]
            if not bx[3]:
                lines.append(self._line("x", bx[2]))
        if by:
            dy = by[1]
            if not by[3]:
                lines.append(self._line("y", by[2]))
        return dx, dy, lines

    def snap_value(self, v: float, axis: str, exclude: Set[QGraphicsItem],
                   guides: bool = True) -> Tuple[float, Optional[QLineF]]:
        xs, ys = self._candidates(exclude, guides=guides)
        b = self._best([v], xs if axis == "x" else ys, self.snap_tolerance())
        if not b:
            return v, None
        return b[2], (None if b[3] else self._line(axis, b[2]))

    # ── moving the selection (all selected items move as one) ────────────────
    def begin_move(self, scene_pos: QPointF) -> bool:
        items = [i for i in self.selected_top() if not i.locked]
        if not items:
            self._move = None
            return False
        bounds = QRectF()
        excl: Set[QGraphicsItem] = set()
        for it in items:
            bounds = bounds.united(it.scene_box()) if not bounds.isNull() else it.scene_box()
            excl.add(it)
            excl.update(it.childItems())
        self._move = _MoveState(QPointF(scene_pos), items, {i: QPointF(i.pos()) for i in items},
                                bounds, exclude=excl)
        return True

    def update_move(self, scene_pos: QPointF, mods: Qt.KeyboardModifier):
        m = self._move
        if m is None:
            return
        d = scene_pos - m.start
        if mods & Qt.KeyboardModifier.ShiftModifier:   # constrain to one axis
            if abs(d.x()) >= abs(d.y()):
                d.setY(0)
            else:
                d.setX(0)
        lines: List[QLineF] = []
        if not (mods & Qt.KeyboardModifier.AltModifier):
            dx, dy, lines = self.snap_rect(m.bounds.translated(d), m.exclude)
            if mods & Qt.KeyboardModifier.ShiftModifier:
                dx = dx if d.y() == 0 else 0
                dy = dy if d.x() == 0 else 0
            d += QPointF(dx, dy)
        if d.manhattanLength() > 0 or m.moved:
            m.moved = True
            for it in m.items:
                it.setPos(m.starts[it] + d)
        self.set_snap_lines(lines)

    def end_move(self) -> bool:
        m, self._move = self._move, None
        self.set_snap_lines([])
        if m is None or not m.moved:
            return False
        moves = {it: (m.starts[it], QPointF(it.pos())) for it in m.items
                 if it.pos() != m.starts[it]}
        if not moves:
            return False
        self.push(MoveItemsCmd(self, moves))
        return True

    def is_moving(self) -> bool:
        return self._move is not None

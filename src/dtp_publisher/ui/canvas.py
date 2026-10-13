# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""CanvasView (zoom, pan, drag & drop) and rulers that create guides."""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QGraphicsView, QSizePolicy, QWidget

from .. import theme
from ..commands import AddGuideCmd
from ..scene import GuideItem, PageScene
from ..units import UNITS

ZOOM_MIN, ZOOM_MAX = 0.1, 8.0
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


class CanvasView(QGraphicsView):
    zoomChanged = pyqtSignal(float)
    mouseScenePos = pyqtSignal(QPointF)
    viewChanged = pyqtSignal()
    contextRequested = pyqtSignal(QPoint, QPointF)      # global pos, scene pos
    filesDropped = pyqtSignal(list, QPointF)            # paths, scene pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.ContainsItemShape)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._zoom = 1.0
        self._space = False
        self._pan_from: Optional[QPoint] = None
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewChanged.emit())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewChanged.emit())

    # ── scene / zoom ─────────────────────────────────────────────────────────
    def page_scene(self) -> Optional[PageScene]:
        sc = self.scene()
        return sc if isinstance(sc, PageScene) else None

    def set_page(self, sc: PageScene):
        self.setScene(sc)
        sc.set_zoom(self._zoom)
        self.viewChanged.emit()

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float, anchor_view: Optional[QPoint] = None):
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if anchor_view is None:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        f = z / self._zoom
        self._zoom = z
        self.scale(f, f)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        sc = self.page_scene()
        if sc is not None:
            sc.set_zoom(z)
        self.zoomChanged.emit(z)
        self.viewChanged.emit()

    def zoom_by(self, factor: float):
        self.set_zoom(self._zoom * factor)

    def fit_page(self):
        sc = self.page_scene()
        if sc is None:
            return
        vp = self.viewport().rect()
        if vp.width() < 10 or vp.height() < 10:
            return
        pr = sc.page_rect()
        z = min((vp.width() - 40) / pr.width(), (vp.height() - 40) / pr.height())
        self.set_zoom(z)
        self.centerOn(pr.center())

    def fit_width(self):
        sc = self.page_scene()
        if sc is None:
            return
        vp = self.viewport().rect()
        pr = sc.page_rect()
        self.set_zoom((vp.width() - 40) / pr.width())
        self.centerOn(QPointF(pr.center().x(), self.mapToScene(vp.center()).y()))

    # ── events ───────────────────────────────────────────────────────────────
    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = e.angleDelta().y() / 120.0
            if steps:
                self.set_zoom(self._zoom * (1.15 ** steps), e.position().toPoint())
            e.accept()
            return
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - e.angleDelta().y())
            e.accept()
            return
        super().wheelEvent(e)

    def _editing_text(self) -> bool:
        sc = self.page_scene()
        if sc is None:
            return False
        fi = sc.focusItem()
        from PyQt6.QtWidgets import QGraphicsTextItem
        return isinstance(fi, QGraphicsTextItem) and bool(
            fi.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat() and not self._editing_text():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat() and self._space:
            self._space = False
            self.viewport().unsetCursor()
            e.accept()
            return
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton or (self._space and
                                                          e.button() == Qt.MouseButton.LeftButton):
            self._pan_from = e.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan_from is not None:
            d = e.position().toPoint() - self._pan_from
            self._pan_from = e.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        self.mouseScenePos.emit(self.mapToScene(e.position().toPoint()))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_from is not None:
            self._pan_from = None
            if self._space:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        sp = self.mapToScene(e.pos())
        sc = self.page_scene()
        if sc is not None:
            for it in sc.items(sp):
                if isinstance(it, GuideItem):
                    super().contextMenuEvent(e)
                    return
        self.contextRequested.emit(e.globalPos(), sp)
        e.accept()

    # drag & drop of pictures / publications
    def _paths(self, md) -> list:
        if not md.hasUrls():
            return []
        out = []
        for u in md.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                ext = os.path.splitext(p)[1].lower()
                if ext in IMAGE_EXTS or ext in (".dtpub", ".json", ".pub"):
                    out.append(p)
        return out

    def dragEnterEvent(self, e):
        if self._paths(e.mimeData()):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._paths(e.mimeData()):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        paths = self._paths(e.mimeData())
        if paths:
            self.filesDropped.emit(paths, self.mapToScene(e.position().toPoint()))
            e.acceptProposedAction()
            return
        super().dropEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.viewChanged.emit()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.viewChanged.emit()


class RulerWidget(QWidget):
    """Ruler along the top ('H') or left ('V') of the canvas.

    Drag from the top ruler to create a horizontal guide, from the left
    ruler for a vertical one — the guide follows the mouse onto the page.
    """

    def __init__(self, orient: str, view: CanvasView, units_getter):
        super().__init__()
        self.orient = orient
        self.view = view
        self._units = units_getter
        self._cursor = None
        self._sel: Optional[QRectF] = None
        self._drag: Optional[GuideItem] = None
        self.setObjectName("Ruler")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        th = 24
        if orient == "H":
            self.setFixedHeight(th)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setCursor(Qt.CursorShape.SplitVCursor)
            self.setToolTip("Drag down onto the page to add a horizontal guide")
        else:
            self.setFixedWidth(th)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            self.setCursor(Qt.CursorShape.SplitHCursor)
            self.setToolTip("Drag right onto the page to add a vertical guide")
        view.viewChanged.connect(self.update)
        view.mouseScenePos.connect(self._on_mouse)

    def _on_mouse(self, sp: QPointF):
        self._cursor = sp.x() if self.orient == "H" else sp.y()
        self.update()

    def set_selection(self, r: Optional[QRectF]):
        self._sel = QRectF(r) if r is not None else None
        self.update()

    def _map(self, v: float) -> float:
        """Scene coordinate → ruler pixel."""
        p = self.view.mapFromScene(QPointF(v, v))
        return float(p.x() if self.orient == "H" else p.y())

    def paintEvent(self, _):
        p = QPainter(self)
        t = theme.tokens()
        p.fillRect(self.rect(), QColor(t["panel_alt"]))
        sc = self.view.page_scene()
        if sc is None:
            return
        unit = self._units()
        upt = UNITS[unit]
        z = self.view.zoom()
        length = self.width() if self.orient == "H" else self.height()
        # page extent shading
        a, b = self._map(0), self._map(sc.page_w if self.orient == "H" else sc.page_h)
        page_col = QColor(t["panel"])
        if self.orient == "H":
            p.fillRect(QRectF(a, 0, b - a, self.height()), page_col)
        else:
            p.fillRect(QRectF(0, a, self.width(), b - a), page_col)
        if self._sel is not None:
            s0, s1 = ((self._sel.left(), self._sel.right()) if self.orient == "H"
                      else (self._sel.top(), self._sel.bottom()))
            c = QColor(t["accent"])
            c.setAlpha(70)
            m0, m1 = self._map(s0), self._map(s1)
            if self.orient == "H":
                p.fillRect(QRectF(m0, 0, m1 - m0, self.height()), c)
            else:
                p.fillRect(QRectF(0, m0, self.width(), m1 - m0), c)
        # ticks: choose a step so labels are ≥ 50px apart
        steps = {"mm": [1, 2, 5, 10, 20, 50, 100, 200, 500],
                 "in": [0.125, 0.25, 0.5, 1, 2, 5, 10, 20],
                 "pt": [1, 5, 10, 25, 50, 100, 200, 500, 1000]}[unit]
        major = steps[-1]
        for s in steps:
            if s * upt * z >= 50:
                major = s
                break
        minor = major / (10 if unit != "in" else 8)
        if minor * upt * z < 5:
            minor = major / 2
        fg = QColor(t["text_dim"])
        p.setPen(QPen(fg, 1))
        f = QFont(t["font"])
        f.setPixelSize(10)
        p.setFont(f)
        thick = self.height() if self.orient == "H" else self.width()
        # walk across the visible range in units
        v0 = self.view.mapToScene(0, 0)
        v1 = self.view.mapToScene(self.view.viewport().width(), self.view.viewport().height())
        lo = (v0.x() if self.orient == "H" else v0.y()) / upt
        hi = (v1.x() if self.orient == "H" else v1.y()) / upt
        k = int(lo // minor) - 1
        while k * minor <= hi + minor:
            u = k * minor
            px = self._map(u * upt)
            if 0 <= px <= length:
                is_major = abs(u / major - round(u / major)) < 1e-6
                half = abs((u / (major / 2)) - round(u / (major / 2))) < 1e-6
                ln = thick * (0.55 if is_major else 0.35 if half else 0.2)
                if self.orient == "H":
                    p.drawLine(QPointF(px, thick), QPointF(px, thick - ln))
                    if is_major:
                        p.drawText(QPointF(px + 3, 11), _fmt(u))
                else:
                    p.drawLine(QPointF(thick, px), QPointF(thick - ln, px))
                    if is_major:
                        p.save()
                        p.translate(11, px + 3)
                        p.rotate(90)
                        p.drawText(QPointF(0, 0), _fmt(u))
                        p.restore()
            k += 1
        if self._cursor is not None:
            p.setPen(QPen(QColor(t["danger"]), 1))
            c = self._map(self._cursor)
            if self.orient == "H":
                p.drawLine(QPointF(c, 0), QPointF(c, thick))
            else:
                p.drawLine(QPointF(0, c), QPointF(thick, c))
        p.setPen(QPen(QColor(t["border"]), 1))
        if self.orient == "H":
            p.drawLine(0, thick - 1, self.width(), thick - 1)
        else:
            p.drawLine(thick - 1, 0, thick - 1, self.height())

    # dragging out a guide
    def _scene_pos(self, global_pt) -> QPointF:
        vp = self.view.viewport().mapFromGlobal(global_pt)
        return self.view.mapToScene(vp)

    def mousePressEvent(self, e):
        sc = self.view.page_scene()
        if e.button() != Qt.MouseButton.LeftButton or sc is None:
            return
        if not sc.doc.view.show_guides:
            sc.doc.view.set("show_guides", True)     # a new guide should be visible
        sp = self._scene_pos(e.globalPosition().toPoint())
        g = GuideItem("H" if self.orient == "H" else "V", sp.y() if self.orient == "H" else sp.x())
        sc.attach_guide(g)
        self._drag = g

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        sp = self._scene_pos(e.globalPosition().toPoint())
        self._drag.set_position(sp.y() if self._drag.orient == "H" else sp.x())

    def mouseReleaseEvent(self, e):
        g, self._drag = self._drag, None
        sc = self.view.page_scene()
        if g is None or sc is None:
            return
        vp = self.view.viewport()
        inside = vp.rect().contains(vp.mapFromGlobal(e.globalPosition().toPoint()))
        sc.detach_guide(g)
        if inside:
            sc.push(AddGuideCmd(sc, g))


def _fmt(u: float) -> str:
    if abs(u - round(u)) < 1e-6:
        return str(int(round(u)))
    return f"{u:g}"

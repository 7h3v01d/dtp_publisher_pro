# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Page thumbnails down the left side (click to switch, drag to reorder)."""

from __future__ import annotations

from typing import Dict, Optional, Set

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem, QSizePolicy,
                             QToolButton, QVBoxLayout, QWidget)

from ... import theme
from ...document import Document
from ...export import render_thumbnail
from ...scene import PageScene
from ..icons import icon
from ..widgets import header_label

THUMB_W, THUMB_H = 120, 150


class _List(QListWidget):
    moveRequested = pyqtSignal(int, int)

    def dropEvent(self, e):
        src = self.currentRow()
        it = self.itemAt(e.position().toPoint())
        dst = self.row(it) if it is not None else self.count() - 1
        if it is not None:
            r = self.visualItemRect(it)
            if e.position().y() > r.center().y() and dst < src:
                dst += 1
            elif e.position().y() < r.center().y() and dst > src:
                dst -= 1
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        if src >= 0 and dst != src:
            self.moveRequested.emit(src, dst)


class ThumbPanel(QWidget):
    pageClicked = pyqtSignal(int)
    contextRequested = pyqtSignal(int, QPoint)
    moveRequested = pyqtSignal(int, int)
    addRequested = pyqtSignal()
    deleteRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ThumbPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(THUMB_W + 52)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        v.addWidget(header_label("Pages"))
        self.list = _List()
        self.list.setIconSize(QSize(THUMB_W + 20, THUMB_H))
        self.list.setSpacing(4)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.customContextMenuRequested.connect(self._ctx)
        self.list.moveRequested.connect(self.moveRequested)
        v.addWidget(self.list, 1)
        row = QVBoxLayout()                 # one above the other: full labels at any width
        row.setSpacing(4)
        self.btn_add = QToolButton()
        self.btn_add.setText("Add page")
        self.btn_add.setToolTip("Add a new page after this one")
        self.btn_del = QToolButton()
        self.btn_del.setText("Delete")
        self.btn_del.setToolTip("Delete this page")
        for b in (self.btn_add, self.btn_del):
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setIconSize(QSize(18, 18))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(b)
        self.btn_add.clicked.connect(self.addRequested)
        self.btn_del.clicked.connect(self.deleteRequested)
        v.addLayout(row)
        self._doc: Optional[Document] = None
        self._cache: Dict[int, QPixmap] = {}
        self._dirty: Set[int] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._render_dirty)
        self._quiet = False
        self.refresh_icons()

    def refresh_icons(self):
        self.btn_add.setIcon(icon("page_add", 18))
        self.btn_del.setIcon(icon("page_del", 18))
        self._cache.clear()
        if self._doc is not None:
            self.rebuild(self.list.currentRow())

    # ── model ────────────────────────────────────────────────────────────────
    def set_document(self, doc: Document, current: int = 0):
        self._doc = doc
        self._cache.clear()
        self.rebuild(current)

    def rebuild(self, current: int):
        doc = self._doc
        if doc is None:
            return
        self._quiet = True
        self.list.clear()
        for i, sc in enumerate(doc.pages):
            it = QListWidgetItem()
            it.setIcon(self._icon(sc, i))
            it.setToolTip(doc.page_label(sc))
            it.setSizeHint(QSize(THUMB_W + 24, THUMB_H + 8))
            self.list.addItem(it)
        self.list.setCurrentRow(max(0, min(current, len(doc.pages) - 1)))
        self._quiet = False
        self.btn_del.setEnabled(len(doc.pages) > 1)

    def set_current(self, idx: int):
        self._quiet = True
        self.list.setCurrentRow(idx)
        self._quiet = False
        it = self.list.item(idx)
        if it is not None:
            self.list.scrollToItem(it)

    def mark_dirty(self, scene: PageScene):
        if self._doc is None:
            return
        self._cache.pop(id(scene), None)
        self._dirty.add(id(scene))
        self._timer.start()

    def _render_dirty(self):
        if self._doc is None:
            return
        for i, sc in enumerate(self._doc.pages):
            if id(sc) in self._dirty:
                it = self.list.item(i)
                if it is not None:
                    it.setIcon(self._icon(sc, i))
        self._dirty.clear()

    def _icon(self, sc: PageScene, idx: int) -> QIcon:
        pm = self._pixmap(sc, idx)
        ic = QIcon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
            ic.addPixmap(pm, mode)       # no blue tint over the selected page
        return ic

    def _pixmap(self, sc: PageScene, idx: int) -> QPixmap:
        pm = self._cache.get(id(sc))
        if pm is None:
            img = render_thumbnail(sc, THUMB_W, THUMB_H - 6)
            pm = QPixmap.fromImage(img)
            self._cache[id(sc)] = pm
        # compose: number on the left, shadowed page on the right
        out = QPixmap(THUMB_W + 20, THUMB_H)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        x = 20 + (THUMB_W - pm.width()) / 2
        y = (THUMB_H - pm.height()) / 2
        p.fillRect(QRectF(x + 2, y + 2, pm.width(), pm.height()), QColor(0, 0, 0, 50))
        p.drawPixmap(int(x), int(y), pm)
        p.setPen(QPen(QColor(0, 0, 0, 80), 1))
        p.drawRect(QRectF(x, y, pm.width() - 1, pm.height() - 1))
        f = QFont(theme.tokens()["font"])
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme.color("text"))
        p.drawText(QRectF(0, 0, 18, THUMB_H), Qt.AlignmentFlag.AlignCenter, str(idx + 1))
        p.end()
        return out

    # ── events ───────────────────────────────────────────────────────────────
    def _row_changed(self, row: int):
        if not self._quiet and row >= 0:
            self.pageClicked.emit(row)

    def _ctx(self, pos: QPoint):
        it = self.list.itemAt(pos)
        row = self.list.row(it) if it is not None else self.list.currentRow()
        self.contextRequested.emit(row, self.list.viewport().mapToGlobal(pos))

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Objects panel: every object on the page, front to back, with show/lock."""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QToolButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ...commands import PropCmd
from ...items import BaseItem, GroupItem
from ...scene import PageScene
from ..icons import icon
from ..widgets import header_label, hint_label

ROLE = Qt.ItemDataRole.UserRole


class LayersPanel(QWidget):
    arrangeRequested = pyqtSignal(str)     # "forward" | "backward"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        v.addWidget(header_label("Objects on this page"))
        v.addWidget(hint_label("Top of the list is in front. Click to select; double-click a "
                               "name to rename. Tick boxes show/hide and lock objects."))
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Object", "Show", "Lock"])
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree.itemSelectionChanged.connect(self._tree_sel)
        self.tree.itemChanged.connect(self._item_changed)
        v.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.btn_fwd = QToolButton()
        self.btn_fwd.setText("Bring forward")
        self.btn_bwd = QToolButton()
        self.btn_bwd.setText("Send backward")
        for b in (self.btn_fwd, self.btn_bwd):
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            row.addWidget(b)
        self.btn_fwd.clicked.connect(lambda: self.arrangeRequested.emit("forward"))
        self.btn_bwd.clicked.connect(lambda: self.arrangeRequested.emit("backward"))
        v.addLayout(row)
        self.scene: Optional[PageScene] = None
        self._map: Dict[str, BaseItem] = {}
        self._quiet = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.rebuild)
        self.refresh_icons()

    def refresh_icons(self):
        self.btn_fwd.setIcon(icon("forward", 18))
        self.btn_bwd.setIcon(icon("backward", 18))

    def set_scene(self, sc: Optional[PageScene]):
        self.scene = sc
        self.rebuild()

    def schedule(self):
        self._timer.start()

    def rebuild(self):
        self._quiet = True
        self.tree.clear()
        self._map.clear()
        sc = self.scene
        if sc is not None:
            for it in reversed(sc.top_items()):
                self.tree.addTopLevelItem(self._row(it))
        self._quiet = False
        self.sync_selection()

    def _row(self, it: BaseItem, member: bool = False) -> QTreeWidgetItem:
        r = QTreeWidgetItem([it.display_name(), "", ""])
        r.setData(0, ROLE, it.uid)
        self._map[it.uid] = it
        flags = Qt.ItemFlag.ItemIsEnabled
        if not member:
            flags |= (Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                      | Qt.ItemFlag.ItemIsUserCheckable)
        r.setFlags(flags)
        if not member:
            r.setCheckState(1, Qt.CheckState.Unchecked if it.hidden else Qt.CheckState.Checked)
            r.setCheckState(2, Qt.CheckState.Checked if it.locked else Qt.CheckState.Unchecked)
            r.setToolTip(1, "Show or hide")
            r.setToolTip(2, "Lock in place")
        if isinstance(it, GroupItem):
            for m in reversed(it.members()):
                r.addChild(self._row(m, member=True))
        return r

    def sync_selection(self):
        sc = self.scene
        if sc is None:
            return
        sel = {i.uid for i in sc.selected_top()}
        self._quiet = True
        for i in range(self.tree.topLevelItemCount()):
            r = self.tree.topLevelItem(i)
            r.setSelected(r.data(0, ROLE) in sel)
        self._quiet = False

    def _items_for(self, rows: List[QTreeWidgetItem]) -> List[BaseItem]:
        return [self._map[r.data(0, ROLE)] for r in rows if r.data(0, ROLE) in self._map]

    def _tree_sel(self):
        if self._quiet or self.scene is None:
            return
        items = self._items_for(self.tree.selectedItems())
        self.scene.blockSignals(True)
        self.scene.clearSelection()
        for it in items:
            it.setSelected(True)
        self.scene.blockSignals(False)
        self.scene.selectionChanged.emit()

    def _item_changed(self, row: QTreeWidgetItem, col: int):
        if self._quiet or self.scene is None:
            return
        it = self._map.get(row.data(0, ROLE))
        if it is None:
            return
        sc = self.scene
        if col == 0:
            name = row.text(0).strip()
            if name and name != it.display_name():
                sc.push(PropCmd(sc, [it], "name", name, text="Rename object"))
        elif col == 1:
            hidden = row.checkState(1) != Qt.CheckState.Checked
            if hidden != it.hidden:
                sc.push(PropCmd(sc, [it], "hidden", hidden, text="Hide" if hidden else "Show"))
        elif col == 2:
            locked = row.checkState(2) == Qt.CheckState.Checked
            if locked != it.locked:
                sc.push(PropCmd(sc, [it], "locked", locked, text="Lock" if locked else "Unlock"))

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Start screen: pick a template or blank size, or open a recent publication."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget)

from ... import templates
from ...document import Document
from ...export import render_thumbnail
from ...units import PAGE_SIZE_BY_KEY, inch, mm
from ..icons import icon

BLANKS: List[Tuple[str, str, float, float]] = [
    ("blank_a4", "Blank A4 (portrait)", PAGE_SIZE_BY_KEY["a4"].width, PAGE_SIZE_BY_KEY["a4"].height),
    ("blank_a4l", "Blank A4 (landscape)", PAGE_SIZE_BY_KEY["a4"].height, PAGE_SIZE_BY_KEY["a4"].width),
    ("blank_a5", "Blank A5", PAGE_SIZE_BY_KEY["a5"].width, PAGE_SIZE_BY_KEY["a5"].height),
    ("blank_a3", "Blank A3 poster", PAGE_SIZE_BY_KEY["a3"].width, PAGE_SIZE_BY_KEY["a3"].height),
    ("blank_letter", "Blank US Letter", inch(8.5), inch(11)),
    ("blank_5x7", "Blank card 5 × 7 in", inch(5), inch(7)),
    ("blank_sq", "Blank square 8 × 8 in", inch(8), inch(8)),
    ("blank_dl", "Blank DL flyer (99 × 210 mm)", mm(99), mm(210)),
]

_thumb_cache: Dict[str, QPixmap] = {}
TILE = QSize(170, 200)


def _thumb_for_doc(doc: Document) -> QPixmap:
    """Page preview with a border and drop shadow, centred on a fixed tile."""
    from PyQt6.QtGui import QColor, QPainter, QPen
    tw, th = TILE.width() - 20, TILE.height() - 20
    img = render_thumbnail(doc.pages[0], tw - 8, th - 8)
    out = QPixmap(tw, th)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    x, y = (tw - img.width()) // 2, (th - img.height()) // 2
    p.fillRect(x + 3, y + 3, img.width(), img.height(), QColor(0, 0, 0, 55))
    p.drawImage(x, y, img)
    p.setPen(QPen(QColor(0, 0, 0, 110), 1))
    p.drawRect(x, y, img.width() - 1, img.height() - 1)
    p.end()
    return out


class StartDialog(QDialog):
    """Returns either ``self.document`` (new) or ``self.open_path`` (open)."""

    def __init__(self, recent: List[str], show_start: bool, parent=None, first_run=False):
        super().__init__(parent)
        self.setWindowTitle("New publication")
        self.resize(1100, 720)
        self.document: Optional[Document] = None
        self.open_path: Optional[str] = None
        self.open_other = False
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        hdr = QLabel("What would you like to make?")
        hdr.setObjectName("StartHeader")
        root.addWidget(hdr)
        sub = QLabel("Pick a design to start from — you can change everything afterwards. "
                     "Double-click to open it.")
        sub.setObjectName("HintLabel")
        root.addWidget(sub)
        split = QSplitter()
        root.addWidget(split, 1)

        # categories
        self.cats = QListWidget()
        self.cats.setMaximumWidth(250)
        self.cats.setIconSize(QSize(22, 22))
        cat_icons = {"Blank page": "new", "Flyers & posters": "picture",
                     "Newsletters": "columns", "Cards & invitations": "wordart",
                     "Labels & business cards": "fill_page", "Photo albums": "placeholder"}
        for c in ["All designs", "Blank page"] + templates.CATEGORIES:
            QListWidgetItem(icon(cat_icons.get(c, "templates"), 22), c, self.cats)
        self.cats.currentRowChanged.connect(self._filter)
        split.addWidget(self.cats)

        # gallery
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(TILE.width() - 20, TILE.height() - 20))
        self.gallery.setGridSize(QSize(TILE.width() + 16, TILE.height() + 52))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setWordWrap(True)
        self.gallery.setSpacing(6)
        self.gallery.itemDoubleClicked.connect(lambda _: self._create())
        self.gallery.currentItemChanged.connect(self._describe)
        mv.addWidget(self.gallery, 1)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setMinimumHeight(40)
        mv.addWidget(self.desc)
        split.addWidget(mid)

        # recent
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Open a recent publication")
        lbl.setObjectName("StartSub")
        rv.addWidget(lbl)
        self.recent = QListWidget()
        self.recent.setIconSize(QSize(18, 18))
        for p in recent:
            it = QListWidgetItem(icon("recent", 18), os.path.basename(p), self.recent)
            it.setToolTip(p)
            it.setData(Qt.ItemDataRole.UserRole, p)
        if not recent:
            it = QListWidgetItem("(nothing yet)", self.recent)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
        self.recent.itemDoubleClicked.connect(self._open_recent)
        rv.addWidget(self.recent, 1)
        b = QPushButton(icon("open", 20), "  Open another file…")
        b.clicked.connect(self._open_other)
        rv.addWidget(b)
        right.setMaximumWidth(300)
        split.addWidget(right)
        split.setSizes([210, 620, 260])

        bottom = QHBoxLayout()
        self.cb_show = QCheckBox("Show this screen when the program starts")
        self.cb_show.setChecked(show_start)
        bottom.addWidget(self.cb_show)
        bottom.addStretch(1)
        cancel = QPushButton("Cancel" if not first_run else "Start with a blank page")
        cancel.clicked.connect(self.reject)
        self.btn_create = QPushButton("Create")
        self.btn_create.setObjectName("Primary")
        self.btn_create.setDefault(True)
        self.btn_create.clicked.connect(self._create)
        bottom.addWidget(cancel)
        bottom.addWidget(self.btn_create)
        root.addLayout(bottom)

        self._entries = self._make_entries()
        self.cats.setCurrentRow(0)

    def _make_entries(self):
        out = []
        for t in templates.TEMPLATES:
            out.append((t.category, t.key, t.name, t.description, ("tmpl", t.key)))
        for key, name, w, h in BLANKS:
            out.append(("Blank page", key, name, "An empty page to design from scratch.",
                        ("blank", w, h)))
        return out

    def _pixmap(self, key: str, spec) -> QPixmap:
        if key not in _thumb_cache:
            if spec[0] == "blank":
                doc = templates.blank(spec[1], spec[2])
            else:
                doc = templates.build(spec[1])
            _thumb_cache[key] = _thumb_for_doc(doc)
        return _thumb_cache[key]

    def _filter(self, row: int):
        cat = self.cats.item(row).text() if row >= 0 else "All designs"
        self.gallery.clear()
        for c, key, name, desc, spec in self._entries:
            if cat != "All designs" and c != cat:
                continue
            pm = self._pixmap(key, spec)
            ic = QIcon()
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
                ic.addPixmap(pm, mode)
            it = QListWidgetItem(ic, name, self.gallery)
            it.setData(Qt.ItemDataRole.UserRole, spec)
            it.setData(Qt.ItemDataRole.UserRole + 1, desc)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        if self.gallery.count():
            self.gallery.setCurrentRow(0)

    def _describe(self, cur, _prev=None):
        if cur is None:
            self.desc.setText("")
            return
        self.desc.setText(f"<b>{cur.text()}</b> — {cur.data(Qt.ItemDataRole.UserRole + 1)}")

    def _create(self):
        it = self.gallery.currentItem()
        if it is None:
            return
        spec = it.data(Qt.ItemDataRole.UserRole)
        if spec[0] == "blank":
            self.document = templates.blank(spec[1], spec[2])
        else:
            self.document = templates.build(spec[1])
            self.document.title = ""
        self.accept()

    def _open_recent(self, it):
        p = it.data(Qt.ItemDataRole.UserRole)
        if p:
            self.open_path = p
            self.accept()

    def _open_other(self):
        self.open_other = True
        self.accept()

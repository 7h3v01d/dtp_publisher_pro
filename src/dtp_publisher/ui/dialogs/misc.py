# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Preferences, export-pictures, fill-page, recovery and about dialogs."""

from __future__ import annotations

import datetime as _dt
import os
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QRadioButton, QSpinBox, QVBoxLayout)

from ... import APP_NAME, __version__, winassoc
from ...settings import UI_SCALES, Settings
from ...theme import THEMES
from ...units import UNIT_LABELS
from ..widgets import UnitSpin, hint_label


class PreferencesDialog(QDialog):
    def __init__(self, s: Settings, parent=None, assoc_registry=None):
        super().__init__(parent)
        self._assoc_registry = assoc_registry
        self.setWindowTitle("Preferences")
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.theme = QComboBox()
        for k, t in THEMES.items():
            self.theme.addItem(t["label"], k)
        self.theme.setCurrentIndex(self.theme.findData(s.theme))
        f.addRow("Look:", self.theme)
        self.scale = QComboBox()
        for x in UI_SCALES:
            self.scale.addItem(f"{int(x * 100)}%", x)
        self.scale.setCurrentIndex(self.scale.findData(s.ui_scale))
        f.addRow("Size of buttons and text:", self.scale)
        f.addRow(hint_label("A new size takes effect the next time the program starts."))
        self.units = QComboBox()
        for k, lbl in UNIT_LABELS.items():
            self.units.addItem(lbl, k)
        self.units.setCurrentIndex(self.units.findData(s.units))
        f.addRow("Measure in:", self.units)
        self.autosave = QSpinBox()
        self.autosave.setRange(0, 60)
        self.autosave.setSuffix(" minutes")
        self.autosave.setSpecialValueText("Off")
        self.autosave.setValue(s.autosave_minutes)
        f.addRow("Save a recovery copy every:", self.autosave)
        self.backup = QCheckBox("Keep the previous version as a .bak file when saving")
        self.backup.setChecked(s.keep_backup)
        f.addRow(self.backup)
        self.start = QCheckBox("Show the start screen when the program opens")
        self.start.setChecked(s.show_start)
        f.addRow(self.start)
        self.splash = QCheckBox("Show the welcome picture while the program starts")
        self.splash.setChecked(s.show_splash)
        f.addRow(self.splash)
        v.addLayout(f)
        self.assoc = {}
        if winassoc.supported() or assoc_registry is not None:
            v.addWidget(self._assoc_group())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _assoc_group(self) -> QGroupBox:
        """Windows: which files open in this program when double-clicked."""
        g = QGroupBox("Double-click to open")
        lay = QVBoxLayout(g)
        lay.addWidget(QLabel("Open these files with DTP Publisher when they are "
                             "double-clicked in File Explorer:"))
        notes = []
        for ext, t in winassoc.TYPES.items():
            st = winassoc.status(ext, self._assoc_registry)
            cb = QCheckBox(t["choice"])
            cb.setChecked(st.registered)
            self.assoc[ext] = cb
            lay.addWidget(cb)
            if st.needs_confirming:
                notes.append(ext)
        self.assoc_note = hint_label(
            "Windows is still opening " + " and ".join(notes) + " files with another program. "
            "Click the button below and choose DTP Publisher Pro." if notes else
            "Windows may ask you once which program to use - choose DTP Publisher Pro.")
        lay.addWidget(self.assoc_note)
        self.btn_default_apps = QPushButton("Choose in Windows Settings…")
        self.btn_default_apps.clicked.connect(winassoc.open_default_apps_settings)
        row = QHBoxLayout()
        row.addWidget(self.btn_default_apps)
        row.addStretch(1)
        lay.addLayout(row)
        return g

    def assoc_wanted(self) -> Optional[List[str]]:
        """The file types ticked, or None if this section isn't shown."""
        if not self.assoc:
            return None
        return [e for e, cb in self.assoc.items() if cb.isChecked()]

    def apply_to(self, s: Settings):
        s.theme = self.theme.currentData()
        s.ui_scale = self.scale.currentData()
        s.units = self.units.currentData()
        s.autosave_minutes = self.autosave.value()
        s.keep_backup = self.backup.isChecked()
        s.show_start = self.start.isChecked()
        s.show_splash = self.splash.isChecked()


class ExportPicturesDialog(QDialog):
    def __init__(self, page_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save as picture")
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.fmt = QComboBox()
        self.fmt.addItem("PNG (best quality)", "png")
        self.fmt.addItem("JPEG (smaller, good for email)", "jpg")
        f.addRow("Type:", self.fmt)
        self.dpi = QComboBox()
        for label, d in (("Screen / email (96 dpi)", 96), ("Good (150 dpi)", 150),
                         ("Print quality (300 dpi)", 300)):
            self.dpi.addItem(label, d)
        self.dpi.setCurrentIndex(1)
        f.addRow("Quality:", self.dpi)
        self.rb_cur = QRadioButton("This page only")
        self.rb_all = QRadioButton(f"All {page_count} pages (one picture each)")
        self.rb_cur.setChecked(True)
        self.rb_all.setEnabled(page_count > 1)
        g = QButtonGroup(self)
        g.addButton(self.rb_cur)
        g.addButton(self.rb_all)
        col = QVBoxLayout()
        col.addWidget(self.rb_cur)
        col.addWidget(self.rb_all)
        f.addRow("Pages:", col)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


class FillPageDialog(QDialog):
    def __init__(self, unit: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fill page with copies")
        v = QVBoxLayout(self)
        v.addWidget(hint_label("Copies of the selected object are laid out in rows and "
                               "columns inside the page margins — handy for labels, tickets "
                               "and business cards."))
        f = QFormLayout()
        self.gap_x = UnitSpin(unit, 0, 720)
        self.gap_y = UnitSpin(unit, 0, 720)
        f.addRow("Gap across:", self.gap_x)
        f.addRow("Gap down:", self.gap_y)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


class RecoveryDialog(QDialog):
    """Offer publications rescued from a crash/power cut."""

    def __init__(self, orphans: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recover unsaved work")
        self.chosen: Optional[dict] = None
        self.discard: List[dict] = []
        v = QVBoxLayout(self)
        v.addWidget(QLabel("<b>The program closed before some work was saved.</b>"))
        v.addWidget(hint_label("These recovery copies were found. Open one to carry on, "
                               "then save it."))
        self.list = QListWidget()
        for o in orphans:
            t = _dt.datetime.fromtimestamp(float(o.get("time", 0))).strftime("%d %b %Y, %I:%M %p")
            name = os.path.basename(o.get("original") or "") or o.get("title") or "Untitled"
            it = QListWidgetItem(f"{name}   —   {t}", self.list)
            it.setData(Qt.ItemDataRole.UserRole, o)
        self.list.setCurrentRow(0)
        v.addWidget(self.list)
        row = QHBoxLayout()
        b_open = QPushButton("Open")
        b_open.setObjectName("Primary")
        b_open.clicked.connect(self._open)
        b_del = QPushButton("Delete recovery copies")
        b_del.clicked.connect(self._delete)
        b_later = QPushButton("Decide later")
        b_later.clicked.connect(self.reject)
        for b in (b_open, b_del, b_later):
            row.addWidget(b)
        v.addLayout(row)
        self._all = orphans

    def _open(self):
        it = self.list.currentItem()
        if it is not None:
            self.chosen = it.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _delete(self):
        self.discard = list(self._all)
        self.accept()


def about_text() -> str:
    return (f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>A friendly desktop publishing program for flyers, newsletters, cards, "
            "labels and photo albums.</p>"
            "<p>© 2026 Leon Priest (GitHub: 7h3v01d)<br>Licensed under the Apache License 2.0.</p>")

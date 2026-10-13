# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Page setup: size, orientation, margins, layout guides, background."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QRadioButton, QSpinBox, QVBoxLayout)

from ...units import PAGE_SIZES, match_page_size, mm
from ..widgets import ColorButton, UnitSpin, hint_label


class PageSetupDialog(QDialog):
    def __init__(self, state: dict, unit: str, multi_page: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Page setup")
        self._unit = unit
        self._multi = multi_page
        v = QVBoxLayout(self)

        g = QGroupBox("Paper size")
        f = QFormLayout(g)
        self.cmb = QComboBox()
        self.cmb.addItem("Custom size", None)
        last_group = None
        for p in PAGE_SIZES:
            if p.group != last_group:
                self.cmb.insertSeparator(self.cmb.count())
                last_group = p.group
            self.cmb.addItem(p.name, p.key)
        f.addRow("Preset:", self.cmb)
        self.sp_w = UnitSpin(unit, 36, 14400)
        self.sp_h = UnitSpin(unit, 36, 14400)
        f.addRow("Width:", self.sp_w)
        f.addRow("Height:", self.sp_h)
        orow = QHBoxLayout()
        self.rb_port = QRadioButton("Portrait (tall)")
        self.rb_land = QRadioButton("Landscape (wide)")
        orow.addWidget(self.rb_port)
        orow.addWidget(self.rb_land)
        f.addRow("Orientation:", orow)
        v.addWidget(g)

        g2 = QGroupBox("Margins (the pink dashed guides)")
        f2 = QFormLayout(g2)
        self.m = [UnitSpin(unit, 0, 1440) for _ in range(4)]
        for lbl, sp in zip(("Left:", "Top:", "Right:", "Bottom:"), self.m):
            f2.addRow(lbl, sp)
        self.cb_same = QCheckBox("Same on all sides")
        f2.addRow(self.cb_same)
        f2.addRow(hint_label("Most home printers can't print right to the edge — keep "
                             "important things at least 5 mm inside."))
        v.addWidget(g2)

        g3 = QGroupBox("Layout guides")
        f3 = QFormLayout(g3)
        self.sp_cols = QSpinBox()
        self.sp_cols.setRange(1, 24)
        self.sp_rows = QSpinBox()
        self.sp_rows.setRange(1, 60)
        self.sp_gut = UnitSpin(unit, 0, 720)
        f3.addRow("Columns:", self.sp_cols)
        f3.addRow("Rows:", self.sp_rows)
        f3.addRow("Gap between:", self.sp_gut)
        v.addWidget(g3)

        g4 = QGroupBox("Page colour")
        f4 = QFormLayout(g4)
        self.btn_bg = ColorButton("Background", allow_none=False, alpha=False)
        f4.addRow(self.btn_bg)
        v.addWidget(g4)

        self.cb_all = QCheckBox("Apply size, margins and guides to every page")
        self.cb_all.setChecked(True)
        self.cb_all.setVisible(multi_page)
        v.addWidget(self.cb_all)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        # populate
        self.sp_w.set_pt(state["width"])
        self.sp_h.set_pt(state["height"])
        for sp, val in zip(self.m, state["margins"]):
            sp.set_pt(val)
        self.cb_same.setChecked(len({round(x, 2) for x in state["margins"]}) == 1)
        self.sp_cols.setValue(state["columns"])
        self.sp_rows.setValue(state["rows"])
        self.sp_gut.set_pt(state["gutter"])
        self.btn_bg.set_color(QColor(state["background"]))
        self._sync_preset()
        self._sync_orient()
        self.cmb.currentIndexChanged.connect(self._preset)
        self.sp_w.valueChanged.connect(self._dims_changed)
        self.sp_h.valueChanged.connect(self._dims_changed)
        self.rb_port.toggled.connect(self._orient)
        self.m[0].valueChanged.connect(self._same)

    def _sync_preset(self):
        key = match_page_size(self.sp_w.pt(), self.sp_h.pt())
        self.cmb.blockSignals(True)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(key)) if key else 0)
        self.cmb.blockSignals(False)

    def _sync_orient(self):
        self.rb_port.blockSignals(True)
        self.rb_land.blockSignals(True)
        land = self.sp_w.pt() > self.sp_h.pt()
        self.rb_land.setChecked(land)
        self.rb_port.setChecked(not land)
        self.rb_port.blockSignals(False)
        self.rb_land.blockSignals(False)

    def _preset(self, _):
        key = self.cmb.currentData()
        if not key:
            return
        p = next(x for x in PAGE_SIZES if x.key == key)
        w, h = p.width, p.height
        if self.rb_land.isChecked():
            w, h = max(w, h), min(w, h)
        self.sp_w.set_pt(w)
        self.sp_h.set_pt(h)
        self._sync_orient()

    def _dims_changed(self, _):
        self._sync_preset()
        self._sync_orient()

    def _orient(self, portrait: bool):
        w, h = self.sp_w.pt(), self.sp_h.pt()
        if portrait == (w > h):
            self.sp_w.set_pt(h)
            self.sp_h.set_pt(w)

    def _same(self, _):
        if self.cb_same.isChecked():
            for sp in self.m[1:]:
                sp.set_pt(self.m[0].pt())

    def result_state(self, base: dict) -> dict:
        st = dict(base)
        st.update(width=self.sp_w.pt(), height=self.sp_h.pt(),
                  margins=[sp.pt() for sp in self.m] if not self.cb_same.isChecked()
                  else [self.m[0].pt()] * 4,
                  columns=self.sp_cols.value(), rows=self.sp_rows.value(),
                  gutter=self.sp_gut.pt(),
                  background=self.btn_bg.color().name(QColor.NameFormat.HexArgb))
        return st

    def apply_all(self) -> bool:
        return self._multi and self.cb_all.isChecked()

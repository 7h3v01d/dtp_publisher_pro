# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""WordArt and table editors."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFontComboBox, QFormLayout, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...items.table import MAX_COLS, MAX_ROWS
from ...items.wordart import WARPS, wordart_path
from ..widgets import ColorButton, hint_label

WORDART_PRESETS = [
    ("Ocean", {"fill": "#1f5fbf", "fill2": "#7fb2ff", "stroke": "#0b2a5c", "gradient": True,
               "shadow": True}),
    ("Sunset", {"fill": "#d9480f", "fill2": "#ffd43b", "stroke": "#7a2000", "gradient": True,
                "shadow": True}),
    ("Gold", {"fill": "#a67c00", "fill2": "#ffe57f", "stroke": "#5c4300", "gradient": True,
              "shadow": True}),
    ("Rose", {"fill": "#b03a6b", "fill2": "#f4a6c8", "stroke": "#5e1336", "gradient": True,
              "shadow": True}),
    ("Forest", {"fill": "#2b8a3e", "fill2": "#b2f2bb", "stroke": "#0b3d16", "gradient": True,
                "shadow": True}),
    ("Classic black", {"fill": "#111111", "fill2": "#555555", "stroke": "#000000",
                       "gradient": False, "shadow": True}),
    ("White outline", {"fill": "#ffffff", "fill2": "#ffffff", "stroke": "#000000",
                       "gradient": False, "shadow": False}),
    ("Red poster", {"fill": "#e03131", "fill2": "#ff8787", "stroke": "#000000",
                    "gradient": False, "shadow": False}),
]


class _WordArtPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state: Dict[str, Any] = {}
        self.setMinimumSize(420, 140)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        st = self.state
        if not st:
            return
        r = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        f = QFont(st["font_family"])
        f.setBold(st["bold"])
        f.setItalic(st["italic"])
        path = wordart_path(st["text"], f, st["warp"], r.width(), r.height()).translated(
            r.left(), r.top())
        if st["shadow"]:
            p.fillPath(path.translated(3, 3), QColor(0, 0, 0, 90))
        if st["gradient"]:
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0, QColor(st["fill2"]))
            g.setColorAt(1, QColor(st["fill"]))
            p.setBrush(QBrush(g))
        else:
            p.setBrush(QColor(st["fill"]))
        sw = float(st["stroke_width"])
        p.setPen(QPen(QColor(st["stroke"]), sw) if sw > 0 else Qt.PenStyle.NoPen)
        p.drawPath(path)


class WordArtDialog(QDialog):
    def __init__(self, state: Dict[str, Any], parent=None, title="WordArt"):
        super().__init__(parent)
        self.setWindowTitle(title)
        v = QVBoxLayout(self)
        self.preview = _WordArtPreview()
        v.addWidget(self.preview)
        f = QFormLayout()
        self.ed = QLineEdit(state.get("text", "Your Text Here"))
        self.ed.setMinimumWidth(360)
        f.addRow("Text:", self.ed)
        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont(state.get("font_family", "Arial Black")))
        frow = QHBoxLayout()
        frow.addWidget(self.font_box, 1)
        self.cb_b = QCheckBox("Bold")
        self.cb_b.setChecked(bool(state.get("bold", True)))
        self.cb_i = QCheckBox("Italic")
        self.cb_i.setChecked(bool(state.get("italic", False)))
        frow.addWidget(self.cb_b)
        frow.addWidget(self.cb_i)
        f.addRow("Font:", frow)
        self.warp = QComboBox()
        for k, lbl in WARPS.items():
            self.warp.addItem(lbl, k)
        self.warp.setCurrentIndex(max(0, self.warp.findData(state.get("warp", "none"))))
        f.addRow("Shape:", self.warp)
        v.addLayout(f)
        v.addWidget(QLabel("Quick styles:"))
        grid = QGridLayout()
        for i, (name, ps) in enumerate(WORDART_PRESETS):
            b = QPushButton(name)
            b.setStyleSheet(f"QPushButton{{color:{ps['fill']}; font-weight:700;}}")
            b.clicked.connect(lambda _=False, p=ps: self._preset(p))
            grid.addWidget(b, i // 4, i % 4)
        v.addLayout(grid)
        c = QHBoxLayout()
        self.c_fill = ColorButton("Fill", allow_none=False)
        self.c_fill2 = ColorButton("Highlight", allow_none=False)
        self.c_line = ColorButton("Outline", allow_none=False)
        for b, k in ((self.c_fill, "fill"), (self.c_fill2, "fill2"), (self.c_line, "stroke")):
            b.set_color(QColor(state.get(k, "#000000")))
            b.colorPicked.connect(lambda _c: self._update())
            c.addWidget(b)
        v.addLayout(c)
        o = QHBoxLayout()
        self.cb_grad = QCheckBox("Gradient")
        self.cb_grad.setChecked(bool(state.get("gradient", True)))
        self.cb_shadow = QCheckBox("Shadow")
        self.cb_shadow.setChecked(bool(state.get("shadow", True)))
        self.sp_w = QDoubleSpinBox()
        self.sp_w.setRange(0, 20)
        self.sp_w.setSingleStep(0.5)
        self.sp_w.setSuffix(" pt outline")
        self.sp_w.setValue(float(state.get("stroke_width", 1.5)))
        for w in (self.cb_grad, self.cb_shadow, self.sp_w):
            o.addWidget(w)
        v.addLayout(o)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for sig in (self.ed.textChanged, self.font_box.currentFontChanged, self.cb_b.toggled,
                    self.cb_i.toggled, self.warp.currentIndexChanged, self.cb_grad.toggled,
                    self.cb_shadow.toggled, self.sp_w.valueChanged):
            sig.connect(lambda *_: self._update())
        self._update()

    def _preset(self, ps):
        self.c_fill.set_color(QColor(ps["fill"]))
        self.c_fill2.set_color(QColor(ps["fill2"]))
        self.c_line.set_color(QColor(ps["stroke"]))
        self.cb_grad.setChecked(ps["gradient"])
        self.cb_shadow.setChecked(ps["shadow"])
        self._update()

    def state(self) -> Dict[str, Any]:
        return {"text": self.ed.text() or " ", "font_family": self.font_box.currentFont().family(),
                "bold": self.cb_b.isChecked(), "italic": self.cb_i.isChecked(),
                "warp": self.warp.currentData(), "gradient": self.cb_grad.isChecked(),
                "shadow": self.cb_shadow.isChecked(),
                "fill": self.c_fill.color().name(QColor.NameFormat.HexArgb),
                "fill2": self.c_fill2.color().name(QColor.NameFormat.HexArgb),
                "stroke": self.c_line.color().name(QColor.NameFormat.HexArgb),
                "stroke_width": self.sp_w.value()}

    def _update(self):
        self.preview.state = self.state()
        self.preview.update()


class TableDialog(QDialog):
    def __init__(self, state: Dict[str, Any], parent=None, title="Edit table"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 520)
        self._state = dict(state)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.sp_r = QSpinBox()
        self.sp_r.setRange(1, MAX_ROWS)
        self.sp_r.setValue(int(state["rows"]))
        self.sp_c = QSpinBox()
        self.sp_c.setRange(1, MAX_COLS)
        self.sp_c.setValue(int(state["cols"]))
        top.addWidget(QLabel("Rows:"))
        top.addWidget(self.sp_r)
        top.addWidget(QLabel("Columns:"))
        top.addWidget(self.sp_c)
        top.addSpacing(16)
        self.cb_head = QCheckBox("First row is a heading")
        self.cb_head.setChecked(bool(state.get("header", True)))
        self.cb_band = QCheckBox("Shade every other row")
        self.cb_band.setChecked(bool(state.get("banded", True)))
        top.addWidget(self.cb_head)
        top.addWidget(self.cb_band)
        top.addStretch(1)
        v.addLayout(top)
        v.addWidget(hint_label("Type into the cells below. Press Tab to move to the next cell."))
        self.grid = QTableWidget(int(state["rows"]), int(state["cols"]))
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        cells = state.get("cells", {})
        for key, val in cells.items():
            r, c = (int(x) for x in key.split(","))
            if r < self.grid.rowCount() and c < self.grid.columnCount():
                self.grid.setItem(r, c, QTableWidgetItem(val))
        v.addWidget(self.grid, 1)
        st = QHBoxLayout()
        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont(state.get("font_family", "Calibri")))
        self.sz = QDoubleSpinBox()
        self.sz.setRange(4, 120)
        self.sz.setValue(float(state.get("font_size", 11)))
        self.sz.setSuffix(" pt")
        self.c_head = ColorButton("Heading colour", allow_none=False)
        self.c_head.set_color(QColor(state.get("header_fill", "#077568")))
        self.c_band = ColorButton("Shading colour", allow_none=False)
        self.c_band.set_color(QColor(state.get("band_fill", "#eef6f5")))
        for w in (QLabel("Font:"), self.font_box, self.sz, self.c_head, self.c_band):
            st.addWidget(w)
        v.addLayout(st)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.sp_r.valueChanged.connect(self.grid.setRowCount)
        self.sp_c.valueChanged.connect(self.grid.setColumnCount)

    def state(self) -> Dict[str, Any]:
        st = dict(self._state)
        cells = {}
        for r in range(self.grid.rowCount()):
            for c in range(self.grid.columnCount()):
                it = self.grid.item(r, c)
                if it is not None and it.text():
                    cells[f"{r},{c}"] = it.text()
        st.update(rows=self.sp_r.value(), cols=self.sp_c.value(), cells=cells,
                  header=self.cb_head.isChecked(), banded=self.cb_band.isChecked(),
                  font_family=self.font_box.currentFont().family(), font_size=self.sz.value(),
                  header_fill=self.c_head.color().name(QColor.NameFormat.HexArgb),
                  band_fill=self.c_band.color().name(QColor.NameFormat.HexArgb))
        return st

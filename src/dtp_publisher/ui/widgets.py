# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Reusable widgets: colour picker button, unit-aware spin box."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QColorDialog, QDoubleSpinBox, QGridLayout, QLabel, QMenu,
                             QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
                             QWidgetAction)

from .. import theme
from ..units import UNIT_DECIMALS, from_pt, to_pt

BASE_COLORS = ["#ffffff", "#000000", "#e7e6e6", "#44546a", "#4472c4",
               "#ed7d31", "#a5a5a5", "#ffc000", "#5b9bd5", "#70ad47"]
STANDARD = ["#c00000", "#ff0000", "#ffc000", "#ffff00", "#92d050",
            "#00b050", "#00b0f0", "#0070c0", "#002060", "#7030a0"]


def _tints(hexs: str):
    c = QColor(hexs)
    h, s, l, a = c.getHslF()
    out = []
    for f in (0.8, 0.6, 0.4, -0.25, -0.5):
        if f > 0:
            nl = l + (1 - l) * f
        else:
            nl = l * (1 + f)
        if hexs in ("#ffffff",):
            nl = max(0.0, 1 - (0.05, 0.15, 0.25, 0.35, 0.5)[(0.8, 0.6, 0.4, -0.25, -0.5).index(f)])
        if hexs in ("#000000",):
            nl = (0.5, 0.35, 0.25, 0.15, 0.05)[(0.8, 0.6, 0.4, -0.25, -0.5).index(f)]
        out.append(QColor.fromHslF(h if h >= 0 else 0, s, min(max(nl, 0), 1), 1).name())
    return out


def swatch_icon(c: Optional[QColor], size: int = 20, none_slash: bool = True) -> QIcon:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if c is None or c.alpha() == 0:
        p.fillRect(1, 1, size - 2, size - 2, QColor("white"))
        if none_slash:
            p.setPen(QPen(QColor("#d00000"), 2))
            p.drawLine(3, size - 3, size - 3, 3)
    else:
        # checkerboard for semi-transparent colours
        if c.alpha() < 255:
            for y in range(0, size, 5):
                for x in range(0, size, 5):
                    p.fillRect(x, y, 5, 5, QColor("#ccc") if (x + y) // 5 % 2 else QColor("#fff"))
        p.fillRect(1, 1, size - 2, size - 2, c)
    p.setPen(QPen(QColor(0, 0, 0, 120), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(px)


class _SwatchGrid(QWidget):
    picked = pyqtSignal(QColor)

    def __init__(self, allow_none: bool, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        lbl = QLabel("Theme colours")
        lbl.setObjectName("HintLabel")
        v.addWidget(lbl)
        g = QGridLayout()
        g.setSpacing(3)
        for col, base in enumerate(BASE_COLORS):
            g.addWidget(self._btn(base), 0, col)
            for row, t in enumerate(_tints(base), start=1):
                g.addWidget(self._btn(t), row + (1 if row >= 1 else 0), col)
        v.addLayout(g)
        lbl2 = QLabel("Standard colours")
        lbl2.setObjectName("HintLabel")
        v.addWidget(lbl2)
        g2 = QGridLayout()
        g2.setSpacing(3)
        for col, hx in enumerate(STANDARD):
            g2.addWidget(self._btn(hx), 0, col)
        v.addLayout(g2)
        if allow_none:
            b = QPushButton(swatch_icon(None, 18), "  No colour (transparent)")
            b.clicked.connect(lambda: self.picked.emit(QColor(0, 0, 0, 0)))
            v.addWidget(b)
        more = QPushButton("More colours…")
        more.clicked.connect(lambda: self.picked.emit(QColor()))   # invalid → open dialog
        v.addWidget(more)

    def _btn(self, hx: str) -> QToolButton:
        b = QToolButton()
        b.setIcon(swatch_icon(QColor(hx), 22))
        b.setIconSize(QSize(22, 22))
        b.setAutoRaise(True)
        b.setToolTip(hx.upper())
        b.clicked.connect(lambda _=False, c=hx: self.picked.emit(QColor(c)))
        return b


class ColorButton(QToolButton):
    """Shows the current colour; click for a swatch palette."""

    colorPicked = pyqtSignal(QColor)

    def __init__(self, text: str = "", allow_none: bool = True, alpha: bool = True, parent=None):
        super().__init__(parent)
        self._color = QColor(0, 0, 0, 0)
        self._allow_none = allow_none
        self._alpha = alpha
        self.setText(text)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text
                                else Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setIconSize(QSize(20, 20))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._menu = QMenu(self)
        grid = _SwatchGrid(allow_none)
        grid.picked.connect(self._on_pick)
        wa = QWidgetAction(self._menu)
        wa.setDefaultWidget(grid)
        self._menu.addAction(wa)
        self.setMenu(self._menu)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, c: Optional[QColor]):
        self._color = QColor(c) if c is not None else QColor(0, 0, 0, 0)
        self._refresh()

    def _refresh(self):
        self.setIcon(swatch_icon(self._color, 20))

    @pyqtSlot(QColor)
    def _on_pick(self, c: QColor):
        self._menu.hide()
        if not c.isValid():
            opts = QColorDialog.ColorDialogOption.ShowAlphaChannel if self._alpha else \
                QColorDialog.ColorDialogOption(0)
            start = self._color if self._color.alpha() else QColor("#4472c4")
            c = QColorDialog.getColor(start, self.window(), "Choose a colour", opts)
            if not c.isValid():
                return
        self._color = QColor(c)
        self._refresh()
        self.colorPicked.emit(QColor(c))


class UnitSpin(QDoubleSpinBox):
    """A spin box that shows a length in the user's unit but stores points."""

    def __init__(self, unit: str = "mm", lo_pt: float = -10000, hi_pt: float = 10000, parent=None):
        super().__init__(parent)
        self._unit = unit
        self._lo, self._hi = lo_pt, hi_pt
        self.setKeyboardTracking(False)
        self.setAccelerated(True)
        self.set_unit(unit)

    def set_unit(self, unit: str):
        pt = self.pt() if hasattr(self, "_unit") and self._unit else 0.0
        self._unit = unit
        self.blockSignals(True)
        self.setDecimals(UNIT_DECIMALS[unit])
        self.setRange(from_pt(self._lo, unit), from_pt(self._hi, unit))
        self.setSingleStep({"mm": 1.0, "in": 0.05, "pt": 1.0}[unit])
        self.setSuffix(f" {unit}")
        self.setValue(from_pt(pt, unit))
        self.blockSignals(False)

    def pt(self) -> float:
        return to_pt(self.value(), self._unit)

    def set_pt(self, v: float):
        self.blockSignals(True)
        self.setValue(from_pt(v, self._unit))
        self.blockSignals(False)


def header_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("PanelHeader")
    return l


def hint_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("HintLabel")
    l.setWordWrap(True)
    return l


def accent_pen() -> QPen:
    return QPen(theme.color("accent"), 2)

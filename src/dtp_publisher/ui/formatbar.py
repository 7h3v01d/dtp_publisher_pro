# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Text formatting bar.

It always stays in the same place (it only greys out), so the layout never
jumps.  While typing, changes apply to the selected words; when a text box is
selected but not being edited, they apply to all of its text.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QTextCharFormat, QTextListFormat
from PyQt6.QtWidgets import (QComboBox, QFontComboBox, QFrame, QHBoxLayout, QLabel, QMenu,
                             QToolButton, QWidget)

from ..items.text import TextItem
from .icons import icon
from .widgets import ColorButton

SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48, 54, 60, 72, 96, 120]
SPACINGS = [("Single (1.0)", 1.0), ("1.15", 1.15), ("1.5 lines", 1.5), ("Double (2.0)", 2.0),
            ("2.5", 2.5), ("Triple (3.0)", 3.0)]


class FormatBar(QWidget):
    def __init__(self, get_targets: Callable[[], List[TextItem]],
                 get_editing: Callable[[], Optional[TextItem]], get_stack, parent=None):
        super().__init__(parent)
        self.setObjectName("FormatBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._targets = get_targets
        self._editing = get_editing
        self._stack = get_stack
        self._updating = False
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(3)
        self.lbl = QLabel("Text:")
        h.addWidget(self.lbl)
        self.font_box = QFontComboBox()
        self.font_box.setMinimumWidth(190)
        self.font_box.setMaxVisibleItems(18)
        self.font_box.setToolTip("Font")
        self.font_box.currentFontChanged.connect(self._font_changed)
        h.addWidget(self.font_box)
        self.size = QComboBox()
        self.size.setEditable(True)
        self.size.setToolTip("Font size")
        self.size.setMinimumWidth(70)
        for s in SIZES:
            self.size.addItem(str(s))
        self.size.lineEdit().editingFinished.connect(self._size_edited)
        self.size.activated.connect(lambda _: self._size_edited())
        h.addWidget(self.size)
        self._btns: List[QToolButton] = []
        self.btn_color = ColorButton(allow_none=False, alpha=False)
        self.btn_color.setToolTip("Text colour")
        self.btn_color.colorPicked.connect(self._color)
        self.spacing_menu = QMenu(self)
        for label, val in SPACINGS:
            a = self.spacing_menu.addAction(label)
            a.triggered.connect(lambda _=False, v=val: self.set_spacing(v))
        self.btn_spacing = QToolButton()
        self.btn_spacing.setToolTip("Line spacing")
        self.btn_spacing.setMenu(self.spacing_menu)
        self.btn_spacing.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._layout = h

    def add_actions(self, groups: List[List[QAction]]):
        """Insert the window's text actions (so shortcuts live in one place)."""
        h = self._layout
        for gi, group in enumerate(groups):
            h.addWidget(self._sep())
            for a in group:
                b = QToolButton()
                b.setDefaultAction(a)
                b.setIconSize(QSize(20, 20))
                b.setAutoRaise(True)
                h.addWidget(b)
                self._btns.append(b)
            if gi == 0:
                h.addWidget(self.btn_color)
        h.addWidget(self.btn_spacing)
        h.addStretch(1)
        self.refresh_icons()

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    def refresh_icons(self):
        self.btn_spacing.setIcon(icon("line_spacing", 20))
        self.btn_spacing.setIconSize(QSize(20, 20))

    # ── state ────────────────────────────────────────────────────────────────
    def refresh(self):
        targets = self._targets()
        on = bool(targets)
        for w in (self.font_box, self.size, self.btn_color, self.btn_spacing, self.lbl):
            w.setEnabled(on)
        if not on:
            return
        it = self._editing() or targets[0]
        cf = it.current_char_format()
        f = cf.font()
        fam = cf.fontFamilies()[0] if cf.fontFamilies() else f.family()
        size = cf.fontPointSize() or f.pointSizeF() or it.document.defaultFont().pointSizeF()
        self._updating = True
        try:
            self.font_box.setCurrentFont(QFont(fam))
            self.size.setEditText(_fmt_size(size))
            fg = cf.foreground()
            self.btn_color.set_color(fg.color() if fg.style() != Qt.BrushStyle.NoBrush
                                     else it.text_color)
        finally:
            self._updating = False

    def state(self):
        """(bold, italic, underline, align, list_style) for checking toolbar actions."""
        targets = self._targets()
        if not targets:
            return None
        it = self._editing() or targets[0]
        cf = it.current_char_format()
        bf = it.current_block_format()
        al = bf.alignment()
        if al & Qt.AlignmentFlag.AlignHCenter:
            a = "center"
        elif al & Qt.AlignmentFlag.AlignRight:
            a = "right"
        elif al & Qt.AlignmentFlag.AlignJustify:
            a = "justify"
        else:
            a = "left"
        bold = cf.fontWeight() >= QFont.Weight.DemiBold.value if cf.hasProperty(
            QTextCharFormat.Property.FontWeight) else cf.font().bold()
        return bold, cf.fontItalic(), cf.fontUnderline(), a, it.current_list_style()

    # ── applying ─────────────────────────────────────────────────────────────
    def _each(self, label: str, fn: Callable[[TextItem], None]):
        ed = self._editing()
        if ed is not None:
            fn(ed)
            return
        targets = self._targets()
        if not targets:
            return
        stack = self._stack()
        stack.beginMacro(label)
        try:
            for it in targets:
                fn(it)
        finally:
            stack.endMacro()
        self.refresh()

    def merge(self, fmt: QTextCharFormat, label: str):
        self._each(label, lambda it: it.merge_char_format(fmt, label))

    def _font_changed(self, f: QFont):
        if self._updating:
            return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([f.family()])
        self.merge(fmt, "Font")

    def _size_edited(self):
        if self._updating:
            return
        try:
            v = float(self.size.currentText().replace(",", "."))
        except ValueError:
            return
        self.set_size(v)

    def set_size(self, v: float):
        v = max(1.0, min(v, 999.0))
        fmt = QTextCharFormat()
        fmt.setFontPointSize(v)
        self.merge(fmt, "Font size")
        self._updating = True
        self.size.setEditText(_fmt_size(v))
        self._updating = False

    def step_size(self, up: bool):
        try:
            cur = float(self.size.currentText())
        except ValueError:
            cur = 12.0
        if up:
            nxt = next((s for s in SIZES if s > cur + 0.01), cur + 12)
        else:
            nxt = next((s for s in reversed(SIZES) if s < cur - 0.01), max(1.0, cur - 1))
        self.set_size(nxt)

    def _color(self, c: QColor):
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(c))
        self.merge(fmt, "Text colour")

    def set_bold(self, on: bool):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold.value if on else QFont.Weight.Normal.value)
        self.merge(fmt, "Bold")

    def set_italic(self, on: bool):
        fmt = QTextCharFormat()
        fmt.setFontItalic(on)
        self.merge(fmt, "Italic")

    def set_underline(self, on: bool):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(on)
        self.merge(fmt, "Underline")

    def set_align(self, key: str):
        self._each("Align text", lambda it: it.set_alignment(key))

    def set_spacing(self, v: float):
        self._each("Line spacing", lambda it: it.set_line_spacing(v))

    def set_list(self, style: Optional[QTextListFormat.Style]):
        self._each("Bullets", lambda it: it.set_list(style))


def _fmt_size(v: float) -> str:
    return str(int(v)) if abs(v - round(v)) < 0.05 else f"{v:.1f}"

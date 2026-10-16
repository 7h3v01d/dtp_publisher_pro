# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Office-style ribbon built on QActions.

Buttons only *show* actions; the actions (and their keyboard shortcuts) are
registered once on the main window.  That is what fixes bug #3: the
prototype created a second QAction per shortcut, Qt saw every shortcut twice,
treated them as ambiguous and fired neither.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy,
                             QStackedWidget, QTabBar,
                             QToolButton, QVBoxLayout, QWidget)


class RibbonButton(QToolButton):
    def __init__(self, large: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonButton")
        self.large = large
        if large:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setIconSize(QSize(32, 32))
            # (no setMinimumWidth: an explicit minimum overrides the Fixed policy
            # and lets the layout squeeze labels; sizeHint() already enforces 62)
            # Fixed width: never elide labels ("Pi…me"); the tab scrolls instead
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(18, 18))
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        if self.large:
            return QSize(max(s.width() + 6, 62), max(s.height(), 70))
        return QSize(s.width(), max(s.height(), 26))


class RibbonGroup(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 2)
        v.setSpacing(1)
        self._row = QHBoxLayout()
        self._row.setSpacing(2)
        self._row.setContentsMargins(0, 0, 0, 0)
        v.addLayout(self._row, 1)
        lbl = QLabel(title)
        lbl.setObjectName("RibbonGroupTitle")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(lbl)
        self.buttons: List[RibbonButton] = []

    def add_large(self, action: QAction, menu: Optional[QMenu] = None) -> RibbonButton:
        b = RibbonButton(True)
        b.setDefaultAction(action)
        if menu is not None:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._row.addWidget(b)
        self.buttons.append(b)
        return b

    def add_menu_large(self, text: str, icon: QIcon, menu: QMenu, tip: str = "") -> RibbonButton:
        b = RibbonButton(True)
        b.setText(text)
        b.setIcon(icon)
        b.setToolTip(tip or text)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._row.addWidget(b)
        self.buttons.append(b)
        return b

    def add_smalls(self, actions: Iterable[Optional[QAction]]) -> List[RibbonButton]:
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        out = []
        for a in actions:
            if a is None:
                continue
            b = RibbonButton(False)
            b.setDefaultAction(a)
            col.addWidget(b)
            out.append(b)
            self.buttons.append(b)
        col.addStretch(1)
        self._row.addLayout(col)
        return out

    def add_small_menu(self, text: str, icon: QIcon, menu: QMenu) -> RibbonButton:
        b = RibbonButton(False)
        b.setText(text)
        b.setIcon(icon)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.buttons.append(b)
        return b

    def add_column(self, buttons: Iterable[QWidget]):
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        for w in buttons:
            col.addWidget(w)
        col.addStretch(1)
        self._row.addLayout(col)

    def add_widget(self, w: QWidget):
        self._row.addWidget(w)


class RibbonPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RibbonPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._h = QHBoxLayout(self)
        self._h.setContentsMargins(4, 2, 4, 2)
        self._h.setSpacing(0)
        self._h.addStretch(1)
        self.groups: List[RibbonGroup] = []

    def group(self, title: str) -> RibbonGroup:
        g = RibbonGroup(title)
        self._h.insertWidget(self._h.count() - 1, g)
        self.groups.append(g)
        return g


class Ribbon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Ribbon")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QWidget()
        bar.setObjectName("RibbonTabBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(6, 0, 6, 0)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setUsesScrollButtons(False)
        bh.addWidget(self.tabs)
        bh.addStretch(1)
        self.corner = QHBoxLayout()
        self.corner.setSpacing(4)
        bh.addLayout(self.corner)
        v.addWidget(bar)
        self.stack = QStackedWidget()
        v.addWidget(self.stack)
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
        self.pages: dict = {}
        self._areas: list = []

    def page(self, name: str) -> RibbonPage:
        p = RibbonPage()
        # at large UI sizes a tab can be wider than the screen: let it scroll
        # sideways instead of forcing the window wider than the monitor
        sa = QScrollArea()
        sa.setObjectName("RibbonPage")
        sa.setWidget(p)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setSizeAdjustPolicy(QScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.tabs.addTab(name)
        self.stack.addWidget(sa)
        self.pages[name] = p
        self._areas.append((sa, p))
        return p

    def finalize(self):
        """Reserve room for the sideways scrollbar so it never covers group titles."""
        h = max(p.sizeHint().height() for _, p in self._areas)
        bar = max(sa.horizontalScrollBar().sizeHint().height() for sa, _ in self._areas)
        for sa, _ in self._areas:
            sa.setFixedHeight(h + bar)

    def show_tab(self, name: str):
        names = list(self.pages)
        if name in names:
            self.tabs.setCurrentIndex(names.index(name))

    def all_buttons(self) -> List[RibbonButton]:
        out = []
        for p in self.pages.values():
            for g in p.groups:
                out.extend(g.buttons)
        return out

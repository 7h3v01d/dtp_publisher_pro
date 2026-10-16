# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Themes: light (Publisher-familiar), dark (Obsidian/Teal), high contrast.

The page itself is always white paper — themes only change the chrome around
it and the on-canvas helpers (selection handles, guides, grid).
"""

from __future__ import annotations

import os
from typing import Dict

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

THEMES: Dict[str, Dict[str, str]] = {
    "light": {
        "label": "Light (Publisher style)",
        "font": "Segoe UI",
        "radius": "4px",
        "border_w": "1px",
        "window": "#f3f2f1",
        "panel": "#ffffff",
        "panel_alt": "#faf9f8",
        "border": "#c8c6c4",
        "text": "#201f1e",
        "text_dim": "#605e5c",
        "accent": "#077568",
        "accent_text": "#ffffff",
        "hover": "#e1dfdd",
        "selected": "#c7e7e3",
        "input": "#ffffff",
        "canvas": "#d2d0ce",
        "ribbon": "#ffffff",
        "tabbar": "#077568",
        "tab_text": "#ffffff",
        "danger": "#c50f1f",
        "ok": "#107c10",
        "warn": "#8a5300",
        # on-canvas helpers (drawn over white paper)
        "c_select": "#0f6cbd",
        "c_handle_fill": "#ffffff",
        "c_guide": "#00a3ae",
        "c_margin": "#d4007f",
        "c_grid": "#c9d7e6",
        "c_snap": "#e81123",
        "c_bounds": "#a19f9d",
        "c_lock": "#c50f1f",
    },
    "dark": {
        "label": "Dark (Obsidian)",
        "font": "JetBrains Mono",
        "radius": "0px",
        "border_w": "1px",
        "window": "#0b0f14",
        "panel": "#11161d",
        "panel_alt": "#0e1319",
        "border": "#1e2831",
        "text": "#c8d3da",
        "text_dim": "#7d8b95",
        "accent": "#2fd6c3",
        "accent_text": "#0b0f14",
        "hover": "#18212b",
        "selected": "#123b3a",
        "input": "#0b0f14",
        "canvas": "#06090c",
        "ribbon": "#11161d",
        "tabbar": "#0b0f14",
        "tab_text": "#c8d3da",
        "danger": "#ff6b6b",
        "ok": "#4be08a",
        "warn": "#ffb454",
        "c_select": "#0aa597",
        "c_handle_fill": "#ffffff",
        "c_guide": "#2fd6c3",
        "c_margin": "#ffb454",
        "c_grid": "#c5d6dc",
        "c_snap": "#ff6b6b",
        "c_bounds": "#8fa3ad",
        "c_lock": "#ff6b6b",
    },
    "contrast": {
        "label": "High contrast",
        "font": "Segoe UI",
        "radius": "0px",
        "border_w": "2px",
        "window": "#000000",
        "panel": "#000000",
        "panel_alt": "#0a0a0a",
        "border": "#ffffff",
        "text": "#ffffff",
        "text_dim": "#f0f0f0",
        "accent": "#ffff00",
        "accent_text": "#000000",
        "hover": "#30307a",
        "selected": "#004d99",
        "input": "#000000",
        "canvas": "#3a3a3a",
        "ribbon": "#000000",
        "tabbar": "#000000",
        "tab_text": "#ffffff",
        "danger": "#ff4040",
        "ok": "#3ff23f",
        "warn": "#ffff00",
        "c_select": "#e000e0",
        "c_handle_fill": "#ffff00",
        "c_guide": "#0090ff",
        "c_margin": "#e000e0",
        "c_grid": "#a0a0a0",
        "c_snap": "#ff0000",
        "c_bounds": "#606060",
        "c_lock": "#ff0000",
    },
}

_current = "light"


def current_name() -> str:
    return _current


def tokens() -> Dict[str, str]:
    return THEMES[_current]


def color(key: str) -> QColor:
    return QColor(THEMES[_current][key])


def ui_font(point_size: float = 10.0) -> QFont:
    f = QFont(tokens()["font"])
    f.setPointSizeF(point_size)
    return f


def build_palette(t: Dict[str, str]) -> QPalette:
    p = QPalette()
    c = QColor
    R = QPalette.ColorRole
    p.setColor(R.Window, c(t["window"]))
    p.setColor(R.WindowText, c(t["text"]))
    p.setColor(R.Base, c(t["input"]))
    p.setColor(R.AlternateBase, c(t["panel_alt"]))
    p.setColor(R.Text, c(t["text"]))
    p.setColor(R.Button, c(t["panel"]))
    p.setColor(R.ButtonText, c(t["text"]))
    p.setColor(R.Highlight, c(t["accent"]))
    p.setColor(R.HighlightedText, c(t["accent_text"]))
    p.setColor(R.ToolTipBase, c(t["panel"]))
    p.setColor(R.ToolTipText, c(t["text"]))
    p.setColor(R.PlaceholderText, c(t["text_dim"]))
    p.setColor(R.Link, c(t["accent"]))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(t["text_dim"]).darker(130)
                   if _is_dark(t) else c(t["text_dim"]).lighter(150))
    return p


def _is_dark(t: Dict[str, str]) -> bool:
    return QColor(t["window"]).lightness() < 128


def _assets(name: str, t: Dict[str, str]) -> Dict[str, str]:
    """Render small indicator images (arrows, tick, dot) in the theme's colours."""
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter, QPen, QPolygonF
    from .settings import config_dir
    folder = os.path.join(config_dir(), "theme-assets", name)
    os.makedirs(folder, exist_ok=True)
    out = {}

    def make(key, draw):
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(p)
        p.end()
        path = os.path.join(folder, f"{key}.png")
        img.save(path)
        out[key] = path.replace("\\", "/")

    fg, ac_txt = QColor(t["text"]), QColor(t["accent_text"])

    def tri(up):
        def d(p):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fg)
            pts = [(6, 22), (26, 22), (16, 9)] if up else [(6, 10), (26, 10), (16, 23)]
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        return d

    def tick(p):
        pen = QPen(ac_txt, 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPolygonF([QPointF(7, 17), QPointF(13, 23), QPointF(25, 9)]))

    def dot(p):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ac_txt)
        p.drawEllipse(QRectF(9, 9, 14, 14))

    make("up", tri(True))
    make("down", tri(False))
    make("tick", tick)
    make("dot", dot)
    return out


def build_qss(t: Dict[str, str], assets: Dict[str, str] | None = None) -> str:
    r = t["radius"]
    bw = t["border_w"]
    a = assets or {}
    return _indicator_qss(t, a) + f"""
* {{ font-family: "{t['font']}"; }}
QMainWindow, QDialog {{ background: {t['window']}; color: {t['text']}; }}
QToolTip {{ background: {t['panel']}; color: {t['text']}; border: {bw} solid {t['border']};
            padding: 6px; }}
QMenu {{ background: {t['panel']}; color: {t['text']}; border: {bw} solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; }}
QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
QMenu::item:disabled {{ color: {t['text_dim']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

QPushButton {{ background: {t['panel']}; color: {t['text']}; border: {bw} solid {t['border']};
               border-radius: {r}; padding: 6px 14px; min-height: 22px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed, QPushButton:checked {{ background: {t['selected']}; }}
QPushButton:default, QPushButton#Primary {{ background: {t['accent']}; color: {t['accent_text']};
               border-color: {t['accent']}; }}
QPushButton:disabled {{ color: {t['text_dim']}; }}
QPushButton:focus, QToolButton:focus {{ outline: none; border: 2px solid {t['accent']}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {t['input']}; color: {t['text']}; border: {bw} solid {t['border']};
    border-radius: {r}; padding: 4px 6px; min-height: 22px;
    selection-background-color: {t['accent']}; selection-color: {t['accent_text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {t['accent']}; }}
QComboBox QAbstractItemView {{ background: {t['panel']}; color: {t['text']};
    selection-background-color: {t['accent']}; selection-color: {t['accent_text']}; }}

QCheckBox, QRadioButton, QLabel {{ color: {t['text']}; background: transparent; }}
QGroupBox {{ color: {t['text']}; border: {bw} solid {t['border']}; border-radius: {r};
             margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}

QTabWidget::pane {{ border: {bw} solid {t['border']}; background: {t['panel']}; }}
QTabBar::tab {{ background: {t['panel_alt']}; color: {t['text']}; padding: 7px 12px;
                border: {bw} solid {t['border']}; border-bottom: none; }}
QTabBar::tab:selected {{ background: {t['panel']}; border-top: 3px solid {t['accent']};
                font-weight: 600; }}

QListWidget, QTreeWidget, QTableWidget {{ background: {t['panel']}; color: {t['text']};
    border: {bw} solid {t['border']}; alternate-background-color: {t['panel_alt']};
    gridline-color: {t['border']}; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {t['selected']}; color: {t['text']}; }}
QHeaderView::section {{ background: {t['panel_alt']}; color: {t['text']}; padding: 4px;
    border: none; border-bottom: {bw} solid {t['border']}; }}

QScrollBar:vertical {{ background: {t['window']}; width: 14px; margin: 0; }}
QScrollBar:horizontal {{ background: {t['window']}; height: 14px; margin: 0; }}
QScrollBar::handle {{ background: {t['border']}; border-radius: {r}; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {t['text_dim']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: {t['panel']}; color: {t['text']}; border-top: {bw} solid {t['border']}; }}
QStatusBar QLabel {{ padding: 0 6px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0; background: {t['accent']};
    border-radius: {'7px' if r != '0px' else '0px'}; }}

/* ── ribbon ─────────────────────────────────────────────────────────── */
#Ribbon {{ background: {t['ribbon']}; border-bottom: {bw} solid {t['border']}; }}
#RibbonTabBar {{ background: {t['tabbar']}; }}
#RibbonTabBar QTabBar::tab {{ background: transparent; color: {t['tab_text']};
    padding: 7px 18px; border: none; font-size: 10.5pt; }}
#RibbonTabBar QTabBar::tab:selected {{ background: {t['ribbon']}; color: {t['text']};
    border-top: 3px solid {t['accent']}; font-weight: 600; }}
#RibbonTabBar QTabBar::tab:hover:!selected {{ background: {t['hover']}; color: {t['text']}; }}
#RibbonPage {{ background: {t['ribbon']}; }}
#RibbonGroup {{ background: transparent; border-right: {bw} solid {t['border']}; }}
#RibbonGroupTitle {{ color: {t['text_dim']}; font-size: 8.5pt; }}
#RibbonButton {{ background: transparent; color: {t['text']}; border: {bw} solid transparent;
    border-radius: {r}; padding: 2px 4px; }}
#RibbonButton:hover {{ background: {t['hover']}; border-color: {t['border']}; }}
#RibbonButton:pressed, #RibbonButton:checked {{ background: {t['selected']};
    border-color: {t['accent']}; }}
#RibbonButton:disabled {{ color: {t['text_dim']}; }}
#RibbonButton::menu-indicator {{ subcontrol-position: bottom center; }}

#FormatBar {{ background: {t['panel_alt']}; border-bottom: {bw} solid {t['border']}; }}
#FormatBar QToolButton {{ background: transparent; color: {t['text']}; border: {bw} solid transparent;
    border-radius: {r}; padding: 3px 6px; min-width: 26px; min-height: 26px; }}
#FormatBar QToolButton:hover {{ background: {t['hover']}; border-color: {t['border']}; }}
#FormatBar QToolButton:checked {{ background: {t['selected']}; border-color: {t['accent']}; }}

#SidePanel, #ThumbPanel {{ background: {t['panel']}; }}
#ThumbPanel {{ border-right: {bw} solid {t['border']}; }}
#PanelHeader {{ color: {t['text']}; font-weight: 700; font-size: 10.5pt; padding: 4px 2px; }}
#HintLabel {{ color: {t['text_dim']}; }}
#Ruler {{ background: {t['panel_alt']}; }}

#StartTile {{ background: {t['panel']}; border: {bw} solid {t['border']}; border-radius: {r};
    color: {t['text']}; padding: 8px; }}
#StartTile:hover {{ border: 2px solid {t['accent']}; background: {t['hover']}; }}
#StartHeader {{ font-size: 18pt; font-weight: 700; color: {t['text']}; }}
#StartSub {{ font-size: 11pt; font-weight: 600; color: {t['text']}; }}
"""


def _indicator_qss(t: Dict[str, str], a: Dict[str, str]) -> str:
    r = t["radius"]
    bw = t["border_w"]
    rr = "8px" if r != "0px" else "0px"
    return f"""
QAbstractSpinBox {{ padding-right: 24px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border;
    width: 22px; border-left: {bw} solid {t['border']}; background: {t['panel_alt']}; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {t['hover']}; }}
QAbstractSpinBox::up-arrow {{ image: url("{a.get('up', '')}"); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url("{a.get('down', '')}"); width: 10px; height: 10px; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 24px;
    border-left: {bw} solid {t['border']}; }}
QComboBox::down-arrow {{ image: url("{a.get('down', '')}"); width: 11px; height: 11px; }}
QCheckBox::indicator, QTreeView::indicator, QListView::indicator {{ width: 17px; height: 17px;
    border: 2px solid {t['text_dim']}; background: {t['input']}; border-radius: {'4px' if r != '0px' else '0px'}; }}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked {{
    background: {t['accent']}; border-color: {t['accent']}; image: url("{a.get('tick', '')}"); }}
QCheckBox::indicator:hover, QTreeView::indicator:hover {{ border-color: {t['accent']}; }}
QRadioButton::indicator {{ width: 17px; height: 17px; border: 2px solid {t['text_dim']};
    background: {t['input']}; border-radius: {rr if rr != '0px' else '0px'}; }}
QRadioButton::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
    image: url("{a.get('dot', '')}"); }}
QToolButton::menu-indicator {{ image: url("{a.get('down', '')}"); width: 9px; height: 9px;
    subcontrol-origin: padding; subcontrol-position: bottom right; }}
QToolButton[popupMode="1"]::menu-button {{ width: 16px; border: none; }}
QToolButton::menu-arrow {{ image: url("{a.get('down', '')}"); width: 9px; height: 9px; }}
"""


def apply(app: QApplication, name: str) -> None:
    """Switch theme at runtime."""
    global _current
    if name not in THEMES:
        name = "light"
    _current = name
    t = THEMES[name]
    app.setPalette(build_palette(t))
    try:
        assets = _assets(name, t)
    except OSError:
        assets = {}
    app.setStyleSheet(build_qss(t, assets))
    f = app.font()
    f.setFamily(t["font"])
    app.setFont(f)

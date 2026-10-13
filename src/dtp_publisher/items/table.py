# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""TableItem — a simple grid table, edited through a dialog."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from .base import BaseItem, color_from, color_to_str, device_font, num

MAX_ROWS = 60
MAX_COLS = 20


class TableItem(BaseItem):
    CAN_FLIP = False
    KIND = "table"
    DISPLAY = "Table"
    MIN_W = 30.0
    MIN_H = 20.0

    def __init__(self, w: float = 360, h: float = 120, rows: int = 4, cols: int = 3):
        super().__init__(w, h)
        self.rows = max(1, min(rows, MAX_ROWS))
        self.cols = max(1, min(cols, MAX_COLS))
        self.cells: Dict[Tuple[int, int], str] = {(0, c): f"Heading {c + 1}" for c in range(self.cols)}
        self.header = True
        self.banded = True
        self.fill = QColor(255, 255, 255)
        self.stroke = QColor("#8c8c8c")
        self.stroke_width = 0.75
        self.header_fill = QColor("#077568")
        self.header_text = QColor(255, 255, 255)
        self.band_fill = QColor("#eef6f5")
        self.text_color = QColor(32, 31, 30)
        self.font_family = "Calibri"
        self.font_size = 11.0

    def display_name(self) -> str:
        return self.name or f"Table ({self.rows} × {self.cols})"

    # ── state as a single undoable value ────────────────────────────────────
    STATE_KEYS = ("rows", "cols", "header", "banded", "font_family", "font_size")

    def table_state(self) -> Dict[str, Any]:
        st = {k: getattr(self, k) for k in self.STATE_KEYS}
        st["cells"] = {f"{r},{c}": v for (r, c), v in self.cells.items() if v}
        for k in ("header_fill", "header_text", "band_fill", "text_color"):
            st[k] = color_to_str(getattr(self, k))
        return st

    def apply_table_state(self, st: Dict[str, Any]):
        self.rows = int(num(st, "rows", self.rows, 1, MAX_ROWS))
        self.cols = int(num(st, "cols", self.cols, 1, MAX_COLS))
        self.header = bool(st.get("header", self.header))
        self.banded = bool(st.get("banded", self.banded))
        self.font_family = str(st.get("font_family", self.font_family))[:100]
        self.font_size = num(st, "font_size", self.font_size, 4, 200)
        for k in ("header_fill", "header_text", "band_fill", "text_color"):
            setattr(self, k, color_from(st.get(k), getattr(self, k)))
        cells: Dict[Tuple[int, int], str] = {}
        raw = st.get("cells", {})
        if isinstance(raw, dict):
            for key, val in raw.items():
                try:
                    r, c = (int(x) for x in str(key).split(","))
                except ValueError:
                    continue
                if 0 <= r < self.rows and 0 <= c < self.cols:
                    cells[(r, c)] = str(val)
        self.cells = cells
        self.update()

    def get_prop(self, key: str):
        if key == "table":
            return self.table_state()
        return super().get_prop(key)

    def set_prop(self, key: str, value):
        if key == "table":
            self.apply_table_state(value)
            return
        super().set_prop(key, value)

    def cell(self, r: int, c: int) -> str:
        return self.cells.get((r, c), "")

    def cell_rect(self, r: int, c: int) -> QRectF:
        cw = self._w / self.cols
        rh = self._h / self.rows
        return QRectF(c * cw, r * rh, cw, rh)

    def cell_at(self, pos: QPointF) -> Tuple[int, int]:
        c = int(pos.x() / (self._w / self.cols))
        r = int(pos.y() / (self._h / self.rows))
        return max(0, min(r, self.rows - 1)), max(0, min(c, self.cols - 1))

    # ── painting ─────────────────────────────────────────────────────────────
    def paint_content(self, p: QPainter):
        p.fillRect(self.rect(), self.fill)
        for r in range(self.rows):
            for c in range(self.cols):
                cr = self.cell_rect(r, c)
                is_head = self.header and r == 0
                if is_head:
                    p.fillRect(cr, self.header_fill)
                elif self.banded and (r % 2 == (0 if self.header else 1)):
                    p.fillRect(cr, self.band_fill)
                txt = self.cell(r, c)
                if txt:
                    p.setFont(device_font(p, self.font_family, self.font_size, bold=is_head))
                    p.setPen(self.header_text if is_head else self.text_color)
                    p.save()
                    p.setClipRect(cr)
                    p.drawText(cr.adjusted(4, 2, -4, -2),
                               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                               | Qt.TextFlag.TextWordWrap, txt)
                    p.restore()
        pen = self.make_pen()
        if pen.style() != Qt.PenStyle.NoPen:
            p.setPen(pen)
            for c in range(self.cols + 1):
                x = c * self._w / self.cols
                p.drawLine(QPointF(x, 0), QPointF(x, self._h))
            for r in range(self.rows + 1):
                y = r * self._h / self.rows
                p.drawLine(QPointF(0, y), QPointF(self._w, y))

    def on_double_click(self, e):
        sc = self.page_scene()
        if sc is not None:
            sc.itemActivated.emit(self)

    def extra_to_dict(self) -> Dict[str, Any]:
        return {"table": self.table_state()}

    def apply_extra(self, d: Dict[str, Any]):
        st = d.get("table")
        if isinstance(st, dict):
            self.apply_table_state(st)

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Label sheets: print several pages (labels, cards) on one sheet of paper.

Like Publisher, a label publication is designed one label per page; the sheet
layout says where each label sits on the paper.  Measurements are from the
manufacturers' published templates — always worth a test print on plain paper
held up to the light against a label sheet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from PyQt6.QtCore import QRectF

from .units import mm


@dataclass(frozen=True)
class SheetLayout:
    key: str
    name: str
    label_w: float          # all in mm
    label_h: float
    cols: int
    rows: int
    left: float
    top: float
    pitch_x: float
    pitch_y: float
    paper_w: float = 210.0
    paper_h: float = 297.0

    @property
    def per_sheet(self) -> int:
        return self.cols * self.rows


PRESETS: List[SheetLayout] = [
    SheetLayout("L7651", "Avery L7651 / L7551 mini labels (65 per sheet, 38.1 × 21.2 mm)",
                38.1, 21.2, 5, 13, 4.7, 10.7, 40.6, 21.2),
    SheetLayout("L7160", "Avery L7160 / J8160 (21 per sheet, 63.5 × 38.1 mm)",
                63.5, 38.1, 3, 7, 7.2, 15.1, 66.0, 38.1),
    SheetLayout("L7159", "Avery L7159 / J8159 (24 per sheet, 63.5 × 33.9 mm)",
                63.5, 33.9, 3, 8, 7.2, 12.9, 66.0, 33.9),
    SheetLayout("L7161", "Avery L7161 / J8161 (18 per sheet, 63.5 × 46.6 mm)",
                63.5, 46.6, 3, 6, 7.2, 8.8, 66.0, 46.6),
    SheetLayout("L7162", "Avery L7162 / J8162 (16 per sheet, 99.1 × 33.9 mm)",
                99.1, 33.9, 2, 8, 4.65, 12.9, 101.6, 33.9),
    SheetLayout("L7163", "Avery L7163 / J8163 (14 per sheet, 99.1 × 38.1 mm)",
                99.1, 38.1, 2, 7, 4.65, 15.15, 101.6, 38.1),
    SheetLayout("L7173", "Avery L7173 / J8173 (10 per sheet, 99.1 × 57 mm)",
                99.1, 57.0, 2, 5, 4.65, 6.0, 101.6, 57.0),
    SheetLayout("L7165", "Avery L7165 / J8165 (8 per sheet, 99.1 × 67.7 mm)",
                99.1, 67.7, 2, 4, 4.65, 13.1, 101.6, 67.7),
    SheetLayout("C32011", "Business cards (10 per sheet, 85 × 54 mm)",
                85.0, 54.0, 2, 5, 15.0, 13.5, 95.0, 54.0),
]
PRESET_BY_KEY: Dict[str, SheetLayout] = {p.key: p for p in PRESETS}

MODES = {"copies": "Fill a whole sheet with each page",
         "sequence": "Print the pages one after another (one label each)"}


def detect(page_w_pt: float, page_h_pt: float, tol_mm: float = 0.6) -> Optional[SheetLayout]:
    """Find a preset whose label is the size of this page (either way round)."""
    w, h = page_w_pt / mm(1), page_h_pt / mm(1)
    for p in PRESETS:
        if (abs(p.label_w - w) <= tol_mm and abs(p.label_h - h) <= tol_mm) or \
           (abs(p.label_w - h) <= tol_mm and abs(p.label_h - w) <= tol_mm):
            return p
    return None


def to_dict(layout: SheetLayout, mode: str = "copies") -> dict:
    d = asdict(layout)
    d["mode"] = mode if mode in MODES else "copies"
    return d


def from_dict(d: Optional[dict]) -> Optional[SheetLayout]:
    if not isinstance(d, dict):
        return None
    try:
        vals = {f: d[f] for f in ("key", "name")}
        for f in ("label_w", "label_h", "left", "top", "pitch_x", "pitch_y",
                  "paper_w", "paper_h"):
            vals[f] = max(0.0, min(float(d[f]), 2000.0))
        for f in ("cols", "rows"):
            vals[f] = max(1, min(int(d[f]), 50))
        return SheetLayout(**vals)
    except (KeyError, TypeError, ValueError):
        return None


def cells(layout: SheetLayout) -> List[QRectF]:
    """Label rectangles on the paper, in points, left-to-right then down."""
    out = []
    for r in range(layout.rows):
        for c in range(layout.cols):
            out.append(QRectF(mm(layout.left + c * layout.pitch_x),
                              mm(layout.top + r * layout.pitch_y),
                              mm(layout.label_w), mm(layout.label_h)))
    return out


def plan(page_count: int, layout: SheetLayout, mode: str) -> List[List[int]]:
    """Which page goes in each cell, sheet by sheet (-1 = leave empty)."""
    n = layout.per_sheet
    if mode == "sequence":
        sheets, cur = [], []
        for i in range(page_count):
            cur.append(i)
            if len(cur) == n:
                sheets.append(cur)
                cur = []
        if cur:
            sheets.append(cur + [-1] * (n - len(cur)))
        return sheets
    return [[i] * n for i in range(page_count)]

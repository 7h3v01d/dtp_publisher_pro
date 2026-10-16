# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Measurement units and page-size presets.

All document geometry is stored in PostScript points (1/72 inch).  The UI can
display millimetres, inches or points; conversion happens only at the edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

PT_PER_INCH = 72.0
PT_PER_MM = 72.0 / 25.4

UNITS: Dict[str, float] = {"mm": PT_PER_MM, "in": PT_PER_INCH, "pt": 1.0}
UNIT_LABELS: Dict[str, str] = {"mm": "Millimetres", "in": "Inches", "pt": "Points"}
UNIT_DECIMALS: Dict[str, int] = {"mm": 1, "in": 2, "pt": 1}


def to_pt(value: float, unit: str) -> float:
    return float(value) * UNITS[unit]


def from_pt(value: float, unit: str) -> float:
    return float(value) / UNITS[unit]


def mm(v: float) -> float:
    return v * PT_PER_MM


def inch(v: float) -> float:
    return v * PT_PER_INCH


@dataclass(frozen=True)
class PageSize:
    key: str
    name: str
    width: float   # points, portrait
    height: float  # points, portrait
    group: str = "Paper"


PAGE_SIZES: List[PageSize] = [
    PageSize("a4", "A4 (210 × 297 mm)", mm(210), mm(297)),
    PageSize("a3", "A3 (297 × 420 mm)", mm(297), mm(420)),
    PageSize("a5", "A5 (148 × 210 mm)", mm(148), mm(210)),
    PageSize("a6", "A6 (105 × 148 mm)", mm(105), mm(148)),
    PageSize("letter", "US Letter (8.5 × 11 in)", inch(8.5), inch(11)),
    PageSize("legal", "US Legal (8.5 × 14 in)", inch(8.5), inch(14)),
    PageSize("tabloid", "Tabloid (11 × 17 in)", inch(11), inch(17)),
    PageSize("dl", "DL envelope (110 × 220 mm)", mm(110), mm(220), "Cards & envelopes"),
    PageSize("c5", "C5 envelope (162 × 229 mm)", mm(162), mm(229), "Cards & envelopes"),
    PageSize("card5x7", "Card 5 × 7 in", inch(5), inch(7), "Cards & envelopes"),
    PageSize("postcard4x6", "Postcard 4 × 6 in", inch(4), inch(6), "Cards & envelopes"),
    PageSize("bizcard", "Business card (55 × 90 mm)", mm(55), mm(90), "Cards & envelopes"),
    PageSize("photo6x4", "Photo 6 × 4 in", inch(4), inch(6), "Photos"),
    PageSize("photo7x5", "Photo 7 × 5 in", inch(5), inch(7), "Photos"),
    PageSize("square8", "Square 8 × 8 in", inch(8), inch(8), "Photos"),
    PageSize("square12", "Square 12 × 12 in", inch(12), inch(12), "Photos"),
]

PAGE_SIZE_BY_KEY: Dict[str, PageSize] = {p.key: p for p in PAGE_SIZES}

DEFAULT_PAGE = PAGE_SIZE_BY_KEY["a4"]


def oriented(w: float, h: float, landscape: bool) -> Tuple[float, float]:
    lo, hi = sorted((w, h))
    return (hi, lo) if landscape else (lo, hi)


def match_page_size(w: float, h: float, tol: float = 1.0) -> str | None:
    """Return the preset key matching (w, h) in either orientation, if any."""
    for p in PAGE_SIZES:
        if (abs(p.width - w) <= tol and abs(p.height - h) <= tol) or (
            abs(p.width - h) <= tol and abs(p.height - w) <= tol
        ):
            return p.key
    return None


def describe_size(w: float, h: float, unit: str = "mm") -> str:
    d = UNIT_DECIMALS[unit]
    return f"{from_pt(w, unit):.{d}f} × {from_pt(h, unit):.{d}f} {unit}"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Resource limits: one place for every "how big is too big".

Files, pictures and converted Publisher documents come from outside the
program, so nothing is allocated on their say-so alone.  Each limit is far
above anything a real publication needs (a 100-page newsletter with hundreds
of photos sits well inside all of them) and far below what would freeze or
exhaust a home PC.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

# ── pages ────────────────────────────────────────────────────────────────────
MIN_PAGE_PT = 18.0                   # ¼ inch
MAX_PAGE_PT = 14400.0                # 200 inches, the most Page Setup offers
MAX_GUIDES_PER_PAGE = 500

# ── documents (.dtpub, clipboard) ───────────────────────────────────────────
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_PAGES = 1000
MAX_OBJECTS = 50_000                 # every object, counting those inside groups
MAX_TEXT_CHARS = 50_000_000          # all text-box HTML together
MAX_GROUP_DEPTH = 32

# ── pictures ─────────────────────────────────────────────────────────────────
MAX_IMAGE_FILE_BYTES = 256 * 1024 * 1024     # a picture file chosen or dropped

# ── raster export (Save as Picture) ─────────────────────────────────────────
MAX_EXPORT_PIXELS = 150_000_000      # A0 at 300 dpi fits; about 600 MB of memory
MAX_EXPORT_SIDE = 30_000             # pixels on the longer side

# ── Publisher import ─────────────────────────────────────────────────────────
MAX_CONVERTED_BYTES = 2 * 1024 ** 3          # the .odg LibreOffice writes
MAX_CONVERT_DIR_BYTES = 4 * 1024 ** 3        # its temp folder while it works
MAX_ODG_ENTRIES = 20_000
MAX_ODG_XML_BYTES = 48 * 1024 * 1024         # content.xml / styles.xml, each
MAX_XML_ELEMENTS = 1_500_000
MAX_ODG_PICTURE_BYTES = 256 * 1024 * 1024    # one embedded picture, uncompressed
MAX_ODG_TOTAL_PICTURE_BYTES = 2 * 1024 ** 3  # all embedded pictures, uncompressed


def clamp(v: Any, lo: float, hi: float, default: float) -> float:
    """float(v) limited to [lo, hi]; junk, NaN and infinities give ``default``."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return min(max(x, lo), hi)


def page_dim(v: Any, default: float) -> float:
    return clamp(v, MIN_PAGE_PT, MAX_PAGE_PT, min(max(default, MIN_PAGE_PT), MAX_PAGE_PT))


def safe_export_dpi(page_w: float, page_h: float, dpi: float) -> float:
    """The highest dpi not above ``dpi`` whose bitmap stays inside the export budget."""
    w_in, h_in = max(page_w, 1.0) / 72.0, max(page_h, 1.0) / 72.0
    by_pixels = math.sqrt(MAX_EXPORT_PIXELS / (w_in * h_in))
    by_side = MAX_EXPORT_SIDE / max(w_in, h_in)
    best = min(float(dpi), by_pixels, by_side)
    return max(1.0, math.floor(best))


class TooBig(ValueError):
    """Input exceeds a resource limit.  The message is written for the user."""


class LoadBudget:
    """Counts what a document would create *before* any Qt object is made."""

    def __init__(self, pages: Optional[int] = None, objects: Optional[int] = None,
                 text_chars: Optional[int] = None, depth: Optional[int] = None):
        # read the module limits now, not when this module was imported
        g = globals()
        self.pages = g["MAX_PAGES"] if pages is None else pages
        self.objects = g["MAX_OBJECTS"] if objects is None else objects
        self.text_chars = g["MAX_TEXT_CHARS"] if text_chars is None else text_chars
        self.depth = g["MAX_GROUP_DEPTH"] if depth is None else depth
        self.n_pages = self.n_objects = self.n_chars = 0

    def check_document(self, data: Dict[str, Any]) -> None:
        pages = data.get("pages")
        if not isinstance(pages, list):
            return
        if len(pages) > self.pages:
            raise TooBig(f"This publication has {len(pages):,} pages; DTP Publisher can "
                         f"open up to {self.pages:,}.")
        for p in pages:
            if isinstance(p, dict):
                self.check_items(p.get("items"))

    def check_items(self, items: Any, depth: int = 0) -> None:
        if not isinstance(items, list):
            return
        if depth > self.depth:
            return          # deeper groups are skipped when loading
        for d in items:
            if not isinstance(d, dict):
                continue
            self.n_objects += 1
            if self.n_objects > self.objects:
                raise TooBig(f"This publication has more than {self.objects:,} objects, "
                             "which is more than DTP Publisher can safely open.")
            html = d.get("html")
            if isinstance(html, str):
                self.n_chars += len(html)
                if self.n_chars > self.text_chars:
                    raise TooBig("This publication has more text than DTP Publisher can "
                                 "safely open.")
            self.check_items(d.get("children"), depth + 1)


def describe_bytes(n: Optional[int]) -> str:
    if n is None:
        return "?"
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

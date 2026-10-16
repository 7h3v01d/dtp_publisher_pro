# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
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
# A 150-photo album is about 240 MB (pictures are stored as base64 text), so the
# file limit stays generous; what JSON parsing actually multiplies is structure
# (64 MB of "{}" took 1.5 GB), which MAX_JSON_NODES bounds before parsing.
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_JSON_NODES = 5_000_000           # objects + arrays + values, counted before parsing
MAX_PAGES = 1000
MAX_OBJECTS = 20_000                 # every object, counting those inside groups
MAX_OBJECTS_PER_PAGE = 2_000         # 5,000 full-page shapes took 5 s to paint
MAX_TEXT_CHARS = 50_000_000          # text-box HTML and table cells together
MAX_GROUP_DEPTH = 32
MAX_IMAGE_B64_CHARS = 96 * 1024 * 1024        # one embedded picture (about 72 MB)
MAX_EMBEDDED_PIXELS = 50_000_000     # pictures are stored at most 3000 px (9 MP) long side
MAX_TOTAL_IMAGE_B64_CHARS = 480 * 1024 * 1024
MAX_PATH_CHARS = 1_000_000           # one drawing's outline data (longer is cut short)
MAX_PAGE_PATH_CHARS = 2_000_000      # all drawings on a page: about 1 s to draw at worst
MAX_TOTAL_PATH_CHARS = 20_000_000

# ── drawings ─────────────────────────────────────────────────────────────────
# Qt's smoothed (antialiased) drawing costs about (edges crossed per pixel row) ×
# (rows): an outline of 90,000 random segments took over 6 minutes at 300 %.
# "Density" is the edges a horizontal line crosses on average: a circle is 2, a
# line of text turned into outlines about 90.  Denser drawings are drawn
# without smoothing, then as a labelled box; their data is kept either way.
MAX_SMOOTH_DENSITY = 400.0           # printing and PDFs
MAX_SCREEN_SMOOTH_WORK = 200.0       # on screen: density × zoom², shared by a page
ALWAYS_SMOOTH_DENSITY = 4.0          # simple shapes (a circle is 2, a ring 4): cheap
MAX_SMOOTH_DRAWINGS_PER_PAGE = 100   # however simple: overlapping smoothed shapes add up
MAX_DRAW_DENSITY = 2000.0
MAX_PAGE_DENSITY = 6000.0            # all drawings on one page together

# ── pictures ─────────────────────────────────────────────────────────────────
MAX_IMAGE_FILE_BYTES = 256 * 1024 * 1024     # a picture file chosen or dropped

# ── raster export (Save as Picture) ─────────────────────────────────────────
MAX_EXPORT_PIXELS = 150_000_000      # A0 at 300 dpi fits; about 600 MB of memory
MAX_EXPORT_SIDE = 30_000             # pixels on the longer side

# ── Publisher import ─────────────────────────────────────────────────────────
MAX_PUB_SOURCE_BYTES = 1024 ** 3            # the .pub itself (checked before copying)
MAX_CONVERTED_BYTES = 2 * 1024 ** 3          # the .odg LibreOffice writes
MAX_CONVERT_DIR_BYTES = 4 * 1024 ** 3        # the whole work folder while it runs
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
        self.n_image_chars = self.n_path_chars = 0
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
                before, paths_before = self.n_objects, self.n_path_chars
                self.check_items(p.get("items"))
                if self.n_objects - before > MAX_OBJECTS_PER_PAGE:
                    raise TooBig(f"A page in this publication has more than "
                                 f"{MAX_OBJECTS_PER_PAGE:,} objects, which is more than "
                                 "DTP Publisher can safely show.")
                if self.n_path_chars - paths_before > MAX_PAGE_PATH_CHARS:
                    raise TooBig("A page in this publication has drawings more detailed "
                                 "than DTP Publisher can safely show.")

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
            self._count_text(d)
            self._count_picture(d)
            self._count_path(d)
            self.check_items(d.get("children"), depth + 1)

    def _count_text(self, d: Dict[str, Any]) -> None:
        n = len(d["html"]) if isinstance(d.get("html"), str) else 0
        table = d.get("table")
        cells = table.get("cells") if isinstance(table, dict) else None
        if isinstance(cells, dict):
            n += sum(len(str(k)) + (len(v) if isinstance(v, str) else 8)
                     for k, v in cells.items())
        self.n_chars += n
        if self.n_chars > self.text_chars:
            raise TooBig("This publication has more text than DTP Publisher can "
                         "safely open.")

    def _count_picture(self, d: Dict[str, Any]) -> None:
        data = d.get("data")
        if d.get("kind") != "image" or not isinstance(data, str):
            return
        if len(data) > MAX_IMAGE_B64_CHARS:
            raise TooBig(f"A picture in this publication is {describe_bytes(len(data) * 3 // 4)}"
                         f"; pictures up to {describe_bytes(MAX_IMAGE_B64_CHARS * 3 // 4)} "
                         "can be opened.")
        self.n_image_chars += len(data)
        if self.n_image_chars > MAX_TOTAL_IMAGE_B64_CHARS:
            raise TooBig("The pictures in this publication add up to more than DTP "
                         "Publisher can safely open.")

    def _count_path(self, d: Dict[str, Any]) -> None:
        path = d.get("d")
        if d.get("kind") != "path" or not isinstance(path, str):
            return
        # one over-long drawing is cut short when loaded (see PathItem); the total
        # is what bounds the work
        self.n_path_chars += min(len(path), MAX_PATH_CHARS)
        if self.n_path_chars > MAX_TOTAL_PATH_CHARS:
            raise TooBig("The drawings in this publication are more detailed than DTP "
                         "Publisher can safely open.")


_JSON_STRING = None


def check_json_structure(raw: bytes, nodes: Optional[int] = None) -> None:
    """Refuse JSON whose *structure* would need far more memory than its size.

    Strings are cheap to parse (one object each, about their own size); every
    ``{}``, ``[]``, value and *key* is a Python object of 30–60+ bytes, so 64 MB
    of ``{}`` becomes 1.5 GB.  Objects are counted without parsing and without
    copying the file: one per ``,`` (a further value or entry), one per ``:`` (the
    key of an entry), one per ``{`` / ``[`` - each outside strings.
    """
    import re
    global _JSON_STRING
    if _JSON_STRING is None:
        _JSON_STRING = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"')
    limit = MAX_JSON_NODES if nodes is None else nodes
    n = (raw.count(b",") + raw.count(b":") + raw.count(b"{") + raw.count(b"[")
         + 1)                                       # fast, no copy; an upper bound
    if n <= limit:
        return
    # over the limit only if the separators are not inside text: count those
    strings = 0
    for m in _JSON_STRING.finditer(raw):
        strings += 1
        if strings > limit:                         # every string is a value too
            break
        t = m.group()
        n -= t.count(b",") + t.count(b":") + t.count(b"{") + t.count(b"[")
    if n > limit or strings > limit:
        n = max(n, strings)
        raise TooBig(f"This file has {n:,} separate values; DTP Publisher can safely open "
                     f"up to {limit:,}.")


def describe_bytes(n: Optional[int]) -> str:
    if n is None:
        return "?"
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

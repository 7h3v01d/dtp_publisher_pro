# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""PDF, print and picture export.

Bug #2 in the prototype: it painted page *points* onto a 1200-dpi printer,
so a full page came out ~6% wide in the top-left corner.  Here every target
rect is computed in the device's own units, each page gets its own page
size, and selection handles/guides/grid are never drawn (``rendering``).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable, List, Optional

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PyQt6.QtPrintSupport import QPrinter

from . import APP_NAME, __version__
from .document import Document
from .scene import PageScene

PDF_DPI = 1200


def page_layout(w_pt: float, h_pt: float) -> QPageLayout:
    landscape = w_pt > h_pt
    pw, ph = (h_pt, w_pt) if landscape else (w_pt, h_pt)
    size = QPageSize(QSizeF(pw, ph), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch)
    return QPageLayout(size, QPageLayout.Orientation.Landscape if landscape
                       else QPageLayout.Orientation.Portrait,
                       QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)


@contextmanager
def rendering(scene: PageScene, end_edits: bool = True):
    """Hide editing aids (handles, guides, grid, text caret) while rendering."""
    from .items.text import TextItem
    if end_edits:
        for it in scene.all_design_items():
            if isinstance(it, TextItem) and it.editing:
                it.end_edit()
    scene.flush_wrap()
    old = scene.rendering
    scene.rendering = True
    scene.set_snap_lines([])
    try:
        yield
    finally:
        scene.rendering = old


def render_page(scene: PageScene, painter: QPainter, target: QRectF,
                keep_aspect: bool = True, end_edits: bool = True):
    """Draw one page into ``target`` (device units of ``painter``)."""
    src = scene.page_rect()
    with rendering(scene, end_edits):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if keep_aspect:
            s = min(target.width() / src.width(), target.height() / src.height())
            w, h = src.width() * s, src.height() * s
            target = QRectF(target.left() + (target.width() - w) / 2,
                            target.top() + (target.height() - h) / 2, w, h)
        painter.setClipRect(target)
        scene.render(painter, target, src, Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.restore()


def sheet_jobs(doc: Document, pages: Optional[Iterable[int]] = None):
    """For label publications: [(paper_w_pt, paper_h_pt, [(cell_rect_pt, page_index)])]."""
    from . import labels
    layout = labels.from_dict(doc.sheet)
    if layout is None:
        return None
    idx = list(pages) if pages is not None else list(range(len(doc.pages)))
    mode = (doc.sheet or {}).get("mode", "copies")
    cells = labels.cells(layout)
    jobs = []
    for assignment in labels.plan(len(idx), layout, mode):
        jobs.append((mm_to_pt(layout.paper_w), mm_to_pt(layout.paper_h),
                     [(cells[c], idx[i]) for c, i in enumerate(assignment) if i >= 0]))
    return jobs


def mm_to_pt(v: float) -> float:
    return v * 72.0 / 25.4


def render_sheet(doc: Document, painter: QPainter, dpi: float, cells):
    k = dpi / 72.0
    for rect, i in cells:
        target = QRectF(rect.left() * k, rect.top() * k, rect.width() * k, rect.height() * k)
        render_page(doc.pages[i], painter, target, keep_aspect=True)


def export_pdf(doc: Document, path: str, pages: Optional[Iterable[int]] = None,
               as_sheets: bool = True) -> int:
    """Write a PDF.  Label publications are written as printed sheets."""
    idx = list(pages) if pages is not None else list(range(len(doc.pages)))
    if not idx:
        raise ValueError("No pages to export")
    jobs = sheet_jobs(doc, idx) if as_sheets else None
    if jobs:
        w = QPdfWriter(path)
        w.setResolution(PDF_DPI)
        w.setCreator(f"{APP_NAME} {__version__}")
        w.setTitle(doc.title or os.path.splitext(os.path.basename(path))[0])
        w.setPageLayout(page_layout(jobs[0][0], jobs[0][1]))
        p = QPainter()
        if not p.begin(w):
            raise OSError(f"Cannot write PDF: {path}")
        try:
            for n, (_pw, _ph, cells) in enumerate(jobs):
                if n > 0:
                    w.newPage()
                render_sheet(doc, p, w.resolution(), cells)
        finally:
            p.end()
        return len(jobs)
    w = QPdfWriter(path)
    w.setResolution(PDF_DPI)
    w.setCreator(f"{APP_NAME} {__version__}")
    w.setTitle(doc.title or os.path.splitext(os.path.basename(path))[0])
    first = doc.pages[idx[0]]
    w.setPageLayout(page_layout(first.page_w, first.page_h))
    p = QPainter()
    if not p.begin(w):
        raise OSError(f"Cannot write PDF: {path}")
    try:
        for n, i in enumerate(idx):
            sc = doc.pages[i]
            if n > 0:
                w.setPageLayout(page_layout(sc.page_w, sc.page_h))
                w.newPage()
            dpi = w.resolution()
            target = QRectF(0, 0, sc.page_w / 72.0 * dpi, sc.page_h / 72.0 * dpi)
            render_page(sc, p, target, keep_aspect=False)
    finally:
        p.end()
    return len(idx)


def render_thumbnail(scene: PageScene, max_w: int, max_h: int) -> QImage:
    """Small preview of a page (empty photo frames are shown, unlike print)."""
    s = min(max_w / scene.page_w, max_h / scene.page_h)
    img = QImage(max(1, round(scene.page_w * s)), max(1, round(scene.page_h * s)),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("white"))
    old = scene.preview
    scene.preview = True
    try:
        p = QPainter(img)
        render_page(scene, p, QRectF(0, 0, img.width(), img.height()), keep_aspect=False,
                    end_edits=False)
        p.end()
    finally:
        scene.preview = old
    return img


def render_page_image(scene: PageScene, dpi: float = 150, transparent: bool = False,
                      opaque: bool = False) -> QImage:
    """Rasterise a page.  Refuses (``limits.TooBig``) rather than allocate gigabytes;
    callers pick a safe dpi with ``limits.safe_export_dpi`` first."""
    from . import limits
    wpx = max(1, round(scene.page_w / 72.0 * dpi))
    hpx = max(1, round(scene.page_h / 72.0 * dpi))
    if wpx * hpx > limits.MAX_EXPORT_PIXELS or max(wpx, hpx) > limits.MAX_EXPORT_SIDE:
        raise limits.TooBig(f"A {wpx:,} × {hpx:,} pixel picture is too big to make.")
    fmt = QImage.Format.Format_RGB32 if opaque and not transparent \
        else QImage.Format.Format_ARGB32_Premultiplied
    img = QImage(wpx, hpx, fmt)
    if img.isNull():
        raise limits.TooBig("There is not enough memory to make a picture this big.")
    img.fill(QColor(0, 0, 0, 0) if transparent else QColor("white"))
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    p = QPainter(img)
    render_page(scene, p, QRectF(0, 0, wpx, hpx), keep_aspect=False)
    p.end()
    return img


def export_dpi(doc: Document, pages: Optional[Iterable[int]], dpi: float) -> float:
    """The dpi Save as Picture will really use: lowered for pages that are too big."""
    from . import limits
    idx = list(pages) if pages is not None else list(range(len(doc.pages)))
    return min([limits.safe_export_dpi(doc.pages[i].page_w, doc.pages[i].page_h, dpi)
                for i in idx] or [dpi])


def export_images(doc: Document, folder: str, base: str, fmt: str = "png", dpi: float = 150,
                  pages: Optional[Iterable[int]] = None) -> List[str]:
    idx = list(pages) if pages is not None else list(range(len(doc.pages)))
    out = []
    ext = "jpg" if fmt.lower() in ("jpg", "jpeg") else "png"
    dpi = export_dpi(doc, idx, dpi)
    for i in idx:
        img = render_page_image(doc.pages[i], dpi, opaque=(ext == "jpg"))
        name = f"{base}.{ext}" if len(idx) == 1 else f"{base}-page{i + 1}.{ext}"
        path = os.path.join(folder, name)
        if not img.save(path, "JPG" if ext == "jpg" else "PNG", 92 if ext == "jpg" else -1):
            raise OSError(f"Cannot write {path}")
        out.append(path)
    return out


def print_document(doc: Document, printer: QPrinter, pages: Optional[Iterable[int]] = None,
                   fit_to_paper: bool = True) -> int:
    """Print pages.

    When a page is the same size as the paper (A4 flyer on A4, a label sheet)
    it prints at exact size from the paper's corner, so labels and business
    cards line up with pre-cut sheets.  Otherwise, with ``fit_to_paper``, it
    is scaled to the printable area; without it, printed actual size, centred.
    """
    idx = list(pages) if pages is not None else list(range(len(doc.pages)))
    if not idx:
        return 0
    jobs = sheet_jobs(doc, idx)
    if jobs:
        printer.setFullPage(True)
        printer.setPageLayout(page_layout(jobs[0][0], jobs[0][1]))
        p = QPainter()
        if not p.begin(printer):
            raise OSError("Cannot start the printer.")
        try:
            for n, (_pw, _ph, cells) in enumerate(jobs):
                if n > 0:
                    printer.newPage()
                render_sheet(doc, p, printer.resolution(), cells)
        finally:
            p.end()
        return len(jobs)
    # remember the printer's margins: full-page mode (needed for exact-size
    # printing from the paper corner) resets them to zero
    margins = printer.pageLayout().margins(QPageLayout.Unit.Point)
    printer.setFullPage(True)
    p = QPainter()
    if not p.begin(printer):
        raise OSError("Cannot start the printer.")
    try:
        for n, i in enumerate(idx):
            sc = doc.pages[i]
            if n > 0:
                printer.newPage()
            dpi = printer.resolution()
            paper = printer.paperRect(QPrinter.Unit.Point)
            k = dpi / 72.0
            printable = QRectF(margins.left() * k, margins.top() * k,
                               (paper.width() - margins.left() - margins.right()) * k,
                               (paper.height() - margins.top() - margins.bottom()) * k)
            w, h = sc.page_w / 72.0 * dpi, sc.page_h / 72.0 * dpi
            if same_size(sc.page_w, sc.page_h, paper.width(), paper.height()):
                render_page(sc, p, QRectF(0, 0, w, h), keep_aspect=False)
            elif fit_to_paper:
                render_page(sc, p, QRectF(printable), keep_aspect=True)
            else:
                pw = paper.width() / 72.0 * dpi
                ph = paper.height() / 72.0 * dpi
                render_page(sc, p, QRectF((pw - w) / 2, (ph - h) / 2, w, h), keep_aspect=False)
    finally:
        p.end()
    return len(idx)


def same_size(w: float, h: float, pw: float, ph: float, tol: float = 0.02) -> bool:
    return abs(w - pw) <= max(pw, 1) * tol and abs(h - ph) <= max(ph, 1) * tol

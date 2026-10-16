# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Windows Metafile (WMF/EMF) → picture.

Old Publisher files store most photos as a WMF/EMF wrapper around an ordinary
bitmap (a DIB).  Those are unwrapped losslessly.  Simple vector clip art
(polygons, lines, rectangles, ellipses) is drawn with a small WMF renderer.
Anything else returns None so the caller can fall back to LibreOffice.

Everything here treats the input as untrusted: every offset and size is
bounds-checked and record counts are capped.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

MAX_RECORDS = 200_000
MAX_PIXELS = 40_000_000


# ── DIB → BMP ────────────────────────────────────────────────────────────────
def dib_to_image(dib: bytes) -> Optional[QImage]:
    """Decode a packed DIB (BITMAPINFOHEADER + palette + bits)."""
    if len(dib) < 12:
        return None
    hsize = struct.unpack_from("<I", dib, 0)[0]
    if hsize == 12:                                # BITMAPCOREHEADER
        w, h, _planes, bpp = struct.unpack_from("<HHHH", dib, 4)
        comp, clr_used = 0, 0
        pal_entry = 3
    elif 40 <= hsize <= len(dib):
        w, h, _planes, bpp, comp = struct.unpack_from("<iiHHI", dib, 4)
        clr_used = struct.unpack_from("<I", dib, 32)[0] if hsize >= 36 else 0
        pal_entry = 4
    else:
        return None
    if w <= 0 or h == 0 or abs(w) * abs(h) > MAX_PIXELS or bpp not in (1, 4, 8, 16, 24, 32):
        return None
    colors = clr_used if clr_used else ((1 << bpp) if bpp <= 8 else 0)
    if colors > 256:
        return None
    masks = 12 if (hsize == 40 and comp == 3) else 0          # BI_BITFIELDS
    off_bits = 14 + hsize + masks + colors * pal_entry
    bmp = b"BM" + struct.pack("<IHHI", 14 + len(dib), 0, 0, off_bits) + dib
    img = QImage()
    if img.loadFromData(bmp, "BMP") and not img.isNull():
        return img
    return None


# ── WMF ──────────────────────────────────────────────────────────────────────
def _wmf_records(b: bytes):
    off = 22 if b[:4] == b"\xd7\xcd\xc6\x9a" else 0
    if len(b) < off + 18:
        return
    hwords = struct.unpack_from("<H", b, off + 2)[0]
    p = off + max(hwords, 9) * 2
    n = 0
    while p + 6 <= len(b) and n < MAX_RECORDS:
        size = struct.unpack_from("<I", b, p)[0] * 2
        fn = struct.unpack_from("<H", b, p + 4)[0]
        if size < 6 or p + size > len(b):
            return
        yield fn, b[p + 6:p + size]
        if fn == 0:
            return
        p += size
        n += 1


def _wmf_dib(fn: int, data: bytes) -> Optional[bytes]:
    if fn == 0x0F43 and len(data) > 22:          # META_STRETCHDIB
        return data[22:]
    if fn == 0x0B41 and len(data) > 20:          # META_DIBSTRETCHBLT (with bitmap)
        return data[20:]
    if fn == 0x0940 and len(data) > 16:          # META_DIBBITBLT (with bitmap)
        return data[16:]
    if fn == 0x0D33 and len(data) > 18:          # META_SETDIBTODEV
        return data[18:]
    return None


# drawing records (0x0626 META_ESCAPE is *not* drawing; Publisher adds it to photos)
VECTOR_FNS = {0x0324, 0x0325, 0x0538, 0x041B, 0x0418, 0x061C, 0x0213, 0x0817, 0x0A32,
              0x0521, 0x081A, 0x0830, 0x0A24}


def wmf_to_image(b: bytes, max_px: int = 2000) -> Optional[QImage]:
    recs = list(_wmf_records(b))
    if not recs:
        return None
    dibs = [d for d in (_wmf_dib(fn, data) for fn, data in recs) if d]
    vector = sum(1 for fn, _ in recs if fn in VECTOR_FNS)
    if dibs and vector == 0:
        best = max(dibs, key=len)
        return dib_to_image(best)
    return _render_wmf(b, recs, max_px)


def _s16(data: bytes, i: int) -> int:
    return struct.unpack_from("<h", data, i * 2)[0] if len(data) >= i * 2 + 2 else 0


def _colorref(data: bytes, off: int) -> QColor:
    if len(data) < off + 3:
        return QColor(0, 0, 0)
    r, g, bl = data[off], data[off + 1], data[off + 2]
    return QColor(r, g, bl)


def _render_wmf(b: bytes, recs, max_px: int) -> Optional[QImage]:
    # logical bounds: placeable header bbox, else SETWINDOWORG/EXT
    org, ext = (0, 0), None
    if b[:4] == b"\xd7\xcd\xc6\x9a" and len(b) >= 22:
        l, t, r, bt = struct.unpack_from("<hhhh", b, 6)
        org, ext = (l, t), (r - l, bt - t)
    for fn, data in recs:
        if fn == 0x020B:
            org = (_s16(data, 1), _s16(data, 0))
        elif fn == 0x020C and ext is None:
            ext = (_s16(data, 1), _s16(data, 0))
    if not ext or ext[0] == 0 or ext[1] == 0:
        return None
    ew, eh = abs(ext[0]), abs(ext[1])
    scale = max_px / max(ew, eh)
    iw, ih = max(1, round(ew * scale)), max(1, round(eh * scale))
    img = QImage(iw, ih, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    sx = iw / ext[0]
    sy = ih / ext[1]
    p.translate(-org[0] * sx if sx > 0 else iw - org[0] * sx, -org[1] * sy if sy > 0 else
                ih - org[1] * sy)
    p.scale(sx, sy)
    objects: List[object] = []
    pen, brush = QPen(QColor(0, 0, 0)), QBrush(QColor(255, 255, 255))
    pen.setCosmetic(True)
    fill_rule = Qt.FillRule.OddEvenFill
    cur = QPointF(0, 0)
    drew = False

    def add_obj(o):
        for i, x in enumerate(objects):
            if x is None:
                objects[i] = o
                return
        objects.append(o)

    for fn, data in recs:
        try:
            if fn == 0x02FA:                                   # CREATEPENINDIRECT
                style = _s16(data, 0) & 0x0F
                w = abs(_s16(data, 1))
                qp = QPen(_colorref(data, 6), max(w, 0))
                qp.setCosmetic(w <= 1)
                if style == 5:
                    qp = QPen(Qt.PenStyle.NoPen)
                add_obj(("pen", qp))
            elif fn == 0x02FC:                                 # CREATEBRUSHINDIRECT
                style = _s16(data, 0)
                qb = QBrush(Qt.BrushStyle.NoBrush) if style == 1 else QBrush(_colorref(data, 2))
                add_obj(("brush", qb))
            elif fn in (0x00F7, 0x0142, 0x06FF, 0x01F9, 0x02FB):  # palette/region/font/dib brush
                add_obj(("other", None))
            elif fn == 0x012D:                                 # SELECTOBJECT
                i = _s16(data, 0)
                if 0 <= i < len(objects) and objects[i] is not None:
                    kind, o = objects[i]
                    if kind == "pen":
                        pen = o
                    elif kind == "brush":
                        brush = o
            elif fn == 0x01F0:                                 # DELETEOBJECT
                i = _s16(data, 0)
                if 0 <= i < len(objects):
                    objects[i] = None
            elif fn == 0x0106:                                 # SETPOLYFILLMODE
                fill_rule = (Qt.FillRule.WindingFill if _s16(data, 0) == 2
                             else Qt.FillRule.OddEvenFill)
            elif fn in (0x0324, 0x0325):                       # POLYGON / POLYLINE
                n = _s16(data, 0)
                pts = [QPointF(_s16(data, 1 + 2 * i), _s16(data, 2 + 2 * i)) for i in range(n)]
                p.setPen(pen)
                if fn == 0x0324:
                    p.setBrush(brush)
                    p.drawPolygon(QPolygonF(pts), fill_rule)
                else:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPolyline(QPolygonF(pts))
                drew = True
            elif fn == 0x0538:                                 # POLYPOLYGON
                npoly = _s16(data, 0)
                counts = [_s16(data, 1 + i) for i in range(npoly)]
                idx = 1 + npoly
                path = QPainterPath()
                path.setFillRule(fill_rule)
                for c in counts:
                    pts = [QPointF(_s16(data, idx + 2 * i), _s16(data, idx + 1 + 2 * i))
                           for i in range(c)]
                    idx += 2 * c
                    path.addPolygon(QPolygonF(pts))
                    path.closeSubpath()
                p.setPen(pen)
                p.setBrush(brush)
                p.drawPath(path)
                drew = True
            elif fn in (0x041B, 0x0418):                       # RECTANGLE / ELLIPSE
                bt, r, t, l = (_s16(data, i) for i in range(4))
                p.setPen(pen)
                p.setBrush(brush)
                rect = QRectF(min(l, r), min(t, bt), abs(r - l), abs(bt - t))
                (p.drawRect if fn == 0x041B else p.drawEllipse)(rect)
                drew = True
            elif fn == 0x061C:                                 # ROUNDRECT
                h, w, bt, r, t, l = (_s16(data, i) for i in range(6))
                p.setPen(pen)
                p.setBrush(brush)
                p.drawRoundedRect(QRectF(min(l, r), min(t, bt), abs(r - l), abs(bt - t)),
                                  abs(w) / 2, abs(h) / 2)
                drew = True
            elif fn == 0x0214:                                 # MOVETO
                cur = QPointF(_s16(data, 1), _s16(data, 0))
            elif fn == 0x0213:                                 # LINETO
                nxt = QPointF(_s16(data, 1), _s16(data, 0))
                p.setPen(pen)
                p.drawLine(cur, nxt)
                cur = nxt
                drew = True
            elif fn in (0x0F43, 0x0B41, 0x0940):               # bitmaps inside drawings
                dib = _wmf_dib(fn, data)
                im = dib_to_image(dib) if dib else None
                if im is not None:
                    if fn == 0x0F43:
                        dh, dw, dy, dx = (_s16(data, i) for i in range(7, 11))
                    elif fn == 0x0B41:
                        dh, dw, dy, dx = (_s16(data, i) for i in range(6, 10))
                    else:
                        dh, dw, dy, dx = (_s16(data, i) for i in range(4, 8))
                    p.drawImage(QRectF(dx, dy, dw, dh), im)
                    drew = True
        except (struct.error, IndexError, ValueError):
            continue
    p.end()
    return img if drew else None


# ── EMF ──────────────────────────────────────────────────────────────────────
def emf_to_image(b: bytes) -> Optional[QImage]:
    """Unwrap the largest bitmap from an EMF (vector EMF returns None)."""
    p, n, best = 0, 0, None
    while p + 8 <= len(b) and n < MAX_RECORDS:
        typ, size = struct.unpack_from("<II", b, p)
        if size < 8 or p + size > len(b):
            break
        rec = b[p:p + size]
        layout = {81: (48, 52, 56, 60), 76: (84, 88, 92, 96), 77: (84, 88, 92, 96)}.get(typ)
        if layout and len(rec) >= layout[3] + 4:
            ob, cb, obits, cbits = (struct.unpack_from("<I", rec, o)[0] for o in layout)
            if 0 < ob and ob + cb <= len(rec) and 0 < obits and obits + cbits <= len(rec):
                dib = rec[ob:ob + cb] + rec[obits:obits + cbits]
                if best is None or len(dib) > len(best):
                    best = dib
        if typ == 14:                      # EMR_EOF
            break
        p += size
        n += 1
    return dib_to_image(best) if best else None


def metafile_to_image(data: bytes) -> Tuple[Optional[QImage], str]:
    """Returns (image, kind) where kind is 'bitmap', 'vector' or ''."""
    if data[:4] == b"\x01\x00\x00\x00" and data[40:44] == b" EMF":
        img = emf_to_image(data)
        return img, ("bitmap" if img is not None else "")
    img = None
    recs = list(_wmf_records(data))
    if recs:
        img = wmf_to_image(data)
        if img is not None:
            vector = any(fn in VECTOR_FNS for fn, _ in recs)
            return img, ("vector" if vector else "bitmap")
    return None, ""

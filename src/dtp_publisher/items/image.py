# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""ImageItem — a picture frame (empty frames act as photo placeholders)."""

from __future__ import annotations

import base64
import math
import os
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (QColor, QFont, QImage, QImageIOHandler, QImageReader, QPainter,
                         QPainterPath, QPen, QPixmap)

from .. import theme
from .base import BaseItem, num

FIT_MODES = {"fill": "Fill frame (crop)", "fit": "Fit inside frame", "stretch": "Stretch"}
MAX_EMBED_PX = 3000      # long side; larger photos are downsampled when inserted
PREVIEW_PX = 1600        # most on-screen preview resolution
MIN_PREVIEW_PX = 256
PREVIEW_ZOOM = 4.0       # previews stay sharp up to about 300 % zoom
OUTPUT_DPI = 300         # photos in PDFs and prints: the usual print-shop resolution
_FULL_CACHE: list = []   # [(key, QImage)] — the last few full-size decodes, for printing
_FULL_CACHE_SIZE = 2


def read_image_bytes(data: bytes, scaled_long: Optional[int] = None) -> QImage:
    """Decode stored picture bytes, optionally straight to a smaller size.

    Never decodes more than ``MAX_EMBED_PX`` on the long side: a file can hold a
    huge picture, but nothing is ever held at more than the insert size.
    """
    if not data:
        return QImage()
    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    try:
        reader = QImageReader(buf)
        reader.setAutoTransform(False)          # stored pictures are already upright
        size = reader.size()
        if size.isValid():
            cap = min(scaled_long or MAX_EMBED_PX, MAX_EMBED_PX)
            if max(size.width(), size.height()) > cap:
                reader.setScaledSize(size.scaled(cap, cap, Qt.AspectRatioMode.KeepAspectRatio))
        return reader.read()
    finally:
        buf.close()


def image_bytes_size(data: bytes) -> QSize:
    """Picture size from the header alone (nothing is decoded)."""
    if not data:
        return QSize()
    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    try:
        return QImageReader(buf).size()
    finally:
        buf.close()


def encode_image(img: QImage, prefer: str = "auto", quality: int = 90) -> Tuple[bytes, str]:
    fmt = prefer
    if fmt == "auto":
        fmt = "png" if img.hasAlphaChannel() else "jpg"
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG" if fmt == "png" else "JPG", quality if fmt == "jpg" else -1)
    buf.close()
    return bytes(ba.data()), fmt


def _decode(device, max_px: Optional[int], upright: bool) -> Tuple[QImage, bool, bool]:
    """Decode from a QIODevice or path.  Returns (img, rotated, scaled).

    The header is read first; pictures bigger than ``max_px`` are decoded at a
    reduced size where the format allows it (JPEG decodes straight to the
    smaller size), so a 100-megapixel phone photo never needs 400 MB.  Qt's
    own allocation limit still guards every decode.
    """
    reader = QImageReader(device)
    reader.setAutoTransform(upright)
    size = reader.size()
    scaled = False
    if max_px and size.isValid() and max(size.width(), size.height()) > max_px:
        reader.setScaledSize(size.scaled(max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio))
        scaled = True
    img = reader.read()
    rotated = upright and reader.transformation() != QImageIOHandler.Transformation.TransformationNone
    return img, rotated, scaled and not img.isNull()


def _read_upright(raw: bytes, max_px: Optional[int] = None) -> Tuple[QImage, bool, bool]:
    """Decode bytes, applying EXIF orientation (phone photos)."""
    ba = QByteArray(raw)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    try:
        return _decode(buf, max_px, True)
    finally:
        buf.close()


def _finish(img: QImage, raw: Optional[bytes], rotated: bool, scaled: bool,
            max_px: int) -> Optional[Tuple[bytes, str, QImage]]:
    if img.isNull():
        return None
    if max(img.width(), img.height()) > max_px:      # formats without scaled decoding
        img = img.scaled(max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        scaled = True
    if raw is not None and not rotated and not scaled:
        head = raw[:12]
        if head.startswith(b"\x89PNG"):
            return raw, "png", img
        if head.startswith(b"\xff\xd8"):
            return raw, "jpg", img
    data, fmt = encode_image(img)
    return data, fmt, img


def prepare_image_bytes(raw: bytes, max_px: int = MAX_EMBED_PX) -> Optional[Tuple[bytes, str, QImage]]:
    """Validate/downsample image bytes for embedding.  Returns (data, fmt, image).

    Photos are stored upright (EXIF orientation applied) and no larger than
    ``max_px`` on the long side, so documents stay a sensible size.
    """
    img, rotated, scaled = _read_upright(raw, max_px)
    return _finish(img, raw, rotated, scaled, max_px)


def image_file_problem(path: str) -> Optional[str]:
    """Why a picture file can't be used, in words for the user (None if it might)."""
    from ..limits import MAX_IMAGE_FILE_BYTES, describe_bytes
    try:
        size = os.path.getsize(path)
    except OSError:
        return "The file could not be opened."
    if size > MAX_IMAGE_FILE_BYTES:
        return (f"The file is {describe_bytes(size)}; pictures up to "
                f"{describe_bytes(MAX_IMAGE_FILE_BYTES)} can be used.")
    return None


def load_image_file(path: str, max_px: int = MAX_EMBED_PX) -> Optional[Tuple[bytes, str, QImage]]:
    """Read a picture file without ever holding more than it needs.

    The size is checked before reading, and big pictures are decoded straight
    from the file at the reduced size; only pictures that are kept as they are
    have their bytes read in full.
    """
    if image_file_problem(path):
        return None
    img, rotated, scaled = _decode(path, max_px, True)
    if img.isNull():
        return None
    raw = None
    if not rotated and not scaled and max(img.width(), img.height()) <= max_px:
        from ..limits import MAX_IMAGE_FILE_BYTES
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_IMAGE_FILE_BYTES + 1)
        except OSError:
            return None
        if len(raw) > MAX_IMAGE_FILE_BYTES:         # it grew since it was checked
            return None
    return _finish(img, raw, rotated, scaled, max_px)


class ImageItem(BaseItem):
    KIND = "image"
    DISPLAY = "Picture"
    KEEP_ASPECT = True
    SHOW_BOUNDARY = True
    MIN_W = 12.0
    MIN_H = 12.0

    def __init__(self, w: float = 200, h: float = 150):
        super().__init__(w, h)
        self.fit_mode = "fill"
        self.crop_x = 0.0      # -1..1 focus offset in fill mode
        self.crop_y = 0.0
        self.corner = 0.0      # corner radius (pt)
        self.data: bytes = b""
        self.fmt = ""
        self.source_name = ""
        self._size = QSize()           # picture size (as it will be drawn)
        self._preview = QPixmap()      # screen copy, sized to the frame
        self._b64: Optional[str] = None
        self._too_big = None
        self.stroke = QColor(60, 60, 60)
        self.stroke_width = 0.0
        self.wrap = "square"           # as in Publisher: text flows round pictures

    def display_name(self) -> str:
        if self.name:
            return self.name
        return f"Picture — {self.source_name}" if self.source_name else (
            "Picture" if self.has_image() else "Picture placeholder")

    # ── image data ──────────────────────────────────────────────────────────
    def has_image(self) -> bool:
        return self._size.isValid() and not self._size.isEmpty()

    def image(self) -> QImage:
        """The picture at full size (decoded when asked; not kept)."""
        return self.full_image()

    def full_image(self) -> QImage:
        if not self.has_image():
            return QImage()
        key = (id(self.data), len(self.data))
        for k, img in _FULL_CACHE:
            if k == key:
                return img
        img = read_image_bytes(self.data)
        _FULL_CACHE.insert(0, (key, img))
        del _FULL_CACHE[_FULL_CACHE_SIZE:]
        return img

    def set_image_data(self, data: bytes, fmt: str, name: str = "",
                       image: Optional[QImage] = None):
        """Only the compressed bytes and a frame-sized preview are kept: a
        150-photo album would otherwise hold gigabytes of decoded pixels."""
        self.data = bytes(data or b"")
        self._b64 = None                         # cached text form for saving
        self.fmt = fmt or ""
        self.source_name = name or ""
        self._preview = QPixmap()
        self._size = QSize()
        self._too_big = None
        if image is not None and not image.isNull():
            self._size = image.size()
            self._make_preview(image)
        elif self.data:
            from ..limits import MAX_EMBEDDED_PIXELS
            size = image_bytes_size(self.data)
            if size.isValid() and size.width() * size.height() > MAX_EMBEDDED_PIXELS:
                self._too_big = (size.width(), size.height())   # not made by this program
                size = QSize()
            if size.isValid() and not size.isEmpty():
                if max(size.width(), size.height()) > MAX_EMBED_PX:
                    size = size.scaled(MAX_EMBED_PX, MAX_EMBED_PX,
                                       Qt.AspectRatioMode.KeepAspectRatio)
                self._size = size
                # the screen preview is made when the picture is first drawn, so
                # opening a 100-page album only decodes the pages you look at
        self.update()

    def _preview_needed(self) -> int:
        """Long side (pixels) the screen preview needs for this frame."""
        if not self.has_image():
            return 0
        iw, ih = self._size.width(), self._size.height()
        r = self.rect()
        sx, sy = r.width() / max(iw, 1), r.height() / max(ih, 1)
        s = min(sx, sy) if self.fit_mode == "fit" else max(sx, sy)
        want = max(iw, ih) * s * PREVIEW_ZOOM
        return int(min(max(iw, ih), PREVIEW_PX, max(MIN_PREVIEW_PX, want)))

    def _make_preview(self, image: Optional[QImage] = None) -> bool:
        px = self._preview_needed()
        if px <= 0:
            return False
        if image is not None:
            pv = image
            if max(pv.width(), pv.height()) > px:
                pv = pv.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        else:
            pv = read_image_bytes(self.data, px)
            if pv.isNull():
                return False
            if max(pv.width(), pv.height()) > px:      # formats without scaled decoding
                pv = pv.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self._preview = QPixmap.fromImage(pv)
        return True

    def _preview_ok(self) -> bool:
        """Make the preview when first drawn, and a sharper one if the frame has
        grown a lot.  False if the picture can't be decoded after all."""
        if not self.has_image():
            return False
        have = max(self._preview.width(), self._preview.height())
        need = self._preview_needed()
        if have == 0 or need > have * 1.25:
            if not self._make_preview() and have == 0:
                return False
        return True

    def get_prop(self, key: str):
        if key == "image":
            return (self.data, self.fmt, self.source_name)
        return super().get_prop(key)

    def set_prop(self, key: str, value):
        if key == "image":
            data, fmt, name = value
            self.set_image_data(data, fmt, name)
            return
        super().set_prop(key, value)

    def natural_aspect(self) -> float:
        if not self.has_image():
            return self._w / max(self._h, 1e-6)
        return self._size.width() / max(self._size.height(), 1)

    # ── painting ─────────────────────────────────────────────────────────────
    def _clip_path(self) -> QPainterPath:
        p = QPainterPath()
        if self.corner > 0:
            r = min(self.corner, self._w / 2, self._h / 2)
            p.addRoundedRect(self.rect(), r, r)
        else:
            p.addRect(self.rect())
        return p

    def _source_target(self, iw: float, ih: float) -> Tuple[QRectF, QRectF]:
        r = self.rect()
        if self.fit_mode == "stretch":
            return QRectF(0, 0, iw, ih), r
        if self.fit_mode == "fit":
            s = min(r.width() / iw, r.height() / ih)
            tw, th = iw * s, ih * s
            return QRectF(0, 0, iw, ih), QRectF((r.width() - tw) / 2, (r.height() - th) / 2, tw, th)
        s = max(r.width() / iw, r.height() / ih)
        sw, sh = r.width() / s, r.height() / s
        fx = max(-1.0, min(1.0, self.crop_x))
        fy = max(-1.0, min(1.0, self.crop_y))
        sx = (iw - sw) / 2 * (1 + fx)
        sy = (ih - sh) / 2 * (1 + fy)
        return QRectF(sx, sy, sw, sh), r

    def paint_content(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        clip = self._clip_path()
        if self.fill.alpha():
            p.fillPath(clip, self.fill)
        if self.has_image():
            p.save()
            p.setClipPath(clip)
            if self.is_rendering():
                self._draw_for_output(p)
            elif self._preview_ok():
                pw, ph = self._preview.width(), self._preview.height()
                src, dst = self._source_target(pw, ph)
                p.drawPixmap(dst, self._preview, src)
            else:
                p.fillRect(self.rect(), QColor(220, 220, 220))   # damaged inside
            p.restore()
        elif not self.is_rendering() or (self.page_scene() and self.page_scene().preview):
            self._paint_placeholder(p)
        pen = self.make_pen()
        if pen.style() != Qt.PenStyle.NoPen:
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(clip)

    def _draw_for_output(self, p: QPainter):
        """Draw the photo for a PDF, print or picture export at no more than
        OUTPUT_DPI: a 3000-pixel photo in a 5 cm frame doesn't need 3000 pixels
        (the 150-photo album's PDF was 323 MB)."""
        img = self.full_image()
        src, dst = self._source_target(img.width(), img.height())
        dev = p.device()
        if dev is None or isinstance(dev, (QImage, QPixmap)):
            p.drawImage(dst, img, src)                   # Save as Picture: every pixel
            return
        dpi = dev.logicalDpiX()
        m = p.worldTransform()
        scale = math.hypot(m.m11(), m.m12())             # item units -> device pixels
        need = dst.width() * scale * min(1.0, OUTPUT_DPI / max(dpi, 1))
        if need >= 1 and src.width() > need * 1.1:
            k = need / src.width()
            box = src.toAlignedRect().intersected(img.rect())
            piece = img.copy(box).scaled(max(1, round(box.width() * k)),
                                         max(1, round(box.height() * k)),
                                         Qt.AspectRatioMode.IgnoreAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
            kx = piece.width() / max(box.width(), 1)
            ky = piece.height() / max(box.height(), 1)
            sub = QRectF((src.left() - box.left()) * kx, (src.top() - box.top()) * ky,
                         src.width() * kx, src.height() * ky)
            p.drawImage(dst, piece, sub)
        else:
            p.drawImage(dst, img, src)

    def _paint_placeholder(self, p: QPainter):
        r = self.rect()
        p.fillRect(r, QColor(236, 236, 236))
        z = self._zoom()
        pen = QPen(QColor(150, 150, 150), 1.2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(r)
        # picture glyph: frame + mountain + sun
        s = min(r.width(), r.height()) * 0.28
        cx, cy = r.center().x(), r.center().y() - s * 0.25
        g = QRectF(cx - s / 2, cy - s * 0.38, s, s * 0.76)
        gp = QPen(QColor(120, 120, 120), max(1.5 / z, s * 0.05))
        p.setPen(gp)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(g)
        path = QPainterPath()
        path.moveTo(g.left(), g.bottom())
        path.lineTo(g.left() + g.width() * .38, g.top() + g.height() * .45)
        path.lineTo(g.left() + g.width() * .62, g.top() + g.height() * .72)
        path.lineTo(g.left() + g.width() * .78, g.top() + g.height() * .55)
        path.lineTo(g.right(), g.bottom())
        p.drawPath(path)
        p.drawEllipse(QPointF(g.left() + g.width() * .75, g.top() + g.height() * .28),
                      g.width() * .08, g.width() * .08)
        f = QFont(theme.tokens()["font"])
        f.setPointSizeF(max(min(10.0 / z, r.height() / 8), 1.0))
        p.setFont(f)
        p.setPen(QColor(90, 90, 90))
        tr = QRectF(r.left() + 4, g.bottom() + 4, r.width() - 8, r.bottom() - g.bottom() - 6)
        p.drawText(tr, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                   | Qt.TextFlag.TextWordWrap, "Double-click to add a picture")

    # ── interaction ──────────────────────────────────────────────────────────
    def on_double_click(self, e):
        sc = self.page_scene()
        if sc is not None:
            sc.itemActivated.emit(self)

    # ── serialisation ────────────────────────────────────────────────────────
    def data_b64(self) -> str:
        """The picture as base64, worked out once (pictures don't change in place)."""
        if not self.data:
            return ""
        if self._b64 is None:
            self._b64 = base64.b64encode(self.data).decode("ascii")
        return self._b64

    def extra_to_dict(self) -> Dict[str, Any]:
        return {
            "fit_mode": self.fit_mode,
            "crop_x": self.crop_x,
            "crop_y": self.crop_y,
            "corner": self.corner,
            "source_name": self.source_name,
            "format": self.fmt,
            "data": self.data_b64(),
        }

    def apply_extra(self, d: Dict[str, Any]):
        fm = d.get("fit_mode", "fill")
        self.fit_mode = fm if fm in FIT_MODES else "fill"
        self.crop_x = num(d, "crop_x", 0.0, -1, 1)
        self.crop_y = num(d, "crop_y", 0.0, -1, 1)
        self.corner = num(d, "corner", 0.0, 0, 10000)
        raw = d.get("data") or ""
        data = b""
        repaired = False
        self._load_notes = []
        strict = False
        if isinstance(raw, str) and raw:
            try:
                data = base64.b64decode(raw, validate=True)
                strict = True
            except (ValueError, TypeError):
                # damaged text: try once more ignoring stray characters, and keep the
                # result only if it really is a picture (checked below)
                try:
                    data = base64.b64decode(raw, validate=False)
                    repaired = True
                except (ValueError, TypeError):
                    data = b""
        fmt = str(d.get("format", ""))[:8]
        self.set_image_data(data, fmt, str(d.get("source_name", ""))[:260])
        name = self.source_name or "a picture"
        if raw and not self.has_image():
            big = self._too_big
            self.set_image_data(b"", "", self.source_name)
            if big:
                self._load_notes.append(f"{name} is {big[0]:,} × {big[1]:,} pixels, far larger "
                                        "than this program stores pictures, and has been left "
                                        "as an empty frame.")
            else:
                self._load_notes.append(f"{name} was damaged and has been left as an empty "
                                        "frame.")
        elif repaired:
            self._load_notes.append(f"{name} was slightly damaged in the file and was "
                                    "repaired; please check it.")
        elif strict and self.has_image():
            self._b64 = raw            # the text form is already in hand: no re-encoding

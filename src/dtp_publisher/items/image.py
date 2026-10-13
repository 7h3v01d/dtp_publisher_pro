# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""ImageItem — a picture frame (empty frames act as photo placeholders)."""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QImage, QImageIOHandler, QImageReader, QPainter,
                         QPainterPath, QPen, QPixmap)

from .. import theme
from .base import BaseItem, num

FIT_MODES = {"fill": "Fill frame (crop)", "fit": "Fit inside frame", "stretch": "Stretch"}
MAX_EMBED_PX = 3000      # long side; larger photos are downsampled when inserted
PREVIEW_PX = 1600        # on-screen preview resolution


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
        self._image = QImage()
        self._preview = QPixmap()
        self.stroke = QColor(60, 60, 60)
        self.stroke_width = 0.0

    def display_name(self) -> str:
        if self.name:
            return self.name
        return f"Picture — {self.source_name}" if self.source_name else (
            "Picture" if self.has_image() else "Picture placeholder")

    # ── image data ──────────────────────────────────────────────────────────
    def has_image(self) -> bool:
        return not self._image.isNull()

    def image(self) -> QImage:
        return self._image

    def set_image_data(self, data: bytes, fmt: str, name: str = "",
                       image: Optional[QImage] = None):
        self.data = bytes(data or b"")
        self._b64: Optional[str] = None          # cached text form for saving
        self.fmt = fmt or ""
        self.source_name = name or ""
        img = image if image is not None else QImage()
        if image is None and self.data:
            img.loadFromData(self.data)
        self._image = img
        if img.isNull():
            self._preview = QPixmap()
        else:
            pv = img
            if max(img.width(), img.height()) > PREVIEW_PX:
                pv = img.scaled(PREVIEW_PX, PREVIEW_PX, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            self._preview = QPixmap.fromImage(pv)
        self.update()

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
        return self._image.width() / max(self._image.height(), 1)

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
                src, dst = self._source_target(self._image.width(), self._image.height())
                p.drawImage(dst, self._image, src)
            else:
                pw, ph = self._preview.width(), self._preview.height()
                src, dst = self._source_target(pw, ph)
                p.drawPixmap(dst, self._preview, src)
            p.restore()
        elif not self.is_rendering() or (self.page_scene() and self.page_scene().preview):
            self._paint_placeholder(p)
        pen = self.make_pen()
        if pen.style() != Qt.PenStyle.NoPen:
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(clip)

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
        if isinstance(raw, str) and raw:
            try:
                data = base64.b64decode(raw, validate=True)
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
        if raw and self._image.isNull():
            self.set_image_data(b"", "", self.source_name)
            self._load_notes.append(f"{name} was damaged and has been left as an empty frame.")
        elif repaired:
            self._load_notes.append(f"{name} was slightly damaged in the file and was "
                                    "repaired; please check it.")

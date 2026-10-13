# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""ImageItem — a picture frame (empty frames act as photo placeholders)."""

from __future__ import annotations

import base64
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


def _read_upright(raw: bytes) -> Tuple[QImage, bool]:
    """Decode bytes, applying EXIF orientation (phone photos).  Returns (img, rotated)."""
    ba = QByteArray(raw)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    reader.setAutoTransform(True)
    img = reader.read()
    rotated = reader.transformation() != QImageIOHandler.Transformation.TransformationNone
    buf.close()
    return img, rotated


def prepare_image_bytes(raw: bytes, max_px: int = MAX_EMBED_PX) -> Optional[Tuple[bytes, str, QImage]]:
    """Validate/downsample image bytes for embedding.  Returns (data, fmt, image).

    Photos are stored upright (EXIF orientation applied) and no larger than
    ``max_px`` on the long side, so documents stay a sensible size.
    """
    img, rotated = _read_upright(raw)
    if img.isNull():
        return None
    head = raw[:12]
    if max(img.width(), img.height()) > max_px:
        img = img.scaled(max_px, max_px, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        data, fmt = encode_image(img)
        return data, fmt, img
    if not rotated and head.startswith(b"\x89PNG"):
        return raw, "png", img
    if not rotated and head.startswith(b"\xff\xd8"):
        return raw, "jpg", img
    data, fmt = encode_image(img)
    return data, fmt, img


def load_image_file(path: str) -> Optional[Tuple[bytes, str, QImage]]:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return prepare_image_bytes(raw)


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
    def extra_to_dict(self) -> Dict[str, Any]:
        return {
            "fit_mode": self.fit_mode,
            "crop_x": self.crop_x,
            "crop_y": self.crop_y,
            "corner": self.corner,
            "source_name": self.source_name,
            "format": self.fmt,
            "data": base64.b64encode(self.data).decode("ascii") if self.data else "",
        }

    def apply_extra(self, d: Dict[str, Any]):
        fm = d.get("fit_mode", "fill")
        self.fit_mode = fm if fm in FIT_MODES else "fill"
        self.crop_x = num(d, "crop_x", 0.0, -1, 1)
        self.crop_y = num(d, "crop_y", 0.0, -1, 1)
        self.corner = num(d, "corner", 0.0, 0, 10000)
        raw = d.get("data") or ""
        data = b""
        if isinstance(raw, str) and raw:
            try:
                data = base64.b64decode(raw, validate=False)
            except (ValueError, TypeError):
                data = b""
        fmt = str(d.get("format", ""))[:8]
        self.set_image_data(data, fmt, str(d.get("source_name", ""))[:260])

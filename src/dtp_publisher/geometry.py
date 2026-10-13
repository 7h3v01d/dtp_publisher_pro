# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Pure geometry helpers (no scene required, so they are trivially testable).

Every design item is a box of size (w, h) whose local rect is (0, 0, w, h).
Its parent-space placement is described by ``Geo``: the unrotated top-left
(x, y), the size, and a rotation in degrees about the box centre.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from PyQt6.QtCore import QPointF, QRectF


class Geo(NamedTuple):
    x: float
    y: float
    w: float
    h: float
    rot: float = 0.0

    @property
    def center(self) -> QPointF:
        return QPointF(self.x + self.w / 2, self.y + self.h / 2)

    def moved(self, dx: float, dy: float) -> "Geo":
        return self._replace(x=self.x + dx, y=self.y + dy)

    def close_to(self, other: "Geo", eps: float = 1e-6) -> bool:
        return all(abs(a - b) <= eps for a, b in zip(self, other))


def rotate_vec(x: float, y: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def local_to_parent(g: Geo, p: QPointF) -> QPointF:
    """Map a point in the item's local box coordinates to parent coordinates."""
    ox, oy = g.w / 2, g.h / 2
    rx, ry = rotate_vec(p.x() - ox, p.y() - oy, g.rot)
    return QPointF(g.x + ox + rx, g.y + oy + ry)


def parent_to_local(g: Geo, q: QPointF) -> QPointF:
    ox, oy = g.w / 2, g.h / 2
    rx, ry = rotate_vec(q.x() - g.x - ox, q.y() - g.y - oy, -g.rot)
    return QPointF(rx + ox, ry + oy)


def geo_from_local_rect(g: Geo, r: QRectF) -> Geo:
    """Geometry of a box occupying local rect ``r`` of the item placed at ``g``.

    Used by resizing: the new box lives in the *old* box's coordinate frame,
    so the edges the user did not drag stay exactly where they were on screen,
    even when the item is rotated.
    """
    c = local_to_parent(g, r.center())
    return Geo(c.x() - r.width() / 2, c.y() - r.height() / 2, r.width(), r.height(), g.rot)


def bounds_of(g: Geo) -> QRectF:
    """Axis-aligned bounding rect of a (possibly rotated) box in parent space."""
    pts = [local_to_parent(g, QPointF(x, y)) for x, y in ((0, 0), (g.w, 0), (g.w, g.h), (0, g.h))]
    xs = [p.x() for p in pts]
    ys = [p.y() for p in pts]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def normalize_angle(deg: float) -> float:
    a = math.fmod(deg, 360.0)
    if a > 180.0:
        a -= 360.0
    elif a <= -180.0:
        a += 360.0
    return 0.0 if abs(a) < 1e-9 else a


def snap_angle(deg: float, step: float = 15.0, magnet: float = 0.0) -> float:
    """Snap to multiples of ``step``; with ``magnet`` only snap when within it."""
    target = round(deg / step) * step
    if magnet <= 0 or abs(target - deg) <= magnet:
        return normalize_angle(target)
    return normalize_angle(deg)

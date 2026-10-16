# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""The picture shown while the program starts.

It appears as soon as Qt is up (before the heavy imports), so on a slow
computer it fills time that would otherwise be an empty wait.  It stays for
at least ``MIN_SECONDS`` - or until loading is done, if that takes longer -
and a click or any key closes it straight away.  Preferences can turn it off.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSplashScreen

from . import __version__

IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art", "splash.jpg")
MIN_SECONDS = 3.0
WIDTH = 720                      # on screen, in Qt's (scaled) pixels


def remaining_ms(started: float, now: float, min_seconds: Optional[float] = None) -> int:
    """How much longer the splash should stay, given when it appeared."""
    if min_seconds is None:
        min_seconds = MIN_SECONDS
    return max(0, int(round((min_seconds - (now - started)) * 1000)))


def make_pixmap(status: str = "Loading…") -> QPixmap:
    """The picture at a crisp size for this screen, with the version and a
    status line in its empty lower-right corner, and a fine border (its edges
    are nearly white and would vanish against a white desktop)."""
    src = QPixmap(IMAGE)
    if src.isNull():                       # missing file: a plain panel, never a crash
        src = QPixmap(1168, 784)
        src.fill(QColor("#f4f6f6"))
    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    px_w = min(src.width(), int(round(WIDTH * dpr)))
    pix = src.scaledToWidth(px_w, Qt.TransformationMode.SmoothTransformation)
    pix.setDevicePixelRatio(px_w / WIDTH)
    w, h = WIDTH, pix.height() / pix.devicePixelRatio()
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont("Segoe UI")
    f.setPixelSize(13)
    p.setFont(f)
    p.setPen(QColor("#5b6466"))
    p.drawText(QRectF(w - 260, h - 40, 240, 22),
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
               f"Version {__version__}   ·   {status}")
    p.setPen(QPen(QColor(0, 0, 0, 70), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
    p.end()
    return pix


class Splash(QSplashScreen):
    """Calls ``on_done`` once, after ``ready()`` has been called: when the
    minimum time is up, or at once if the picture was clicked away (a click
    before loading finishes closes the picture; the program follows when ready)."""

    def __init__(self, on_done: Callable[[], None], min_seconds: Optional[float] = None,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(make_pixmap())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._on_done: Optional[Callable[[], None]] = on_done
        self._min = MIN_SECONDS if min_seconds is None else min_seconds    # read now, not at import
        self._clock = clock
        self._started = clock()
        self._ready = False
        self._dismissed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.done)

    def ready(self):
        """Loading has finished."""
        self._ready = True
        if self._dismissed:
            self._fire()
        else:
            self._timer.start(remaining_ms(self._started, self._clock(), self._min))

    def done(self):
        """Time is up, or the user clicked: close the picture."""
        self._dismissed = True
        self._timer.stop()
        self.close()
        if self._ready:
            self._fire()

    def _fire(self):
        cb, self._on_done = self._on_done, None
        if cb is not None:
            cb()

    # a click or a key: don't make anyone wait
    def mousePressEvent(self, e):
        self.done()

    def keyPressEvent(self, e):
        self.done()

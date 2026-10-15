# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""The welcome picture shown while the program starts (splash.py)."""

import os

from dtp_publisher import splash


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_remaining_time():
    assert splash.remaining_ms(10.0, 10.0, 3.0) == 3000
    assert splash.remaining_ms(10.0, 11.25, 3.0) == 1750
    assert splash.remaining_ms(10.0, 15.0, 3.0) == 0          # slow start: no extra wait


def test_stays_the_minimum_time_then_shows_the_window(qapp):
    clock, calls = Clock(), []
    s = splash.Splash(lambda: calls.append(1), min_seconds=3.0, clock=clock)
    s.show()
    clock.t += 1.0                                # loading took a second
    s.ready()
    assert s._timer.isActive() and s._timer.interval() == 2000 and calls == []
    s._timer.timeout.emit()                       # time is up
    assert calls == [1] and not s.isVisible()
    s.done()                                      # never twice
    assert calls == [1]


def test_slow_loading_closes_at_once(qapp):
    clock, calls = Clock(), []
    s = splash.Splash(lambda: calls.append(1), min_seconds=3.0, clock=clock)
    clock.t += 5.0
    s.ready()
    assert s._timer.interval() == 0


def test_a_click_skips_the_wait(qapp):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    calls = []
    s = splash.Splash(lambda: calls.append(1), clock=Clock())
    s.show()
    s.ready()
    s.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5),
                                  QPointF(5, 5), Qt.MouseButton.LeftButton,
                                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert calls == [1] and not s.isVisible()


def test_a_click_while_still_loading_waits_for_the_window(qapp):
    """Clicked before the main window exists: the picture goes now, the
    program follows as soon as it is ready (never a call into nothing)."""
    calls = []
    s = splash.Splash(lambda: calls.append(1), clock=Clock())
    s.show()
    s.done()
    assert not s.isVisible() and calls == []
    s.ready()
    assert calls == [1]


def test_picture_is_crisp_and_shows_the_version(qapp):
    from dtp_publisher import __version__
    assert os.path.isfile(splash.IMAGE)
    p = splash.make_pixmap()
    assert not p.isNull()
    assert abs(p.width() / p.devicePixelRatio() - splash.WIDTH) < 1
    # the version is painted in the lower-right corner: that area differs from the bare picture
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import Qt
    bare = QPixmap(splash.IMAGE).scaledToWidth(p.width(), Qt.TransformationMode.SmoothTransformation)
    a, b = p.toImage(), bare.toImage()
    y = int(p.height() - 29 * p.devicePixelRatio())
    xs = range(int(p.width() * 0.75), p.width() - 30)
    assert sum(a.pixelColor(x, y) != b.pixelColor(x, y) for x in xs) > 20, __version__


def test_missing_picture_does_not_stop_the_program(qapp, monkeypatch):
    monkeypatch.setattr(splash, "IMAGE", os.path.join("nowhere", "splash.jpg"))
    assert not splash.make_pixmap().isNull()


def test_can_be_turned_off_in_preferences(window, monkeypatch):
    from dtp_publisher.ui.dialogs import misc

    def untick(self):
        assert self.splash.isChecked()
        self.splash.setChecked(False)
        return True
    monkeypatch.setattr(misc.PreferencesDialog, "exec", untick)
    assert window.settings.show_splash
    window.preferences()
    from dtp_publisher.settings import Settings
    assert Settings.load().show_splash is False


def test_picture_ships_with_the_program():
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "packaging", "dtp_publisher.spec"), encoding="utf-8") as f:
        assert '"dtp_publisher/art"' in f.read()


def test_program_start_shows_the_picture_then_the_window(tmp_path):
    """The real app.main(): while the picture shows, the main window stays
    hidden; once it goes, the window is up.  In its own process (main makes
    its own QApplication)."""
    import json
    import subprocess
    import sys
    import textwrap
    home = tmp_path / "apphome"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"show_start": False}))
    script = tmp_path / "start.py"
    script.write_text(textwrap.dedent("""
        import sys
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        from dtp_publisher import app, splash
        from dtp_publisher.ui.window import MainWindow
        splash.MIN_SECONDS = 0.6
        seen = []

        def windows():
            return [w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)]

        real_ready = splash.Splash.ready
        def ready(self):
            seen.append(("splash", self.isVisible(), any(w.isVisible() for w in windows())))
            real_ready(self)
            def after():
                seen.append(("after", self.isVisible(), any(w.isVisible() for w in windows())))
                print(seen, flush=True)
                QApplication.quit()
            QTimer.singleShot(1500, after)
        splash.Splash.ready = ready
        sys.exit(app.main(["dtp"]))
    """))
    import os
    src = os.path.dirname(os.path.dirname(os.path.abspath(splash.__file__)))   # the code under test
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", DTP_PUBLISHER_HOME=str(home),
               PYTHONPATH=os.path.abspath(src) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    env.pop("QT_SCALE_FACTOR", None)
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       env=env, timeout=120)
    assert "[('splash', True, False), ('after', False, True)]" in r.stdout, r.stdout + r.stderr[-800:]

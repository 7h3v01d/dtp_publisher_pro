# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Application start-up: scaling, theme, crash recovery, start screen."""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from . import APP_NAME, APP_ORG, __version__
from . import settings as settings_mod


def install_error_handler(log_path: str):
    """Log unexpected errors and keep running.

    PyQt6 aborts the process on an exception escaping a slot; for someone
    mid-way through a newsletter that would mean losing work.  Instead the
    error is written to crash.log and a gentle message suggests saving.
    """
    import datetime
    import traceback

    showing = {"busy": False}

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                        f"v{__version__} ===\n{text}")
        except OSError:
            pass
        try:                    # a windowed program may have no usable console
            if sys.__stderr__ is not None:
                sys.__stderr__.write(text)
        except (OSError, ValueError, AttributeError):
            pass
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None or showing["busy"]:
            return
        showing["busy"] = True
        try:
            QMessageBox.warning(None, APP_NAME,
                                "Sorry — something went wrong, but your work is still open.\n\n"
                                "It's a good idea to save now (File ▸ Save As, with a new "
                                f"name).\n\nDetails were written to:\n{log_path}")
        finally:
            showing["busy"] = False

    sys.excepthook = hook


def close_boot_splash():
    """The one-file .exe shows a picture while it unpacks itself (PyInstaller's
    pyi_splash); close it once the program's own window or picture is up."""
    if "_PYI_SPLASH_IPC" not in os.environ:     # no such picture in this build
        return
    try:
        import pyi_splash  # type: ignore[import-not-found]
        pyi_splash.close()
    except Exception:                   # never stop the program over a picture
        pass


def self_test(out_path: str) -> int:
    """``DTP Publisher.exe --self-test=result.json``: check a built program has
    everything it needs (used by build_onefile.bat; handy after any build).
    Writes the results as JSON; returns 0 if all passed."""
    import json
    import tempfile
    import traceback

    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt6.QtGui import QImage, QImageReader
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    checks = []

    def check(name, fn):
        try:
            detail = fn()
            checks.append({"name": name, "ok": True, "detail": detail})
        except Exception:
            checks.append({"name": name, "ok": False, "detail": traceback.format_exc(limit=3)})

    def manual():
        from .ui.window import manual_for_browser, manual_path
        assert os.path.isfile(manual_path()), manual_path()
        img = os.path.join(os.path.dirname(manual_path()), "img")
        n = len(os.listdir(img))
        assert n >= 10, n
        shown = manual_for_browser()
        assert os.path.isfile(shown), shown
        return f"{n} pictures; opens {shown}"

    def splash_picture():
        from .splash import IMAGE
        img = QImage(IMAGE)
        assert not img.isNull(), IMAGE
        return f"{img.width()}x{img.height()}"

    def photos():
        fmts = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
        for need in ("jpeg", "png", "gif", "bmp"):
            assert need in fmts, f"cannot read {need}: {sorted(fmts)}"
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        src = QImage(64, 48, QImage.Format.Format_RGB32)
        src.fill(0x3366AA)
        assert src.save(buf, "JPEG"), "cannot write JPEG"
        back = QImage.fromData(ba)
        assert not back.isNull() and back.width() == 64, "JPEG round trip"
        return ", ".join(sorted(fmts))

    def pdf():
        from .export import export_pdf
        from .templates import build
        out = os.path.join(tempfile.mkdtemp(prefix="dtp-selftest-"), "t.pdf")
        export_pdf(build("flyer"), out)
        size = os.path.getsize(out)
        assert size > 1000, size
        return f"{size} bytes"

    def program():
        from . import winassoc
        exe = winassoc.launcher()[0]
        assert os.path.isfile(exe), exe
        return {"frozen": bool(getattr(sys, "frozen", False)), "launcher": exe,
                "unpacked_to": getattr(sys, "_MEIPASS", "")}

    check("version", lambda: __version__)
    check("program", program)
    check("manual", manual)
    check("welcome picture", splash_picture)
    check("photos (Qt image plugins)", photos)
    check("PDF export", pdf)
    ok = all(c["ok"] for c in checks)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"ok": ok, "version": __version__, "checks": checks}, f, indent=2)
    except OSError:
        pass
    del app
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    for a in argv[1:]:
        if a == "--self-test" or a.startswith("--self-test="):
            close_boot_splash()
            out = a.partition("=")[2] or os.path.join(settings_mod.config_dir(),
                                                      "self-test.json")
            return self_test(out)
    s = settings_mod.get()
    # UI scaling must be decided before QApplication exists.
    if "QT_SCALE_FACTOR" not in os.environ and abs(s.ui_scale - 1.0) > 1e-6:
        os.environ["QT_SCALE_FACTOR"] = f"{s.ui_scale:g}"

    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from . import theme
    from .autosave import find_orphans, remove_orphan

    install_error_handler(os.path.join(settings_mod.config_dir(), "crash.log"))
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    f = app.font()
    f.setPointSizeF(10.0)
    app.setFont(f)
    theme.apply(app, s.theme)

    splash = None
    if s.show_splash:
        from .splash import Splash
        splash = Splash(lambda: begin())
        splash.show()
        app.processEvents()             # paint it now, before the slow imports
    close_boot_splash()                 # the one-file .exe's unpacking picture

    from .serialize import DocumentError, load_document
    from .ui.window import MainWindow

    win = MainWindow(s)

    def startup():
        files = [a for a in argv[1:] if not a.startswith("-") and os.path.isfile(a)]
        if files:
            win.open_path(files[0], ask=False)
            return
        orphans = find_orphans()
        if orphans:
            from .ui.dialogs.misc import RecoveryDialog
            dlg = RecoveryDialog(orphans, win)
            if dlg.exec():
                for o in dlg.discard:
                    remove_orphan(o["path"])
                if dlg.chosen is not None:
                    try:
                        doc, _ = load_document(dlg.chosen["path"])
                    except DocumentError as ex:
                        QMessageBox.warning(win, "Recover", str(ex))
                    else:
                        doc.path = dlg.chosen.get("original") or None
                        if doc.path and not doc.path.lower().endswith(".dtpub"):
                            doc.path = None
                        win.set_document(doc)
                        doc.undo_stack.resetClean()     # it still needs saving
                        win._update_title()
                        remove_orphan(dlg.chosen["path"])
                        return
        if s.show_start:
            from .ui.dialogs.start import StartDialog
            dlg = StartDialog(s.existing_recent(), s.show_start, win, first_run=True)
            if dlg.exec():
                s.show_start = dlg.cb_show.isChecked()
                s.save()
                if dlg.document is not None:
                    win.set_document(dlg.document)
                elif dlg.open_path:
                    win.open_path(dlg.open_path, ask=False)
                elif dlg.open_other:
                    win.open_dialog(ask=False)
            else:
                s.show_start = dlg.cb_show.isChecked()
                s.save()

    def begin():
        win.show()
        win.raise_()
        win.activateWindow()
        QTimer.singleShot(50, startup)

    if splash is not None:
        splash.ready()                  # the window appears when the picture goes
    else:
        begin()
    QTimer.singleShot(2000, _repair_file_types)
    return app.exec()


def _repair_file_types():
    """If double-click was set up and the program folder has since moved,
    point Windows at this copy (only for the types the user chose)."""
    from . import winassoc
    try:
        winassoc.repair()
    except Exception:                   # never stop the program over this
        pass

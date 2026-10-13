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
        sys.__stderr__ and sys.__stderr__.write(text)
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


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
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

    from .serialize import DocumentError, load_document
    from .ui.window import MainWindow

    win = MainWindow(s)
    win.show()

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

    QTimer.singleShot(50, startup)
    return app.exec()

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Microsoft Publisher (.pub) import: LibreOffice converts, we rebuild.

``PubConverter`` runs LibreOffice on a worker QThread (it can take a minute
for big files) and reports back; building the document happens on the GUI
thread because Qt graphics items belong there.
"""

from __future__ import annotations

import os
import shutil
import threading
from typing import Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from ..document import Document
from .libreoffice import ConversionError, convert, find_soffice
from .odg import ImportReport, import_odg

LIBREOFFICE_URL = "https://www.libreoffice.org/download/download-libreoffice/"


def is_pub(path: str) -> bool:
    return path.lower().endswith(".pub")


def looks_like_pub(path: str) -> bool:
    """Publisher files are OLE compound documents."""
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except OSError:
        return False


def build_from_odg(odg_path: str, source: str) -> Tuple[Document, ImportReport]:
    from .. import labels
    doc, rep = import_odg(odg_path)
    doc.title = os.path.splitext(os.path.basename(source))[0]
    doc.path = None
    sizes = {(round(p.page_w, 1), round(p.page_h, 1)) for p in doc.pages}
    if len(sizes) == 1:
        w, h = next(iter(sizes))
        layout = labels.detect(w, h)
        if layout is not None:
            doc.sheet = labels.to_dict(layout, "copies")
            rep.warn(f"This is a label publication. It is set to print on {layout.name}; "
                     "you can change that in Page Setup.")
    doc.undo_stack.clear()
    return doc, rep


def import_pub_blocking(path: str) -> Tuple[Document, ImportReport]:
    """Convert and build in one go (tests / command line)."""
    odg = convert(path, "odg")
    try:
        return build_from_odg(odg, path)
    finally:
        shutil.rmtree(os.path.dirname(os.path.dirname(odg)), ignore_errors=True)


class _Worker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, path: str, cancel: threading.Event):
        super().__init__()
        self.path = path
        self.cancel = cancel

    @pyqtSlot()
    def run(self):
        try:
            out = convert(self.path, "odg", cancelled=self.cancel.is_set)
        except ConversionError as ex:
            self.failed.emit(str(ex))
            return
        except OSError as ex:
            self.failed.emit(f"Could not run LibreOffice:\n{ex}")
            return
        self.finished.emit(out)


class PubConverter(QObject):
    """Runs the LibreOffice conversion on its own thread."""

    converted = pyqtSignal(str)      # path to the .odg
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cancel = threading.Event()
        self._thread = QThread(self)
        self._worker = _Worker(path, self._cancel)
        self._worker_refs = [self._worker]            # GC safety
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._done)
        self._worker.failed.connect(self._fail)

    def start(self):
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    @pyqtSlot(str)
    def _done(self, path: str):
        self._stop()
        self.converted.emit(path)

    @pyqtSlot(str)
    def _fail(self, msg: str):
        self._stop()
        self.failed.emit(msg)

    def _stop(self):
        self._thread.quit()
        self._thread.wait(10000)


__all__ = ["is_pub", "looks_like_pub", "find_soffice", "build_from_odg", "import_pub_blocking",
           "PubConverter", "LIBREOFFICE_URL", "ConversionError"]

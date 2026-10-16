# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Autosave + crash recovery.

Qt items live on the GUI thread, so the document's state is captured there as
plain Python data (pictures reuse their cached text form, so this is quick).
Turning that into JSON and writing it happens on a worker QThread.

Each autosave request carries a generation number.  The writer encodes and
writes to a temporary file without holding any lock, then renames it into
place under a lock only if its generation is still current.  Saving or
closing makes every earlier generation stale under that lock, so a write that
was queued or running when the user saved can never bring back an
out-of-date recovery file, and Save never waits for an autosave.
"""

from __future__ import annotations

import glob
import json
import os
import threading
import time
import uuid
from typing import List, Optional

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from . import settings as settings_mod
from .serialize import document_to_dict, dump_json


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _detached(obj):
    """Copy the containers (strings and numbers are immutable and shared)."""
    if isinstance(obj, dict):
        return {k: _detached(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_detached(v) for v in obj]
    return obj


class _Writer(QObject):
    done = pyqtSignal(str, bool)

    def __init__(self, gate: "_Gate"):
        super().__init__()
        self.gate = gate

    @pyqtSlot(str, object, str, int)
    def write(self, path: str, data: object, meta: str, gen: int):
        """Encode and write outside the lock; only the final rename is done under it.

        So Save never waits for an autosave in progress: it just makes the
        generation stale, and a stale write deletes its own temporary files."""
        with self.gate.lock:
            if gen < self.gate.min_gen:            # saved or discarded since: stale
                return
        part, meta_part = f"{path}.{gen}.part", f"{path}.json.{gen}.part"
        try:
            _write_synced(part, lambda f: dump_json(data, f))
            _write_synced(meta_part, meta.encode("utf-8"))
        except (OSError, ValueError, TypeError):
            _remove(part, meta_part)
            self.done.emit(path, False)
            return
        with self.gate.lock:                       # commit only if still current
            if gen < self.gate.min_gen:
                _remove(part, meta_part)
                return
            try:
                os.replace(part, path)
                os.replace(meta_part, path + ".json")
                ok = True
            except OSError:
                _remove(part, meta_part)
                ok = False
        self.done.emit(path, ok)


def _write_synced(path: str, payload) -> None:
    with open(path, "wb") as f:
        if callable(payload):
            payload(f)
        else:
            f.write(payload)
        f.flush()
        os.fsync(f.fileno())


def _remove(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


class _Gate:
    """Shared between the GUI thread and the writer."""

    def __init__(self):
        self.lock = threading.Lock()
        self.min_gen = 0


class Autosaver(QObject):
    requestWrite = pyqtSignal(str, object, str, int)
    saved = pyqtSignal(str)

    def __init__(self, get_doc, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._get_doc = get_doc
        self.session = uuid.uuid4().hex[:10]
        self.path = os.path.join(settings_mod.autosave_dir(),
                                 f"autosave-{os.getpid()}-{self.session}.dtpub")
        self._gen = 0
        self._gate = _Gate()
        self._thread = QThread(self)
        self._writer = _Writer(self._gate)
        self._worker_refs = [self._writer]          # keep the worker alive (GC safety)
        self._writer.moveToThread(self._thread)
        self.requestWrite.connect(self._writer.write)
        self._writer.done.connect(self._on_done)
        self._thread.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self.set_interval(settings_mod.get().autosave_minutes)

    def set_interval(self, minutes: int):
        self._timer.stop()
        if minutes > 0:
            self._timer.start(minutes * 60_000)

    @pyqtSlot()
    def tick(self):
        doc = self._get_doc()
        if doc is None or not doc.is_modified():
            return
        data = _detached(document_to_dict(doc))     # nothing the GUI can still change
        meta = json.dumps({"pid": os.getpid(), "time": time.time(), "original": doc.path or "",
                           "title": doc.title})
        self._gen += 1
        self.requestWrite.emit(self.path, data, meta, self._gen)

    @pyqtSlot(str, bool)
    def _on_done(self, path: str, ok: bool):
        if ok:
            self.saved.emit(path)

    def discard(self):
        """Forget the recovery copy: called after a real save, on close, on New/Open.

        Makes every earlier request stale, whether queued or being written; the
        lock is only ever held for a rename, so this never waits for a write.
        """
        with self._gate.lock:
            self._gate.min_gen = self._gen + 1
            for p in (self.path, self.path + ".json"):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def shutdown(self):
        self._timer.stop()
        self.discard()
        self._thread.quit()
        self._thread.wait(5000)
        self.discard()


def find_orphans() -> List[dict]:
    """Autosaves left behind by sessions that are no longer running."""
    out = []
    folder = settings_mod.autosave_dir()
    for part in glob.glob(os.path.join(folder, "autosave-*.part")):   # a crash mid-write
        try:
            pid = int(os.path.basename(part).split("-")[1])
        except (IndexError, ValueError):
            continue
        if not pid_alive(pid):
            _remove(part)
    for p in sorted(glob.glob(os.path.join(folder, "autosave-*.dtpub"))):
        meta = {}
        try:
            with open(p + ".json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            pass
        pid = int(meta.get("pid", 0) or 0) if isinstance(meta, dict) else 0
        if pid and pid_alive(pid):
            continue
        meta = meta if isinstance(meta, dict) else {}
        meta["path"] = p
        meta.setdefault("time", os.path.getmtime(p))
        out.append(meta)
    return out


def remove_orphan(path: str):
    for p in (path, path + ".json"):
        try:
            os.remove(p)
        except OSError:
            pass

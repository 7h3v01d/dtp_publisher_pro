# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Autosave against Save / close: a recovery file must never outlive a real save.

The writer thread is deliberately held inside its write so the races happen
every time instead of once in a thousand runs.
"""

import os
import threading
import time

import pytest


@pytest.fixture
def held_writer(monkeypatch):
    """Make the autosave writer stop inside its file write until released."""
    from dtp_publisher import autosave
    entered = threading.Event()
    release = threading.Event()
    real = autosave._write_synced

    def slow(path, payload):
        entered.set()
        assert release.wait(10), "test never released the writer"
        return real(path, payload)
    monkeypatch.setattr(autosave, "_write_synced", slow)
    yield entered, release
    release.set()


@pytest.fixture
def saver(qapp, doc, monkeypatch):
    from dtp_publisher.autosave import Autosaver
    monkeypatch.setattr(doc, "is_modified", lambda: True)
    a = Autosaver(lambda: doc)
    yield a
    a.shutdown()


def _settle(qapp, seconds=0.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


def test_save_during_a_running_autosave_leaves_no_recovery_file(qapp, saver, held_writer):
    entered, release = held_writer
    saver.tick()
    assert entered.wait(5)                     # the writer is now mid-write
    t = threading.Thread(target=saver.discard)  # the user pressed Save
    t.start()
    time.sleep(0.2)
    release.set()
    t.join(5)
    _settle(qapp)
    assert not os.path.exists(saver.path)
    assert not os.path.exists(saver.path + ".json")


def test_save_does_not_wait_for_a_running_autosave(qapp, saver, held_writer):
    """B4: the lock is held only for the final rename, never for the write."""
    entered, release = held_writer
    saver.tick()
    assert entered.wait(5)                     # the writer is mid-write (no lock held)
    t0 = time.monotonic()
    saver.discard()                            # on the GUI thread, as Save does
    waited = time.monotonic() - t0
    release.set()
    _settle(qapp, 0.5)
    assert waited < 0.5
    assert not os.path.exists(saver.path)
    leftovers = [f for f in os.listdir(os.path.dirname(saver.path)) if f.endswith(".part")]
    assert leftovers == []                     # the stale write removed its temp files


def test_queued_autosaves_are_dropped_after_save(qapp, saver, held_writer):
    entered, release = held_writer
    saver.tick()                               # gen 1: held inside the write
    assert entered.wait(5)
    saver.tick()                               # gen 2, 3: queued behind it
    saver.tick()
    t = threading.Thread(target=saver.discard)
    t.start()
    time.sleep(0.2)
    release.set()
    t.join(5)
    _settle(qapp, 0.6)                         # let the queued requests run
    assert not os.path.exists(saver.path)


def test_autosave_after_save_still_works(qapp, saver):
    saver.discard()
    saver.tick()
    end = time.monotonic() + 5
    while not os.path.exists(saver.path) and time.monotonic() < end:
        _settle(qapp, 0.05)
    assert os.path.exists(saver.path) and os.path.exists(saver.path + ".json")


def test_shutdown_while_writing_leaves_nothing_behind(qapp, doc, monkeypatch, held_writer):
    from dtp_publisher.autosave import Autosaver
    entered, release = held_writer
    monkeypatch.setattr(doc, "is_modified", lambda: True)
    a = Autosaver(lambda: doc)
    a.tick()
    assert entered.wait(5)
    a.tick()                                   # one more queued
    t = threading.Thread(target=a.shutdown)
    t.start()
    time.sleep(0.2)
    release.set()
    t.join(10)
    assert not t.is_alive()
    assert not os.path.exists(a.path)


# ── backup copy failure (A9) ────────────────────────────────────────────────
def test_backup_failure_is_reported_but_save_succeeds(qapp, doc, tmp_path, monkeypatch):
    from dtp_publisher import serialize
    p = str(tmp_path / "a.dtpub")
    assert serialize.save_document(doc, p) is True       # nothing to back up yet: fine
    assert serialize.save_document(doc, p) is True and os.path.exists(p + ".bak")

    def broken_copy(*a, **k):
        raise PermissionError("read-only")
    monkeypatch.setattr(serialize.shutil, "copy2", broken_copy)
    assert serialize.save_document(doc, p) is False      # saved, but no fresh backup
    assert serialize.load_document(p)[0].pages


def test_window_tells_the_user_when_the_backup_failed(window, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from dtp_publisher import serialize
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    p = str(tmp_path / "w.dtpub")
    window.settings.keep_backup = True
    assert window._save_to(p)
    monkeypatch.setattr(serialize.shutil, "copy2",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError("no")))
    assert window._save_to(p)
    assert shown and "backup" in shown[-1]
    assert window.doc.undo_stack.isClean()               # the save itself counted


def test_crashed_write_leftovers_are_cleaned_up(qapp, monkeypatch):
    from dtp_publisher import autosave, settings as settings_mod
    folder = settings_mod.autosave_dir()
    dead = os.path.join(folder, "autosave-999999-abc.dtpub.3.part")
    mine = os.path.join(folder, f"autosave-{os.getpid()}-abc.dtpub.3.part")
    for p in (dead, mine):
        open(p, "wb").close()
    monkeypatch.setattr(autosave, "pid_alive", lambda pid: pid == os.getpid())
    autosave.find_orphans()
    assert not os.path.exists(dead) and os.path.exists(mine)

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Things only a built program meets: the one-file .exe unpacks itself into a
temporary folder, PyInstaller's own start-up picture, and --self-test."""

import json
import os
import sys
import tempfile
import types

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_manual_opens_from_a_lasting_copy_when_unpacked_to_temp(qapp, monkeypatch):
    """The one-file .exe deletes its temporary folder on exit, which would
    leave the browser with a manual whose pictures have gone."""
    import shutil

    from dtp_publisher.ui import window
    real = window.manual_path()
    assert window.manual_for_browser() == real            # an ordinary install: as is
    tmp = tempfile.mkdtemp(prefix="_MEI-test-")
    try:
        shutil.copytree(os.path.dirname(real), os.path.join(tmp, "help"))
        monkeypatch.setattr(window, "manual_path", lambda: os.path.join(tmp, "help", "manual.html"))
        shown = window.manual_for_browser()
        assert not shown.startswith(tmp)
        assert os.path.isfile(shown)
        assert os.path.isfile(os.path.join(os.path.dirname(shown), "img", "window.png"))
        shutil.rmtree(tmp)                                  # the program has closed
        assert os.path.isfile(shown)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_boot_picture_closed_only_when_there_is_one(monkeypatch):
    from dtp_publisher import app
    calls = []
    fake = types.ModuleType("pyi_splash")
    fake.close = lambda: calls.append(1)
    monkeypatch.setitem(sys.modules, "pyi_splash", fake)
    monkeypatch.delenv("_PYI_SPLASH_IPC", raising=False)
    app.close_boot_splash()
    assert calls == []                                     # not built in: leave it alone
    monkeypatch.setenv("_PYI_SPLASH_IPC", "1")
    app.close_boot_splash()
    assert calls == [1]

    def broken():
        raise RuntimeError("gone")
    fake.close = broken
    app.close_boot_splash()                                # never stops the program


def test_self_test_passes_and_reports(qapp, tmp_path):
    from dtp_publisher import app
    out = tmp_path / "self-test.json"
    assert app.main(["dtp", f"--self-test={out}"]) == 0
    d = json.loads(out.read_text())
    assert d["ok"] and {c["name"] for c in d["checks"]} >= {
        "manual", "photos (Qt image plugins)", "PDF export", "welcome picture"}


def test_self_test_reports_a_missing_part(qapp, tmp_path, monkeypatch):
    from dtp_publisher import app, splash
    monkeypatch.setattr(splash, "IMAGE", str(tmp_path / "gone.jpg"))
    out = tmp_path / "self-test.json"
    assert app.main(["dtp", f"--self-test={out}"]) == 1
    bad = [c["name"] for c in json.loads(out.read_text())["checks"] if not c["ok"]]
    assert bad == ["welcome picture"]


def test_both_builds_check_themselves():
    for bat in ("build_exe.bat", "build_onefile.bat"):
        with open(os.path.join(ROOT, bat), encoding="utf-8") as f:
            text = f.read()
        assert "--self-test=" in text and "errorlevel 1" in text, bat
    with open(os.path.join(ROOT, "build_onefile.bat"), "rb") as f:
        assert b"\r\n" in f.read()                         # Windows line endings
    with open(os.path.join(ROOT, "packaging", "dtp_publisher.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert 'os.environ.get("DTP_ONEFILE") == "1"' in spec and "boot_splash.png" in spec
    assert os.path.isfile(os.path.join(ROOT, "packaging", "boot_splash.png"))


def test_older_manual_copies_are_removed(qapp, monkeypatch):
    """Each version copies the manual (one-file .exe); the old copies go, and
    nothing else in the settings folder is touched."""
    import shutil

    from dtp_publisher import settings as settings_mod
    from dtp_publisher.ui import window
    base = settings_mod.config_dir()
    old = os.path.join(base, "manual-5.3.2")
    os.makedirs(os.path.join(old, "img"))
    open(os.path.join(old, "manual.html"), "w").close()
    other = os.path.join(base, "manual-notes")             # not one of ours
    os.makedirs(other)
    open(os.path.join(other, "manual.html"), "w").close()
    real = window.manual_path()
    tmp = tempfile.mkdtemp(prefix="_MEI-test-")
    try:
        shutil.copytree(os.path.dirname(real), os.path.join(tmp, "help"))
        monkeypatch.setattr(window, "manual_path", lambda: os.path.join(tmp, "help", "manual.html"))
        shown = window.manual_for_browser()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert os.path.isfile(shown)
    assert not os.path.exists(old)
    assert os.path.isdir(other)

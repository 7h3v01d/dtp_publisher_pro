# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Windows file associations (winassoc.py), against a fake HKEY_CURRENT_USER."""

import sys

import pytest
from fake_registry import FakeRegistry

from dtp_publisher import winassoc

PARTS = []
CMD = ""


@pytest.fixture
def reg(monkeypatch, tmp_path, fake_registry):
    """The per-test fake registry, with the program at a real (temporary) path."""
    exe = tmp_path / "Program Files" / "DTP Publisher" / "DTP Publisher.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    PARTS[:] = [str(exe)]
    globals()["CMD"] = f'"{exe}" "%1"'
    monkeypatch.setattr(winassoc, "launcher", lambda: list(PARTS))
    monkeypatch.setattr(winassoc, "icon_location", lambda parts=None: f'"{(parts or PARTS)[0]}",0')
    return fake_registry


def _publisher_installed(r):
    """What another program (here LibreOffice) leaves in HKCU for .pub."""
    r.set(r"Software\Classes\.pub", "", "LibreOffice.PubFile")
    r.set(r"Software\Classes\.pub\OpenWithProgids", "LibreOffice.PubFile", "")


def test_register_both_types(reg):
    out = winassoc.register([".dtpub", ".pub"], reg)
    for ext, progid in ((".dtpub", "DTPPublisher.Document"), (".pub", "DTPPublisher.PubFile")):
        assert reg.get(rf"Software\Classes\{progid}\shell\open\command") == CMD
        assert reg.get(rf"Software\Classes\{progid}\DefaultIcon") == f'"{PARTS[0]}",0'
        assert reg.get(rf"Software\Classes\{ext}") == progid
        assert reg.get(rf"Software\Classes\{ext}\OpenWithProgids", progid) == ""
        assert reg.get(r"Software\DTP Publisher\Capabilities\FileAssociations", ext) == progid
    assert reg.get(r"Software\RegisteredApplications", "DTP Publisher Pro") == \
        r"Software\DTP Publisher\Capabilities"
    assert [(s.ext, s.registered, s.default) for s in out] == \
        [(".dtpub", True, True), (".pub", True, True)]


def test_nothing_written_outside_the_current_user_classes_and_own_keys(reg):
    winassoc.register([".dtpub", ".pub"], reg)
    allowed = ("software\\classes\\", "software\\dtp publisher", "software\\registeredapplications")
    for k in reg.snapshot():
        assert k.startswith(allowed), k
        assert "userchoice" not in k                     # never forge the user's choice


def test_removing_puts_back_exactly_what_was_there(reg):
    _publisher_installed(reg)
    reg.set(r"Software\RegisteredApplications", "Some Other App", r"Software\Other\Capabilities")
    before = reg.snapshot()
    winassoc.register([".dtpub", ".pub"], reg)
    assert reg.get(r"Software\Classes\.pub") == "DTPPublisher.PubFile"
    winassoc.unregister([".dtpub", ".pub"], reg)
    assert reg.snapshot() == before


def test_a_choice_made_since_is_not_undone(reg):
    winassoc.register([".pub"], reg)
    reg.set(r"Software\Classes\.pub", "", "Someone.Else")     # changed by another program
    winassoc.unregister([".pub"], reg)
    assert reg.get(r"Software\Classes\.pub") == "Someone.Else"


def test_earlier_user_choice_needs_confirming_in_settings(reg):
    reg.set(r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pub\UserChoice",
            "ProgId", "Publisher.Document.16")
    (st,) = winassoc.register([".pub"], reg)
    assert st.registered and not st.default and st.needs_confirming
    assert st.other_choice == "Publisher.Document.16"
    # once the user picks us in Settings, Windows records it as their choice
    reg.set(r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pub\UserChoice",
            "ProgId", "DTPPublisher.PubFile")
    assert winassoc.status(".pub", reg).default


def test_apply_sets_exactly_the_ticked_types(reg):
    winassoc.apply([".dtpub", ".pub"], reg)
    assert winassoc.registered_types(reg) == [".dtpub", ".pub"]
    winassoc.apply([".dtpub"], reg)
    assert winassoc.registered_types(reg) == [".dtpub"]
    assert reg.get(r"Software\Classes\.pub") is None
    assert reg.get(r"Software\RegisteredApplications", "DTP Publisher Pro")
    winassoc.apply([], reg)
    assert winassoc.registered_types(reg) == []
    assert reg.snapshot() == {}


def test_registering_twice_keeps_the_original_to_restore(reg):
    _publisher_installed(reg)
    winassoc.register([".pub"], reg)
    winassoc.register([".pub"], reg)                     # e.g. after the folder moved
    winassoc.unregister([".pub"], reg)
    assert reg.get(r"Software\Classes\.pub") == "LibreOffice.PubFile"


def test_repair_follows_a_moved_program_folder(reg, monkeypatch, tmp_path):
    winassoc.register([".dtpub"], reg)
    assert not winassoc.status(".dtpub", reg).stale
    old = PARTS[0]
    new = tmp_path / "Moved" / "DTP Publisher.exe"
    new.parent.mkdir()
    __import__("os").replace(old, new)                  # the folder was moved
    monkeypatch.setattr(winassoc, "launcher", lambda: [str(new)])
    assert winassoc.status(".dtpub", reg).stale
    assert winassoc.repair(reg) == [".dtpub"]
    assert reg.get(r"Software\Classes\DTPPublisher.Document\shell\open\command") == \
        f'"{new}" "%1"'
    assert not winassoc.status(".dtpub", reg).stale


def test_repair_leaves_another_existing_copy_alone(reg, monkeypatch, tmp_path):
    """Running a second copy (e.g. from source) must not take the files over."""
    winassoc.register([".dtpub"], reg)
    other = tmp_path / "other" / "pythonw.exe"
    other.parent.mkdir()
    other.write_bytes(b"MZ")
    monkeypatch.setattr(winassoc, "launcher", lambda: [str(other)])
    assert winassoc.repair(reg) == []
    assert reg.get(r"Software\Classes\DTPPublisher.Document\shell\open\command") == CMD


def test_repair_never_registers_what_the_user_did_not_choose(reg):
    assert winassoc.repair(reg) == []
    assert reg.snapshot() == {}
    _publisher_installed(reg)
    before = reg.snapshot()
    winassoc.repair(reg)
    assert reg.snapshot() == before


def test_command_lines(monkeypatch, tmp_path):
    assert winassoc.command_line([r"C:\A B\pythonw.exe", r"C:\A B\run.py"]) == \
        r'"C:\A B\pythonw.exe" "C:\A B\run.py" "%1"'
    assert winassoc.command_line([r"C:\py\pythonw.exe", "-m", "dtp_publisher"]) == \
        r'"C:\py\pythonw.exe" -m "dtp_publisher" "%1"'
    exe = tmp_path / "DTP Publisher.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert winassoc.launcher() == [str(exe)]


def test_running_from_source_uses_run_py():
    parts = winassoc.launcher()
    assert parts[-1].endswith("run.py") or parts[-2:] == ["-m", "dtp_publisher"]


def test_settings_link(monkeypatch):
    monkeypatch.setattr(winassoc, "supported", lambda: True)
    monkeypatch.setattr(sys, "getwindowsversion",
                        lambda: type("V", (), {"build": 22631})(), raising=False)
    assert winassoc.default_apps_uri() == \
        "ms-settings:defaultapps?registeredAppUser=DTP%20Publisher%20Pro"
    monkeypatch.setattr(sys, "getwindowsversion",
                        lambda: type("V", (), {"build": 19045})(), raising=False)
    assert winassoc.default_apps_uri() == "ms-settings:defaultapps"     # Windows 10


# ── in the program ─────────────────────────────────────────────────────────
def test_preferences_tick_boxes_register(window, reg, monkeypatch):
    from dtp_publisher.ui.dialogs import misc

    def ticked(self):
        for cb in self.assoc.values():
            cb.setChecked(True)
        return True
    monkeypatch.setattr(misc.PreferencesDialog, "exec", ticked)
    window.assoc_registry = reg
    window.preferences()
    assert winassoc.registered_types(reg) == [".dtpub", ".pub"]

    def untick_pub(self):
        assert self.assoc[".pub"].isChecked()                 # shows the current state
        self.assoc[".pub"].setChecked(False)
        return True
    monkeypatch.setattr(misc.PreferencesDialog, "exec", untick_pub)
    window.preferences()
    assert winassoc.registered_types(reg) == [".dtpub"]


def test_preferences_offer_settings_when_windows_wants_confirmation(window, reg, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from dtp_publisher.ui.dialogs import misc
    reg.set(r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pub\UserChoice",
            "ProgId", "Publisher.Document.16")

    def tick_pub(self):
        self.assoc[".pub"].setChecked(True)
        return True
    asked, opened = [], []
    monkeypatch.setattr(misc.PreferencesDialog, "exec", tick_pub)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(winassoc, "open_default_apps_settings", lambda: opened.append(1))
    window.assoc_registry = reg
    window.preferences()
    assert asked and ".pub" in asked[0][2] and opened == [1]

    dlg = misc.PreferencesDialog(window.settings, window, assoc_registry=reg)
    assert ".pub" in dlg.assoc_note.text() and "still" in dlg.assoc_note.text()


def test_section_hidden_off_windows(window, monkeypatch):
    from dtp_publisher.ui.dialogs import misc
    monkeypatch.setattr(winassoc, "supported", lambda: False)
    dlg = misc.PreferencesDialog(window.settings, window)
    assert dlg.assoc_wanted() is None


@pytest.mark.skipif(sys.platform != "win32", reason="the real registry exists only on Windows")
def test_real_registry_in_a_sandbox_key():
    """The winreg code itself, under a throwaway key - not the real file types."""
    base = r"Software\DTP Publisher Test Sandbox"
    real = winassoc.Registry(base)
    real.delete_tree("")
    try:
        real.set(r"Software\Classes\.pub", "", "LibreOffice.PubFile")
        before = {"pub": real.get(r"Software\Classes\.pub")}
        out = winassoc.register([".dtpub", ".pub"], real, parts=[sys.executable])
        assert all(s.registered and s.default for s in out)
        assert winassoc.registered_types(real) == [".dtpub", ".pub"]
        assert real.get(r"Software\Classes\DTPPublisher.Document\shell\open\command") == \
            f'"{sys.executable}" "%1"'
        winassoc.unregister([".dtpub", ".pub"], real)
        assert real.get(r"Software\Classes\.pub") == before["pub"]
        assert not real.has_key(r"Software\Classes\DTPPublisher.PubFile")
        assert not real.has_key(r"Software\DTP Publisher")
        assert winassoc.registered_types(real) == []
    finally:
        real.delete_tree("")
    assert not real.has_key("")


def test_winreg_code_against_a_strict_fake(monkeypatch, tmp_path):
    """The Registry class's own winreg calls (run for real on Windows by the
    sandbox test above), checked everywhere against a strict stand-in."""
    from fake_registry import FakeWinreg
    w = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", w)
    exe = tmp_path / "DTP Publisher.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(winassoc, "icon_location", lambda parts=None: f'"{exe}",0')
    real = winassoc.Registry(r"Software\Sandbox")
    real.set(r"Software\Classes\.pub", "", "LibreOffice.PubFile")
    out = winassoc.register([".dtpub", ".pub"], real, parts=[str(exe)])
    assert all(s.registered and s.default for s in out)
    assert real.get(r"Software\Classes\.dtpub\OpenWithProgids", "DTPPublisher.Document") == ""
    assert real.get(r"Software\Classes\.dtpub", "nothing") is None
    winassoc.unregister([".dtpub", ".pub"], real)
    assert real.get(r"Software\Classes\.pub") == "LibreOffice.PubFile"
    assert not real.has_key(r"Software\Classes\DTPPublisher.Document")
    assert not real.has_key(r"Software\Classes\.dtpub")
    assert not real.has_key(r"Software\DTP Publisher")
    real.delete_tree("")
    assert w.reg.keys.get("software") is not None and not real.has_key("")


def test_a_key_windows_will_not_delete_does_not_hang(monkeypatch):
    from fake_registry import FakeWinreg
    w = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", w)
    real = winassoc.Registry()
    real.set(r"Software\Classes\DTPPublisher.Document\shell\open\command", "", "x")
    calls = {"n": 0}
    enum = w.EnumKey

    def counting_enum(h, i):
        calls["n"] += 1
        if calls["n"] > 50:
            raise AssertionError("delete_tree is looping")
        return enum(h, i)

    def refuse(root, key):
        raise PermissionError(5, "Access is denied", key)
    monkeypatch.setattr(w, "EnumKey", counting_enum)
    monkeypatch.setattr(w, "DeleteKey", refuse)
    real.delete_tree(r"Software\Classes\DTPPublisher.Document")      # gives up, quietly
    assert calls["n"] < 10

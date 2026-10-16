# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# DTP_SRC lets tools/revert_proofs.py run the suite against a deliberately broken copy
sys.path.insert(0, os.environ.get("DTP_SRC") or os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def doc(qapp):
    from dtp_publisher.document import Document
    d = Document()
    d.add_page(d.make_page())
    d.undo_stack.clear()
    return d


@pytest.fixture
def page(doc):
    return doc.pages[0]


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Settings/autosave go to a temp folder, never the real user profile."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DTP_PUBLISHER_HOME", str(home))
    from dtp_publisher import settings as settings_mod
    settings_mod.set_current(settings_mod.Settings(show_start=False, autosave_minutes=0))
    yield home
    settings_mod.set_current(None)


@pytest.fixture
def window(qapp, _isolated_home):
    from dtp_publisher import theme
    from dtp_publisher.ui.window import MainWindow
    if theme.current_name() != "light" or not qapp.styleSheet():
        theme.apply(qapp, "light")
    w = MainWindow()
    w.resize(1400, 900)
    yield w
    w._end_edits()
    w.doc.mark_saved()
    w.close()
    w.deleteLater()
    from PyQt6.QtCore import QEvent
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch):
    """No test may touch the real Windows registry (file associations)."""
    from fake_registry import FakeRegistry

    from dtp_publisher import winassoc
    fake = FakeRegistry()
    monkeypatch.setattr(winassoc, "_default_registry", lambda: fake)
    return fake

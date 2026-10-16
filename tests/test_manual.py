# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""The user manual (help/manual.html): complete, and true to the program.

Every button the manual names as "Tab ▸ Button" must be on that ribbon tab,
every shortcut it lists must exist, and every picture must be there."""

import os
import re
from html.parser import HTMLParser

import pytest

HELP = os.path.join(os.path.dirname(__file__), "..", "src", "dtp_publisher", "help")
MANUAL = os.path.join(HELP, "manual.html")
ROOT = os.path.join(os.path.dirname(__file__), "..")


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs, self.ids, self.hrefs, self.paths, self.key_cells = [], set(), [], [], []
        self._span = None
        self._td = None
        self._in_keys = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
            self._in_keys = a["id"] == "keys" or (self._in_keys and a["id"] not in ("help",))
        if tag == "img":
            self.imgs.append(a.get("src", ""))
            assert a.get("alt"), f"picture without a description: {a.get('src')}"
        if tag == "a" and a.get("href", "").startswith("#"):
            self.hrefs.append(a["href"][1:])
        if tag == "span" and a.get("class") == "path":
            self._span = ""
        if tag == "td" and self._in_keys and self._td is None:
            self._td = ""
        if tag == "kbd" and self._td is not None:
            self._td += "<k>"

    def handle_endtag(self, tag):
        if tag == "span" and self._span is not None:
            self.paths.append(self._span)
            self._span = None
        if tag == "td" and self._td is not None:
            self.key_cells.append(self._td)
            self._td = None
        if tag == "kbd" and self._td is not None:
            self._td += "</k>"

    def handle_data(self, data):
        if self._span is not None:
            self._span += data
        if self._td is not None:
            self._td += data


@pytest.fixture(scope="module")
def scan():
    s = _Scan()
    with open(MANUAL, encoding="utf-8") as f:
        s.feed(f.read())
    return s


def test_every_picture_is_there_and_used(scan):
    files = set(os.listdir(os.path.join(HELP, "img")))
    used = {os.path.basename(s) for s in scan.imgs}
    for src in scan.imgs:
        assert os.path.isfile(os.path.join(HELP, src)), src
    assert files - used == set(), "pictures not in the manual"


def test_contents_links_go_somewhere(scan):
    assert scan.hrefs
    for h in scan.hrefs:
        assert h in scan.ids, h


def test_manual_is_for_this_version():
    from dtp_publisher import __version__
    major_minor = ".".join(__version__.split(".")[:2])
    with open(MANUAL, encoding="utf-8") as f:
        assert f"DTP Publisher Pro {major_minor}." in f.read(), \
            "update the manual (and its screenshots) for this version"


def _ribbon(window):
    """{tab: {button and menu names}} as built by the program."""
    from PyQt6.QtWidgets import QToolButton
    out = {}
    for name, page in window.ribbon.pages.items():
        texts = set()
        for b in page.findChildren(QToolButton):
            t = (b.defaultAction().text() if b.defaultAction() else b.text())
            texts.add(t.replace("&", "").replace("\n", " ").rstrip("…").strip())
        out[name] = texts
    return out


def test_every_button_the_manual_names_is_on_that_tab(window, scan):
    ribbon = _ribbon(window)
    assert scan.paths
    for path in scan.paths:
        tab, _, button = " ".join(path.split()).partition(" ▸ ")
        assert tab in ribbon, f"{path}: no {tab} tab"
        assert button.rstrip("…") in ribbon[tab], f"{path}: not on the {tab} tab"


def test_every_shortcut_the_manual_lists_exists(window, scan):
    from PyQt6.QtGui import QKeySequence
    have = set()
    for a in window.acts.values():
        for sc in a.shortcuts():
            have.add(sc.toString(QKeySequence.SequenceFormat.PortableText).lower())
    named = {"delete": "del", "pgup": "pgup", "pgdn": "pgdown", "esc": "esc"}
    checked = 0
    for cell in scan.key_cells[::2]:                     # the "Keys" column
        if "mouse" in cell or "Arrow" in cell or "Space" in cell:
            continue
        for combo in cell.split(" / "):
            keys = re.findall(r"<k>(.*?)</k>", combo)
            if not keys:
                continue
            seq = "+".join(named.get(k.lower(), k.lower()) for k in keys)
            assert seq in have, f"the manual lists {seq}, which the program doesn't have"
            checked += 1
    assert checked >= 20


def test_f1_opens_the_manual(window, monkeypatch):
    from PyQt6.QtGui import QDesktopServices, QKeySequence
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url) or True))
    act = window.acts["manual"]
    assert QKeySequence("F1") in act.shortcuts()
    act.trigger()
    (url,) = opened
    assert url.isLocalFile() and os.path.isfile(url.toLocalFile())
    assert url.toLocalFile().endswith(os.path.join("help", "manual.html"))


def test_manual_ships_with_the_program():
    with open(os.path.join(ROOT, "packaging", "dtp_publisher.spec"), encoding="utf-8") as f:
        assert '"dtp_publisher/help"' in f.read()
    with open(os.path.join(ROOT, "build_exe.bat"), encoding="utf-8") as f:
        assert "User Manual.pdf" in f.read()
    pdf = os.path.join(ROOT, "User Manual.pdf")
    assert os.path.getsize(pdf) > 500_000
    with open(pdf, "rb") as f:
        assert f.read(5) == b"%PDF-"

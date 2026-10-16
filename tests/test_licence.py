# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Every file of ours carries the same licence notice as LICENSE."""

import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
SPDX = "SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1"
OURS = (".py", ".bat", ".spec", ".html")
SKIP = {".venv", ".venv-build", "__pycache__", "dist", "build", "dist-single", "build-single",
        ".pytest_cache"}


def _files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            if f.endswith(OURS):
                yield os.path.join(d, f)


def test_licence_file():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("Restricted Use Software Licence v1.1")
    assert "Leon Priest" in text


def test_every_file_has_the_notice():
    missing, old = [], []
    for p in _files():
        with open(p, encoding="utf-8") as f:
            head = f.read(600)
        if SPDX not in head:
            missing.append(os.path.relpath(p, ROOT))
        if "Apache" in head:
            old.append(os.path.relpath(p, ROOT))
    assert not missing and not old, (missing, old)


def test_about_box_states_the_licence():
    from dtp_publisher.ui.dialogs.misc import about_text
    t = about_text()
    assert "Restricted Use Software Licence" in t and "non-commercial" in t
    assert "Apache" not in t

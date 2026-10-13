# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Write packaging/app.ico from the program's own drawn icon (used by the .exe)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from dtp_publisher.ui.icons import icon  # noqa: E402

out = os.path.join(HERE, "app.ico")
if not icon("wordart", 256).pixmap(256, 256).save(out, "ICO"):
    # some Qt builds have no ICO writer; PNG still works as a window icon
    out = os.path.join(HERE, "app.png")
    icon("wordart", 256).pixmap(256, 256).save(out, "PNG")
print(out)

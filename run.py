# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Launcher: python run.py [publication.dtpub]"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from dtp_publisher.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

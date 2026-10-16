# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Entry point: ``python -m dtp_publisher [file.dtpub]``."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Automatic text fields: page numbers and today's date."""

from __future__ import annotations

import datetime as _dt

from .document import Document
from .items.text import TextItem

FIELD_KINDS = {"page": "Page number", "page_of": "Page X of Y", "date": "Today's date"}


def field_text(kind: str, page_no: int, total: int, today: _dt.date | None = None) -> str:
    if kind == "page":
        return str(page_no)
    if kind == "page_of":
        return f"Page {page_no} of {total}"
    if kind == "date":
        d = today or _dt.date.today()
        return f"{d.day} {d.strftime('%B %Y')}"
    return ""


def refresh_fields(doc: Document) -> None:
    total = len(doc.pages)
    for i, sc in enumerate(doc.pages):
        for it in sc.all_design_items():
            if isinstance(it, TextItem) and it.auto:
                it.update_auto(field_text(it.auto, i + 1, total))

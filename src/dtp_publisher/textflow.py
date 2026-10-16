# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Connecting and disconnecting linked text boxes (with undo)."""

from __future__ import annotations

from typing import Dict, List

from PyQt6.QtGui import QTextCursor, QTextDocumentFragment

from .commands import SceneCommand
from .items.text import TextItem


def can_connect(a: TextItem, b: TextItem) -> str:
    """Empty string if ``a`` may flow into ``b``; otherwise the reason why not."""
    if a is b:
        return "A box can't continue into itself."
    if a.link_next is not None:
        return "That box already continues into another one. Break that link first."
    if b.link_prev is not None:
        return "The other box already receives text from somewhere else."
    if b in a.chain():
        return "Those boxes are already in the same story."
    return ""


def _adopt(frames: List[TextItem], owner: TextItem):
    doc = owner._own_doc
    for f in frames:
        if f._ti.document() is not doc:
            f._ti.setDocument(doc)
        f._ti.setDefaultTextColor(owner.text_color)


def connect(a: TextItem, b: TextItem, merge_text: bool = True):
    """Make the story in ``a``'s chain continue into ``b`` (and b's followers).

    To join many boxes at once (loading, importing), do it inside
    ``deferred_layout`` so each story is laid out once, not once per link."""
    owner = a.chain_root()
    if merge_text and not b.chain_root().is_empty():
        frag = QTextDocumentFragment(b.chain_root()._own_doc)
        c = QTextCursor(owner._own_doc)
        c.movePosition(QTextCursor.MoveOperation.End)
        if not owner.is_empty():
            c.insertBlock()
        c.insertFragment(frag)
    tail = b.chain()
    a.link_next = b
    b.link_prev = a
    _adopt(tail, owner)
    owner.layout_chain()


def disconnect(a: TextItem) -> TextItem:
    """Break the link after ``a``; the text stays in a's part of the chain."""
    b = a.link_next
    if b is None:
        return None
    a.link_next = None
    b.link_prev = None
    b._own_doc.clear()
    b._set_block_defaults()
    tail = b.chain()
    for f in tail:
        f._ti.setDocument(b._own_doc)
    if b.link_next is None:
        b._slice = (0.0, 0.0)
        b.refit()
    else:
        b.layout_chain()
    if a.is_linked():
        a.chain_root().layout_chain()
    else:
        a.refit()
    for f in tail + [a]:
        f.update()
    return b


class LinkCmd(SceneCommand):
    def __init__(self, scene, a: TextItem, b: TextItem):
        super().__init__("Link text boxes", scene)
        self.a, self.b = a, b
        self.story = a.chain_root()._own_doc.toHtml()
        self.b_html = b.chain_root()._own_doc.toHtml()

    def redo(self):
        connect(self.a, self.b, merge_text=True)
        self._changed()

    def undo(self):
        disconnect(self.a)
        self.b.chain_root()._own_doc.setHtml(self.b_html)
        self.a.chain_root()._own_doc.setHtml(self.story)
        self._changed()


class UnlinkCmd(SceneCommand):
    def __init__(self, scene, a: TextItem):
        super().__init__("Break text link", scene)
        self.a = a
        self.b = a.link_next

    def redo(self):
        disconnect(self.a)
        self._changed()

    def undo(self):
        connect(self.a, self.b, merge_text=False)
        self._changed()


def resolve_links(items: List[TextItem]) -> int:
    """After loading: connect boxes whose saved ``link_next`` points at another box."""
    by_uid: Dict[str, TextItem] = {t.uid: t for t in items}
    n = 0
    with deferred_layout(lambda: items):
        for a in items:
            uid = a._pending_next
            a._pending_next = ""
            b = by_uid.get(uid) if uid else None
            if b is not None and not can_connect(a, b):
                connect(a, b, merge_text=False)
                n += 1
    return n


class deferred_layout:
    """``with deferred_layout(items):`` link and resize many boxes, then lay every
    story out once on the way out (instead of once per change: quadratic)."""

    def __init__(self, items_fn):
        self.items_fn = items_fn

    def __enter__(self):
        TextItem._defer_layout += 1
        return self

    def __exit__(self, *exc):
        TextItem._defer_layout -= 1
        if not TextItem._defer_layout:
            layout_stories(self.items_fn())
        return False


def layout_stories(items: List[TextItem]) -> None:
    """Lay out every linked story among ``items`` once."""
    done = set()
    for t in items:
        if t.is_linked():
            root = t.chain_root()
            if id(root) not in done:
                done.add(id(root))
                root.layout_chain()

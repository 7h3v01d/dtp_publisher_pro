# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Linked text boxes: flow, editing hand-off, undo, save/load, copies."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTextCursor

from dtp_publisher import serialize
from dtp_publisher.commands import AddItemsCmd, DeleteItemsCmd, TextCmd
from dtp_publisher.geometry import Geo
from dtp_publisher.items import TextItem
from dtp_publisher.textflow import LinkCmd, UnlinkCmd, can_connect, connect

LONG = "\n".join(f"Paragraph {i}: " + "words " * 12 for i in range(40))


def box(sc, x, y, w=150, h=120, text=""):
    t = TextItem(w, h)
    t.set_geometry(Geo(x, y, w, h))
    if text:
        t.set_text(text, "DejaVu Sans", 10)
    sc.addItem(t)
    return t


def visible(t: TextItem) -> str:
    a, b = t._slice_pos
    return t.document.toPlainText()[a:b] if t.is_linked() else t.plain_text()


def test_story_flows_without_repeating(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    c = box(page, 380, 20)
    assert a.overflow
    page.push(LinkCmd(page, a, b))
    page.push(LinkCmd(page, b, c))
    va, vb, vc = visible(a), visible(b), visible(c)
    assert va and vb and vc
    assert va.startswith("Paragraph 0") and not vb.startswith("Paragraph 0")
    # nothing lost, nothing repeated (up to the line breaks between slices)
    joined = (va + vb + vc).replace("\n", "").replace(" ", "")
    assert LONG.replace("\n", "")[:len(joined)].replace(" ", "") == joined.replace(" ", "")
    assert c.overflow and not a.overflow and not b.overflow
    assert a.document is b.document is c.document


def test_slices_cut_at_whole_lines(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    connect(a, b)
    a0, a1 = a._slice
    b0, b1 = b._slice
    assert a1 <= a.inner_rect().height() + 0.5
    assert b0 >= a1 - 0.01


def test_link_undo_restores_both_texts(doc, page):
    a = box(page, 20, 20, text="first story")
    b = box(page, 200, 20, text="second story")
    page.push(LinkCmd(page, a, b))
    assert "second story" in a.document.toPlainText() and b.is_linked()
    doc.undo_stack.undo()
    assert not a.is_linked() and not b.is_linked()
    assert a.plain_text() == "first story" and b.plain_text() == "second story"
    doc.undo_stack.redo()
    assert b.document is a.document


def test_break_link_keeps_text_in_first_box(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    page.push(LinkCmd(page, a, b))
    page.push(UnlinkCmd(page, a))
    assert not b.is_linked() and b.is_empty()
    assert a.plain_text().startswith("Paragraph 0") and a.overflow
    doc.undo_stack.undo()
    assert b.document is a.document and visible(b)


def test_rules(page):
    a, b, c = box(page, 0, 0), box(page, 200, 0), box(page, 400, 0)
    connect(a, b)
    assert can_connect(a, c)          # a already continues
    assert can_connect(c, b)          # b already receives
    assert can_connect(b, a)          # same story
    assert can_connect(a, a)
    assert can_connect(b, c) == ""


def test_deleted_middle_box_is_skipped_and_undo_restores(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    c = box(page, 380, 20)
    connect(a, b)
    connect(b, c)
    second = visible(b)
    page.push(DeleteItemsCmd(page, [b]))
    assert visible(c) == second            # c now shows what b showed
    doc.undo_stack.undo()
    assert visible(b) == second


def test_deleting_first_box_keeps_story(doc, page, tmp_path):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    connect(a, b)
    page.push(DeleteItemsCmd(page, [a]))
    assert visible(b).startswith("Paragraph 0")
    p = str(tmp_path / "d.dtpub")
    serialize.save_document(doc, p)
    d2, _ = serialize.load_document(p)
    t = d2.pages[0].top_items()[0]
    assert t.plain_text().startswith("Paragraph 0")


def test_save_load_across_pages_stores_story_once(doc, tmp_path):
    p1 = doc.pages[0]
    p2 = doc.make_page()
    doc.add_page(p2)
    a = box(p1, 20, 20, text=LONG)
    b = box(p2, 20, 20)
    connect(a, b)
    data = serialize.document_to_dict(doc)
    htmls = [i["html"] for pg in data["pages"] for i in pg["items"]]
    assert sum(1 for h in htmls if "Paragraph 0" in h) == 1
    path = str(tmp_path / "x.dtpub")
    serialize.save_document(doc, path)
    d2, _ = serialize.load_document(path)
    a2 = d2.pages[0].top_items()[0]
    b2 = d2.pages[1].top_items()[0]
    assert a2.link_next is b2 and b2.document is a2.document
    assert visible(b2) == visible(b)


def test_copy_of_linked_box_gets_only_its_text(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    connect(a, b)
    c = serialize.clone_item(b, QPointF(5, 5))
    assert not c.is_linked()
    assert c.plain_text().strip() == visible(b).strip()


def test_typing_in_linked_box_reflows_and_is_one_undo(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    page.push(LinkCmd(page, a, b))
    before_b = visible(b)
    a.begin_edit()
    c = a.text_child().textCursor()
    c.setPosition(0)
    c.insertText("NEW WORDS " * 30)
    a.text_child().setTextCursor(c)
    editing = a if a.editing else b
    editing.end_edit()
    assert visible(b) != before_b
    doc.undo_stack.undo()
    assert visible(b) == before_b


def test_caret_moves_into_next_box(doc, page):
    a = box(page, 20, 20, text=LONG)
    b = box(page, 200, 20)
    connect(a, b)
    a.begin_edit()
    c = a.text_child().textCursor()
    c.setPosition(b._slice_pos[0] + 3)
    a.text_child().setTextCursor(c)
    a.notify_caret()
    assert b.editing and not a.editing
    assert b.text_child().textCursor().position() == b._slice_pos[0] + 3
    b.end_edit()


def test_window_link_mode(window, qapp, monkeypatch):
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    window.show()
    window.view.set_zoom(1.0)
    sc = window.scene
    a = box(sc, 20, 20, text=LONG)
    b = box(sc, 250, 300)
    window._select([a])
    assert window.acts["link_text"].isEnabled()
    window.start_link()
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, window.view.mapFromScene(QPointF(300, 350)))
    assert a.link_next is b
    window._select([a])
    window.break_link()
    assert a.link_next is None
    window.undo()
    assert a.link_next is b

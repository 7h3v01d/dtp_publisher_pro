# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Regression tests for the seven bugs confirmed in the March prototype.

Each was reproduced against the original code before the rewrite (see
REVIEW.md); tools/revert_proofs.py re-breaks each fix and checks the matching
test fails.
"""

import os
from collections import Counter

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest

from dtp_publisher import export, serialize
from dtp_publisher.geometry import Geo
from dtp_publisher.items import GroupItem, ShapeItem, TextItem
from dtp_publisher.units import mm


def _render_pdf_page(path, index=0, width=200):
    from PyQt6.QtCore import QSize
    from PyQt6.QtPdf import QPdfDocument
    pdf = QPdfDocument(None)
    pdf.load(path)
    size = pdf.pagePointSize(index)
    img = pdf.render(index, QSize(width, round(width * size.height() / size.width())))
    return pdf, size, img


def _dark_fraction(img: QImage) -> float:
    dark = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)          # QtPdf renders onto a transparent canvas
            if c.alpha() > 200 and c.lightness() < 60:
                dark += 1
    return dark / ((img.height() // 2 + img.height() % 2) * (img.width() // 2 + img.width() % 2))


# ── #1 objects moved when a saved file was reopened ──────────────────────────
def test_r1_positions_survive_save_and_reload(doc, page, tmp_path):
    t = TextItem(200, 80)
    t.set_geometry(Geo(65, 65, 200, 80, 0))
    s = ShapeItem(100, 60)
    s.set_geometry(Geo(300, 300, 100, 60, 30))
    a, b = ShapeItem(40, 40), ShapeItem(30, 30, "ellipse")
    a.setPos(100, 600)
    b.setPos(170, 650)
    for it in (t, s, a, b):
        page.addItem(it)
    g = GroupItem()
    page.addItem(g)
    g.adopt([a, b])
    before = {it.uid: it.scene_box() for it in (t, s, a, b, g)}
    path = str(tmp_path / "x.dtpub")
    serialize.save_document(doc, path)
    doc2, warnings = serialize.load_document(path)
    assert warnings == []
    sc2 = doc2.pages[0]
    for uid, box in before.items():
        it = sc2.find_uid(uid)
        assert it is not None, uid
        got = it.scene_box()
        assert abs(got.left() - box.left()) < 1e-3 and abs(got.top() - box.top()) < 1e-3, uid
        assert abs(got.width() - box.width()) < 1e-3 and abs(got.height() - box.height()) < 1e-3


# ── #2 PDF export drew the page in a tiny corner ─────────────────────────────
def test_r2_pdf_fills_the_page(doc, page, tmp_path):
    s = ShapeItem(page.page_w, page.page_h)
    s.fill = QColor("black")
    s.stroke_width = 0
    page.addItem(s)
    s.setSelected(True)                 # handles must not be printed either
    path = str(tmp_path / "full.pdf")
    export.export_pdf(doc, path)
    _pdf, size, img = _render_pdf_page(path)
    assert abs(size.width() - page.page_w) < 0.5 and abs(size.height() - page.page_h) < 0.5
    assert _dark_fraction(img) > 0.97


def test_r2_mixed_page_sizes_each_get_their_own_size(doc, tmp_path):
    land = doc.make_page(mm(297), mm(210))
    doc.add_page(land)
    path = str(tmp_path / "mixed.pdf")
    assert export.export_pdf(doc, path) == 2
    from PyQt6.QtPdf import QPdfDocument
    pdf = QPdfDocument(None)
    pdf.load(path)
    assert pdf.pageCount() == 2
    s0, s1 = pdf.pagePointSize(0), pdf.pagePointSize(1)
    assert s0.width() < s0.height()
    assert abs(s1.width() - mm(297)) < 0.5 and abs(s1.height() - mm(210)) < 0.5


def test_r2_selection_handles_not_printed(doc, page):
    s = ShapeItem(100, 100)
    s.fill = QColor(0, 0, 0, 0)
    s.stroke_width = 0
    s.setPos(200, 200)
    page.addItem(s)
    s.setSelected(True)
    img = export.render_page_image(page, 72)
    # the corner handle would be drawn at (200,200); the page must stay white there
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            assert QColor(img.pixel(200 + dx, 200 + dy)).lightness() > 250


# ── #3 keyboard shortcuts were all ambiguous / hijacked typing ──────────────
def test_r3_no_duplicate_or_bare_letter_shortcuts(window):
    from PyQt6.QtGui import QAction
    seqs = Counter()
    for a in window.findChildren(QAction):
        for sc in a.shortcuts():
            seqs[sc.toString()] += 1
    dupes = {k: v for k, v in seqs.items() if v > 1}
    assert dupes == {}
    bare = [k for k in seqs if len(k) == 1 and k.isalpha()]
    assert bare == []


def test_r3_shortcut_actually_fires(window, qapp):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    qapp.processEvents()
    sc = window.scene
    s = ShapeItem(50, 50)
    window._insert([s], "Add")
    assert s.scene() is sc
    QTest.keyClick(window.view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert s.scene() is None, "Ctrl+Z did not undo"


# ── #4 rotating flung objects off the page ───────────────────────────────────
def test_r4_rotation_pivots_on_centre(page):
    s = ShapeItem(100, 60)
    s.setPos(300, 300)
    page.addItem(s)
    c0 = s.mapToScene(s.rect().center())
    s.set_geometry(s.geometry()._replace(rot=90))
    c1 = s.mapToScene(s.rect().center())
    assert abs(c0.x() - c1.x()) < 1e-6 and abs(c0.y() - c1.y()) < 1e-6


# ── #5 deleted objects were still written to the file ───────────────────────
def test_r5_deleted_objects_not_saved(doc, page, tmp_path):
    from dtp_publisher.commands import AddItemsCmd, DeleteItemsCmd
    a = ShapeItem(10, 10)
    page.push(AddItemsCmd(page, [a]))
    page.push(DeleteItemsCmd(page, [a]))
    data = serialize.document_to_dict(doc)
    assert data["pages"][0]["items"] == []


# ── #6 grid size / snap distance settings had no effect ─────────────────────
def test_r6_grid_size_setting_changes_snapping(doc, page):
    v = doc.view
    v.update_from({"snap_grid": True, "snap_objects": False, "snap_guides": False,
                   "grid_size": 50.0, "snap_px": 8})
    page.margins = [0, 0, 0, 0]
    # a box whose left edge is 3pt from the 50pt grid line should snap to it
    v_snapped, _ = page.snap_value(103.0, "x", set())
    assert v_snapped == pytest.approx(100.0)
    v.set("grid_size", 40.0)
    v_snapped, _ = page.snap_value(83.0, "x", set())
    assert v_snapped == pytest.approx(80.0)


def test_r6_snap_distance_setting_changes_tolerance(doc, page):
    v = doc.view
    v.update_from({"snap_grid": True, "snap_objects": False, "snap_guides": False,
                   "grid_size": 100.0})
    page.margins = [0, 0, 0, 0]
    page.set_zoom(1.0)
    v.set("snap_px", 2)
    assert page.snap_value(195.0, "x", set())[0] == pytest.approx(195.0)
    v.set("snap_px", 10)
    assert page.snap_value(195.0, "x", set())[0] == pytest.approx(200.0)


# ── #7 a guide dragged from the top ruler landed in the wrong place ─────────
def test_r7_top_ruler_creates_horizontal_guide_where_dropped(window, qapp):
    window.show()
    qapp.processEvents()
    sc = window.scene
    window.view.set_zoom(1.0)
    qapp.processEvents()
    target_scene = QPointF(150, 333)
    vp = window.view.viewport()
    drop = window.view.mapFromScene(target_scene)
    ruler = window.ruler_h
    start = QPoint(ruler.width() // 2, ruler.height() // 2)
    QTest.mousePress(ruler, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    gp = vp.mapToGlobal(drop)
    QTest.mouseMove(ruler, ruler.mapFromGlobal(gp))
    QTest.mouseRelease(ruler, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       ruler.mapFromGlobal(gp))
    qapp.processEvents()
    assert len(sc.guides) == 1
    g = sc.guides[0]
    assert g.orient == "H"
    assert abs(g.position - window.view.mapToScene(drop).y()) < 1.0
    window.undo()
    assert sc.guides == []

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Geometry, items, undo commands, serialisation and migration."""

import json
import os

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QTextCharFormat, QFont

from dtp_publisher import serialize
from dtp_publisher.commands import (AddGuideCmd, AddItemsCmd, AddPageCmd, DeleteItemsCmd,
                                    GeometryCmd, GroupCmd, MoveItemsCmd, MovePageCmd,
                                    PageSetupCmd, PropCmd, RemovePageCmd, TextCmd, UngroupCmd,
                                    ZOrderCmd)
from dtp_publisher.document import Document
from dtp_publisher.geometry import (Geo, bounds_of, geo_from_local_rect, local_to_parent,
                                    normalize_angle, parent_to_local, snap_angle)
from dtp_publisher.items import (GroupItem, ImageItem, ShapeItem, TableItem, TextItem,
                                 WordArtItem)
from dtp_publisher.items.image import encode_image, prepare_image_bytes
from dtp_publisher.scene import GuideItem
from dtp_publisher.units import mm

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ── geometry ─────────────────────────────────────────────────────────────────
def test_local_parent_roundtrip():
    g = Geo(10, 20, 100, 50, 37)
    for p in (QPointF(0, 0), QPointF(100, 50), QPointF(33, 7)):
        q = parent_to_local(g, local_to_parent(g, p))
        assert abs(q.x() - p.x()) < 1e-9 and abs(q.y() - p.y()) < 1e-9


def test_resize_rotated_keeps_opposite_edge():
    g = Geo(100, 100, 100, 50, 45)
    # drag the east edge out by 40: the west edge midpoint must not move on screen
    west_before = local_to_parent(g, QPointF(0, 25))
    ng = geo_from_local_rect(g, QRectF(0, 0, 140, 50))
    west_after = local_to_parent(ng, QPointF(0, 25))
    assert abs(west_before.x() - west_after.x()) < 1e-9
    assert abs(west_before.y() - west_after.y()) < 1e-9
    assert ng.w == 140 and ng.rot == 45


def test_bounds_of_rotated_square():
    b = bounds_of(Geo(0, 0, 10, 10, 45))
    assert b.width() == pytest.approx(10 * 2 ** 0.5)


@pytest.mark.parametrize("a,want", [(370, 10), (-190, 170), (180, 180), (-180, 180), (0, 0)])
def test_normalize_angle(a, want):
    assert normalize_angle(a) == pytest.approx(want)


def test_snap_angle_magnet():
    assert snap_angle(88, 90, magnet=4) == 90
    assert snap_angle(80, 90, magnet=4) == 80
    assert snap_angle(22, 15) == 15


# ── item geometry & interaction maths ────────────────────────────────────────
def test_item_geometry_roundtrip(page):
    s = ShapeItem(50, 30)
    page.addItem(s)
    g = Geo(12.5, 40, 80, 33, -20)
    s.set_geometry(g)
    assert s.geometry().close_to(g)


def test_resize_drag_snaps_to_margin(doc, page, qapp):
    from dtp_publisher.items.base import _Drag
    doc.view.update_from({"snap_grid": False, "snap_objects": False})
    page.set_zoom(1.0)
    s = ShapeItem(100, 100)
    s.setPos(100, 100)
    page.addItem(s)
    s._drag = _Drag("resize", "e", s.geometry(), QPointF())
    right_margin = page.margin_rect().right()
    s._resize_to(QPointF(right_margin - 3, 150), Qt.KeyboardModifier.NoModifier)
    assert s.geometry().x + s.geometry().w == pytest.approx(right_margin)
    s._resize_to(QPointF(right_margin - 3, 150), Qt.KeyboardModifier.AltModifier)
    assert s.geometry().x + s.geometry().w == pytest.approx(right_margin - 3)


def test_picture_corner_resize_keeps_aspect(page):
    from dtp_publisher.items.base import _Drag
    im = ImageItem(200, 100)
    page.addItem(im)
    page.doc.view.update_from({"snap_grid": False, "snap_objects": False,
                               "snap_guides": False})
    page.margins = [0, 0, 0, 0]
    im._drag = _Drag("resize", "se", im.geometry(), QPointF())
    im._resize_to(QPointF(301, 133), Qt.KeyboardModifier.NoModifier)
    g = im.geometry()
    assert g.w / g.h == pytest.approx(2.0)


def test_group_move_whole_selection_with_undo(doc, page):
    a, b = ShapeItem(10, 10), ShapeItem(10, 10)
    a.setPos(10, 10)
    b.setPos(50, 50)
    page.addItem(a)
    page.addItem(b)
    a.setSelected(True)
    b.setSelected(True)
    doc.view.update_from({"snap_grid": False, "snap_objects": False, "snap_guides": False})
    page.margins = [0, 0, 0, 0]
    page.begin_move(QPointF(15, 15))
    page.update_move(QPointF(15 + 33.3, 15 + 21.1), Qt.KeyboardModifier.AltModifier)
    assert page.end_move()
    assert a.pos() == QPointF(43.3, 31.1) and b.pos() == QPointF(83.3, 71.1)
    doc.undo_stack.undo()
    assert a.pos() == QPointF(10, 10) and b.pos() == QPointF(50, 50)


def test_locked_items_do_not_move(doc, page):
    a = ShapeItem(10, 10)
    page.addItem(a)
    a.set_prop("locked", True)
    a.setSelected(True)
    assert page.begin_move(QPointF(0, 0)) is False


# ── commands / undo ──────────────────────────────────────────────────────────
def test_add_delete_undo(doc, page):
    s = ShapeItem()
    page.push(AddItemsCmd(page, [s]))
    assert s.scene() is page
    page.push(DeleteItemsCmd(page, [s]))
    assert s.scene() is None
    doc.undo_stack.undo()
    assert s.scene() is page
    doc.undo_stack.undo()
    assert s.scene() is None


def test_prop_cmd_merges(doc, page):
    s = ShapeItem()
    page.addItem(s)
    for w in (1, 2, 3, 4):
        page.push(PropCmd(page, [s], "stroke_width", float(w), merge=True))
    assert doc.undo_stack.count() == 1
    doc.undo_stack.undo()
    assert s.stroke_width == 1.0          # ShapeItem default


def test_nudges_merge_into_one_undo(doc, page):
    s = ShapeItem()
    page.addItem(s)
    for i in range(5):
        p = s.pos()
        page.push(MoveItemsCmd(page, {s: (QPointF(p), p + QPointF(1, 0))}, nudge=True))
    assert doc.undo_stack.count() == 1
    doc.undo_stack.undo()
    assert s.pos() == QPointF(0, 0)


def test_group_ungroup_preserves_positions_and_rotation(doc, page):
    a, b = ShapeItem(40, 20), ShapeItem(30, 30, "ellipse")
    a.set_geometry(Geo(100, 100, 40, 20, 30))
    b.set_geometry(Geo(200, 150, 30, 30, 0))
    page.addItem(a)
    page.addItem(b)

    def boxes():
        return {it: it.scene_box() for it in (a, b)}

    def same(x, y):
        for it in (a, b):
            for f in ("left", "top", "width", "height"):
                assert abs(getattr(x[it], f)() - getattr(y[it], f)()) < 1e-6

    before = boxes()
    g = GroupItem()
    page.push(GroupCmd(page, g, [a, b]))
    assert a.parentItem() is g and not (a.flags() & a.GraphicsItemFlag.ItemIsSelectable)
    same(before, boxes())
    g0 = g.geometry()
    page.push(GeometryCmd(page, {g: (g0, g0._replace(rot=90))}, "Rotate"))
    rotated = boxes()
    page.push(UngroupCmd(page, g))
    assert a.parentItem() is None and a.rotation() == pytest.approx(120)
    same(rotated, boxes())
    doc.undo_stack.undo()          # regroup
    same(rotated, boxes())
    doc.undo_stack.undo()          # un-rotate
    same(before, boxes())
    doc.undo_stack.undo()          # ungroup
    assert a.parentItem() is None
    same(before, boxes())


def test_group_resize_scales_members(doc, page):
    from dtp_publisher.items.base import _Drag
    a, b = ShapeItem(50, 50), ShapeItem(50, 50)
    a.setPos(0, 0)
    b.setPos(100, 0)
    page.addItem(a)
    page.addItem(b)
    g = GroupItem()
    page.push(GroupCmd(page, g, [a, b]))
    doc.view.update_from({"snap_grid": False, "snap_objects": False, "snap_guides": False})
    page.margins = [0, 0, 0, 0]
    g._drag = _Drag("resize", "e", g.geometry(), QPointF())
    g.on_drag_start()
    g._resize_to(QPointF(300, 25), Qt.KeyboardModifier.AltModifier)
    assert a.w == pytest.approx(100) and b.pos().x() == pytest.approx(200)
    changes = {g: (g._drag.start_geo, g.geometry())}
    changes.update(g.extra_geometry_changes())
    page.push(GeometryCmd(page, changes))
    doc.undo_stack.undo()
    assert a.w == pytest.approx(50) and b.pos().x() == pytest.approx(100)


def test_zorder_cmd(doc, page):
    items = [ShapeItem() for _ in range(3)]
    for i, it in enumerate(items):
        it.setZValue(i + 1)
        page.addItem(it)
    old = {i: i.zValue() for i in items}
    new = {items[0]: 3.0, items[1]: 1.0, items[2]: 2.0}
    page.push(ZOrderCmd(page, old, new))
    assert page.top_items()[-1] is items[0]
    doc.undo_stack.undo()
    assert page.top_items()[-1] is items[2]


# ── cross-page undo (old prototype re-added items to the wrong page) ────────
def test_undo_on_other_page_stays_on_that_page(doc):
    p1 = doc.pages[0]
    p2 = doc.make_page()
    doc.undo_stack.push(AddPageCmd(doc, 1, p2))
    s = ShapeItem()
    p1.push(AddItemsCmd(p1, [s]))
    p1.push(DeleteItemsCmd(p1, [s]))
    doc.undo_stack.undo()          # restore on page 1, even though page 2 exists
    assert s.scene() is p1
    assert s not in p2.items()


def test_page_commands(doc):
    p1 = doc.pages[0]
    p2, p3 = doc.make_page(name="two"), doc.make_page(name="three")
    doc.undo_stack.push(AddPageCmd(doc, 1, p2))
    doc.undo_stack.push(AddPageCmd(doc, 2, p3))
    doc.undo_stack.push(MovePageCmd(doc, p3, 0))
    assert doc.pages == [p3, p1, p2]
    doc.undo_stack.push(RemovePageCmd(doc, p1))
    assert doc.pages == [p3, p2]
    doc.undo_stack.undo()
    assert doc.pages == [p3, p1, p2]
    doc.undo_stack.undo()
    assert doc.pages == [p1, p2, p3]


def test_page_setup_cmd(doc, page):
    old = page.setup_state()
    new = dict(old, width=mm(148), height=mm(210), columns=3)
    doc.undo_stack.push(PageSetupCmd([page], [old], [new]))
    assert page.page_w == pytest.approx(mm(148)) and page.columns == 3
    doc.undo_stack.undo()
    assert page.page_w == pytest.approx(old["width"])


def test_guides_move_and_persist(doc, page):
    g = GuideItem("V", 100)
    page.push(AddGuideCmd(page, g))
    g.set_position(222)
    st = page.guide_state()
    assert st == [{"orient": "V", "pos": 222.0}]
    _, xs = page._candidates(set()), None
    xs, ys = page._candidates(set())
    assert 222 in xs


def test_hidden_guides_do_not_catch_clicks(doc, page):
    g = GuideItem("V", 100)
    page.push(AddGuideCmd(page, g))
    assert g in page.items(QPointF(100, 50))
    doc.view.set("show_guides", False)
    assert g not in page.items(QPointF(100, 50))


# ── text ─────────────────────────────────────────────────────────────────────
def test_text_rich_roundtrip(doc, page, tmp_path):
    t = TextItem(200, 100)
    t.set_text("Hello ", "DejaVu Sans", 12)
    t.add_paragraphs("Second paragraph", "DejaVu Serif", 20, bold=True, color=QColor("#ff0000"))
    page.addItem(t)
    path = str(tmp_path / "t.dtpub")
    serialize.save_document(doc, path)
    d2, _ = serialize.load_document(path)
    t2 = d2.pages[0].top_items()[0]
    assert t2.plain_text() == "Hello \nSecond paragraph"
    blk = t2.document.lastBlock()
    fmt = blk.begin().fragment().charFormat()
    assert fmt.fontPointSize() == 20 and fmt.foreground().color() == QColor("#ff0000")


def test_text_point_size_is_true_points(page):
    t = TextItem(400, 200)
    t.set_text("X", "DejaVu Sans", 72)
    # a 72pt line is roughly 1 inch (72 scene units) tall, not 96
    assert 70 < t.document.size().height() < 90


@pytest.mark.parametrize("mode", ["none", "shrink", "best", "grow"])
def test_autofit_modes(page, mode):
    t = TextItem(100, 30)
    t.set_text("A fairly long sentence that will not fit in one small box at this size.",
               "DejaVu Sans", 14)
    page.addItem(t)
    t.set_prop("fit", mode)
    used = t.document.size().height() * t._scale
    if mode == "none":
        assert t.overflow and t._scale == 1.0
    elif mode == "shrink":
        assert not t.overflow and t._scale < 1.0 and used <= t.inner_rect().height() + 0.5
    elif mode == "best":
        assert not t.overflow and used <= t.inner_rect().height() + 0.5
    else:
        assert not t.overflow and t.h > 30


def test_best_fit_enlarges_short_text(page):
    t = TextItem(300, 200)
    t.set_text("Hi", "DejaVu Sans", 10)
    page.addItem(t)
    t.set_prop("fit", "best")
    assert t._scale > 2


def test_format_whole_box_is_undoable(doc, page):
    t = TextItem(200, 60)
    t.set_text("Make me bold")
    page.addItem(t)
    fmt = QTextCharFormat()
    fmt.setFontWeight(QFont.Weight.Bold.value)
    t.merge_char_format(fmt)
    assert t.current_char_format().fontWeight() == QFont.Weight.Bold.value
    doc.undo_stack.undo()
    assert t.current_char_format().fontWeight() != QFont.Weight.Bold.value


def test_edit_session_is_one_undo_step(doc, page, qapp):
    t = TextItem(200, 60)
    page.addItem(t)
    t.begin_edit()
    c = t.text_child().textCursor()
    c.insertText("abc")
    c.insertText("def")
    t.end_edit()
    assert t.plain_text() == "abcdef"
    assert doc.undo_stack.count() == 1
    doc.undo_stack.undo()
    assert t.plain_text() == ""


def test_page_number_fields(doc):
    from dtp_publisher.fields import field_text, refresh_fields
    p2 = doc.make_page()
    doc.add_page(p2)
    t = TextItem(100, 20)
    t.auto = "page_of"
    p2.addItem(t)
    refresh_fields(doc)
    assert t.plain_text() == "Page 2 of 2"
    import datetime
    assert field_text("date", 1, 1, datetime.date(2026, 3, 4)) == "4 March 2026"


# ── pictures ─────────────────────────────────────────────────────────────────
def _jpeg_bytes(w, h, color="red"):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return encode_image(img, "jpg")[0]


def test_large_photos_are_downsampled():
    data, fmt, img = prepare_image_bytes(_jpeg_bytes(5000, 2000))
    assert max(img.width(), img.height()) == 3000 and fmt == "jpg"


def test_small_jpeg_kept_byte_for_byte():
    raw = _jpeg_bytes(300, 200)
    data, fmt, _ = prepare_image_bytes(raw)
    assert data == raw and fmt == "jpg"


def test_not_an_image_rejected():
    assert prepare_image_bytes(b"this is not a picture") is None


def test_exif_rotated_photo_is_stored_upright():
    # build a JPEG 40x20 with EXIF orientation 6 (rotate 90° CW)
    raw = _jpeg_bytes(40, 20)
    exif = (b"Exif\x00\x00" + b"MM\x00\x2a\x00\x00\x00\x08" + b"\x00\x01"
            + b"\x01\x12\x00\x03\x00\x00\x00\x01\x00\x06\x00\x00" + b"\x00\x00\x00\x00")
    app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    rotated = raw[:2] + app1 + raw[2:]
    data, fmt, img = prepare_image_bytes(rotated)
    assert (img.width(), img.height()) == (20, 40)
    re = QImage()
    re.loadFromData(data)
    assert (re.width(), re.height()) == (20, 40)


def test_image_roundtrip_and_modes(doc, page, tmp_path):
    im = ImageItem(100, 100)
    raw = _jpeg_bytes(200, 100, "blue")
    im.set_image_data(raw, "jpg", "photo.jpg")
    im.fit_mode = "fit"
    im.crop_x = 0.5
    page.addItem(im)
    path = str(tmp_path / "i.dtpub")
    serialize.save_document(doc, path)
    im2 = serialize.load_document(path)[0].pages[0].top_items()[0]
    assert im2.data == raw and im2.fit_mode == "fit" and im2.crop_x == 0.5
    assert im2.has_image() and im2.source_name == "photo.jpg"
    src, dst = im2._source_target(200, 100)
    assert dst.height() == pytest.approx(50)            # letterboxed
    im2.fit_mode = "fill"
    src, dst = im2._source_target(200, 100)
    assert src.width() == pytest.approx(100) and src.left() == pytest.approx(75)


def test_change_picture_undo(doc, page):
    im = ImageItem()
    page.addItem(im)
    raw = _jpeg_bytes(10, 10)
    page.push(PropCmd(page, [im], "image", (raw, "jpg", "a.jpg")))
    assert im.has_image()
    doc.undo_stack.undo()
    assert not im.has_image()


# ── table / wordart ──────────────────────────────────────────────────────────
def test_table_state_roundtrip(doc, page):
    t = TableItem(200, 100, 3, 2)
    st = t.table_state()
    st["cells"] = {"1,1": "x", "9,9": "out of range"}
    st["rows"] = 4
    page.addItem(t)
    page.push(PropCmd(page, [t], "table", st))
    assert t.rows == 4 and t.cell(1, 1) == "x" and (9, 9) not in t.cells
    doc.undo_stack.undo()
    assert t.rows == 3


def test_wordart_warps_render(page):
    for warp in ("none", "arch_up", "arch_down", "wave", "bulge"):
        w = WordArtItem(200, 60, "Hello")
        w.warp = warp
        p = w.path()
        assert not p.isEmpty()
        br = p.boundingRect()
        assert br.width() <= 200.5 and br.height() <= 60.5


# ── files ────────────────────────────────────────────────────────────────────
def test_atomic_save_keeps_backup(doc, page, tmp_path):
    path = str(tmp_path / "doc.dtpub")
    serialize.save_document(doc, path)
    first = open(path, "rb").read()
    page.addItem(ShapeItem())
    serialize.save_document(doc, path)
    assert open(path + ".bak", "rb").read() == first
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]


def test_save_marks_clean(doc, page, tmp_path):
    page.push(AddItemsCmd(page, [ShapeItem()]))
    assert doc.is_modified()
    serialize.save_document(doc, str(tmp_path / "a.dtpub"))
    assert not doc.is_modified()


@pytest.mark.parametrize("payload", [b"", b"{not json", b"[1,2,3]", b'{"format":"other"}',
                                     b"\xff\xfe\x00garbage"])
def test_bad_files_raise_friendly_error(tmp_path, payload, qapp):
    p = tmp_path / "bad.dtpub"
    p.write_bytes(payload)
    with pytest.raises(serialize.DocumentError):
        serialize.load_document(str(p))


def test_damaged_item_is_skipped_not_fatal(qapp):
    data = {"format": "dtpub", "version": 5, "pages": [{"setup": {"width": 300, "height": 300},
            "items": [{"kind": "shape", "x": "NaN", "w": "oops"},
                      {"kind": "spaceship"},
                      {"kind": "text", "html": 12345}]}]}
    doc, warnings = serialize.document_from_dict(data)
    assert len(doc.pages) == 1
    assert any("unknown" in w for w in warnings)


def test_v3_migration_from_march_prototype(qapp):
    doc, warnings = serialize.load_document(os.path.join(FIXTURES, "v3_sample.json"))
    assert doc.path is None                 # must "Save As" a new .dtpub
    assert len(doc.pages) == 2
    kinds = [it.KIND for it in doc.pages[0].top_items()]
    assert "table" in kinds and "image" in kinds and "group" in kinds and "text" in kinds
    g = next(it for it in doc.pages[0].top_items() if it.KIND == "group")
    assert len(g.members()) == 2
    img = next(it for it in doc.pages[0].top_items() if it.KIND == "image")
    assert img.has_image()
    assert [gd.orient for gd in doc.pages[0].guides] == ["V"]
    texts = [it.plain_text() for it in doc.pages[0].all_design_items() if it.KIND == "text"]
    assert any("DTP Publisher Pro v4" in t for t in texts)
    assert any("converted" in w.lower() for w in warnings)


def test_clipboard_payload_roundtrip(page):
    a = ShapeItem(10, 10, "star")
    page.addItem(a)
    items = serialize.items_from_clip(serialize.items_to_clip([a]))
    assert len(items) == 1 and items[0].shape_kind == "star"
    assert serialize.items_from_clip(b"garbage") == []


def test_clone_has_fresh_uids(page):
    a, b = ShapeItem(), ShapeItem()
    page.addItem(a)
    page.addItem(b)
    g = GroupItem()
    page.addItem(g)
    g.adopt([a, b])
    c = serialize.clone_item(g, QPointF(5, 5))
    uids = {g.uid, a.uid, b.uid}
    assert c.uid not in uids and not ({m.uid for m in c.members()} & uids)
    assert c.pos() == g.pos() + QPointF(5, 5)


def test_settings_roundtrip_and_sanitize(tmp_path, monkeypatch):
    from dtp_publisher.settings import Settings
    s = Settings(theme="dark", ui_scale=1.5, units="in")
    s.add_recent(str(tmp_path / "a.dtpub"))
    s.save()
    s2 = Settings.load()
    assert (s2.theme, s2.ui_scale, s2.units) == ("dark", 1.5, "in")
    with open(Settings.path(), "w") as f:
        json.dump({"theme": "neon", "ui_scale": 9, "units": "furlongs", "autosave_minutes": -5}, f)
    s3 = Settings.load()
    assert s3.theme == "light" and s3.ui_scale == 2.0 and s3.units == "mm"
    assert s3.autosave_minutes == 0

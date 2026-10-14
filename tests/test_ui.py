# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Main-window behaviour driven through real mouse/keyboard events."""

import os

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from dtp_publisher.geometry import Geo
from dtp_publisher.items import GroupItem, ImageItem, ShapeItem, TableItem, TextItem
from dtp_publisher.items.image import encode_image
from dtp_publisher.units import mm


@pytest.fixture
def win(window, qapp):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    window.view.set_zoom(1.0)
    qapp.processEvents()
    return window


def vp_point(win, sp: QPointF) -> QPoint:
    return win.view.mapFromScene(sp)


def drag(win, a: QPointF, b: QPointF, mods=Qt.KeyboardModifier.NoModifier, steps=6):
    vp = win.view.viewport()
    pa, pb = vp_point(win, a), vp_point(win, b)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, mods, pa)
    for i in range(1, steps + 1):
        p = pa + (pb - pa) * (i / steps)
        QTest.mouseMove(vp, p)
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mods, pb)
    QApplication.processEvents()


def add_shape(win, x=100, y=100, w=80, h=60, kind="rect"):
    s = ShapeItem(w, h, kind)
    s.setPos(x, y)
    win._insert([s], "Add")
    return s


# ── mouse ────────────────────────────────────────────────────────────────────
def test_drag_moves_object_and_undo_restores(win):
    win.doc.view.update_from({"snap_grid": False, "snap_objects": False, "snap_guides": False})
    s = add_shape(win)
    drag(win, QPointF(140, 130), QPointF(240, 210), Qt.KeyboardModifier.AltModifier)
    assert s.pos().x() == pytest.approx(200, abs=1.5) and s.pos().y() == pytest.approx(180, abs=1.5)
    win.undo()
    assert s.pos() == QPointF(100, 100)


def test_drag_corner_handle_resizes(win):
    win.doc.view.update_from({"snap_grid": False, "snap_objects": False, "snap_guides": False})
    s = add_shape(win)
    assert s.isSelected()
    drag(win, QPointF(180, 160), QPointF(230, 200), Qt.KeyboardModifier.AltModifier)
    assert s.w == pytest.approx(130, abs=1.5) and s.h == pytest.approx(100, abs=1.5)
    assert s.pos() == QPointF(100, 100)
    win.undo()
    assert (s.w, s.h) == (80, 60)


def test_click_empty_page_deselects(win):
    s = add_shape(win)
    assert s.isSelected()
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     vp_point(win, QPointF(400, 600)))
    assert not s.isSelected()


def test_shift_click_adds_to_selection(win):
    a = add_shape(win, 100, 100)
    b = add_shape(win, 300, 100)
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     vp_point(win, QPointF(140, 130)))
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     vp_point(win, QPointF(340, 130)))
    assert a.isSelected() and b.isSelected()


# ── typing ───────────────────────────────────────────────────────────────────
def test_typing_letters_and_delete_edit_text_not_objects(win, qapp):
    win.insert_text()
    t = win.selected()[0]
    assert isinstance(t, TextItem) and t.editing
    QTest.keyClicks(win.view, "Tree")           # T/R/E/I used to insert objects
    QTest.keyClick(win.view, Qt.Key.Key_Delete)
    QTest.keyClick(win.view, Qt.Key.Key_Backspace)
    qapp.processEvents()
    assert t.plain_text() == "Tre"
    assert t.scene() is win.scene
    assert len(win.scene.top_items()) == 1
    QTest.keyClick(win.view, Qt.Key.Key_Escape)
    assert not t.editing and t.isSelected()
    QTest.keyClick(win.view, Qt.Key.Key_Delete)  # now Delete removes the box
    assert t.scene() is None


def test_ctrl_b_bolds_only_selected_words(win, qapp):
    from PyQt6.QtGui import QFont, QTextCursor
    win.insert_text()
    t = win.selected()[0]
    QTest.keyClicks(win.view, "plain bold")
    c = t.text_child().textCursor()
    c.setPosition(6)
    c.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    t.text_child().setTextCursor(c)
    QTest.keyClick(win.view, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    doc = t.document
    first = QTextCursor(doc)
    first.setPosition(1)
    last = QTextCursor(doc)
    last.setPosition(9)
    assert first.charFormat().fontWeight() < QFont.Weight.DemiBold.value
    assert last.charFormat().fontWeight() >= QFont.Weight.Bold.value


def test_format_bar_keeps_editing_session(win, qapp):
    """Clicking the font box must not end editing (formatting the selection)."""
    win.insert_text()
    t = win.selected()[0]
    QTest.keyClicks(win.view, "abc")
    win.fmt.font_box.setFocus()
    qapp.processEvents()
    assert t.editing
    win.fmt.set_size(30)
    from PyQt6.QtGui import QTextCursor
    c = QTextCursor(t.document)
    c.setPosition(2)
    assert t.editing


def test_editing_ends_when_clicking_elsewhere_and_is_one_undo(win, qapp):
    win.insert_text()
    t = win.selected()[0]
    n0 = win.doc.undo_stack.count()
    QTest.keyClicks(win.view, "Hello")
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     vp_point(win, QPointF(500, 700)))
    qapp.processEvents()
    assert not t.editing
    assert win.doc.undo_stack.count() == n0 + 1
    win.undo()
    assert t.plain_text() == ""


# ── clipboard / duplicate ────────────────────────────────────────────────────
def test_copy_paste_offsets_and_fresh_uids(win):
    s = add_shape(win)
    win.copy()
    win.paste()
    win.paste()
    tops = win.scene.top_items()
    assert len(tops) == 3
    assert len({t.uid for t in tops}) == 3
    assert tops[2].pos() == s.pos() + QPointF(mm(10), mm(10))


def test_paste_image_from_clipboard(win):
    img = QImage(60, 30, QImage.Format.Format_RGB32)
    img.fill(QColor("green"))
    QApplication.clipboard().setImage(img)
    win.paste()
    it = win.selected()[0]
    assert isinstance(it, ImageItem) and it.has_image()
    assert it.w / it.h == pytest.approx(2.0)


def test_paste_plain_text_makes_text_box(win):
    QApplication.clipboard().setText("Hello from the clipboard")
    win.paste()
    it = win.selected()[0]
    assert isinstance(it, TextItem) and it.plain_text() == "Hello from the clipboard"


def test_duplicate_and_cut(win):
    s = add_shape(win)
    win.duplicate()
    assert len(win.scene.top_items()) == 2
    win.cut()
    assert len(win.scene.top_items()) == 1
    win.paste()
    assert len(win.scene.top_items()) == 2


# ── arrange ──────────────────────────────────────────────────────────────────
def test_align_and_distribute(win):
    items = [add_shape(win, 50 + i * 37, 100 + i * 50, 40, 40) for i in range(3)]
    win._select(items)
    win.align("left")
    assert {round(i.scene_box().left(), 3) for i in items} == {50}
    win.undo()
    items[2].setPos(300, 200)
    win._select(items)
    win.distribute("h")
    b = sorted((i.scene_box() for i in items), key=lambda r: r.left())
    assert (b[1].left() - b[0].right()) == pytest.approx(b[2].left() - b[1].right())


def test_single_object_aligns_to_margins(win):
    s = add_shape(win, 200, 200)
    win._select([s])
    win.align("right")
    assert s.scene_box().right() == pytest.approx(win.scene.margin_rect().right())


def test_arrange_front_back(win):
    a, b, c = add_shape(win), add_shape(win), add_shape(win)
    win._select([a])
    win.arrange("front")
    assert win.scene.top_items()[-1] is a
    win.arrange("back")
    assert win.scene.top_items()[0] is a
    win.arrange("forward")
    assert win.scene.top_items()[1] is a
    win.undo()
    assert win.scene.top_items()[0] is a


def test_group_ungroup_via_window(win):
    a, b = add_shape(win, 50, 50), add_shape(win, 200, 50)
    win._select([a, b])
    win.group()
    g = win.selected()[0]
    assert isinstance(g, GroupItem) and len(g.members()) == 2
    win.ungroup()
    assert set(win.selected()) == {a, b}


def test_rotate_and_flip(win):
    s = add_shape(win, kind="triangle")
    win.rotate_by(90)
    assert s.rotation() == 90
    win.flip("flip_v")
    assert s.flip_v
    win.undo()
    assert not s.flip_v


def test_lock_prevents_delete_and_move(win):
    s = add_shape(win)
    win.toggle_lock()
    assert s.locked
    win.delete()
    assert s.scene() is win.scene
    win.nudge(1, 0, False)
    assert s.pos() == QPointF(100, 100)


def test_nudge_with_arrow_keys(win, qapp):
    s = add_shape(win)
    QTest.keyClick(win.view, Qt.Key.Key_Right)
    QTest.keyClick(win.view, Qt.Key.Key_Right)
    QTest.keyClick(win.view, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    qapp.processEvents()
    assert s.pos() == QPointF(102, 100 + mm(5))


def test_fill_page_with_copies(win, monkeypatch):
    from dtp_publisher.ui.dialogs import misc
    monkeypatch.setattr(misc.FillPageDialog, "exec", lambda self: True)
    sc = win.scene
    st = sc.setup_state()
    st["margins"] = [0, 0, 0, 0]
    sc.apply_setup(st)
    card = add_shape(win, 10, 10, sc.page_w / 2, sc.page_h / 5)
    win._select([card])
    win.fill_page()
    assert len(sc.top_items()) == 10
    win.undo()
    assert len(sc.top_items()) == 1 and card.pos() == QPointF(10, 10)


# ── pages ────────────────────────────────────────────────────────────────────
def test_pages_add_duplicate_delete_and_undo_follows(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    p1 = win.scene
    s = add_shape(win)
    win.page_add()
    assert len(win.doc.pages) == 2 and win.page_index() == 1
    win.show_page(0)
    win.page_duplicate()
    assert len(win.doc.pages) == 3 and len(win.scene.top_items()) == 1
    assert win.scene.top_items()[0].uid != s.uid
    win.show_page(0)
    win.page_delete()
    assert len(win.doc.pages) == 2 and p1 not in win.doc.pages
    win.undo()
    assert win.doc.pages[0] is p1
    # an undo of something on another page brings that page into view
    win.show_page(0)
    s.setSelected(True)
    win.nudge(1, 0, False)
    win.show_page(1)
    win.undo()
    assert win.scene is p1 and s.pos() == QPointF(100, 100)


def test_thumbnail_reorder(win):
    win.page_add()
    p1, p2 = win.doc.pages
    win.thumbs.moveRequested.emit(1, 0)
    assert win.doc.pages == [p2, p1]
    win.undo()
    assert win.doc.pages == [p1, p2]


def test_page_size_and_orientation(win):
    win.page_add()
    win.set_orientation(True)
    assert all(p.page_w > p.page_h for p in win.doc.pages)
    win.set_page_size(mm(148), mm(210))
    assert all(p.page_w == pytest.approx(mm(210)) for p in win.doc.pages)
    win.undo()
    win.undo()
    assert all(p.page_w < p.page_h for p in win.doc.pages)


def test_footer_on_every_page_numbers_pages(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    win.page_add()
    win.page_add()
    win.insert_block("footer")
    nums = []
    for sc in win.doc.pages:
        nums += [t.plain_text() for t in sc.all_design_items()
                 if isinstance(t, TextItem) and t.auto]
    assert nums == ["Page 1 of 3", "Page 2 of 3", "Page 3 of 3"]
    win.thumbs.moveRequested.emit(2, 0)
    first = [t for t in win.doc.pages[0].all_design_items() if isinstance(t, TextItem) and t.auto]
    assert first[0].plain_text() == "Page 1 of 3"


# ── insert everything ────────────────────────────────────────────────────────
def test_insert_every_kind(win, monkeypatch, tmp_path):
    from dtp_publisher.ui.dialogs import editors
    monkeypatch.setattr(editors.TableDialog, "exec", lambda self: True)
    monkeypatch.setattr(editors.WordArtDialog, "exec", lambda self: True)
    win.insert_placeholder()
    win.insert_table()
    win.insert_wordart()
    from dtp_publisher.items.shape import SHAPES
    for k in SHAPES:
        win.insert_shape(k)
    for k in ("story", "quote", "sidebar", "coupon", "pagenum", "date", "header"):
        win.insert_block(k)
    kinds = {it.KIND for it in win.scene.top_items()}
    assert kinds >= {"image", "table", "wordart", "shape", "text", "group"}
    for it in win.scene.top_items():
        assert win.scene.page_rect().intersects(it.scene_box()), it.display_name()


def test_drop_picture_on_placeholder_fills_it(win, tmp_path):
    win.insert_placeholder()
    ph = win.selected()[0]
    img = QImage(100, 50, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    p = str(tmp_path / "pic.png")
    img.save(p)
    win._files_dropped([p], ph.scene_box().center())
    assert ph.has_image() and len(win.scene.top_items()) == 1
    win._files_dropped([p], QPointF(20, 20))
    assert len(win.scene.top_items()) == 2


# ── files & prompts ──────────────────────────────────────────────────────────
def test_save_open_and_title(win, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    path = str(tmp_path / "flyer")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (path, "")))
    add_shape(win)
    assert win.isWindowModified()
    assert win.save()
    assert os.path.exists(path + ".dtpub") and not win.isWindowModified()
    assert "flyer.dtpub" in win.windowTitle()
    win.open_path(path + ".dtpub", ask=False)
    assert len(win.scene.top_items()) == 1
    assert win.settings.recent[0].endswith("flyer.dtpub")


def test_unsaved_changes_prompt(win, monkeypatch):
    add_shape(win)
    seen = {}

    def fake_exec(box):
        seen["text"] = box.text()
        for b in box.buttons():
            if b.text() == "Cancel":
                box._clicked = b
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    assert win.maybe_save() is False
    assert "save the changes" in seen["text"]


def test_export_pdf_and_pictures(win, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from dtp_publisher.ui.dialogs import misc
    add_shape(win)
    pdf = str(tmp_path / "out.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    win.export_pdf()
    assert os.path.getsize(pdf) > 500
    png = str(tmp_path / "pic.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (png, "")))
    monkeypatch.setattr(misc.ExportPicturesDialog, "exec", lambda self: True)
    win.export_pictures()
    img = QImage(png)
    assert img.width() == round(win.scene.page_w / 72 * 150)


def test_themes_switch_cleanly(win, qapp):
    for name in ("dark", "contrast", "light"):
        win.set_theme(name)
        qapp.processEvents()
        assert win.acts[f"theme_{name}"].isChecked()
        win.grab()


def test_start_dialog_builds_every_tile(qapp):
    from dtp_publisher.ui.dialogs.start import StartDialog
    dlg = StartDialog([], True)
    dlg.cats.setCurrentRow(0)
    n = dlg.gallery.count()
    assert n >= 18
    for i in range(n):
        dlg.gallery.setCurrentRow(i)
        dlg._create()
        assert dlg.document is not None and dlg.document.pages
    dlg.deleteLater()


def test_autosave_and_orphan_recovery(win, monkeypatch, qapp):
    from dtp_publisher import autosave
    add_shape(win)
    win.autosaver.tick()
    import time
    for _ in range(50):
        qapp.processEvents()
        if os.path.exists(win.autosaver.path + ".json"):
            break
        time.sleep(0.02)
    assert os.path.exists(win.autosaver.path)
    assert autosave.find_orphans() == []          # our own session is alive
    monkeypatch.setattr(autosave, "pid_alive", lambda pid: False)
    orphans = autosave.find_orphans()
    assert len(orphans) == 1
    win.save = lambda: True
    win.doc.mark_saved()
    win.autosaver.discard()
    assert not os.path.exists(win.autosaver.path)


def test_properties_panel_changes_are_undoable(win):
    s = add_shape(win)
    win.props.sp_w.setValue(win.props.sp_w.value() + 10)
    assert s.w > 80
    win.props.btn_fill.colorPicked.emit(QColor("#ff0000"))
    assert s.fill == QColor("#ff0000")
    win.undo()
    win.undo()
    assert s.w == pytest.approx(80) and s.fill != QColor("#ff0000")


def test_unexpected_errors_are_logged_not_fatal(tmp_path, monkeypatch, qapp):
    import sys
    from dtp_publisher.app import install_error_handler
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    import io
    console = io.StringIO()               # the handler's copy for the console goes here
    monkeypatch.setattr(sys, "__stderr__", console)
    old = sys.excepthook
    log = tmp_path / "crash.log"
    try:
        install_error_handler(str(log))
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old
    assert "ValueError: boom" in log.read_text() and shown



def test_error_handler_survives_a_missing_console(tmp_path, monkeypatch, qapp):
    """On Windows (pythonw, a packaged program, some test runners) stderr can
    exist but have an invalid handle: writing to it raised inside the handler."""
    import sys
    from dtp_publisher.app import install_error_handler

    class BadConsole:
        def write(self, _):
            raise OSError(6, "The handle is invalid")
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    monkeypatch.setattr(sys, "__stderr__", BadConsole())
    old = sys.excepthook
    log = tmp_path / "crash.log"
    try:
        install_error_handler(str(log))
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old
    assert "ValueError: boom" in log.read_text() and shown


def test_wordart_quick_style_buttons_are_readable_in_every_theme(qapp):
    """'White outline' was white text on a white button, and 'Classic black'
    vanished on the dark theme's buttons."""
    import re

    from PyQt6.QtGui import QColor

    from dtp_publisher.ui.dialogs.editors import WORDART_PRESETS, preset_button_style

    def lum(c):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())

    for name, ps in WORDART_PRESETS:
        css = preset_button_style(ps)
        fg = QColor(re.search(r"color:(#[0-9a-fA-F]{6})", css).group(1))
        bg = QColor(re.search(r"background:(#[0-9a-fA-F]{6})", css).group(1))
        hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
        assert (hi + 0.05) / (lo + 0.05) >= 3.0, name


def test_page_panel_buttons_show_their_whole_label(window):
    """At 1300 px wide, side by side they were cut to "Ad...ge"."""
    window.resize(1300, 820)
    window.show()
    QApplication.processEvents()
    for b in (window.thumbs.btn_add, window.thumbs.btn_del):
        assert b.width() >= b.sizeHint().width(), b.text()

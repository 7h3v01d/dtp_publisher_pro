# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""FlowLayout: identical to Qt's layout when nothing is in the way, and text
wrap around pictures / through boxes of different widths when something is."""

import random

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QImage, QPainter, QPalette,
                         QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextOption)

SYNTHETIC = [
    '<p style="margin-top:12px;margin-bottom:20px">One</p><p style="margin-top:30px">'
    'Two two two two two two two two two two two two two</p>',
    '<ul><li>apple</li><li>banana with a much longer item that wraps round the line</li></ul>'
    '<ol><li>one</li><li>two</li></ol>',
    '<p style="line-height:150%">a b c d e f g h i j k l m n o p q r s t u v w x y z a b c</p>'
    '<p style="line-height:20pt">fixed fixed fixed fixed fixed fixed fixed fixed</p>',
    '<p style="text-indent:30px;margin-left:15px;margin-right:25px">indented paragraph with '
    'several words to wrap round a few times here</p>',
    '<p align="center">centred words words words words words words</p><p align="justify">'
    'justified text text text text text text text text text text text</p><p align="right">r</p>',
    '<p><span style="font-size:40pt">Big</span> small <span style="font-size:8pt">tiny tiny tiny'
    ' tiny tiny tiny tiny</span></p>',
    '<p dir="rtl">שלום עולם '
    'שלום עולם שלום</p>',
    '<p>tab\there\tand\tthere</p><p></p><p></p><p>after empties</p>',
    '<p>Averyveryveryverylongwordthatcannotbreakanywhereatallsoitmustwrapanywhere</p>',
    '<p>Above the rule</p><hr/><p>Below the rule</p><hr width="50%"/>',
    '<p align="justify"><b>A travel diary of our journeys through five countries, during '
    'March and April. </b></p><p></p><p align="justify">Highlights were the mountains. </p>',
]


def _doc(html, width, flow):
    from dtp_publisher.items.flowlayout import install
    from dtp_publisher.items.text import layout_device
    d = QTextDocument()
    d.documentLayout().setPaintDevice(layout_device())
    if flow:
        install(d)
    d.setUseDesignMetrics(True)
    d.setDocumentMargin(0)
    o = d.defaultTextOption()
    o.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    d.setDefaultTextOption(o)
    d.setDefaultFont(QFont("Calibri", 14))
    d.setHtml(html)
    d.setTextWidth(width)
    return d


def _dump(d):
    out, b, lay = [], d.begin(), d.documentLayout()
    while b.isValid():
        r = lay.blockBoundingRect(b)
        out.append(("B", b.blockNumber(), round(r.top(), 3), round(r.left(), 3)))
        tl = b.layout()
        for i in range(tl.lineCount()):
            ln = tl.lineAt(i)
            out.append(("L", round(ln.x(), 3), round(ln.y(), 3), round(ln.width(), 3),
                        ln.textStart(), ln.textLength(), round(ln.height(), 3)))
        b = b.next()
    out.append(("S", round(d.size().width(), 3), round(d.size().height(), 3)))
    return out


def _samples():
    from dtp_publisher import templates
    out = [(f"syn{i}", h, 160.0) for i, h in enumerate(SYNTHETIC)]
    for t in templates.TEMPLATES:
        for it in templates.build(t.key).text_items():
            out.append((t.key, it.document.toHtml(), it.inner_rect().width() / (it._scale or 1)))
    return out


# ── the same as Qt when nothing is in the way ───────────────────────────────
def test_layout_matches_qt_line_for_line(qapp):
    samples = _samples()
    assert len(samples) > 60
    for name, html, w in samples:
        assert _dump(_doc(html, w, True)) == _dump(_doc(html, w, False)), name


def test_incremental_layout_matches_qt_while_editing(qapp):
    html = ("<p>" + "word " * 80 + "</p><ul><li>one</li><li>two three</li></ul>"
            '<p style="margin-top:20px">' + "more text " * 40 + "</p>")
    a, b = _doc(html, 180, False), _doc(html, 180, True)
    r = random.Random(4)
    for step in range(250):
        op, pos = r.randrange(5), r.randrange(max(a.characterCount() - 1, 1))
        for d in (a, b):
            rr = random.Random(step)
            c = QTextCursor(d)
            c.setPosition(min(pos, d.characterCount() - 1))
            if op == 0:
                c.insertText(rr.choice(["x", "hello ", "  ", "longwordlongword "]))
            elif op == 1:
                c.movePosition(QTextCursor.MoveOperation.NextCharacter,
                               QTextCursor.MoveMode.KeepAnchor, rr.randrange(1, 6))
                c.removeSelectedText()
            elif op == 2:
                c.insertBlock()
            elif op == 3:
                bf = QTextBlockFormat()
                bf.setTopMargin(rr.choice([0, 6, 18]))
                bf.setLineHeight(rr.choice([100, 150]), 1)
                c.mergeBlockFormat(bf)
            else:
                cf = QTextCharFormat()
                cf.setFontPointSize(rr.choice([8, 14, 30]))
                c.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor)
                c.mergeCharFormat(cf)
        assert _dump(b) == _dump(a), f"step {step}"


def _render(d, cur=-1, sel=None):
    sz = d.size()
    img = QImage(int(sz.width()) + 40, int(sz.height()) + 40,
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.translate(20, 20)
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.cursorPosition = cur
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Text, QColor("black"))
    ctx.palette = pal
    if sel is not None:
        s = QAbstractTextDocumentLayout.Selection()
        c = QTextCursor(d)
        c.setPosition(sel[0])
        c.setPosition(sel[1], QTextCursor.MoveMode.KeepAnchor)
        s.cursor = c
        f = QTextCharFormat()
        f.setBackground(QColor("yellow"))
        f.setForeground(QColor("black"))
        s.format = f
        ctx.selections = [s]
    d.documentLayout().draw(p, ctx)
    p.end()
    return img


def test_drawing_and_hit_testing_match_qt(qapp):
    r = random.Random(1)
    for name, html, w in _samples():
        a, b = _doc(html, w, False), _doc(html, w, True)
        cur = r.randrange(a.characterCount())
        assert _render(a, cur) == _render(b, cur), name
        if "<li" not in html:     # (Qt hides a selected list number; we show it)
            n = a.characterCount()
            for sel in (sorted((r.randrange(n), r.randrange(n))), (0, n - 1), (n // 3, n - 1)):
                assert _render(a, -1, sel) == _render(b, -1, sel), (name, "selection", sel)
        edges = [QPointF(r.uniform(0, w), y) for l in _lines(a)
                 for y in (l.top() - 0.0015, l.top() + 0.0015, l.bottom() - 0.0015)]
        edges += [QPointF(l.left() + l.width() * f, l.center().y()) for l in _lines(a)[:20]
                  for f in (0.0007, 0.3333, 0.66671)]
        for pt in edges:
            for acc in (Qt.HitTestAccuracy.FuzzyHit, Qt.HitTestAccuracy.ExactHit):
                assert (a.documentLayout().hitTest(pt, acc)
                        == b.documentLayout().hitTest(pt, acc)), (name, pt, "edge")
        for _ in range(25):
            pt = QPointF(r.uniform(-10, w + 10), r.uniform(-10, a.size().height() + 10))
            for acc in (Qt.HitTestAccuracy.FuzzyHit, Qt.HitTestAccuracy.ExactHit):
                assert (a.documentLayout().hitTest(pt, acc)
                        == b.documentLayout().hitTest(pt, acc)), (name, pt)


# ── regions and exclusions ──────────────────────────────────────────────────
def _lines(d):
    out, b = [], d.begin()
    while b.isValid():
        tl = b.layout()
        for i in range(tl.lineCount()):
            ln = tl.lineAt(i)
            out.append(QRectF(tl.position().x() + ln.x(), tl.position().y() + ln.y(),
                              ln.naturalTextWidth(), ln.height()))
        b = b.next()
    return out


LONG = "<p>" + "The village fete raised more than ever this year. " * 30 + "</p>"


def test_lines_flow_round_an_exclusion(qapp):
    from dtp_publisher.items.flowlayout import INF, Region
    d = _doc(LONG, 300, True)
    hole = QRectF(150, 40, 200, 100)            # a picture over the right half
    d.documentLayout().set_regions([Region(300, INF, [hole])])
    lines = _lines(d)
    assert not any(l.intersects(hole) for l in lines)
    beside = [l for l in lines if l.bottom() > hole.top() and l.top() < hole.bottom()]
    assert beside and all(l.right() <= hole.left() + 0.01 for l in beside)


def test_narrow_gaps_are_skipped(qapp):
    from dtp_publisher.items.flowlayout import INF, Region
    d = _doc(LONG, 300, True)
    hole = QRectF(20, 40, 280, 100)             # leaves a 20 pt sliver: unusable
    d.documentLayout().set_regions([Region(300, INF, [hole])])
    lines = _lines(d)
    assert not [l for l in lines if l.bottom() > hole.top() and l.top() < hole.bottom()]
    assert any(l.top() >= hole.bottom() for l in lines)


def test_obstacle_edge_cannot_trap_a_line(qapp):
    """A line exactly at an obstacle's bottom edge (float rounding) once looped."""
    from dtp_publisher.items.flowlayout import INF, Region
    d = _doc(LONG, 175, True)
    holes = [QRectF(-3, 0, 179, 183.546875000001), QRectF(3, 179, 168, 250)]
    d.documentLayout().set_regions([Region(175, INF, holes)])
    tops = [l.top() for l in _lines(d)]
    assert min(tops) >= 429 - 0.01


def test_regions_of_different_widths(qapp):
    from dtp_publisher.items.flowlayout import Region
    d = _doc(LONG, 300, True)
    lay = d.documentLayout()
    lay.set_regions([Region(300, 60), Region(120, 80), Region(200, 400)])
    tops = lay.region_tops()
    assert tops == [0, 60, 140]
    for l in _lines(d):
        k = 0 if l.top() < 60 else 1 if l.top() < 140 else 2
        assert l.bottom() <= tops[k] + [60, 80, 400][k] + 0.01 or k == 2
        assert l.right() <= [300, 120, 200][k] + 0.01
    assert lay.overflow_position() == -1 or lay.overflow_position() > 0


# ── text boxes and pictures on a page ───────────────────────────────────────
def _page_with_text_and_picture(page, wrap="square", picture_on_top=True):
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import ImageItem, TextItem
    t = TextItem(300, 400)
    t.set_geometry(Geo(50, 50, 300, 400, 0))
    t.document.setPlainText("The village fete raised more than ever this year. " * 30)
    im = ImageItem(150, 120)
    im.set_geometry(Geo(200, 120, 150, 120, 0))
    im.wrap = wrap
    t.setZValue(1)
    im.setZValue(2 if picture_on_top else 0)
    page.addItem(t)
    page.addItem(im)
    page.flush_wrap()
    t.refit()
    return t, im


def _text_lines_in_scene(t):
    out = []
    for r in _lines(t.document):
        out.append(t._ti.mapRectToScene(r))
    return out


def test_text_box_wraps_round_picture_in_front(qapp, page):
    t, im = _page_with_text_and_picture(page)
    pic = im.scene_box()
    assert not any(l.intersects(pic) for l in _text_lines_in_scene(t))


def test_picture_behind_or_set_to_none_does_not_wrap(qapp, page):
    t, im = _page_with_text_and_picture(page, picture_on_top=False)
    assert t.wrap_exclusions() == []
    im.setZValue(5)
    im.set_prop("wrap", "none")
    page.flush_wrap()
    assert t.wrap_exclusions() == []


def test_top_and_bottom_leaves_nothing_beside(qapp, page):
    t, im = _page_with_text_and_picture(page, wrap="top_bottom")
    pic = im.scene_box()
    beside = [l for l in _text_lines_in_scene(t) if l.bottom() > pic.top() and l.top() < pic.bottom()]
    assert beside == []


def test_moving_the_picture_reflows_and_undo_restores(qapp, doc, page):
    from dtp_publisher.commands import GeometryCmd
    t, im = _page_with_text_and_picture(page)
    before = _dump(t.document)
    old = im.geometry()
    new = old._replace(x=60)
    page.push(GeometryCmd(page, {im: (old, new)}, "Move"))
    page.flush_wrap()
    moved = _dump(t.document)
    assert moved != before
    doc.undo_stack.undo()
    page.flush_wrap()
    assert _dump(t.document) == before


def test_wrap_saved_and_old_files_do_not_wrap(qapp, page):
    from dtp_publisher.items import ImageItem
    from dtp_publisher.serialize import item_from_dict, item_to_dict
    im = ImageItem(10, 10)
    assert im.wrap == "square"                          # new pictures wrap, like Publisher
    im.wrap = "top_bottom"
    assert item_from_dict(item_to_dict(im)).wrap == "top_bottom"
    d = item_to_dict(im)
    del d["wrap"]
    assert item_from_dict(d).wrap == "none"             # nothing made before 5.2 moves


def test_linked_boxes_of_different_widths(qapp, page):
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import TextItem
    from dtp_publisher.textflow import connect
    a, b = TextItem(300, 100), TextItem(120, 300)
    a.set_geometry(Geo(20, 20, 300, 100, 0))
    b.set_geometry(Geo(20, 200, 120, 300, 0))
    page.addItem(a)
    page.addItem(b)
    a.document.setPlainText("word " * 200)
    connect(a, b, merge_text=False)
    lay = a.document.documentLayout()
    tops = lay.region_tops()
    for l in _lines(a.document):
        width = b.inner_rect().width() if l.top() >= tops[1] - 0.01 else a.inner_rect().width()
        assert l.right() <= width + 0.01
    assert b._slice[0] == pytest.approx(tops[1])


def test_wrap_actions_in_the_window(window):
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import ImageItem
    sc = window.scene
    im = ImageItem(100, 80)
    im.set_geometry(Geo(100, 100, 100, 80, 0))
    sc.addItem(im)
    sc.clearSelection()
    im.setSelected(True)
    window._update_actions()
    assert window.acts["wrap_square"].isChecked()
    window.acts["wrap_top_bottom"].trigger()
    assert im.wrap == "top_bottom"
    window.doc.undo_stack.undo()
    assert im.wrap == "square"


def test_imported_pictures_wrap_unless_they_cover_the_text(qapp, tmp_path):
    from test_import import _frame, make_odg
    from dtp_publisher.importers.odg import import_odg
    png = QImage(8, 8, QImage.Format.Format_RGB32)
    png.fill(QColor("red"))
    from dtp_publisher.items.image import encode_image
    data = encode_image(png, "png")[0]
    frames = (_frame(10, 10, 90, 80, "Story " * 100)
              + '<draw:frame svg:x="60mm" svg:y="20mm" svg:width="30mm" svg:height="20mm">'
                '<draw:image xlink:href="Pictures/a.png"/></draw:frame>'
              + _frame(110, 10, 40, 30, "Label on a picture")
              + '<draw:frame svg:x="108mm" svg:y="8mm" svg:width="45mm" svg:height="35mm">'
                '<draw:image xlink:href="Pictures/a.png"/></draw:frame>')
    path = make_odg(tmp_path / "w.odg", frames)
    import zipfile
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("Pictures/a.png", data)
    doc, _ = import_odg(path)
    pics = sorted((i for i in doc.pages[0].all_design_items() if i.KIND == "image"),
                  key=lambda i: i.scene_box().left())
    assert pics[0].wrap == "square"        # beside a story
    assert pics[1].wrap == "none"          # covers a whole text box: decoration


def test_editing_a_wrapped_box(window):
    """Click beside the picture, type, and the caret and text stay beside it."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    sc = window.scene
    t, im = _page_with_text_and_picture(sc)
    pic = im.scene_box()
    beside = [l for l in _text_lines_in_scene(t) if l.bottom() > pic.top() and l.top() < pic.bottom()]
    target = beside[1]
    t.begin_edit(QPointF(target.left() + 5, target.center().y()))
    c = t.text_child().textCursor()
    line_rect = t.text_child().mapRectToScene(
        _cursor_line_rect(t.document, c.position()))
    assert line_rect.contains(QPointF(target.left() + 5, target.center().y()))
    for ch in "Hello ":
        t.text_child().keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, 0,
                                               Qt.KeyboardModifier.NoModifier, ch))
    assert "Hello " in t.plain_text()
    assert not any(l.intersects(pic) for l in _text_lines_in_scene(t))
    t.end_edit()
    assert window.doc.undo_stack.canUndo()


def _cursor_line_rect(doc, pos):
    b = doc.findBlock(pos)
    tl = b.layout()
    ln = tl.lineForTextPosition(pos - b.position())
    return QRectF(tl.position().x() + ln.x(), tl.position().y() + ln.y(), ln.width(), ln.height())


def test_dragging_a_picture_over_a_long_story_stays_quick(qapp, page):
    import time
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import TextItem
    t, im = _page_with_text_and_picture(page)
    t.document.setPlainText("The village fete raised more than ever this year. " * 400)
    t0 = time.perf_counter()
    for k in range(20):
        im.set_geometry(Geo(100 + k * 5, 120 + k * 3, 150, 120, 0))
        page.flush_wrap()
    per_step = (time.perf_counter() - t0) / 20
    assert per_step < 0.25, per_step


def test_no_template_text_is_pushed_by_its_own_pictures(qapp):
    """Templates are designed with pictures next to text, never over it."""
    from dtp_publisher import templates
    for t in templates.TEMPLATES:
        d = templates.build(t.key)
        for sc in d.pages:
            sc.wrap_dirty()
            sc.flush_wrap()
            for it in sc.all_design_items():
                if it.KIND == "text":
                    assert it.wrap_exclusions() == [], (t.key, it.plain_text()[:20])


def test_step_past_an_obstacle_always_moves_down(qapp):
    from dtp_publisher.items.flowlayout import FlowLayout, Region
    reg = Region(175, 1000, [QRectF(0, 0, 175, 183.546875000001)])
    y = 183.546875
    nxt = FlowLayout._below_obstacles(reg, y - 20, 21)
    assert nxt is not None and nxt > reg.exclusions[0].bottom()


def test_obstacle_ending_at_the_line_top_does_not_block_it(qapp):
    from dtp_publisher.items.flowlayout import FlowLayout, Region
    reg = Region(175, 1000, [QRectF(0, 0, 175, 183.546875000001)])
    assert FlowLayout._free_span(reg, 183.546875, 21, 0, 175) == (0, 175)


# ═════════════════════════════════════════════════════════════════════════════
# 5.2.2 — third review (C1–C5) and wrap torture cases
# ═════════════════════════════════════════════════════════════════════════════
TABLE_HTML = ('<table border="1"><tr><td>Cell <b>A1</b></td><td><p>B1 one</p><p>B1 two</p>'
              '</td></tr><tr><td>A2</td><td>B2</td></tr></table>'
              '<div style="border:1px solid red;margin:10px">In a box<table><tr><td>nested'
              '</td></tr></table></div><p>After <img src="x.png" width="50" height="50"> end</p>')


def _text_box(page, text="Before the table."):
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import TextItem
    t = TextItem(300, 300)
    t.set_geometry(Geo(20, 20, 300, 300, 0))
    page.addItem(t)
    t.document.setPlainText(text)
    return t


def _assert_story_model(doc):
    from test_richtext import assert_story_model
    assert_story_model(doc)
    assert "￼" not in doc.toPlainText()


def test_pasted_tables_frames_and_pictures_become_story_text(qapp, page):
    """C1: rich text from Word or a browser must not bring in structures the
    layout can't draw."""
    t = _text_box(page)
    c = QTextCursor(t.document)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertHtml(TABLE_HTML)
    _assert_story_model(t.document)
    blocks = []
    b = t.document.begin()
    while b.isValid():
        blocks.append(b.text())
        b = b.next()
    assert blocks[0] == "Before the table."
    assert blocks[1] == "Cell A1\tB1 one B1 two"              # one row, one paragraph
    assert blocks[2] == "A2\tB2"
    assert "In a box" in blocks and "nested" in blocks
    assert blocks[-1].replace("  ", " ") == "After end"
    bold = t.document.find("A1").charFormat().fontWeight()
    assert bold >= 700                                              # formatting kept


def test_pasting_in_the_editor_flattens(window):
    from PyQt6.QtCore import QEvent, QMimeData
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    t = _text_box(window.scene, "x")
    md = QMimeData()
    md.setHtml(TABLE_HTML)
    md.setText("plain")
    QApplication.clipboard().setMimeData(md)
    t.begin_edit()
    t.text_child().keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                                           Qt.KeyboardModifier.ControlModifier, "v"))
    _assert_story_model(t.document)
    assert "B1 one" in t.plain_text()
    t.end_edit()
    window.doc.undo_stack.undo()
    assert t.plain_text() == "x"


def test_old_file_with_a_table_is_flattened_on_load(qapp, tmp_path):
    from dtp_publisher.document import Document
    from dtp_publisher.export import export_pdf
    from dtp_publisher.serialize import document_to_dict, document_from_dict, load_document, \
        save_document
    d = Document()
    d.add_page(d.make_page())
    data = document_to_dict(d)
    data["pages"][0]["items"] = [{"kind": "text", "x": 10, "y": 10, "w": 300, "h": 300,
                                  "html": "<p>Intro</p>" + TABLE_HTML}]
    doc, _ = document_from_dict(data)
    (t,) = doc.text_items()
    _assert_story_model(t.document)
    p = str(tmp_path / "t.dtpub")
    save_document(doc, p)
    assert "<table" not in open(p, encoding="utf-8").read()
    again, _ = load_document(p)
    assert again.text_items()[0].plain_text() == t.plain_text()
    export_pdf(again, str(tmp_path / "t.pdf"))
    assert (tmp_path / "t.pdf").stat().st_size > 1000


def test_document_size_signal_once_per_change(qapp):
    """C3: one documentSizeChanged per real size change, none when unchanged."""
    d = _doc("<p>one</p>", 200, True)
    seen = []
    d.documentLayout().documentSizeChanged.connect(lambda s: seen.append(s))
    c = QTextCursor(d)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertBlock()                             # one line taller: one signal
    assert len(seen) == 1
    c.insertText("two")                         # same size: none
    assert len(seen) == 1
    c.insertBlock()
    c.insertText("three")
    assert len(seen) == 2


def test_width_shrinks_when_the_widest_paragraph_does(qapp):
    """C4: the width used to be a running maximum, so it never shrank."""
    html = "<p>short</p><pre>" + "x" * 120 + "</pre><p>" + "word " * 60 + "</p>"
    a, b = _doc(html, 160, False), _doc(html, 160, True)
    assert b.size().width() > 500
    sizes = []
    b.documentLayout().documentSizeChanged.connect(lambda sz: sizes.append(sz.width()))
    for d in (a, b):
        c = QTextCursor(d.findBlockByNumber(1))
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        c.insertText("y")
    assert b.size() == a.size() and b.size().width() == 160
    assert sizes and sizes[-1] == 160                # listeners are told it shrank
    for d in (a, b):
        QTextCursor(d.findBlockByNumber(1)).insertText("z" * 200)
    assert b.size() == a.size()


# ── wrap torture: random obstacles must never be overlapped or lose text ───
def _check_invariants(d, regions, tops):
    """Every character laid out once, in order; no line over an obstacle; every
    line inside its region's width."""
    b = d.begin()
    expected = 0
    while b.isValid():
        tl = b.layout()
        pos = 0
        for i in range(tl.lineCount()):
            ln = tl.lineAt(i)
            assert ln.textStart() == pos
            pos += ln.textLength()
            top = tl.position().y() + ln.y()
            k = max(i for i in range(len(tops)) if tops[i] <= top + 0.01)
            reg = regions[k]
            rect = QRectF(ln.x(), top - tops[k], ln.width(), ln.height())
            assert rect.left() >= -0.01 and rect.right() <= reg.width + 0.01
            for e in reg.exclusions:
                assert not rect.intersected(e).isValid() or \
                    rect.intersected(e).width() < 0.02 or rect.intersected(e).height() < 0.02, \
                    (rect, e)
        assert pos == b.length() - 1
        expected += b.length()
        b = b.next()
    assert expected == d.characterCount()


@pytest.mark.parametrize("seed", range(400))
def test_random_obstacles_never_overlapped_never_lose_text(qapp, seed):
    import time
    from dtp_publisher.items.flowlayout import INF, Region
    r = random.Random(seed)
    rtl = seed % 4 == 3
    words = ["שלום", "עולם"] if rtl else \
        ["village", "fete", "raised", "more", "than", "ever", "this", "year"]
    html = "".join(f'<p{" dir=rtl" if rtl else ""}>' + " ".join(r.choice(words) for _ in range(
        r.randrange(10, 80))) + "</p>" for _ in range(r.randrange(1, 5)))
    d = _doc(html, 300, True)
    regions = []
    for k in range(r.randrange(1, 4)):
        w = r.uniform(120, 360)
        holes = []
        for _ in range(r.randrange(0, 6)):
            kind = r.random()
            x, y = r.uniform(-20, w), r.uniform(-10, 300)
            if kind < 0.2 and holes:                     # touching the previous one
                p = holes[-1]
                x, y = p.right(), p.top()
            holes.append(QRectF(x, y, r.uniform(10, w * 0.8), r.uniform(8, 120)))
        last = k == 2 or r.random() < 0.4
        regions.append(Region(w, INF if last else r.uniform(80, 300), holes))
        if last:
            break
    lay = d.documentLayout()
    t0 = time.perf_counter()
    lay.set_regions(regions)
    assert time.perf_counter() - t0 < 2.0
    _check_invariants(d, lay.regions(), lay.region_tops())


def test_right_to_left_text_takes_the_right_hand_gap(qapp):
    from dtp_publisher.items.flowlayout import INF, Region
    hole = QRectF(130, 0, 40, 200)               # two equal 130 pt gaps
    for direction, expect_right in (("ltr", False), ("rtl", True)):
        d = _doc(f'<p dir="{direction}">' + "שלום " * 40 + "</p>", 300, True)
        d.documentLayout().set_regions([Region(300, INF, [hole])])
        first = d.begin().layout().lineAt(0)
        assert (first.x() >= hole.right() - 0.01) == expect_right, direction


def test_rotated_picture_and_obstacles_per_linked_box(qapp, page):
    """Each linked box flows round its own obstacles; a rotated picture is
    avoided by its rotated outline's bounds."""
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import ImageItem, TextItem
    from dtp_publisher.textflow import connect
    a, b = TextItem(250, 300), TextItem(180, 300)
    a.set_geometry(Geo(20, 20, 250, 300, 0))
    b.set_geometry(Geo(300, 20, 180, 300, 0))
    for t in (a, b):
        t.setZValue(1)
        page.addItem(t)
    a.document.setPlainText("The village fete raised more than ever this year. " * 40)
    connect(a, b, merge_text=False)
    p1, p2 = ImageItem(100, 60), ImageItem(80, 80)
    p1.set_geometry(Geo(120, 80, 100, 60, 30))       # rotated 30 degrees, over box a
    p2.set_geometry(Geo(340, 150, 80, 80, 0))        # over box b
    for p in (p1, p2):
        p.setZValue(5)
        page.addItem(p)
    page.wrap_dirty()
    page.flush_wrap()
    shown = []
    for t in (a, b):                         # lines each box actually shows
        lo, hi = t._slice
        shown += [t._ti.mapRectToScene(r) for r in _lines(a.document)
                  if r.top() >= lo - 0.01 and r.bottom() <= hi + 0.01]
    assert len(shown) > 20
    for pic in (p1, p2):
        box = pic.scene_box()                # bounds of the (rotated) outline
        beside = [l for l in shown if l.bottom() > box.top() and l.top() < box.bottom()]
        assert beside, pic                   # text really does run alongside it
        assert not any(l.intersected(box).width() > 0.5 for l in beside), pic



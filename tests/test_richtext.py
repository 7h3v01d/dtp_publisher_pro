# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""The story model (items/richtext.py): whatever comes in - pasted from Word or
a browser, typed, or loaded from an old file - a text box ends up holding only
paragraphs and character formatting.  No input path may leave a frame, table
or inline object behind (5.2.3 review D1/D2)."""

import re
import subprocess
import sys
import textwrap

import pytest
from PyQt6.QtCore import QEvent, QMimeData, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor, QTextDocument

from dtp_publisher.items import richtext


def assert_story_model(doc: QTextDocument):
    """The invariant itself, checked independently of richtext's own test."""
    assert doc.rootFrame().childFrames() == [], "a frame or table survived"
    b = doc.begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            assert not fmt.isImageFormat(), f"picture left in {b.text()!r}"
            assert not fmt.objectType(), f"object left in {b.text()!r}"
            it += 1
        b = b.next()
    assert richtext.in_story_model(doc)


def _words(html: str) -> set:
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return set(re.findall(r"[A-Za-z]{3,}", text))


def _blocks(doc):
    out, b = [], doc.begin()
    while b.isValid():
        out.append(b.text())
        b = b.next()
    return out


def _flat(html):
    d = QTextDocument()
    d.setHtml(html)
    richtext.flatten(d)
    return d


WORD_HTML = """<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta name=Generator
content="Microsoft Word 15"><style><!-- p.MsoNormal {margin:0cm; font-family:Calibri}
--></style><!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View>
</w:WordDocument></xml><![endif]--></head><body lang=EN-AU><div class=WordSection1>
<p class=MsoNormal><b><span style='font-size:16pt'>Church Fete Roster<o:p></o:p></span></b></p>
<table class=MsoTableGrid border=1 cellspacing=0 cellpadding=0>
 <tr><td width=200 valign=top><p class=MsoNormal>Saturday<o:p></o:p></p>
  <p class=MsoNormal>Morning<o:p></o:p></p><p class=MsoNormal>Early<o:p></o:p></p></td>
  <td width=200 rowspan=2><p class=MsoNormal>Cakes stall</p></td></tr>
 <tr><td><table border=1><tr><td>Helpers</td><td>Volunteers</td></tr></table>
  <p class=MsoNormal>Afternoon</p></td></tr>
 <tr><td colspan=2><p class=MsoNormal>Raffle drawn at closing</p></td></tr>
</table>
<p class=MsoListParagraph style='mso-list:l0 level1 lfo1'><![if !supportLists]>1.<![endif]>Bring
chairs</p>
<p class=MsoNormal><!--[if gte vml 1]><v:shape id="Picture_1" style='width:100pt'>
<v:imagedata src="file:///C:/Users/x/AppData/Local/Temp/msohtmlclip1/01/clip_image001.png"/>
</v:shape><![endif]--><![if !vml]><img width=133 height=100
src="file:///C:/Users/x/AppData/Local/Temp/msohtmlclip1/01/clip_image002.jpg"><![endif]>Map
below</p></div></body></html>"""

BROWSER_HTML = """<meta charset='utf-8'><article><header><h1>Garden Club News</h1></header>
<section><p>Welcome to <em>spring</em>, with <a href="https://example.org">photos</a>
<img src="https://example.org/rose.jpg" alt="rose" style="float:right"> of roses.</p>
<figure><img src="tulip.png"><figcaption>Tulips beside fountain</figcaption></figure>
<div style="border:2px solid green;padding:8px"><div style="background:#eef">
<p>Nested notice boxes</p><table><thead><tr><th>Month</th><th>Speaker</th></tr></thead>
<tbody><tr><td>April</td><td>Compost <img src="c.gif"> expert</td></tr></tbody></table>
</div></div><ul><li>Pruning<ul><li>Roses</li><li>Hedges</li></ul></li></ul>
<blockquote>Gardening adds years</blockquote><hr><pre>Plots   available</pre>
</section></article>"""

DEEP_HTML = ("<div style='border:1px solid'>" * 40 + "<table><tr><td>Top" +
             "<table><tr><td>Inner" * 30 + " Deepest" + "</td></tr></table>Tail" * 30 +
             "</td></tr></table>" + "</div>" * 40)

MANY_TABLES = "".join(f"<table><tr><td><b>Name{i:03d}</b></td><td>Phone</td></tr></table>"
                      for i in range(100))

CORPUS = {"word": WORD_HTML, "browser": BROWSER_HTML, "deep": DEEP_HTML,
          "hundred_tables": MANY_TABLES}


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_insert_html_ends_in_the_story_model(qapp, name):
    html = CORPUS[name]
    d = QTextDocument()
    d.setPlainText("Start")
    c = QTextCursor(d)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertHtml(html)
    richtext.flatten(d)
    assert_story_model(d)
    text = d.toPlainText()
    missing = {w for w in _words(html) if w not in text}
    assert not missing, missing


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_paste_in_the_editor_ends_in_the_story_model(window, name):
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import TextItem
    t = TextItem(300, 300)
    t.set_geometry(Geo(20, 20, 300, 300, 0))
    window.doc.pages[0].addItem(t)
    t.document.setPlainText("x")
    md = QMimeData()
    md.setHtml(CORPUS[name])
    md.setText("plain")
    from PyQt6.QtWidgets import QApplication
    QApplication.clipboard().setMimeData(md)
    t.begin_edit()
    t.text_child().keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                                           Qt.KeyboardModifier.ControlModifier, "v"))
    assert_story_model(t.document)
    t.end_edit()
    window.doc.undo_stack.undo()
    assert t.plain_text() == "x"


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_old_file_ends_in_the_story_model(qapp, tmp_path, name):
    from dtp_publisher.document import Document
    from dtp_publisher.serialize import document_from_dict, document_to_dict, load_document, \
        save_document
    d = Document()
    d.add_page(d.make_page())
    data = document_to_dict(d)
    data["pages"][0]["items"] = [{"kind": "text", "x": 10, "y": 10, "w": 300, "h": 300,
                                  "html": CORPUS[name]}]
    doc, _ = document_from_dict(data)
    (t,) = doc.text_items()
    assert_story_model(t.document)
    p = str(tmp_path / "t.dtpub")
    save_document(doc, p)
    again, _ = load_document(p)
    assert_story_model(again.text_items()[0].document)


def test_a_hundred_tables_keep_their_formatting(qapp):
    """D1: 5.2.2 stopped after 64 frames and left the 65th table onwards in place."""
    d = _flat(MANY_TABLES)
    assert_story_model(d)
    rows = [b for b in _blocks(d) if b]
    assert rows[0] == "Name000\tPhone" and rows[-1] == "Name099\tPhone"
    assert d.find("Name099").charFormat().fontWeight() >= 700     # converted, not stripped


def test_cell_with_text_round_a_nested_table_does_not_crash(qapp, tmp_path):
    """Asking Qt for a table cell's extent while the cell still holds another
    table (with text beside it) crashes Qt; 5.2.2 did exactly that.  Run in a
    separate process so a regression fails this test, not the whole run."""
    script = tmp_path / "nested.py"
    script.write_text(textwrap.dedent("""
        import sys
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QTextDocument
        app = QApplication(sys.argv[:1])
        from dtp_publisher.items import richtext
        d = QTextDocument()
        d.setHtml('a<table><tr><td>p<table><tr><td>x</td></tr></table>q</td>'
                  '<td>w</td></tr></table>b')
        richtext.flatten(d)
        b, out = d.begin(), []
        while b.isValid():
            out.append(b.text())
            b = b.next()
        print(repr(out))
    """))
    import os
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    src = str(__import__("pathlib").Path(richtext.__file__).parents[2])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       env=env, timeout=120)
    assert r.returncode == 0, f"crashed ({r.returncode}): {r.stderr[-500:]}"
    assert r.stdout.strip() == repr(["a", "p\u2028x\u2028q\tw", "b"])


def test_every_paragraph_of_a_cell_joins_its_row(qapp):
    """A cell's paragraphs become one row; 5.2.2 joined only the last two."""
    d = _flat("<table><tr><td><p>one</p><p>two</p><p>three</p><p>four</p></td>"
              "<td>B</td></tr></table>")
    assert [b for b in _blocks(d) if b] == ["one\u2028two\u2028three\u2028four\tB"]


def test_over_the_structure_budget_falls_back_to_plain_text(qapp, monkeypatch):
    """D1: past the budget, flatten must still not return unsupported frames."""
    monkeypatch.setattr(richtext, "MAX_RICH_STRUCTURES", 5)
    d = _flat(MANY_TABLES)
    assert_story_model(d)
    text = d.toPlainText()
    assert "Name000" in text and "Name099" in text


def test_over_the_picture_budget_falls_back_to_plain_text(qapp, monkeypatch):
    """D2: past the inline-picture budget, none may be left behind."""
    monkeypatch.setattr(richtext, "MAX_INLINE_OBJECTS", 5)
    d = _flat("<p>Photos" + '<img src="a.png"> here' * 12 + "</p>")
    assert_story_model(d)
    assert d.toPlainText().count("here") == 12


def test_a_typed_object_character_is_left_alone(qapp):
    """U+FFFC typed as ordinary text is not a picture."""
    d = QTextDocument()
    d.setPlainText("odd \ufffc char")
    assert richtext.in_story_model(d)
    assert richtext.flatten(d) is False
    assert d.toPlainText() == "odd \ufffc char"


def test_flatten_is_one_undo_step(qapp):
    d = QTextDocument()
    d.setPlainText("Start")
    c = QTextCursor(d)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertHtml(MANY_TABLES)
    richtext.flatten(d)
    assert_story_model(d)
    d.undo()                                    # the flatten
    assert d.rootFrame().childFrames()          # back to the tables as pasted
    d.undo()                                    # the paste
    assert d.toPlainText() == "Start"


def test_large_pastes_stay_quick(qapp):
    import time
    html = "".join(f"<table><tr><td><b>c{i}</b></td><td>d</td></tr></table>"
                   for i in range(richtext.MAX_RICH_STRUCTURES))
    d = QTextDocument()
    d.setHtml(html)
    t = time.perf_counter()
    richtext.flatten(d)
    assert time.perf_counter() - t < 5.0        # ~0.25 s here; 6 s before one edit block
    assert_story_model(d)


def test_joining_paragraphs_never_merges_into_a_table(qapp):
    """Defence in depth: the join only replaces real paragraph breaks, never
    the edge of a table (merging those corrupted the table and crashed Qt)."""
    d = QTextDocument()
    d.setHtml("<p>one</p><p>two</p><table><tr><td>in</td><td>side</td></tr></table><p>after</p>")
    richtext._join_blocks(d, 0, d.characterCount() - 1)
    (t,) = d.rootFrame().childFrames()
    cell = t.cellAt(0, 1)
    c = QTextCursor(d)
    c.setPosition(cell.firstCursorPosition().position())
    c.setPosition(cell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
    assert c.selectedText() == "side"
    assert _blocks(d)[:2] == ["one", "two"]    # stopped at the table's edge

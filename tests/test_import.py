# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Publisher import: ODG rebuild, metafile pictures, paths, label sheets.

Everything here runs on synthetic data.  Real Publisher files are only used
when DTP_PUB_SAMPLES points at a folder of them (they are never committed:
they hold people's names and addresses).
"""

import os
import re
import shutil
import struct
import zipfile

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor

ODF_NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
          'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
          'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
          'xmlns:xlink="http://www.w3.org/1999/xlink"')

STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {ODF_NS}>
 <office:styles>
  <draw:gradient draw:name="g1" draw:style="linear" draw:start-color="#ff0000"
                 draw:end-color="#0000ff" draw:angle="900"/>
  <draw:opacity draw:name="o1" draw:start="40%" draw:end="40%"/>
 </office:styles>
 <office:automatic-styles>
  <style:page-layout style:name="PM1">
   <style:page-layout-properties fo:page-width="200mm" fo:page-height="100mm"/>
  </style:page-layout>
 </office:automatic-styles>
 <office:master-styles>
  <style:master-page style:name="Default" style:page-layout-name="PM1">
   <draw:rect draw:style-name="red" svg:x="0mm" svg:y="0mm" svg:width="200mm" svg:height="5mm"/>
  </style:master-page>
 </office:master-styles>
</office:document-styles>"""

LONG = ("Grandad wrote this story about the long walk up the hill to the old church, where the "
        "whole family met for tea and cake after the harvest festival, and then we all went")


def _content(frames: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {ODF_NS}>
 <office:automatic-styles>
  <style:style style:name="red" style:family="graphic">
   <style:graphic-properties draw:fill="solid" draw:fill-color="#ff0000" draw:stroke="none"/>
  </style:style>
  <style:style style:name="grad" style:family="graphic">
   <style:graphic-properties draw:fill="gradient" draw:fill-gradient-name="g1"
                             draw:opacity-name="o1" draw:stroke="none"/>
  </style:style>
  <style:style style:name="box" style:family="graphic">
   <style:graphic-properties draw:fill="none" draw:stroke="none" fo:min-height="20mm"/>
  </style:style>
  <style:style style:name="dp1" style:family="drawing-page">
   <style:drawing-page-properties draw:fill="solid" draw:fill-color="#ffffcc"/>
  </style:style>
  <style:style style:name="P1" style:family="paragraph">
   <style:text-properties fo:font-weight="bold" fo:font-size="18pt"/>
  </style:style>
 </office:automatic-styles>
 <office:body><office:drawing>
  <draw:page draw:name="p1" draw:master-page-name="Default" draw:style-name="dp1">
{frames}
  </draw:page>
 </office:drawing></office:body>
</office:document-content>"""


def _frame(x, y, w, h, text, style="box", pstyle=""):
    ps = f' text:style-name="{pstyle}"' if pstyle else ""
    return (f'<draw:frame draw:style-name="{style}" svg:x="{x}mm" svg:y="{y}mm" '
            f'svg:width="{w}mm" svg:height="{h}mm"><draw:text-box>'
            f'<text:p{ps}>{text}</text:p></draw:text-box></draw:frame>')


def make_odg(path, frames: str) -> str:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.graphics")
        z.writestr("content.xml", _content(frames))
        z.writestr("styles.xml", STYLES)
    return str(path)


def _texts(doc):
    from dtp_publisher.items import TextItem
    out = [it for sc in doc.pages for it in sc.items() if isinstance(it, TextItem)]
    return sorted(out, key=lambda t: (t.geometry().x, t.geometry().y))


# ── ODG → document ──────────────────────────────────────────────────────────
def test_odg_builds_page_master_background_text_and_shapes(qapp, tmp_path):
    from dtp_publisher.importers.odg import import_odg
    from dtp_publisher.items import PathItem, ShapeItem
    from dtp_publisher.units import mm
    frames = (_frame(10, 10, 80, 15, "Hello <text:span>world</text:span>", pstyle="P1")
              + '<draw:rect draw:style-name="grad" svg:x="100mm" svg:y="10mm" '
                'svg:width="50mm" svg:height="30mm"/>')
    doc, rep = import_odg(make_odg(tmp_path / "a.odg", frames))
    assert rep.pages == len(doc.pages) == 1
    sc = doc.pages[0]
    assert sc.page_w == pytest.approx(mm(200), abs=0.01)
    assert sc.page_h == pytest.approx(mm(100), abs=0.01)
    assert QColor(sc.setup_state()["background"]).name() == "#ffffcc"
    (t,) = _texts(doc)
    assert t.plain_text() == "Hello world"
    cf = t.document.begin().begin().fragment().charFormat()
    assert cf.fontPointSize() == 18 and cf.fontWeight() >= 700
    master = [it for it in sc.items() if isinstance(it, ShapeItem)]
    assert len(master) == 1 and master[0].locked and master[0].fill.name() == "#ff0000"
    (grad,) = [it for it in sc.items() if isinstance(it, PathItem)]
    assert grad.fill.name() == "#ff0000" and grad.fill2.name() == "#0000ff"
    # the opacity gradient must be honoured, or it hides whatever is underneath
    assert grad.fill.alphaF() == pytest.approx(0.4, abs=0.02)
    assert grad.fill2.alphaF() == pytest.approx(0.4, abs=0.02)
    assert not rep.warnings


def test_odg_relinks_duplicated_story_and_restores_box_heights(qapp, tmp_path):
    """libmspub gives every box of a linked story the whole story."""
    from dtp_publisher.importers.odg import import_odg
    from dtp_publisher.units import mm
    story = LONG + " home."
    frames = (_frame(10, 10, 60, 70, story) + _frame(80, 10, 60, 70, story)
              + _frame(10, 70, 60, 25, "A caption long enough to group"))
    doc, rep = import_odg(make_odg(tmp_path / "b.odg", frames))
    a, cap, b = _texts(doc)
    assert rep.stories == 1
    assert a.link_next is b and b.link_prev is a
    assert a.chain_root().document.toPlainText().count("Grandad") == 1
    assert a.geometry().h == pytest.approx(mm(20), abs=0.1)    # Publisher's own height
    assert b.geometry().h == pytest.approx(mm(20), abs=0.1)
    # a box that is not linked keeps the height LibreOffice gave it
    assert cap.geometry().h == pytest.approx(mm(25), abs=0.1)
    assert not cap.is_linked()


def test_odg_joins_split_story_to_same_width_box(qapp, tmp_path):
    from dtp_publisher.importers.odg import import_odg
    frames = (_frame(10, 10, 60, 40, LONG)
              # earlier in reading order but a different width: not the continuation
              + _frame(10, 60, 150, 10, "lowercase address line, 1997")
              + _frame(80, 10, 60, 40, "on to the pub for a sing-song."))
    doc, rep = import_odg(make_odg(tmp_path / "c.odg", frames))
    first, wide, cont = _texts(doc)
    assert first.link_next is cont
    assert not wide.is_linked()
    assert first.document.toPlainText() == LONG + "on to the pub for a sing-song."
    assert rep.stories == 1


def test_odg_rejects_files_without_content(qapp, tmp_path):
    from dtp_publisher.importers.odg import import_odg
    p = tmp_path / "bad.odg"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "x")
    with pytest.raises(ValueError):
        import_odg(str(p))


def test_odg_angles_and_lengths():
    from dtp_publisher.importers.odg import angle_deg, length, percent
    assert angle_deg("900") == 90 and angle_deg("45deg") == 45
    assert length("1in") == 72 and length("10%") is None and length("junk") is None
    assert percent("40%") == pytest.approx(0.4)


# ── metafile pictures ───────────────────────────────────────────────────────
def _dib_2x2_red() -> bytes:
    hdr = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 2835, 2835, 0, 0)
    row = bytes([0, 0, 255, 0, 0, 255, 0, 0])            # BGR BGR + padding
    return hdr + row * 2


def _wmf(records) -> bytes:
    body = b""
    for fn, params in records + [(0, b"")]:
        body += struct.pack("<IH", (6 + len(params)) // 2, fn) + params
    total = (18 + len(body)) // 2
    return struct.pack("<HHHIHIH", 1, 9, 0x300, total, 0, 64, 0) + body


def test_wmf_photo_with_escape_record_is_unwrapped_as_bitmap(qapp):
    """Publisher puts a META_ESCAPE (0x0626) before its photos: not vector art."""
    from dtp_publisher.importers.metafile import metafile_to_image
    stretch = struct.pack("<IHhhhhhhhhh", 0x00CC0020, 0, 2, 2, 0, 0, 2, 2, 0, 0, 0)[:22]
    data = _wmf([(0x0626, b"\x0f\x00\x00\x00"), (0x0F43, stretch + _dib_2x2_red())])
    img, kind = metafile_to_image(data)
    assert kind == "bitmap"
    assert (img.width(), img.height()) == (2, 2)
    assert QColor(img.pixel(0, 0)).name() == "#ff0000"


def test_wmf_vector_rectangle_is_drawn(qapp):
    from dtp_publisher.importers.metafile import metafile_to_image
    recs = [(0x020B, struct.pack("<hh", 0, 0)), (0x020C, struct.pack("<hh", 100, 100)),
            (0x041B, struct.pack("<hhhh", 90, 90, 10, 10))]
    img, kind = metafile_to_image(_wmf(recs))
    assert kind == "vector" and img is not None
    assert QColor.fromRgba(img.pixel(img.width() // 2, img.height() // 2)).alpha() > 0
    assert QColor.fromRgba(img.pixel(2, 2)).alpha() == 0


@pytest.mark.parametrize("junk", [b"", b"\x01" * 5, b"\xd7\xcd\xc6\x9a" + b"\xff" * 40,
                                  b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\xff" * 20])
def test_metafile_survives_junk(qapp, junk):
    from dtp_publisher.importers.metafile import metafile_to_image
    img, kind = metafile_to_image(junk)
    assert img is None and kind == ""


# ── vector paths ────────────────────────────────────────────────────────────
def test_svg_path_parser_and_roundtrip(qapp):
    from dtp_publisher.items.path import parse_svg_path, path_to_svg
    p = parse_svg_path("M0 0 h1 v1 H0 z m0.25 0.25 c0 .1 .1 .2 .2 .2 s.1 0 .1 -.1 "
                       "q.1 .1 .2 0 t.1 0 a.1 .1 0 0 1 .1 .1")
    r = p.boundingRect()
    assert r.left() == pytest.approx(0) and r.width() == pytest.approx(1, abs=0.01)
    again = parse_svg_path(path_to_svg(p))
    assert again.elementCount() == p.elementCount()
    assert parse_svg_path("M0 0 L").elementCount() == 1          # truncated data is safe
    assert parse_svg_path("garbage").isEmpty()


def test_path_item_saves_and_loads(qapp, doc):
    from dtp_publisher.items import PathItem
    from dtp_publisher.serialize import item_from_dict, item_to_dict
    it = PathItem(50, 20, "M0 0L1 0L0.5 1Z")
    it.fill2 = QColor("#00ff00")
    it.grad_angle = 45
    back = item_from_dict(item_to_dict(it))
    assert isinstance(back, PathItem)
    assert back.d == it.d and back.fill2.name() == "#00ff00" and back.grad_angle == 45
    assert back.path().boundingRect().width() == pytest.approx(50)


# ── label sheets ────────────────────────────────────────────────────────────
def test_label_detect_and_plan():
    from dtp_publisher import labels
    from dtp_publisher.units import mm
    lay = labels.detect(mm(38.1), mm(21.2))
    assert lay.key == "L7651" and lay.per_sheet == 65
    assert labels.detect(mm(21.2), mm(38.1)).key == "L7651"     # either way round
    assert labels.detect(mm(50), mm(50)) is None
    cells = labels.cells(lay)
    assert len(cells) == 65
    assert cells[1].left() - cells[0].left() == pytest.approx(mm(40.6))
    assert cells[5].top() - cells[0].top() == pytest.approx(mm(21.2))
    assert cells[-1].bottom() <= mm(297)
    seq = labels.plan(70, lay, "sequence")
    assert len(seq) == 2 and seq[1][:5] == [65, 66, 67, 68, 69] and seq[1][5] == -1
    assert labels.plan(3, lay, "copies") == [[0] * 65, [1] * 65, [2] * 65]
    d = labels.to_dict(lay, "sequence")
    assert labels.from_dict(d) == lay and d["mode"] == "sequence"
    assert labels.from_dict({"key": "x"}) is None
    assert labels.from_dict({**d, "cols": 10**9}).cols == 50     # clamped


def test_label_sheet_pdf_has_one_page_per_sheet(qapp, doc, tmp_path):
    from dtp_publisher import labels
    from dtp_publisher.export import export_pdf
    lay = labels.PRESET_BY_KEY["L7160"]          # 21 per sheet
    for _ in range(2):
        doc.add_page(doc.make_page())
    doc.sheet = labels.to_dict(lay, "copies")
    out = tmp_path / "s.pdf"
    assert export_pdf(doc, str(out)) == 3
    doc.sheet = labels.to_dict(lay, "sequence")
    assert export_pdf(doc, str(out)) == 1
    raw = out.read_bytes()
    assert len(re.findall(rb"/Type\s*/Page[^s]", raw)) == 1
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", raw)
    assert float(m.group(1)) == pytest.approx(595.3, abs=1)     # A4 paper, not label size


def test_sheet_setting_undo_and_save(qapp, doc, tmp_path):
    from dtp_publisher import labels
    from dtp_publisher.commands import SheetCmd
    from dtp_publisher.serialize import load_document, save_document
    new = labels.to_dict(labels.PRESETS[0])
    doc.undo_stack.push(SheetCmd(doc, None, new))
    assert doc.sheet == new
    p = str(tmp_path / "l.dtpub")
    save_document(doc, p)
    assert load_document(p)[0].sheet == new
    doc.undo_stack.undo()
    assert doc.sheet is None


def test_page_setup_dialog_sheet_choice(qapp):
    from dtp_publisher.document import Document
    from dtp_publisher.ui.dialogs.page_setup import PageSetupDialog
    from dtp_publisher.units import mm
    d = Document()
    sc = d.make_page(mm(38.1), mm(21.2))
    dlg = PageSetupDialog(sc.setup_state(), "mm", False, None, sheet=None)
    assert dlg.result_sheet() is None
    assert dlg.cmb_sheet.currentData() == "L7651"           # guessed from the page size
    dlg.cb_sheet.setChecked(True)
    dlg.cmb_sheet.setCurrentIndex(dlg.cmb_sheet.findData("L7160"))
    st = dlg.result_state(sc.setup_state())
    assert st["width"] == pytest.approx(mm(63.5), abs=0.1)  # page follows the label size
    assert dlg.result_sheet()["key"] == "L7160"
    dlg.deleteLater()


# ── finding LibreOffice / converting ────────────────────────────────────────
def test_find_soffice_override_and_missing(monkeypatch, tmp_path):
    from dtp_publisher.importers import libreoffice
    exe = tmp_path / "soffice.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("DTP_SOFFICE", str(exe))
    assert libreoffice.find_soffice() == str(exe)
    monkeypatch.setenv("DTP_SOFFICE", str(tmp_path / "nope"))
    monkeypatch.setattr(libreoffice, "_windows_candidates", lambda: [])
    monkeypatch.setattr(libreoffice.shutil, "which", lambda n: None)
    monkeypatch.setattr(libreoffice.sys, "platform", "linux")
    assert libreoffice.find_soffice() is None
    with pytest.raises(libreoffice.ConversionError):
        libreoffice.convert(str(exe))


def test_looks_like_pub(tmp_path):
    from dtp_publisher.importers.pub import is_pub, looks_like_pub
    p = tmp_path / "a.pub"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    assert is_pub("X.PUB") and looks_like_pub(str(p))
    p.write_bytes(b"PK")
    assert not looks_like_pub(str(p))


def test_build_from_odg_detects_label_publication(qapp, tmp_path):
    from dtp_publisher.importers.pub import build_from_odg
    odg = make_odg(tmp_path / "l.odg", _frame(1, 1, 30, 10, "Mr A Sample, 1 The Street"))
    s = open(odg.replace("l.odg", "l.odg"), "rb").read()
    # make the page the size of an L7651 mini label
    with zipfile.ZipFile(odg) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts["styles.xml"] = parts["styles.xml"].replace(b'fo:page-width="200mm" '
                                                      b'fo:page-height="100mm"',
                                                      b'fo:page-width="38.1mm" '
                                                      b'fo:page-height="21.2mm"')
    with zipfile.ZipFile(odg, "w") as z:
        for n, b in parts.items():
            z.writestr(n, b)
    assert s
    doc, rep = build_from_odg(odg, "/x/Party labels.pub")
    assert doc.title == "Party labels" and doc.path is None
    assert doc.sheet["key"] == "L7651"
    assert any("label" in w for w in rep.warnings)
    assert not doc.undo_stack.canUndo()


class _FakeConverter:
    """Stands in for PubConverter: 'converts' by copying a ready-made ODG."""
    odg = ""
    error = ""

    def __init__(self, path, parent=None):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Sig(QObject):
            converted = pyqtSignal(str)
            failed = pyqtSignal(str)
        self._s = _Sig()
        self.converted, self.failed = self._s.converted, self._s.failed

    def start(self):
        def go():
            if self.error:
                self.failed.emit(self.error)
                return
            work = os.path.join(os.path.dirname(self.odg), "work", "out")
            os.makedirs(work, exist_ok=True)
            dst = os.path.join(work, "input.odg")
            shutil.copyfile(self.odg, dst)
            self.converted.emit(dst)
        QTimer.singleShot(50, go)

    def cancel(self):
        pass

    def _stop(self):
        pass

    def deleteLater(self):
        pass


def test_window_opens_pub_through_converter(window, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from dtp_publisher.importers import pub
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append("WARN " + a[2]))
    monkeypatch.setattr(pub, "find_soffice", lambda: "/fake/soffice")
    monkeypatch.setattr(pub, "PubConverter", _FakeConverter)
    _FakeConverter.odg = make_odg(tmp_path / "x.odg", _frame(10, 10, 80, 15, "Christmas 1997"))
    _FakeConverter.error = ""
    src = tmp_path / "Xmas 97.pub"
    src.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert window.open_path(str(src)) is not False
    assert window.doc.title == "Xmas 97" and window.doc.path is None
    assert _texts(window.doc)[0].plain_text() == "Christmas 1997"
    assert not window.doc.undo_stack.isClean()          # still needs saving as .dtpub
    assert window._pub_source == str(src)
    assert not os.path.exists(tmp_path / "work")         # temp conversion removed
    assert "Opened Xmas 97.pub" in shown[-1]
    assert os.path.exists(src)                           # the original is untouched

    _FakeConverter.error = "LibreOffice could not read this file."
    before = window.doc
    window.doc.mark_saved()
    assert window.import_publisher(str(src)) is False
    assert window.doc is before and shown[-1].startswith("WARN")


def test_window_explains_missing_libreoffice(window, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QMessageBox
    from dtp_publisher.importers import pub
    seen = []
    monkeypatch.setattr(pub, "find_soffice", lambda: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: seen.append(self.text()) or 0)
    assert window.import_publisher(str(tmp_path / "a.pub")) is False
    assert "LibreOffice" in seen[0]


# ── real Publisher files (only when provided locally) ───────────────────────
SAMPLES = os.environ.get("DTP_PUB_SAMPLES", "")


@pytest.mark.skipif(not (SAMPLES and os.path.isdir(SAMPLES)),
                    reason="set DTP_PUB_SAMPLES to a folder of .pub files")
def test_real_publisher_samples(qapp):
    from dtp_publisher.importers.libreoffice import find_soffice
    from dtp_publisher.importers.pub import import_pub_blocking
    from dtp_publisher.serialize import document_from_dict, document_to_dict
    if not find_soffice():
        pytest.skip("LibreOffice is not installed")
    files = sorted(f for f in os.listdir(SAMPLES) if f.lower().endswith(".pub"))
    assert files
    for f in files:
        doc, rep = import_pub_blocking(os.path.join(SAMPLES, f))
        assert doc.pages and rep.texts + rep.pictures + rep.shapes > 0, f
        again = document_from_dict(document_to_dict(doc))
        again = again[0] if isinstance(again, tuple) else again
        assert len(again.pages) == len(doc.pages), f



@pytest.mark.skipif(not (SAMPLES and os.path.isdir(SAMPLES)),
                    reason="set DTP_PUB_SAMPLES to a folder of .pub files")
def test_real_publisher_text_lays_out_exactly_as_qt(qapp):
    """The text of real publications, laid out and drawn (with selections) by
    FlowLayout and by Qt's own layout, must match pixel for pixel."""
    import random
    from test_flowlayout import _doc, _dump, _render
    from dtp_publisher.importers.libreoffice import find_soffice
    from dtp_publisher.importers.pub import import_pub_blocking
    if not find_soffice():
        pytest.skip("LibreOffice is not installed")
    r = random.Random(1)
    for f in sorted(f for f in os.listdir(SAMPLES) if f.lower().endswith(".pub")):
        doc, _ = import_pub_blocking(os.path.join(SAMPLES, f))
        for it in doc.text_items():
            if it.is_linked() and not it.writes_story():
                continue
            html, w = it.document.toHtml(), it.inner_rect().width()
            a, b = _doc(html, w, False), _doc(html, w, True)
            assert _dump(a) == _dump(b), f
            n = a.characterCount()
            if "<li" not in html:
                sel = sorted((r.randrange(n), r.randrange(n)))
                assert _render(a, -1, sel) == _render(b, -1, sel), (f, sel)


@pytest.mark.skipif(not (SAMPLES and os.path.isdir(SAMPLES)),
                    reason="set DTP_PUB_SAMPLES to a folder of .pub files")
def test_real_publisher_round_trip(qapp, tmp_path):
    """.pub -> import -> save .dtpub -> reopen -> PDF, with the text and pictures
    surviving every step."""
    from dtp_publisher.export import export_pdf
    from dtp_publisher.importers.libreoffice import find_soffice
    from dtp_publisher.importers.pub import import_pub_blocking
    from dtp_publisher.serialize import load_document, save_document
    if not find_soffice():
        pytest.skip("LibreOffice is not installed")
    for f in sorted(f for f in os.listdir(SAMPLES) if f.lower().endswith(".pub")):
        doc, _ = import_pub_blocking(os.path.join(SAMPLES, f))
        text = sorted(t.plain_text() for t in doc.text_items() if t.writes_story())
        pics = sum(1 for sc in doc.pages for i in sc.all_design_items() if i.KIND == "image"
                   and i.has_image())
        p = str(tmp_path / (f + ".dtpub"))
        save_document(doc, p)
        again, warnings = load_document(p)
        assert not warnings, (f, warnings)
        assert sorted(t.plain_text() for t in again.text_items() if t.writes_story()) == text
        assert sum(1 for sc in again.pages for i in sc.all_design_items()
                   if i.KIND == "image" and i.has_image()) == pics
        for t in again.text_items():
            assert t.document.rootFrame().childFrames() == []
        pdf = tmp_path / (f + ".pdf")
        assert export_pdf(again, str(pdf)) == len(again.pages) or again.sheet
        assert pdf.stat().st_size > 1000

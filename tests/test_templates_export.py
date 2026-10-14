# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Every template builds, round-trips, fits, and exports; printing path works."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtPrintSupport import QPrinter

from dtp_publisher import export, serialize, templates
from dtp_publisher.items import ImageItem, TextItem

KEYS = [t.key for t in templates.TEMPLATES]


@pytest.mark.parametrize("key", KEYS)
def test_template_roundtrips_without_warnings(qapp, key):
    doc = templates.build(key)
    assert doc.pages and not doc.is_modified()
    data = serialize.document_to_dict(doc)
    doc2, warnings = serialize.document_from_dict(data)
    assert warnings == []
    assert serialize.document_to_dict(doc2)["pages"] == data["pages"]


@pytest.mark.parametrize("key", KEYS)
def test_template_text_fits_and_items_on_page(qapp, key):
    doc = templates.build(key)
    for sc in doc.pages:
        pr = sc.page_rect().adjusted(-1, -1, 1, 1)
        for it in sc.top_items():
            assert pr.contains(it.scene_box()) or pr.intersects(it.scene_box()), it.display_name()
        for it in sc.all_design_items():
            if isinstance(it, TextItem):
                assert not it.overflow, f"{key}: {it.display_name()} overflows"


@pytest.mark.parametrize("key", ["newsletter", "card", "labels"])
def test_template_exports_pdf(qapp, key, tmp_path):
    from PyQt6.QtPdf import QPdfDocument
    doc = templates.build(key)
    p = str(tmp_path / f"{key}.pdf")
    assert export.export_pdf(doc, p) == len(doc.pages)
    pdf = QPdfDocument(None)
    pdf.load(p)
    assert pdf.pageCount() == len(doc.pages)
    for i, sc in enumerate(doc.pages):
        s = pdf.pagePointSize(i)
        assert abs(s.width() - sc.page_w) < 0.6 and abs(s.height() - sc.page_h) < 0.6


def test_empty_photo_frames_do_not_print_but_show_in_thumbnails(qapp):
    from PyQt6.QtGui import QColor
    doc = templates.blank(400, 400)
    sc = doc.pages[0]
    ph = ImageItem(200, 200)
    ph.setPos(100, 100)
    sc.addItem(ph)
    printed = export.render_page_image(sc, 72)
    assert QColor(printed.pixel(200, 200)) == QColor("white")
    thumb = export.render_thumbnail(sc, 400, 400)
    assert QColor(thumb.pixel(200, 120)) != QColor("white")


def test_print_document_to_pdf_printer(qapp, tmp_path):
    doc = templates.build("postcard")
    out = str(tmp_path / "printed.pdf")
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    pr.setOutputFileName(out)
    pr.setPageLayout(export.page_layout(doc.pages[0].page_w, doc.pages[0].page_h))
    assert export.print_document(doc, pr, [0, 1], fit_to_paper=True) == 2
    from PyQt6.QtPdf import QPdfDocument
    pdf = QPdfDocument(None)
    pdf.load(out)
    assert pdf.pageCount() == 2


def test_double_click_text_inside_group_edits_it(qapp):
    from dtp_publisher.items import GroupItem
    doc = templates.build("bizcards")
    sc = doc.pages[0]
    g = next(i for i in sc.top_items() if isinstance(i, GroupItem))
    name = next(m for m in g.members() if isinstance(m, TextItem) and "Name" in m.plain_text())

    class E:
        def scenePos(self):
            return name.mapToScene(name.rect().center())
    g.on_double_click(E())
    assert name.editing
    name.end_edit()


def test_label_sheet_prints_at_exact_size_on_matching_paper(qapp, tmp_path):
    """Labels must not be shrunk to the printable area, or they miss the sheet."""
    from PyQt6.QtCore import QMarginsF
    from PyQt6.QtGui import QColor, QPageLayout
    from dtp_publisher.items import ShapeItem
    doc = templates.blank(595.2756, 841.8898)
    sc = doc.pages[0]
    s = ShapeItem(sc.page_w, sc.page_h)
    s.fill = QColor("black")
    sc.addItem(s)
    out = str(tmp_path / "labels.pdf")
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    pr.setOutputFileName(out)
    lay = export.page_layout(sc.page_w, sc.page_h)
    lay.setMargins(QMarginsF(15, 15, 15, 15))          # a printer with 15pt margins
    pr.setPageLayout(lay)
    export.print_document(doc, pr, fit_to_paper=True)
    from PyQt6.QtCore import QSize
    from PyQt6.QtPdf import QPdfDocument
    pdf = QPdfDocument(None)
    pdf.load(out)
    img = pdf.render(0, QSize(200, 283))
    # exact size: black reaches the paper corner (it would be white if shrunk to fit)
    c = img.pixelColor(2, 2)
    assert c.alpha() > 200 and c.lightness() < 60


def test_same_size_helper():
    assert export.same_size(595, 842, 595.3, 841.9)
    assert not export.same_size(595, 842, 612, 792)


def test_pdf_photos_are_embedded_at_print_resolution(qapp, doc, page, tmp_path):
    """A 3000-pixel photo in a 150 pt frame needs 625 pixels at 300 dpi; the
    150-photo album's PDF was 323 MB before."""
    import re
    from PyQt6.QtGui import QColor, QImage
    from dtp_publisher.export import export_pdf, render_page_image
    from dtp_publisher.geometry import Geo
    from dtp_publisher.items import ImageItem
    from dtp_publisher.items.image import encode_image
    img = QImage(3000, 2250, QImage.Format.Format_RGB32)
    img.fill(QColor("#3366aa"))
    data, fmt = encode_image(img, "jpg")
    im = ImageItem(150, 112.5)
    im.set_image_data(data, fmt, "a.jpg", img)
    im.set_geometry(Geo(50, 50, 150, 112.5, 0))
    page.addItem(im)
    out = tmp_path / "p.pdf"
    export_pdf(doc, str(out))
    widths = [int(w) for w in re.findall(rb"/Width\s+(\d+)", out.read_bytes())]
    assert widths and max(widths) <= 640
    # Save as Picture keeps every pixel: 1-pixel stripes stay sharp at 600 dpi
    stripes = QImage(3000, 100, QImage.Format.Format_RGB32)
    for x in range(3000):
        for y in range(100):
            stripes.setPixel(x, y, 0xFF000000 if x % 2 else 0xFFFFFFFF)
    data, fmt = encode_image(stripes, "png")
    im.set_image_data(data, fmt, "s.png", stripes)
    im.fit_mode = "stretch"
    im.set_geometry(Geo(0, 0, 500, 300, 0))       # 4,167 px wide at 600 dpi
    big = render_page_image(page, 600)
    row = [QColor(big.pixel(x, 600)).lightness() for x in range(1000, 1100)]
    assert max(row) - min(row) > 150



def test_templates_fit_on_computers_with_taller_fonts(qapp, monkeypatch):
    """Windows' real Calibri/Georgia have taller lines than the stand-ins used
    elsewhere; template text overflowed there.  Simulated with a font whose
    lines are 1.5 em tall (Calibri's are 1.22)."""
    from PyQt6.QtGui import QFontDatabase
    if "Poppins" not in QFontDatabase.families():
        pytest.skip("needs a tall font to simulate with")
    from dtp_publisher.items.text import TextItem
    real_set, real_add = TextItem.set_text, TextItem.add_paragraphs
    monkeypatch.setattr(TextItem, "set_text",
                        lambda self, text, family="x", *a, **k: real_set(self, text, "Poppins", *a, **k))
    monkeypatch.setattr(TextItem, "add_paragraphs",
                        lambda self, text, family="x", *a, **k: real_add(self, text, "Poppins", *a, **k))
    for key in KEYS:
        doc = templates.build(key)
        for sc in doc.pages:
            for it in sc.all_design_items():
                if isinstance(it, TextItem):
                    assert not it.overflow, f"{key}: {it.display_name()} overflows"

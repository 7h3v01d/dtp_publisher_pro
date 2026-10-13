# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Hostile and oversized input: every resource limit has a test here.

Limits are lowered with monkeypatch where the real ones would need gigabytes,
so these run in a second or two.  Memory claims are checked with tracemalloc,
which sees every Python allocation (file reads, decompressed zip members).
"""

import base64
import json
import os
import tracemalloc
import zipfile

import pytest
from PyQt6.QtGui import QColor, QImage, QImageReader

from test_import import STYLES, _content, _frame


def _doc_data(pages=1, items_per_page=0, item=None):
    from dtp_publisher.document import Document
    from dtp_publisher.serialize import document_to_dict
    d = Document()
    d.add_page(d.make_page())
    data = document_to_dict(d)
    item = item or {"kind": "shape", "x": 1, "y": 1, "w": 10, "h": 10}
    data["pages"] = [dict(data["pages"][0], items=[dict(item) for _ in range(items_per_page)])
                     for _ in range(pages)]
    return data


def _peak_bytes(fn):
    tracemalloc.start()
    try:
        out = fn()
        return out, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _odg(path, frames, pictures=None, content=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.graphics")
        z.writestr("content.xml", content if content is not None else _content(frames))
        z.writestr("styles.xml", STYLES)
        for name, data in (pictures or {}).items():
            z.writestr(name, data)
    return str(path)


def _pic_frame(href, x=0):
    return (f'<draw:frame svg:x="{x}mm" svg:y="0mm" svg:width="20mm" svg:height="20mm">'
            f'<draw:image xlink:href="{href}"/></draw:frame>')


def _png(w=8, h=8, color="red") -> bytes:
    from dtp_publisher.items.image import encode_image
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return encode_image(img, "png")[0]


# ── 1, 17. page size, margins and gutter from a file ────────────────────────
@pytest.mark.parametrize("w", [1e9, "Infinity", "NaN", -50, 0, "wide", None])
def test_page_size_from_file_is_clamped(qapp, w):
    from dtp_publisher import limits
    from dtp_publisher.serialize import document_from_dict
    data = _doc_data()
    setup = data["pages"][0]["setup"]
    setup.update(width=w, height=w, margins=[1e12, -5, "x", float("nan")], gutter=1e12)
    raw = json.dumps(data).replace('"Infinity"', "Infinity").replace('"NaN"', "NaN")
    doc, _ = document_from_dict(json.loads(raw))
    sc = doc.pages[0]
    for v in (sc.page_w, sc.page_h):
        assert limits.MIN_PAGE_PT <= v <= limits.MAX_PAGE_PT
    half = min(sc.page_w, sc.page_h) / 2
    assert all(0 <= m <= half for m in sc.margins)
    assert 0 <= sc.gutter <= half


def test_page_constructor_is_clamped(qapp, doc):
    from dtp_publisher import limits
    sc = doc.make_page(1e9, float("inf"))
    assert sc.page_w == limits.MAX_PAGE_PT and sc.page_h <= limits.MAX_PAGE_PT


def test_guides_per_page_are_capped(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import document_from_dict
    monkeypatch.setattr(limits, "MAX_GUIDES_PER_PAGE", 5)
    data = _doc_data()
    data["pages"][0]["guides"] = [{"orient": "H", "pos": i} for i in range(50)]
    doc, warnings = document_from_dict(data)
    assert len(doc.pages[0].guides) == 5
    assert any("guides" in w for w in warnings)


# ── 2. raster export budget ─────────────────────────────────────────────────
def test_raster_export_refuses_huge_bitmaps(qapp, doc):
    from dtp_publisher import limits
    from dtp_publisher.export import render_page_image
    sc = doc.make_page(limits.MAX_PAGE_PT, limits.MAX_PAGE_PT)
    with pytest.raises(limits.TooBig):
        render_page_image(sc, 150)          # 30,000 × 30,000 px: 3.6 GB


def test_raster_export_budget_is_checked_before_allocating(qapp, doc, monkeypatch):
    """Below Qt's own allocation limit too: our budget, not Qt failing, must stop it."""
    from dtp_publisher import limits
    from dtp_publisher.export import render_page_image
    monkeypatch.setattr(limits, "MAX_EXPORT_PIXELS", 1_000_000)
    with pytest.raises(limits.TooBig):
        render_page_image(doc.pages[0], 150)      # A4 at 150 dpi: about 2.2 MP
    assert not render_page_image(doc.pages[0], 72).isNull()


def test_safe_export_dpi():
    from dtp_publisher import limits
    a4 = limits.safe_export_dpi(595, 842, 300)
    assert a4 == 300                                         # ordinary pages untouched
    big = limits.safe_export_dpi(limits.MAX_PAGE_PT, limits.MAX_PAGE_PT, 300)
    side = limits.MAX_PAGE_PT / 72 * big
    assert side * side <= limits.MAX_EXPORT_PIXELS and side <= limits.MAX_EXPORT_SIDE
    assert big >= 1


def test_save_as_picture_lowers_dpi_instead_of_failing(qapp, doc, tmp_path, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.export import export_dpi, export_images
    monkeypatch.setattr(limits, "MAX_EXPORT_PIXELS", 400_000)
    doc.pages[0].apply_setup({"width": 720, "height": 720})         # 10 × 10 inches
    assert export_dpi(doc, None, 300) == 63
    (out,) = export_images(doc, str(tmp_path), "p", "jpg", 300)
    img = QImage(out)
    assert img.width() * img.height() <= 400_000 and img.width() == 630


# ── 3, 4. picture files ─────────────────────────────────────────────────────
def test_huge_picture_file_is_refused_without_reading_it(qapp, tmp_path):
    from dtp_publisher import limits
    from dtp_publisher.items.image import image_file_problem, load_image_file
    p = tmp_path / "huge.jpg"
    with open(p, "wb") as f:
        f.truncate(limits.MAX_IMAGE_FILE_BYTES + 1)              # sparse: no disk used
    res, peak = _peak_bytes(lambda: load_image_file(str(p)))
    assert res is None
    assert peak < 16 * 1024 * 1024
    assert "MB" in image_file_problem(str(p))


def test_unreadable_big_file_is_not_slurped(qapp, tmp_path):
    """Under the size limit but not a picture: decoded from the file, never read whole."""
    from dtp_publisher.items.image import load_image_file
    p = tmp_path / "junk.png"
    with open(p, "wb") as f:
        f.truncate(64 * 1024 * 1024)
    res, peak = _peak_bytes(lambda: load_image_file(str(p)))
    assert res is None
    assert peak < 16 * 1024 * 1024


def test_very_large_photo_is_decoded_at_reduced_size(qapp, tmp_path):
    """A photo bigger than Qt's decode allowance (e.g. 108 MP) still goes in, scaled."""
    from dtp_publisher.items.image import load_image_file, prepare_image_bytes
    img = QImage(2000, 1500, QImage.Format.Format_RGB32)
    img.fill(QColor("orange"))
    p = tmp_path / "big.jpg"
    assert img.save(str(p), "JPG", 85)
    old = QImageReader.allocationLimit()
    QImageReader.setAllocationLimit(8)          # MB: the full 12 MB decode is refused
    try:
        res = load_image_file(str(p), max_px=1000)
        res2 = prepare_image_bytes(p.read_bytes(), max_px=1000)
    finally:
        QImageReader.setAllocationLimit(old)
    for r in (res, res2):
        assert r is not None
        data, fmt, im = r
        assert (im.width(), im.height()) == (1000, 750) and fmt == "jpg"


def test_small_picture_bytes_are_kept_as_they_are(qapp, tmp_path):
    from dtp_publisher.items.image import load_image_file
    raw = _png()
    p = tmp_path / "a.png"
    p.write_bytes(raw)
    data, fmt, _ = load_image_file(str(p))
    assert data == raw and fmt == "png"


# ── 5, 6, 15. Publisher import (converted ODG) ──────────────────────────────
def test_odg_picture_bomb_is_not_decompressed(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.importers.odg import import_odg
    monkeypatch.setattr(limits, "MAX_ODG_PICTURE_BYTES", 4 * 1024 * 1024)
    bomb = b"\x89PNG" + b"\0" * (40 * 1024 * 1024)               # 40 MB → ~40 KB zipped
    p = _odg(tmp_path / "b.odg", _pic_frame("Pictures/bomb.png"),
             {"Pictures/bomb.png": bomb})
    del bomb
    (doc, rep), peak = _peak_bytes(lambda: import_odg(p))
    assert peak < 16 * 1024 * 1024
    assert any("too big" in w for w in rep.warnings)
    assert len(doc.pages) == 1                                    # the rest still opens


def test_odg_total_picture_budget(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.importers.odg import import_odg
    from dtp_publisher.items import ImageItem
    pics = {f"Pictures/p{i}.png": _png(64, 64, c) for i, c in enumerate(("red", "blue", "lime"))}
    size = max(len(v) for v in pics.values())
    monkeypatch.setattr(limits, "MAX_ODG_TOTAL_PICTURE_BYTES", size * 2 + 10)
    frames = "".join(_pic_frame(n, 25 * i) for i, n in enumerate(pics))
    doc, rep = import_odg(_odg(tmp_path / "t.odg", frames, pics))
    ims = [it for it in doc.pages[0].items() if isinstance(it, ImageItem)]
    assert sum(1 for im in ims if im.has_image()) == 2
    assert any("too big" in w for w in rep.warnings)


def test_odg_repeated_picture_is_read_once(qapp, tmp_path, monkeypatch):
    from dtp_publisher.importers import odg
    reads = []
    real = odg.OdgImporter._read_member
    monkeypatch.setattr(odg.OdgImporter, "_read_member",
                        lambda self, n: reads.append(n) or real(self, n))
    frames = "".join(_pic_frame("Pictures/a.png", i) for i in range(40))
    doc, rep = odg.import_odg(_odg(tmp_path / "r.odg", frames, {"Pictures/a.png": _png()}))
    assert reads == ["Pictures/a.png"] and rep.pictures == 40


def test_odg_xml_size_and_element_limits(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.importers.odg import import_odg
    p = _odg(tmp_path / "x.odg", "".join(_frame(1, 1, 5, 5, "hi") for _ in range(30)))
    monkeypatch.setattr(limits, "MAX_XML_ELEMENTS", 60)
    with pytest.raises(limits.TooBig):
        import_odg(p)
    monkeypatch.setattr(limits, "MAX_XML_ELEMENTS", 10_000)
    monkeypatch.setattr(limits, "MAX_ODG_XML_BYTES", 2000)
    with pytest.raises(limits.TooBig):
        import_odg(p)


def test_odg_entity_expansion_is_rejected(qapp, tmp_path):
    from xml.etree.ElementTree import ParseError
    from dtp_publisher.importers.odg import import_odg
    ents = "".join(f'<!ENTITY e{i} "{f"&e{i - 1};" * 10}">' for i in range(1, 9))
    bomb = (f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY e0 "laugh">{ents}]>'
            "<d>&e8;</d>")
    p = _odg(tmp_path / "e.odg", "", content=bomb)
    with pytest.raises(ParseError):
        import_odg(p)


def test_odg_page_and_object_budgets(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.importers.odg import import_odg
    frames = "".join(_frame(1, 1, 5, 5, "x") for _ in range(30))
    p = _odg(tmp_path / "o.odg", frames)
    monkeypatch.setattr(limits, "MAX_OBJECTS", 10)
    with pytest.raises(limits.TooBig):
        import_odg(p)
    monkeypatch.setattr(limits, "MAX_OBJECTS", 1000)
    monkeypatch.setattr(limits, "MAX_PAGES", 0)
    with pytest.raises(limits.TooBig):
        import_odg(p)


@pytest.mark.parametrize("w", ["-5mm", "0mm", "1e30mm", "nan", "junk", "1e-30mm"])
def test_odg_absurd_dimensions_do_not_crash(qapp, tmp_path, w):
    from dtp_publisher.importers.odg import import_odg
    frames = (f'<draw:rect svg:x="{w}" svg:y="{w}" svg:width="{w}" svg:height="{w}"/>'
              + f'<draw:frame svg:x="0mm" svg:y="0mm" svg:width="{w}" svg:height="{w}">'
                '<draw:text-box><text:p>hello</text:p></draw:text-box></draw:frame>')
    doc, rep = import_odg(_odg(tmp_path / "d.odg", frames))
    for it in doc.pages[0].items():
        g = getattr(it, "geometry", None)
        if g:
            gg = g()
            assert all(abs(v) < 1e8 for v in (gg.x, gg.y, gg.w, gg.h))


def test_converted_output_too_large_is_refused(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("uses a shell script as a stand-in for LibreOffice")
    from dtp_publisher import limits
    from dtp_publisher.importers import libreoffice
    fake = tmp_path / "soffice"
    fake.write_text('#!/bin/sh\nfor a; do out="$prev"; prev="$a"; done\n'
                    'd=$(dirname "$a"); n=$(basename "$a" .pub)\n'
                    'while [ $# -gt 0 ]; do [ "$1" = "--outdir" ] && d="$2"; shift; done\n'
                    'head -c 5000 /dev/zero > "$d/$n.odg"\n')
    fake.chmod(0o755)
    src = tmp_path / "a.pub"
    src.write_bytes(b"x")
    monkeypatch.setattr(limits, "MAX_CONVERTED_BYTES", 1000)
    with pytest.raises(libreoffice.ConversionError, match="too large"):
        libreoffice.convert(str(src), soffice=str(fake))
    monkeypatch.setattr(limits, "MAX_CONVERTED_BYTES", 10_000)
    out = libreoffice.convert(str(src), soffice=str(fake))
    assert os.path.getsize(out) == 5000
    import shutil
    shutil.rmtree(os.path.dirname(os.path.dirname(out)))


# ── 7, 8, 9. document complexity budget ─────────────────────────────────────
def test_too_many_pages_refused_before_building(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_PAGES", 3)
    with pytest.raises(DocumentError, match="pages"):
        document_from_dict(_doc_data(pages=5))


def test_too_many_objects_refused_before_any_is_made(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.items import ShapeItem
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_OBJECTS", 20)
    made = []
    real_init = ShapeItem.__init__
    monkeypatch.setattr(ShapeItem, "__init__",
                        lambda self, *a, **k: made.append(1) or real_init(self, *a, **k))
    group = {"kind": "group", "x": 0, "y": 0, "w": 10, "h": 10,
             "children": [{"kind": "shape", "x": 0, "y": 0, "w": 5, "h": 5}] * 15}
    with pytest.raises(DocumentError, match="objects"):
        document_from_dict(_doc_data(items_per_page=2, item=group))   # 2 + 30 objects
    assert made == []


def test_too_much_text_refused(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_TEXT_CHARS", 1000)
    item = {"kind": "text", "x": 0, "y": 0, "w": 50, "h": 50, "html": "<p>" + "a" * 600}
    with pytest.raises(DocumentError, match="text"):
        document_from_dict(_doc_data(items_per_page=2, item=item))


def test_deeply_nested_groups_load_without_recursion_error(qapp):
    from dtp_publisher.serialize import document_from_dict
    node = {"kind": "shape", "x": 0, "y": 0, "w": 5, "h": 5}
    for _ in range(400):
        node = {"kind": "group", "x": 0, "y": 0, "w": 5, "h": 5, "children": [node]}
    doc, _ = document_from_dict(json.loads(json.dumps(_doc_data(items_per_page=1, item=node)),
                                           ))
    assert len(doc.pages) == 1


def test_clipboard_over_budget_pastes_nothing(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import items_from_clip
    monkeypatch.setattr(limits, "MAX_OBJECTS", 5)
    raw = json.dumps({"format": "dtpub",
                      "items": [{"kind": "shape", "x": 0, "y": 0, "w": 5, "h": 5}] * 6})
    assert items_from_clip(raw.encode()) == []


# ── 10. damaged pictures in a .dtpub ────────────────────────────────────────
def _image_item_dict(data: str):
    return {"kind": "image", "x": 0, "y": 0, "w": 50, "h": 50, "data": data,
            "format": "png", "source_name": "Nan.png"}


def test_damaged_picture_text_is_repaired_with_a_warning(qapp):
    from dtp_publisher.items import ImageItem
    from dtp_publisher.serialize import item_from_dict
    good = base64.b64encode(_png()).decode()
    warnings = []
    it = item_from_dict(_image_item_dict(good[:10] + "!*~\n" + good[10:]), warnings)
    assert isinstance(it, ImageItem) and it.has_image()
    assert any("repaired" in w for w in warnings)
    warnings = []
    it = item_from_dict(_image_item_dict(good), warnings)
    assert it.has_image() and warnings == []


def test_garbage_picture_becomes_empty_frame_with_a_warning(qapp):
    from dtp_publisher.serialize import item_from_dict
    warnings = []
    it = item_from_dict(_image_item_dict(base64.b64encode(b"not a picture").decode()),
                        warnings)
    assert it is not None and not it.has_image() and it.data == b""
    assert any("damaged" in w for w in warnings)


# ── 16. duplicate ids ───────────────────────────────────────────────────────
def test_duplicate_uids_are_made_unique_on_load(qapp):
    from dtp_publisher.serialize import document_from_dict
    item = {"kind": "shape", "x": 0, "y": 0, "w": 5, "h": 5, "uid": "same"}
    doc, warnings = document_from_dict(_doc_data(pages=2, items_per_page=3, item=item))
    uids = [it.uid for sc in doc.pages for it in sc.top_items()]
    assert len(uids) == 6 and len(set(uids)) == 6 and "same" in uids
    assert any("duplicate" in w for w in warnings)


def test_duplicate_uid_cannot_hijack_a_text_link(qapp):
    """A copy of the first box (same uid) must not become the link target."""
    from dtp_publisher.serialize import document_from_dict
    a = {"kind": "text", "x": 0, "y": 0, "w": 50, "h": 20, "uid": "A",
         "html": "<p>" + "story " * 200 + "</p>", "link_next": "B"}
    b = {"kind": "text", "x": 0, "y": 30, "w": 50, "h": 20, "uid": "B", "html": "",
         "linked": True}
    impostor = {"kind": "text", "x": 0, "y": 60, "w": 50, "h": 20, "uid": "B",
                "html": "<p>other</p>"}
    data = _doc_data()
    data["pages"][0]["items"] = [a, b, impostor]
    doc, _ = document_from_dict(data)
    first, second, third = sorted(doc.text_items(), key=lambda t: t.geometry().y)
    assert first.link_next is second
    assert not third.is_linked() and third.plain_text() == "other"

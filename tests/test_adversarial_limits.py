# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
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


# ═════════════════════════════════════════════════════════════════════════════
# 5.1.2 — second review (B1–B6) and the large-document benchmark
# ═════════════════════════════════════════════════════════════════════════════
def _write(tmp_path, data, name="d.dtpub"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ── B1. JSON structure is bounded before parsing ────────────────────────────
def test_json_structure_refused_before_parsing(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits, serialize
    monkeypatch.setattr(limits, "MAX_JSON_NODES", 1000)
    data = _doc_data()
    data["view"] = {"junk": [{} for _ in range(2000)]}      # tiny file, big structure
    path = _write(tmp_path, data)

    def never(*a, **k):
        raise AssertionError("json.loads ran on a file that should have been refused")
    monkeypatch.setattr(serialize.json, "loads", never)
    with pytest.raises(serialize.DocumentError, match="values"):
        serialize.load_document(path)


def test_json_structure_counts_only_outside_strings(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits, serialize
    monkeypatch.setattr(limits, "MAX_JSON_NODES", 300)
    item = {"kind": "text", "x": 0, "y": 0, "w": 50, "h": 50,
            "html": "<p>" + "a, b, {c} [d] \\" ' \\"q\\", ' * 400 + "</p>"}
    path = _write(tmp_path, _doc_data(items_per_page=1, item=item))
    doc, _ = serialize.load_document(path)                 # commas in text don't count
    assert doc.text_items()


def test_clipboard_structure_bomb_pastes_nothing(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import items_from_clip
    monkeypatch.setattr(limits, "MAX_JSON_NODES", 100)
    raw = json.dumps({"format": "dtpub", "items": [], "junk": [[]] * 500}).encode()
    assert items_from_clip(raw) == []


# ── B2 and the benchmark: pictures in a .dtpub ──────────────────────────────
def _big_png(w, h):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#336699"))
    from dtp_publisher.items.image import encode_image
    return encode_image(img, "png")[0]


def test_embedded_picture_budget_checked_before_decoding(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits, serialize
    from dtp_publisher.items import image as image_mod
    b64 = base64.b64encode(_png()).decode()
    monkeypatch.setattr(limits, "MAX_IMAGE_B64_CHARS", len(b64) - 1)
    monkeypatch.setattr(image_mod.base64, "b64decode",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("decoded")))
    path = _write(tmp_path, _doc_data(items_per_page=1, item=_image_item_dict(b64)))
    with pytest.raises(serialize.DocumentError, match="picture"):
        serialize.load_document(path)


def test_total_embedded_pictures_budget(qapp, tmp_path, monkeypatch):
    from dtp_publisher import limits, serialize
    b64 = base64.b64encode(_png()).decode()
    monkeypatch.setattr(limits, "MAX_TOTAL_IMAGE_B64_CHARS", len(b64) * 3)
    path = _write(tmp_path, _doc_data(items_per_page=4, item=_image_item_dict(b64)))
    with pytest.raises(serialize.DocumentError, match="pictures"):
        serialize.load_document(path)


def test_embedded_picture_beyond_pixel_limit_is_refused(qapp, monkeypatch):
    """40 such pictures in a 10 MB file took 35 s and would have needed 10 GB."""
    from dtp_publisher import limits
    from dtp_publisher.serialize import item_from_dict
    monkeypatch.setattr(limits, "MAX_EMBEDDED_PIXELS", 1000 * 1000)
    warnings = []
    it = item_from_dict(_image_item_dict(base64.b64encode(_big_png(1200, 1000)).decode()),
                        warnings)
    assert it is not None and not it.has_image()
    assert any("1,200 × 1,000 pixels" in w for w in warnings)


def test_huge_embedded_picture_is_never_decoded_full_size(qapp):
    """A small file can hold an 8000 × 8000 picture; it is decoded at most at the
    insert size (it used to be held at full size: 256 MB each)."""
    from dtp_publisher.items.image import MAX_EMBED_PX
    from dtp_publisher.serialize import item_from_dict
    it = item_from_dict(_image_item_dict(base64.b64encode(_big_png(4000, 3000)).decode()))
    assert it.has_image()
    full = it.full_image()
    assert max(full.width(), full.height()) <= MAX_EMBED_PX
    assert abs(it.natural_aspect() - 4 / 3) < 0.01


def test_pictures_keep_only_bytes_and_a_frame_sized_preview(qapp):
    """150 photos used to need ~35 MB each (full decode + 1600 px preview)."""
    from dtp_publisher.items import ImageItem
    from dtp_publisher.items.image import read_image_bytes
    data = _big_png(3000, 2250)
    it = ImageItem(150, 112)
    it.set_image_data(data, "png", "a.png", read_image_bytes(data))
    held = [v for v in vars(it).values() if isinstance(v, QImage)]
    assert held == []                                     # no decoded copy kept
    assert max(it._preview.width(), it._preview.height()) <= 800
    it.set_geometry(it.geometry()._replace(w=600, h=450))   # made much bigger
    it._preview_ok()
    assert max(it._preview.width(), it._preview.height()) > 800   # sharper preview made
    img = it.full_image()                                  # printing gets every pixel
    assert (img.width(), img.height()) == (3000, 2250)


def test_preview_survives_save_and_reload_without_reencoding(qapp, tmp_path):
    from dtp_publisher.items import ImageItem
    from dtp_publisher.serialize import item_from_dict, item_to_dict
    it = ImageItem(100, 75)
    it.set_image_data(_png(), "png", "a.png")
    d = item_to_dict(it)
    back = item_from_dict(d)
    assert back.has_image() and back.data == it.data
    assert back.data_b64() is d["data"]                   # loaded text reused, not re-made


# ── B3. Publisher source file ───────────────────────────────────────────────
def test_pub_source_size_checked_before_copying(tmp_path, monkeypatch):
    import tempfile
    from dtp_publisher import limits
    from dtp_publisher.importers import libreoffice
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "t"))
    os.makedirs(tmp_path / "t")
    src = tmp_path / "big.pub"
    src.write_bytes(b"x" * 5000)
    monkeypatch.setattr(limits, "MAX_PUB_SOURCE_BYTES", 1000)
    monkeypatch.setattr(libreoffice, "_copy_capped",
                        lambda *a: (_ for _ in ()).throw(AssertionError("copied")))
    with pytest.raises(libreoffice.ConversionError, match="up to"):
        libreoffice.convert(str(src), soffice="/bin/true")
    assert os.listdir(tmp_path / "t") == []


def test_failed_conversion_leaves_no_temp_folder(tmp_path, monkeypatch):
    import tempfile
    from dtp_publisher.importers import libreoffice
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "t"))
    os.makedirs(tmp_path / "t")
    src = tmp_path / "a.pub"
    src.write_bytes(b"x" * 100)

    def disk_full(*a):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(libreoffice, "_copy_capped", disk_full)
    with pytest.raises(OSError):
        libreoffice.convert(str(src), soffice="/bin/true")
    assert os.listdir(tmp_path / "t") == []


def test_libreoffice_temp_files_count_against_the_budget(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("uses a shell script as a stand-in for LibreOffice")
    from dtp_publisher import limits
    from dtp_publisher.importers import libreoffice
    fake = tmp_path / "soffice"
    fake.write_text('#!/bin/sh\nhead -c 5000 /dev/zero > "$TMPDIR/scratch"\nsleep 6\n')
    fake.chmod(0o755)
    src = tmp_path / "a.pub"
    src.write_bytes(b"x")
    monkeypatch.setattr(limits, "MAX_CONVERT_DIR_BYTES", 1000)
    with pytest.raises(libreoffice.ConversionError, match="too large"):
        libreoffice.convert(str(src), soffice=str(fake), timeout=20)


# ── B5. drawings ────────────────────────────────────────────────────────────
def _random_path(n, seed=1):
    import random
    r = random.Random(seed)
    return "M0 0" + "".join(f"L{r.random():.3f} {r.random():.3f}" for _ in range(n))


def _path_page(d, count):
    items = [{"kind": "path", "x": 0, "y": 0, "w": 500, "h": 500, "d": d, "uid": f"p{i}"}
             for i in range(count)]
    return _doc_data(items_per_page=0) | {"pages": [{"setup": {"width": 595, "height": 842},
                                                      "items": items}]}


def test_edge_density():
    from dtp_publisher.items.path import edge_density, parse_svg_path
    assert edge_density(parse_svg_path("M0 0L1 0L1 1L0 1Z")) == pytest.approx(2)
    zig = parse_svg_path("M0 0" + "L1 1L0 0" * 50)
    assert edge_density(zig) == pytest.approx(100)


def test_drawing_detail_on_a_hostile_page(qapp):
    """It took 382 s to draw one page of 20 dense drawings; now each drawing is
    smoothed, drawn plain or shown as a box according to the page's allowance."""
    from dtp_publisher import limits
    from dtp_publisher.items import PathItem
    from dtp_publisher.serialize import document_from_dict
    doc, warnings = document_from_dict(_path_page(_random_path(1190), 20))   # density ≈ 390
    paths = [i for i in doc.pages[0].all_design_items() if isinstance(i, PathItem)]
    per = paths[0].density()
    assert limits.MAX_SMOOTH_DENSITY > per > limits.MAX_SCREEN_SMOOTH_WORK
    kinds = [p.detail() for p in paths]
    assert "smooth" not in kinds                                    # too costly on screen
    boxed = kinds.count("box")
    assert boxed == len(paths) - int(limits.MAX_PAGE_DENSITY // per)
    assert any("boxes" in w for w in warnings)


def test_screen_smoothing_shares_one_allowance_per_page(qapp):
    from dtp_publisher import limits
    from dtp_publisher.items import PathItem
    from dtp_publisher.serialize import document_from_dict
    doc, _ = document_from_dict(_path_page(_random_path(100), 15))          # density ≈ 33
    sc = doc.pages[0]
    paths = [i for i in sc.all_design_items() if isinstance(i, PathItem)]
    d = paths[0].density()
    for zoom in (1.0, 2.0, 4.0):
        sc.zoom = zoom
        smooth = sum(p.detail() == "smooth" for p in paths)
        assert smooth == min(len(paths), int(limits.MAX_SCREEN_SMOOTH_WORK // (d * zoom * zoom)))


def test_smoothed_drawings_per_page_are_capped(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.items import PathItem
    from dtp_publisher.serialize import document_from_dict
    monkeypatch.setattr(limits, "MAX_SMOOTH_DRAWINGS_PER_PAGE", 25)
    doc, _ = document_from_dict(_path_page("M0 0L1 0L1 1L0 1Z", 40))
    paths = [i for i in doc.pages[0].all_design_items() if isinstance(i, PathItem)]
    assert sum(p.detail() == "smooth" for p in paths) == 25


def test_simple_drawings_stay_smooth(qapp):
    """Circles and boxes are cheap at any zoom (up to a page's worth)."""
    from dtp_publisher.items import PathItem
    from dtp_publisher.serialize import document_from_dict
    circle = "M1 .5A.5 .5 0 1 1 0 .5A.5 .5 0 1 1 1 .5Z"
    doc, warnings = document_from_dict(_path_page(circle, 40))
    sc = doc.pages[0]
    sc.zoom = 4.0
    assert all(p.detail() == "smooth" for p in sc.all_design_items() if isinstance(p, PathItem))
    assert warnings == []


def test_printing_smooths_up_to_the_print_limit(qapp, monkeypatch):
    from dtp_publisher.items import PathItem
    it = PathItem(100, 100, _random_path(1190))
    monkeypatch.setattr(it, "is_rendering", lambda: True)
    assert it.detail() == "smooth"


def test_page_drawing_detail_budget_refuses_file(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_PAGE_PATH_CHARS", 10_000)
    with pytest.raises(DocumentError, match="drawings"):
        document_from_dict(_path_page(_random_path(1000), 2))


def test_table_cells_count_as_text(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_TEXT_CHARS", 1000)
    item = {"kind": "table", "x": 0, "y": 0, "w": 50, "h": 50,
            "table": {"rows": 2, "cols": 2, "cells": {"0,0": "x" * 600, "1,1": "y" * 600}}}
    with pytest.raises(DocumentError, match="text"):
        document_from_dict(_doc_data(items_per_page=1, item=item))


# ── B6. objects on one page ─────────────────────────────────────────────────
def test_objects_per_page_limit(qapp, monkeypatch):
    from dtp_publisher import limits
    from dtp_publisher.serialize import DocumentError, document_from_dict
    monkeypatch.setattr(limits, "MAX_OBJECTS_PER_PAGE", 10)
    document_from_dict(_doc_data(pages=3, items_per_page=10))       # 30 in all: fine
    with pytest.raises(DocumentError, match="page"):
        document_from_dict(_doc_data(pages=1, items_per_page=11))


# ── benchmark finding: linked stories laid out once when opening ───────────
def test_opening_lays_out_each_story_once(qapp, monkeypatch):
    from dtp_publisher.items.text import TextItem
    from dtp_publisher.serialize import document_from_dict
    n = 30
    items = []
    for i in range(n):
        d = {"kind": "text", "x": 10, "y": 10 + i * 25, "w": 100, "h": 20, "uid": f"t{i}",
             "html": "<p>" + "word " * 2000 + "</p>" if i == 0 else ""}
        if i:
            d["linked"] = True
        if i < n - 1:
            d["link_next"] = f"t{i + 1}"
        items.append(d)
    data = _doc_data()
    data["pages"][0]["items"] = items
    calls = []
    real = TextItem._line_spans                 # the expensive part of a layout

    def counting(doc):
        calls.append(1)
        return real(doc)
    monkeypatch.setattr(TextItem, "_line_spans", staticmethod(counting))
    doc, _ = document_from_dict(data)
    frames = sorted(doc.text_items(), key=lambda t: t.geometry().y)
    assert frames[0].chain() == frames
    assert len(calls) <= 3                   # it was once per link: 29 full layouts
    assert frames[-1]._slice_pos[1] > frames[-1]._slice_pos[0]      # text reached the end


def test_import_lays_out_each_story_once(qapp, tmp_path, monkeypatch):
    """libmspub gives all 30 boxes of a story the whole story; re-linking them and
    restoring their heights must not lay the story out once per box."""
    from dtp_publisher.importers.odg import import_odg
    from dtp_publisher.items.text import TextItem
    story = "Grandad wrote this story about the long walk up the hill. " * 60
    frames = "".join(_frame(10 + (i % 3) * 60, 10 + (i // 3) * 8, 55, 30, story)
                     for i in range(30))
    path = _odg(tmp_path / "s.odg", frames)
    calls = []
    real = TextItem._line_spans
    monkeypatch.setattr(TextItem, "_line_spans",
                        staticmethod(lambda doc: calls.append(1) or real(doc)))
    doc, rep = import_odg(path)
    assert rep.stories == 1
    assert len(calls) <= 3


def test_dictionary_keys_count_towards_the_json_budget(qapp, tmp_path, monkeypatch):
    """C2: every dictionary entry makes a key *and* a value; counting separators
    alone let a dictionary-heavy file through at about two-thirds of its cost."""
    from dtp_publisher import limits, serialize
    monkeypatch.setattr(limits, "MAX_JSON_NODES", 3000)
    data = _doc_data()
    data["view"] = {"junk": {f"k{i}": [] for i in range(1200)}}     # ~2,400 by separators
    path = _write(tmp_path, data)
    with pytest.raises(serialize.DocumentError, match="values"):
        serialize.load_document(path)
    data["view"] = {"junk": {f"k{i}": [] for i in range(600)}}      # well inside
    serialize.load_document(_write(tmp_path, data, "ok.dtpub"))

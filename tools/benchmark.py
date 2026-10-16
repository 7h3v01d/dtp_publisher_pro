# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Benchmark a large but ordinary publication (not an attack document).

Default: 100 pages, about 1,000 objects, 150 photos at the 3000-pixel
insert size, long linked stories.  Each step runs in a fresh process so the
peak memory figure belongs to that step alone.

    python tools/benchmark.py              (full size)
    python tools/benchmark.py --pages 20 --photos 30
    python tools/benchmark.py --objects-only 20000   (many objects, 1,000 a page)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("DTP_SRC") or os.path.join(ROOT, "src")


def _peak_mb() -> float:
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 1024 if sys.platform != "darwin" else r / 1024 / 1024
    except ImportError:                                   # Windows
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t)] + \
                       [(n, ctypes.c_size_t) for n in ("a", "b", "c", "d", "e", "f")]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                 ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1024 / 1024


_APP = None


def _app():
    global _APP                       # the QApplication must outlive every Qt object
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, SRC)
    from PyQt6.QtWidgets import QApplication
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _photo(i: int, w: int = 3000, h: int = 2250) -> bytes:
    """A photo-like JPEG (smooth light, texture, edges) of the normal insert size."""
    from PyQt6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient
    import random
    rnd = random.Random(i)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor.fromHsv(rnd.randrange(360), 90, 230))
    g.setColorAt(1, QColor.fromHsv(rnd.randrange(360), 140, 90))
    p.fillRect(0, 0, w, h, g)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for _ in range(140):
        c = QColor.fromHsv(rnd.randrange(360), rnd.randrange(40, 220), rnd.randrange(40, 255))
        rg = QRadialGradient(QPointF(rnd.random() * w, rnd.random() * h), rnd.uniform(40, 500))
        rg.setColorAt(0, c)
        c2 = QColor(c)
        c2.setAlpha(0)
        rg.setColorAt(1, c2)
        p.setBrush(rg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(rnd.random() * w - 300, rnd.random() * h - 300, 600, 600))
    p.end()
    # fine grain, as in a real photo (this is what makes JPEGs big)
    bits = img.bits()
    bits.setsize(img.sizeInBytes())
    mv = memoryview(bits).cast("B")
    noise = bytes(rnd.getrandbits(8) & 0x1F for _ in range(65536))
    for off in range(0, len(mv) - 65536, 65536 * 3):
        chunk = bytes(a ^ b for a, b in zip(mv[off:off + 65536], noise))
        mv[off:off + 65536] = chunk
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", 90)
    buf.close()
    return bytes(ba)


def build(path: str, pages: int, photos: int, objects_only: int = 0) -> dict:
    _app()
    from PyQt6.QtGui import QColor
    from dtp_publisher.document import Document
    from dtp_publisher.items import ImageItem, ShapeItem, TextItem
    from dtp_publisher.geometry import Geo
    from dtp_publisher.serialize import save_document
    from dtp_publisher.textflow import connect
    t0 = time.perf_counter()
    doc = Document()
    if objects_only:
        sc = None
        for i in range(objects_only):
            if i % 1000 == 0:                         # 1,000 objects a page
                sc = doc.make_page()
                doc.add_page(sc)
            it = ShapeItem(20, 20) if i % 2 else TextItem(60, 20)
            if isinstance(it, TextItem):
                it.document.setPlainText(f"Label {i}")
            it.set_geometry(Geo((i * 7) % 560, (i * 3) % 800, it.w, it.h, 0))
            sc.addItem(it)
        save_document(doc, path)
        return {"objects": objects_only, "build_s": round(time.perf_counter() - t0, 1)}
    story = ("The village fete raised more than ever this year, thanks to everyone who baked, "
             "sold raffle tickets and put up the bunting in the rain. ") * 12
    jpg = [_photo(i) for i in range(min(photos, 12))]     # 12 distinct photos, reused bytes
    n_photo = n_obj = 0
    prev = None
    for pg in range(pages):
        sc = doc.make_page()
        doc.add_page(sc)
        for col in range(3):                              # a linked story through every page
            t = TextItem(160, 600)
            t.set_geometry(Geo(36 + col * 180, 120, 160, 600, 0))
            if prev is None:
                t.document.setPlainText(story * pages)
            sc.addItem(t)
            if prev is not None:
                connect(prev, t, merge_text=False)
            prev = t
            n_obj += 1
        head = TextItem(520, 60)
        head.document.setPlainText(f"Page {pg + 1} — Parish News")
        head.set_geometry(Geo(36, 36, 520, 60, 0))
        sc.addItem(head)
        for k in range(4):
            s = ShapeItem(40, 40)
            s.fill = QColor.fromHsv((pg * 40 + k * 90) % 360, 120, 220)
            s.set_geometry(Geo(36 + k * 60, 760, 40, 40, 0))
            sc.addItem(s)
        n_obj += 5
        per_page = photos // pages + (1 if pg < photos % pages else 0)
        for k in range(per_page):
            im = ImageItem(150, 112)
            im.set_image_data(jpg[n_photo % len(jpg)], "jpg", f"photo{n_photo}.jpg")
            im.set_geometry(Geo(36 + (k % 3) * 180, 620 - (k // 3) * 120, 150, 112, 0))
            sc.addItem(im)
            n_photo += 1
            n_obj += 1
    built = time.perf_counter()
    save_document(doc, path)
    return {"pages": pages, "objects": n_obj, "photos": n_photo,
            "jpeg_mb": round(sum(map(len, jpg)) / len(jpg) / 2**20, 2),
            "build_s": round(built - t0, 1), "save_s": round(time.perf_counter() - built, 1),
            "file_mb": round(os.path.getsize(path) / 2**20, 1), "peak_mb": round(_peak_mb())}


def step(name: str, path: str) -> dict:
    app = _app()
    from dtp_publisher.serialize import load_document, save_document, document_to_dict
    t0 = time.perf_counter()
    doc, warnings = load_document(path)
    out = {"open_s": round(time.perf_counter() - t0, 1), "warnings": len(warnings)}
    if name == "open":
        pass
    elif name == "paint":           # draw every page as the screen does (scrolling through)
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtCore import QRectF
        t = time.perf_counter()
        for sc in doc.pages:
            img = QImage(800, 1100, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            sc.render(p, QRectF(0, 0, 800, 1100), sc.page_rect())
            p.end()
        out["paint_all_s"] = round(time.perf_counter() - t, 1)
    elif name == "autosave":
        from dtp_publisher.autosave import _detached
        t = time.perf_counter()
        _detached(document_to_dict(doc))
        out["capture_first_ms"] = round((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        _detached(document_to_dict(doc))
        out["capture_next_ms"] = round((time.perf_counter() - t) * 1000)
    elif name == "save":
        t = time.perf_counter()
        save_document(doc, path + ".resave.dtpub")
        out["save_s"] = round(time.perf_counter() - t, 1)
        os.remove(path + ".resave.dtpub")
    elif name == "pdf":
        from dtp_publisher.export import export_pdf
        t = time.perf_counter()
        export_pdf(doc, path + ".pdf")
        out["pdf_s"] = round(time.perf_counter() - t, 1)
        out["pdf_mb"] = round(os.path.getsize(path + ".pdf") / 2**20, 1)
        os.remove(path + ".pdf")
    out["peak_mb"] = round(_peak_mb())
    app.processEvents()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=100)
    ap.add_argument("--photos", type=int, default=150)
    ap.add_argument("--objects-only", type=int, default=0)
    ap.add_argument("--_child", nargs=2, help=argparse.SUPPRESS)
    ap.add_argument("--_build", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a._build:
        print(json.dumps(build(a._build, a.pages, a.photos, a.objects_only)))
        return 0
    if a._child:
        print(json.dumps(step(*a._child)))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bench.dtpub")

        def run(*args):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), *args,
                                "--pages", str(a.pages), "--photos", str(a.photos),
                                "--objects-only", str(a.objects_only)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return json.loads(r.stdout.strip().splitlines()[-1])
        print("build ", run("--_build", path), flush=True)
        steps = ("open", "paint") if a.objects_only else ("open", "paint", "autosave", "save", "pdf")
        for s in steps:
            print(f"{s:<7}", run("--_child", s, path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

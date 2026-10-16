# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Take the screenshots used by the user manual (src/dtp_publisher/help/img).

Runs the real program off-screen with a throw-away settings folder, so the
pictures always match the program.  The sample photos are drawn here (sky,
hills, flowers) - no real photos or personal details go into the manual.

    python tools/manual_screens.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "src", "dtp_publisher", "help", "img")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.5")             # crisp pictures
os.environ["DTP_PUBLISHER_HOME"] = tempfile.mkdtemp(prefix="dtp-manual-")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter,  # noqa: E402
                         QPainterPath, QPen, QPixmap, QPolygonF, QTextCursor)
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication(sys.argv[:1])
app.setStyle("Fusion")
_f = app.font()
_f.setPointSizeF(10.0)
app.setFont(_f)

from dtp_publisher import templates, theme  # noqa: E402
from dtp_publisher.export import render_thumbnail  # noqa: E402
from dtp_publisher.geometry import Geo  # noqa: E402
from dtp_publisher.items import ImageItem, TextItem  # noqa: E402
from dtp_publisher.ui.window import MainWindow  # noqa: E402

theme.apply(app, "light")
ACCENT = QColor("#d9480f")


def settle(n=6):
    for _ in range(n):
        app.processEvents()


def save(pix: QPixmap, name: str):
    os.makedirs(OUT, exist_ok=True)
    pix.save(os.path.join(OUT, name), "PNG")
    print("  ", name, pix.width(), "x", pix.height())


# ── sample photos ──────────────────────────────────────────────────────────
PALETTES = [
    ("#7fb3e0", "#d8ecfa", "#5c8a3c", "#3f6b2a", "#f6c34a"),     # summer
    ("#f2a65a", "#fde3c2", "#8c6b3f", "#5a4326", "#fff1b8"),     # sunset
    ("#9ccfd8", "#eaf6f8", "#6c9a5b", "#466b38", "#ffffff"),     # coast
]


def photo(i: int, w=1600, h=1067) -> bytes:
    sky1, sky2, hill1, hill2, sun = PALETTES[i % len(PALETTES)]
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor(sky1))
    g.setColorAt(1, QColor(sky2))
    p.fillRect(0, 0, w, h, g)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(sun))
    p.drawEllipse(QPointF(w * (0.25 + 0.25 * i), h * 0.28), h * 0.11, h * 0.11)
    for k, (col, base, amp) in enumerate(((hill1, 0.62, 0.07), (hill2, 0.74, 0.05))):
        path = QPainterPath(QPointF(0, h))
        for x in range(0, w + 40, 40):
            path.lineTo(x, h * base - h * amp * math.sin(x / w * math.pi * (2 + k) + i))
        path.lineTo(w, h)
        p.setBrush(QColor(col))
        p.drawPath(path)
    for j in range(40):                               # flowers in the grass
        x = (j * 397 + i * 131) % w
        y = h * 0.82 + (j * 53 % int(h * 0.15))
        p.setBrush(QColor(["#ffffff", "#ffd43b", "#ff8787", "#b197fc"][j % 4]))
        p.drawEllipse(QPointF(x, y), h * 0.012, h * 0.012)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPEG", 88)
    return bytes(ba)


def fill_frames(doc):
    n = 0
    for sc in doc.pages:
        for it in sc.items():
            if isinstance(it, ImageItem) and not it.has_image():
                it.set_image_data(photo(n), "jpg", f"photo{n + 1}.jpg")
                it.update()
                n += 1


# ── helpers for the main window ────────────────────────────────────────────
def window(doc=None, size=(1440, 900)) -> MainWindow:
    w = MainWindow()
    w.resize(*size)
    if doc is not None:
        w.set_document(doc)
    w.show()
    settle()
    w.view.fit_page()
    settle()
    return w


def rect_in(w: QWidget, child: QWidget) -> QRect:
    return QRect(child.mapTo(w, QPoint(0, 0)), QWidget.size(child))   # FormatBar has a .size combo


def item_rect(w: MainWindow, it, pad=24) -> QRect:
    poly = w.view.mapFromScene(it.sceneBoundingRect())
    r = poly.boundingRect().adjusted(-pad, -pad, pad, pad)
    return QRect(w.view.viewport().mapTo(w, r.topLeft()), r.size())


def badge(p: QPainter, x: float, y: float, n: int):
    r = 17
    p.setPen(QPen(QColor("white"), 3))
    p.setBrush(ACCENT)
    p.drawEllipse(QPointF(x, y), r, r)
    f = QFont("Carlito")
    f.setPixelSize(20)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(n))


def main():
    print("Writing screenshots to", OUT)

    # 1. the main window, numbered -------------------------------------------
    doc = templates.build("newsletter")
    fill_frames(doc)
    w = window(doc)
    pix = w.grab()
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rb = rect_in(w, w.ribbon)
    fb = rect_in(w, w.fmt)
    th = rect_in(w, w.thumbs)
    vw = rect_in(w, w.view)
    rt = rect_in(w, w.right)
    sb = rect_in(w, w.statusBar())
    for n, (x, y) in enumerate([
            (rb.left() + 505, rb.top() + 16),                 # 1 tabs (right of View)
            (rb.left() + 1060, rb.top() + 75),                # 2 buttons (empty ribbon space)
            (fb.left() + 1010, fb.center().y()),              # 3 text bar (after its buttons)
            (th.left() + 120, th.top() + 22),                 # 4 pages
            (vw.left() + 170, vw.top() + 140),                # 5 page (grey area beside it)
            (rt.left() + 240, rt.top() + 20),                 # 6 format/objects
            (sb.right() - 370, sb.center().y() - 2),          # 7 zoom
    ], start=1):
        badge(p, x, y, n)
    p.end()
    save(pix, "window.png")

    # 2. each ribbon tab ---------------------------------------------------------
    for tab, name in (("File", "file"), ("Home", "home"), ("Insert", "insert"),
                      ("Page Design", "pagedesign"), ("Arrange", "arrange"), ("View", "view")):
        w.ribbon.show_tab(tab)
        settle()
        r = rect_in(w, w.ribbon)
        save(w.grab(r), f"ribbon_{name}.png")
    w.ribbon.show_tab("Home")
    settle()

    # 3. typing in a text box -----------------------------------------------------
    texts = [t for t in doc.pages[0].items() if isinstance(t, TextItem)]
    head = next(t for t in texts if "headline" in t.plain_text().lower())
    w.view.set_zoom(1.6)
    w.view.centerOn(head)
    settle()
    head.setSelected(True)
    head.begin_edit()
    c = head.text_child().textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    c.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.KeepAnchor)
    head.text_child().setTextCursor(c)
    w._update_actions() if hasattr(w, "_update_actions") else None
    settle()
    box = item_rect(w, head, pad=30)
    fbr = rect_in(w, w.fmt)
    top = fbr.top()
    shot = QRect(0, top, min(w.width(), max(box.right(), fbr.left() + 1000)) + 10,
                 box.bottom() - top)
    save(w.grab(shot), "typing.png")
    head.end_edit() if hasattr(head, "end_edit") else None
    w.deselect()
    settle()

    # 4. a picture selected, with the Format panel ------------------------------
    doc = templates.build("flyer")
    fill_frames(doc)
    w2 = window(doc)
    pic = next(i for i in doc.pages[0].items() if isinstance(i, ImageItem))
    pic.setSelected(True)
    settle()
    save(w2.grab(), "picture_selected.png")
    w2.deselect()

    # 5. text overflow marker (on a blank page of its own) ---------------------------
    w3 = window(templates.blank(420, 300, 24), size=(1000, 700))
    sc3 = w3.scene
    t = TextItem(220, 70)
    t.set_geometry(Geo(60, 60, 220, 70, 0))
    sc3.addItem(t)
    t.document.setPlainText("This box has more words in it than will fit, so the rest of "
                            "the story is hidden until the box is made bigger or the text "
                            "smaller. Look for the little red marker in the corner.")
    t.refit()
    t.setSelected(True)
    w3.view.set_zoom(2.0)
    w3.view.centerOn(t)
    settle()
    save(w3.grab(item_rect(w3, t, pad=28)), "overflow.png")

    # 6. text wrapping round a picture (page only) -----------------------------------
    d = templates.blank(420, 250, 24)
    sc = d.pages[0]
    story = TextItem(372, 202)
    story.set_geometry(Geo(24, 24, 372, 202, 0))
    sc.addItem(story)
    story.document.setPlainText(
        "Our street garden is looking its best this spring. Thanks to everyone who came "
        "along to the working bee: the new beds by the gate are planted, the compost bays "
        "are finished and the tap by the shed has finally been fixed. The tomatoes went in "
        "last weekend and the herbs are already doing well. Next month we will be planting "
        "the native strip along the fence, so bring gloves and a trowel if you can. Morning "
        "tea is provided, and children are welcome to help with the watering.")
    pic = ImageItem(150, 105)
    pic.set_image_data(photo(1), "jpg", "garden.jpg")
    pic.set_geometry(Geo(236, 70, 160, 112, 0))
    pic.wrap = "square"
    sc.addItem(pic)
    sc.flush_wrap() if hasattr(sc, "flush_wrap") else None
    save(QPixmap.fromImage(render_thumbnail(sc, 1260, 750)), "wrap.png")

    # 7. dialogs -----------------------------------------------------------------------
    from fake_registry import FakeRegistry

    from dtp_publisher.ui.dialogs.editors import WordArtDialog
    from dtp_publisher.ui.dialogs.misc import (ExportPicturesDialog, FillPageDialog,
                                               PreferencesDialog, RecoveryDialog)
    from dtp_publisher.ui.dialogs.page_setup import PageSetupDialog
    from dtp_publisher.ui.dialogs.start import StartDialog
    from dtp_publisher.items import WordArtItem

    def grab_dialog(dlg, name, size=None):
        if size:
            dlg.resize(*size)
        else:
            dlg.adjustSize()
        dlg.show()
        settle(10)
        save(dlg.grab(), name)
        dlg.close()

    sd = StartDialog([os.path.join("Documents", n) for n in
                      ("Spring newsletter.dtpub", "Party invitation.dtpub",
                       "Christmas letter.dtpub")], True, w)
    sd.cats.setCurrentRow(0)
    grab_dialog(sd, "start.png", (1100, 700))

    grab_dialog(PreferencesDialog(w.settings, w, assoc_registry=FakeRegistry()), "prefs.png")
    sc = w.scene
    grab_dialog(PageSetupDialog(sc.setup_state(), w.settings.units, True, w, sheet=None),
                "page_setup.png")
    grab_dialog(WordArtDialog(WordArtItem().wordart_state(), w, "New WordArt"), "wordart.png")
    grab_dialog(FillPageDialog(w.settings.units, w), "fill_page.png")
    grab_dialog(ExportPicturesDialog(2, w), "save_picture.png")
    import time
    grab_dialog(RecoveryDialog([{"path": "x", "original": "Spring newsletter.dtpub",
                                 "time": time.time() - 3600}], w), "recovery.png")

    # 8. a business card sheet (page only) ----------------------------------------------
    d = templates.build("bizcards")
    save(QPixmap.fromImage(render_thumbnail(d.pages[0], 700, 990)), "bizcards.png")

    print("done")


if __name__ == "__main__":
    main()
    os._exit(0)          # skip Qt's tear-down of worker threads; files are written

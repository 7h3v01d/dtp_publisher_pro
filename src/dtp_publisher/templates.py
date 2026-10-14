# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Built-in templates: flyers, signs, posters, newsletters, cards, invitations,
postcards, labels, business cards, photo albums, collages and certificates.

Every template is built through the normal item API, so it is exactly what
the user could have made by hand, and saves/loads like any other document.
All template coordinates are in millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from .document import Document
from .geometry import Geo
from .items import GroupItem, ImageItem, ShapeItem, TableItem, TextItem, WordArtItem
from .scene import GuideItem, PageScene
from .units import inch, mm

FILLER = ("Replace this text with your own words. Double-click a text box to start typing; "
          "when you are finished, click anywhere outside it.")
FILLER_LONG = (
    "This is a place for your story. Double-click to replace this text with your own.\n"
    "Keep paragraphs short so they are easy to read. You can change the font, size and colour "
    "with the text toolbar above the page.\n"
    "If the text does not fit, a small red box with dots appears in the bottom corner. Make the "
    "box bigger, use a smaller size, or choose Shrink text on overflow on the Format panel.")


class Page:
    """Builder for one page; all positions in millimetres."""

    def __init__(self, doc: Document, w_mm: float, h_mm: float, name: str = "",
                 margins_mm: float = 12.7, columns: int = 1, rows: int = 1,
                 gutter_mm: float = 5.0, background: str = "#ffffff"):
        self.sc: PageScene = doc.make_page(mm(w_mm), mm(h_mm), name, margins=[mm(margins_mm)] * 4,
                                           columns=columns, rows=rows, gutter=mm(gutter_mm),
                                           background=background)
        doc.add_page(self.sc)
        self._z = 0.0

    def _add(self, it):
        self._z += 1
        it.setZValue(self._z)
        self.sc.addItem(it)
        return it

    @staticmethod
    def _place(it, x, y, w, h, rot=0.0):
        it.set_geometry(Geo(mm(x), mm(y), mm(w), mm(h), rot))

    def text(self, x, y, w, h, text, size=14.0, family="Calibri", bold=False, italic=False,
             color="#201f1e", align="left", fit="none", valign="top", fill=None,
             padding=1.0, line=None, auto="") -> TextItem:
        t = TextItem(mm(w), mm(h))
        t.padding = mm(padding)
        t.text_color = QColor(color)
        t.set_text(text, family, size, bold, italic, QColor(color), align, line)
        t.fit, t.valign, t.auto = fit, valign, auto
        if fill:
            t.fill = QColor(fill)
        self._place(t, x, y, w, h)
        _no_overflow(t)
        return self._add(t)

    def story(self, x, y, w, h, heading, body, hsize=16.0, bsize=11.0, family="Calibri",
              hfamily="Georgia", color="#201f1e", hcolor="#1f3864", fit="none") -> TextItem:
        t = TextItem(mm(w), mm(h))
        t.padding = mm(1.5)
        t.set_text(heading, hfamily, hsize, True, False, QColor(hcolor))
        t.add_paragraphs(body, family, bsize, color=QColor(color), line_height=1.1,
                         space_after=mm(1.5))
        t.fit = fit
        self._place(t, x, y, w, h)
        _no_overflow(t)
        return self._add(t)

    def shape(self, kind, x, y, w, h, fill="#5b9bd5", stroke=None, sw=0.0, radius=4.0,
              rot=0.0, opacity=1.0) -> ShapeItem:
        s = ShapeItem(mm(w), mm(h), kind)
        s.fill = QColor(fill) if fill else QColor(0, 0, 0, 0)
        s.stroke = QColor(stroke) if stroke else QColor(0, 0, 0, 0)
        s.stroke_width = sw
        s.radius = mm(radius)
        s.setOpacity(opacity)
        self._place(s, x, y, w, h, rot)
        return self._add(s)

    def line(self, x, y, w, color="#7f7f7f", sw=1.0) -> ShapeItem:
        s = ShapeItem(mm(w), 4, "line")
        s.stroke, s.stroke_width = QColor(color), sw
        s.set_geometry(Geo(mm(x), mm(y) - 2, mm(w), 4, 0))
        return self._add(s)

    def picture(self, x, y, w, h, corner=0.0, border=None, bw=0.0, rot=0.0) -> ImageItem:
        im = ImageItem(mm(w), mm(h))
        im.corner = mm(corner)
        if border:
            im.stroke, im.stroke_width = QColor(border), bw
        self._place(im, x, y, w, h, rot)
        return self._add(im)

    def wordart(self, x, y, w, h, text, family="Arial Black", fill="#1f5fbf", fill2="#7fb2ff",
                stroke="#0b2a5c", sw=1.2, warp="none", gradient=True, shadow=True,
                bold=True, italic=False) -> WordArtItem:
        wa = WordArtItem(mm(w), mm(h), text)
        wa.apply_wordart_state({"font_family": family, "fill": fill, "fill2": fill2,
                                "stroke": stroke, "stroke_width": sw, "warp": warp,
                                "gradient": gradient, "shadow": shadow, "bold": bold,
                                "italic": italic})
        self._place(wa, x, y, w, h)
        return self._add(wa)

    def table(self, x, y, w, h, rows, cols, cells, header_fill="#077568") -> TableItem:
        t = TableItem(mm(w), mm(h), rows, cols)
        st = t.table_state()
        st["cells"] = {f"{r},{c}": v for (r, c), v in cells.items()}
        st["header_fill"] = header_fill
        t.apply_table_state(st)
        self._place(t, x, y, w, h)
        return self._add(t)

    def guide(self, orient: str, pos_mm: float):
        self.sc.attach_guide(GuideItem(orient, mm(pos_mm)))

    def group(self, items) -> GroupItem:
        g = GroupItem()
        self.sc.addItem(g)
        g.adopt(items)
        return g


# ═════════════════════════════════════════════════════════════════════════════
def _no_overflow(t: TextItem) -> None:
    """Fonts differ between computers (Windows' Calibri has a taller line than the
    Carlito that stands in for it elsewhere), so a box sized snugly on one can
    overflow on another.  A template box that overflows here is set to shrink
    its text just enough, so every design opens without overflow markers."""
    t.refit()
    if t.overflow and t.fit == "none":
        t.fit = "shrink"
        t.refit()


def flyer(doc: Document):
    acc, dark = "#c0392b", "#2c1810"
    p = Page(doc, 210, 297, background="#fffaf3", margins_mm=15)
    p.shape("rect", 0, 0, 210, 10, fill=acc)
    p.picture(15, 18, 180, 100, corner=3)
    p.text(15, 124, 180, 26, "Community Fair", 46, "Georgia", True, color=dark,
           align="center", fit="shrink")
    p.text(15, 151, 180, 12, "Saturday 14 March  ·  10 am – 3 pm", 20, color=acc,
           align="center", bold=True)
    p.shape("rect", 70, 167, 70, 1.2, fill=acc)
    p.text(25, 174, 160, 62, "Live music on the green\nHome-made food and cake stalls\n"
           "Games, face painting and a jumping castle\nRaffle with fantastic local prizes",
           17, color=dark, align="center", line=1.35, fit="shrink")
    p.shape("rect", 0, 250, 210, 47, fill=dark)
    p.text(15, 256, 180, 14, "Town Hall, 12 Main Street", 20, bold=True, color="#ffffff",
           align="center")
    p.text(15, 271, 180, 18, "Free entry · Everyone welcome · Enquiries 0400 000 000",
           13, color="#f5d7c6", align="center")


def sign(doc: Document):
    p = Page(doc, 297, 210, margins_mm=12)
    p.shape("rounded", 10, 10, 277, 190, fill="#ffffff", stroke="#c00000", sw=mm(4), radius=10)
    p.text(25, 30, 247, 110, "PLEASE USE\nTHE SIDE DOOR", 80, "Arial Black", True,
           color="#c00000", align="center", fit="best", valign="middle")
    p.shape("rect", 98, 148, 101, 1.5, fill="#c00000")
    p.text(25, 155, 247, 30, "Sorry for any inconvenience — thank you!", 26, color="#3b3b3b",
           align="center", fit="shrink", valign="middle")


def poster(doc: Document):
    p = Page(doc, 297, 420, background="#0f2741", margins_mm=18)
    p.picture(18, 18, 261, 230, corner=4, border="#ffffff", bw=3)
    p.wordart(28, 258, 241, 55, "GRAND OPENING", "Arial Black", "#ffb000", "#ffe38a",
              "#7a4a00", 1.5, "arch_down")
    p.text(28, 318, 241, 22, "Friday 1 May · from 9 am", 30, bold=True, color="#ffffff",
           align="center")
    p.text(38, 345, 221, 40, "Join us for free coffee, special offers and a chance to "
           "win a hamper. Bring the family!", 20, color="#cfe0f2", align="center",
           fit="shrink", line=1.2)
    p.text(18, 392, 261, 12, "123 High Street  ·  www.example.com", 16, color="#ffb000",
           align="center", bold=True)


def newsletter(doc: Document):
    navy, acc = "#1f3864", "#c55a11"
    for n in range(2):
        p = Page(doc, 210, 297, margins_mm=15, columns=3, gutter_mm=5)
        cw = (180 - 10) / 3
        c1, c2, c3 = 15, 15 + cw + 5, 15 + 2 * (cw + 5)
        if n == 0:
            p.shape("rect", 0, 0, 210, 44, fill=navy)
            p.text(15, 8, 180, 20, "The Neighbourhood News", 34, "Georgia", True,
                   color="#ffffff", fit="shrink")
            p.text(15, 30, 120, 8, "News, events and stories from our street", 12,
                   italic=True, color="#d9e2f3")
            p.text(135, 30, 60, 8, "Issue 1 · Autumn 2026", 11, color="#d9e2f3",
                   align="right")
            p.text(c1, 50, 2 * cw + 5, 13, "Main story headline", 22,
                   "Georgia", True, color=navy, fit="shrink")
            p.picture(c1, 65, 2 * cw + 5, 68)
            p.text(c1, 134, 2 * cw + 5, 6, "Photo caption: describe the picture in a sentence.",
                   9, italic=True, color="#595959")
            p.text(c1, 143, cw, 132, FILLER_LONG, 10.5, line=1.15)
            p.text(c2, 143, cw, 132, FILLER, 10.5, line=1.15)
            side = p.text(c3, 50, cw, 225, "", 11, fill="#eef3fa", padding=3)
            side.set_text("In this issue", "Georgia", 15, True, False, QColor(navy))
            side.add_paragraphs("Welcome from the editor\nGarden club news\nRecipe corner\n"
                                "What's on this month", "Calibri", 11, line_height=1.4)
            side.add_paragraphs("\nDates for your diary", "Georgia", 15, True,
                                color=QColor(navy))
            side.add_paragraphs("Sat 7 — Working bee, 9 am\nTue 10 — Book club, 7 pm\n"
                                "Sun 22 — Street BBQ, 12 pm", "Calibri", 11, line_height=1.4)
            side.refit()
        else:
            p.text(c1, 15, 180, 13, "Second story headline", 21, "Georgia", True, color=navy)
            p.text(c1, 30, cw, 110, FILLER_LONG, 10.5, line=1.15)
            p.text(c2, 30, cw, 110, FILLER, 10.5, line=1.15)
            p.picture(c3, 30, cw, 70)
            p.text(c3, 102, cw, 38, "Photo caption: who, what, where.", 9, italic=True,
                   color="#595959")
            p.shape("rect", 15, 146, 180, 0.8, fill=acc)
            p.story(c1, 152, 2 * cw + 5, 60, "Recipe corner", FILLER, 18, 10.5)
            p.picture(c3, 152, cw, 60, corner=3)
            p.table(c1, 218, 180, 50, 5, 3, {
                (0, 0): "Date", (0, 1): "Event", (0, 2): "Where",
                (1, 0): "Sat 7", (1, 1): "Working bee", (1, 2): "Community garden",
                (2, 0): "Tue 10", (2, 1): "Book club", (2, 2): "No. 14",
                (3, 0): "Sun 22", (3, 1): "Street BBQ", (3, 2): "The park",
                (4, 0): "Fri 27", (4, 1): "Movie night", (4, 2): "Hall"}, navy)
        p.line(15, 280, 180, "#bfbfbf", 0.75)
        p.text(15, 282, 120, 8, "The Neighbourhood News", 9, color="#7f7f7f")
        p.text(135, 282, 60, 8, "", 9, color="#7f7f7f", align="right", auto="page_of")


def greeting_card(doc: Document):
    acc = "#b03a6b"
    out = Page(doc, 297, 210, "Outside — print first", margins_mm=10)
    out.guide("V", 148.5)
    out.picture(160, 14, 125, 118, corner=4)
    out.wordart(158, 138, 129, 36, "Happy Birthday!", "Georgia", acc, "#f4a6c8", "#5e1336",
                1.0, "arch_down", italic=True)
    out.text(160, 178, 125, 12, "to someone very special", 16, "Georgia", italic=True,
             color="#5e1336", align="center")
    out.text(20, 185, 108, 10, "Made with love", 10, italic=True, color="#7f7f7f",
             align="center")
    out.shape("heart", 66, 168, 16, 14, fill=acc)
    ins = Page(doc, 297, 210, "Inside", margins_mm=10)
    ins.guide("V", 148.5)
    ins.picture(25, 30, 98, 130, corner=4)
    ins.text(165, 40, 115, 120, "Dear …,\n\nWishing you a wonderful birthday filled with "
             "laughter, cake and all your favourite people.\n\nWith love,\n…", 20,
             "Segoe Script", color="#3b1f2b", align="center", valign="middle", fit="shrink",
             line=1.2)


def invitation(doc: Document):
    acc = "#4b2c83"
    p = Page(doc, 127, 177.8, background="#f7f3ff", margins_mm=8)
    p.shape("rounded", 5, 5, 117, 167.8, fill=None, stroke=acc, sw=2, radius=5)
    for x, y, s in ((14, 14, 8), (104, 18, 6), (18, 150, 6), (100, 152, 9)):
        p.shape("star", x, y, s, s, fill="#f2c94c")
    p.wordart(14, 28, 99, 26, "You're Invited!", "Georgia", acc, "#9b7fd4", "#2b1752", 0.8,
              "arch_down", italic=True)
    p.text(14, 60, 99, 12, "to Grandpa's 80th Birthday", 15, "Georgia", True, color=acc,
           align="center", fit="shrink")
    p.picture(33.5, 76, 60, 42, corner=21)
    p.text(14, 122, 99, 30, "Sunday 9 August, 12 noon\nThe Bowls Club, 4 River Road\n"
           "Lunch provided", 12, color="#2b1752", align="center", line=1.3, fit="shrink")
    p.text(14, 154, 99, 9, "RSVP to Mary by 1 August · 0400 000 000", 9, italic=True,
           color="#5f4b8b", align="center")


def postcard(doc: Document):
    front = Page(doc, 152.4, 101.6, "Front", margins_mm=5)
    front.picture(0, 0, 152.4, 101.6)
    front.shape("rect", 0, 82, 152.4, 19.6, fill="#000000", opacity=0.55)
    front.text(6, 85, 140, 13, "Greetings from the coast!", 22, "Georgia", True,
               color="#ffffff", fit="shrink", valign="middle")
    back = Page(doc, 152.4, 101.6, "Back", margins_mm=5)
    back.text(8, 8, 66, 85, "Write your message here…", 12, "Segoe Script", color="#1f3864",
              line=1.3, fit="shrink")
    back.shape("line", 33.5, 50.25, 85, 0.5, fill=None, stroke="#a6a6a6", sw=0.75, rot=90)
    back.shape("rect", 124, 8, 20, 24, fill=None, stroke="#a6a6a6", sw=0.75)
    back.text(124, 16, 20, 8, "Stamp", 8, color="#a6a6a6", align="center")
    for i in range(4):
        back.line(84, 50 + i * 10, 62, "#a6a6a6", 0.75)


def address_labels(doc: Document):
    # Avery L7163 / J8163 layout: 2 × 7 labels, 99.1 × 38.1 mm
    p = Page(doc, 210, 297, margins_mm=0)
    for r in range(7):
        for c in range(2):
            x, y = 4.65 + c * 101.6, 15.15 + r * 38.1
            p.text(x + 4, y + 3, 91, 32, "Name\nStreet address\nSuburb  STATE  0000", 12,
                   color="#000000", valign="middle", fit="shrink", line=1.15)


def business_cards(doc: Document):
    acc = "#077568"
    p = Page(doc, 210, 297, margins_mm=0)
    first = None
    for r in range(5):
        for c in range(2):
            x, y = 20 + c * 85, 11 + r * 55
            parts = [
                p.shape("rect", x, y, 85, 55, fill="#ffffff", stroke="#d9d9d9", sw=0.5),
                p.shape("rect", x, y, 5, 55, fill=acc),
                p.text(x + 10, y + 8, 70, 10, "Your Name", 16, "Georgia", True, color="#1b1b1b"),
                p.text(x + 10, y + 18, 70, 7, "Job title or business", 10, color=acc),
                p.shape("rect", x + 10, y + 27, 30, 0.6, fill=acc),
                p.text(x + 10, y + 31, 70, 20, "0400 000 000\nname@example.com\nwww.example.com",
                       9, color="#404040", line=1.2),
            ]
            g = p.group(parts)
            g.name = "Business card" if first is None else "Business card (copy)"
            first = first or g


def photo_album(doc: Document):
    bg = "#faf7f2"
    p1 = Page(doc, 297, 210, "Album page 1", background=bg, margins_mm=12)
    p1.text(12, 8, 273, 14, "Our Summer Holiday", 26, "Georgia", True, color="#3c2f2f",
            align="center")
    w, h = 85, 64
    for r in range(2):
        for c in range(3):
            x, y = 12 + c * (w + 9), 28 + r * (h + 20)
            p1.picture(x, y, w, h, border="#ffffff", bw=4)
            p1.text(x, y + h + 2, w, 9, "Caption", 11, "Georgia", italic=True,
                    color="#5a4a42", align="center")
    p2 = Page(doc, 297, 210, "Album page 2", background=bg, margins_mm=12)
    w, h = 130, 82
    for r in range(2):
        for c in range(2):
            x, y = 12 + c * (w + 13), 10 + r * (h + 15)
            ph = p2.picture(x, y, w, h, border="#ffffff", bw=4, rot=(-2 if (r + c) % 2 else 2))
            ph.wrap = "none"           # tilted photos reach over their captions
            p2.text(x, y + h + 3, w, 9, "Caption", 11, "Georgia", italic=True,
                    color="#5a4a42", align="center")


def collage(doc: Document):
    s = 304.8
    p = Page(doc, s, s, background="#1e1e1e", margins_mm=10)
    p.picture(12, 12, s - 24, 170, border="#ffffff", bw=3)
    w = (s - 24 - 3 * 8) / 4
    for i in range(4):
        p.picture(12 + i * (w + 8), 192, w, 75, border="#ffffff", bw=3)
    p.text(12, 274, s - 24, 20, "Family Memories 2026", 34, "Georgia", True, color="#ffffff",
           align="center", fit="shrink")


def certificate(doc: Document):
    gold, navy = "#b8860b", "#1f2a44"
    p = Page(doc, 297, 210, background="#fffdf6", margins_mm=15)
    p.shape("rect", 8, 8, 281, 194, fill=None, stroke=navy, sw=mm(2.5))
    p.shape("rect", 13, 13, 271, 184, fill=None, stroke=gold, sw=1.2)
    p.wordart(40, 26, 217, 30, "Certificate of Achievement", "Georgia", navy, "#41598a",
              "#0c1426", 0.6, "none", gradient=True, shadow=False)
    p.text(40, 66, 217, 10, "This certificate is proudly presented to", 15, "Georgia",
           italic=True, color="#444444", align="center")
    p.text(40, 80, 217, 24, "Recipient Name", 38, "Segoe Script", color=navy, align="center",
           fit="shrink", valign="middle")
    p.line(70, 106, 157, gold, 1.2)
    p.text(50, 112, 197, 24, "for outstanding effort and dedication.", 15, "Georgia",
           color="#444444", align="center", fit="shrink")
    p.shape("star", 133.5, 140, 30, 30, fill=gold, stroke="#8a6508", sw=0.8)
    for x, label in ((40, "Signature"), (187, "Date")):
        p.line(x, 172, 70, "#444444", 0.8)
        p.text(x, 174, 70, 8, label, 11, color="#444444", align="center")


# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class Template:
    key: str
    name: str
    category: str
    description: str
    build: Callable[[Document], None]


TEMPLATES: List[Template] = [
    Template("flyer", "Event flyer", "Flyers & posters",
             "A4 flyer with a photo, big title and event details.", flyer),
    Template("sign", "Notice / sign", "Flyers & posters",
             "Big bold A4 landscape sign that's easy to read from afar.", sign),
    Template("poster", "Poster", "Flyers & posters",
             "A3 poster with a large photo and curved headline.", poster),
    Template("newsletter", "Newsletter", "Newsletters",
             "Two A4 pages in three columns with masthead, stories, photos, "
             "an events table and page numbers.", newsletter),
    Template("card", "Greeting card", "Cards & invitations",
             "Folds in half. Print the Outside page, then turn the paper over and print the "
             "Inside page.", greeting_card),
    Template("invite", "Party invitation", "Cards & invitations",
             "5 × 7 inch invitation with photo and details.", invitation),
    Template("postcard", "Postcard", "Cards & invitations",
             "6 × 4 inch postcard: photo front, message and address back.", postcard),
    Template("labels", "Address labels (14 per sheet)", "Labels & business cards",
             "Fits Avery L7163 / J8163 label sheets (99.1 × 38.1 mm).", address_labels),
    Template("bizcards", "Business cards (10 per sheet)", "Labels & business cards",
             "Ten 85 × 55 mm cards on A4. Design one, then use Arrange ▸ Fill page with copies.",
             business_cards),
    Template("album", "Photo album pages", "Photo albums",
             "Two landscape A4 pages of photo frames with captions.", photo_album),
    Template("collage", "Photo collage", "Photo albums",
             "12 × 12 inch scrapbook-style collage.", collage),
    Template("certificate", "Certificate", "Flyers & posters",
             "A4 landscape certificate with border and signature lines.", certificate),
]

TEMPLATE_BY_KEY = {t.key: t for t in TEMPLATES}
CATEGORIES = ["Flyers & posters", "Newsletters", "Cards & invitations",
              "Labels & business cards", "Photo albums"]


def build(key: str) -> Document:
    t = TEMPLATE_BY_KEY[key]
    doc = Document()
    doc.title = t.name
    t.build(doc)
    from .fields import refresh_fields
    refresh_fields(doc)
    doc.undo_stack.clear()
    return doc


def blank(width_pt: float, height_pt: float, margins_pt: Optional[float] = None) -> Document:
    doc = Document()
    sc = doc.make_page(width_pt, height_pt)
    if margins_pt is not None:
        st = sc.setup_state()
        st["margins"] = [margins_pt] * 4
        sc.apply_setup(st)
    doc.add_page(sc)
    doc.undo_stack.clear()
    return doc

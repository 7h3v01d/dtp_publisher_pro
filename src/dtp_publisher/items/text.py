# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""TextItem — a rich-text frame.

* Rich text (per-character fonts, colours, bold…) stored as Qt HTML.
* Autofit works by *scaling* the text block rather than rewriting font sizes,
  so the user's formatting is never destroyed:
    none   – text keeps its size; overflow is clipped and flagged
    shrink – shrinks to fit when it overflows, otherwise actual size
    best   – grows or shrinks to fill the frame
    grow   – the frame grows/shrinks in height to fit the text
* Editing happens in place (double-click); the whole edit session becomes a
  single undo step when editing ends.
* Linked text boxes: boxes can be chained (``link_next``/``link_prev``).  The
  first box of a chain owns the story's QTextDocument and every box in the
  chain displays that same document, each showing its own slice cut at line
  boundaries.  Boxes that are deleted (not in a scene) are skipped, so undo of
  a delete simply puts the box back into the flow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                         QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                         QTextDocumentFragment, QTextListFormat, QTextOption)
from PyQt6.QtWidgets import QGraphicsTextItem, QStyle, QStyleOptionGraphicsItem

from .. import theme
from ..commands import TextCmd
from ..geometry import geo_from_local_rect
from .base import BaseItem, color_from, color_to_str, num

FIT_MODES = {"none": "Do not autofit", "shrink": "Shrink text on overflow",
             "best": "Best fit", "grow": "Grow text box to fit"}
VALIGNS = {"top": "Top", "middle": "Middle", "bottom": "Bottom"}
ALIGNS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
    "justify": Qt.AlignmentFlag.AlignJustify,
}

DEFAULT_FAMILY = "Calibri"
DEFAULT_SIZE = 14.0

_LAYOUT_DEVICE = None


def layout_device():
    """A 72-dpi paint device for text layout.

    Scene units are points (1/72 in).  Without this, Qt lays text out at the
    screen's DPI (96, or 120 on a 125% Windows display), so text came out
    33–66% too large and line breaks differed from one computer to the next.
    """
    global _LAYOUT_DEVICE
    if _LAYOUT_DEVICE is None:
        img = QImage(4, 4, QImage.Format.Format_ARGB32)
        dpm = round(72 / 0.0254)
        img.setDotsPerMeterX(dpm)
        img.setDotsPerMeterY(dpm)
        _LAYOUT_DEVICE = img
    return _LAYOUT_DEVICE


class _FrameText(QGraphicsTextItem):
    """The editable text inside a frame."""

    def __init__(self, frame: "TextItem"):
        super().__init__(frame)
        self.frame = frame
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        # get a real exposed rect, so a box showing page 9 of a long linked story
        # only draws the lines it shows
        self.setFlag(self.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def paint(self, p: QPainter, option, widget=None):
        o = QStyleOptionGraphicsItem(option)
        o.state = o.state & ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus)
        clip = self.frame.clip_rect_in_child()
        o.exposedRect = o.exposedRect.intersected(clip.adjusted(-2, -2, 2, 2))
        p.save()
        p.setClipRect(clip)
        super().paint(p, o, widget)
        p.restore()

    def shape(self) -> QPainterPath:
        # only the visible part of the document catches clicks (the document of a
        # linked story can be many pages tall)
        p = QPainterPath()
        p.addRect(self.frame.clip_rect_in_child())
        return p

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        sc = self.scene()
        # Keep editing when focus merely left the canvas (e.g. to the font box on the
        # format bar or a menu) so formatting still applies to the selected words.
        # Focus moving to something else *on the page* ends the edit.
        if e.reason() != Qt.FocusReason.PopupFocusReason and sc is not None and sc.hasFocus():
            self.frame.end_edit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.frame.end_edit()
            self.frame.setSelected(True)
            self.frame.setFocus()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        super().keyReleaseEvent(e)
        self.frame.notify_caret()

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.frame.notify_caret()


class TextItem(BaseItem):
    CAN_FLIP = False
    KIND = "text"
    DISPLAY = "Text box"
    MIN_W = 18.0
    MIN_H = 14.0
    SHOW_BOUNDARY = True

    def __init__(self, w: float = 240, h: float = 90):
        super().__init__(w, h)
        self.padding = 5.0
        self.fit = "none"
        self.valign = "top"
        self.text_color = QColor(32, 31, 30)
        self.auto = ""            # "", "page", "page_of", "date": text kept up to date
        self.editing = False
        self.overflow = False
        self._scale = 1.0
        self._edit_html = ""
        self._refitting = False
        self.link_next: Optional["TextItem"] = None
        self.link_prev: Optional["TextItem"] = None
        self._pending_next = ""                       # uid to link to after loading
        self._slice: Tuple[float, float] = (0.0, 0.0)        # visible doc y-range (linked)
        self._slice_pos: Tuple[int, int] = (0, 0)            # visible char range (linked)
        self._ti = _FrameText(self)
        # the item owns its document (parented to the item, not the text control,
        # so it survives being swapped out while this box shows a linked story)
        doc = QTextDocument(self)
        self._own_doc = doc
        doc.documentLayout().setPaintDevice(layout_device())
        doc.setUseDesignMetrics(True)
        doc.setDocumentMargin(0)
        opt = doc.defaultTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(opt)
        doc.setDefaultFont(QFont(DEFAULT_FAMILY, int(DEFAULT_SIZE)))
        self._ti.setDocument(doc)
        self._ti.setDefaultTextColor(self.text_color)
        self._set_block_defaults()
        doc.contentsChanged.connect(self._on_contents_changed)
        self.refit()

    # ── content API ─────────────────────────────────────────────────────────
    @property
    def document(self):
        return self._ti.document()

    def text_child(self) -> QGraphicsTextItem:
        return self._ti

    def html(self) -> str:
        return self.document.toHtml()

    def set_html(self, html: str):
        self.document.setHtml(html)
        self.refit()
        self.update()

    def plain_text(self) -> str:
        return self.document.toPlainText()

    def is_empty(self) -> bool:
        return self.document.isEmpty()

    def update_auto(self, text: str):
        """Replace the content of a field box (page number/date), keeping its style."""
        if self.plain_text() == text or self.editing:
            return
        fmt = self.current_char_format()
        c = QTextCursor(self.document)
        c.select(QTextCursor.SelectionType.Document)
        c.insertText(text, fmt)
        self.refit()

    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.auto:
            return {"page": "Page number", "page_of": "Page number",
                    "date": "Date"}.get(self.auto, "Field")
        t = self.plain_text().strip().replace("\n", " ")
        return f"Text — {t[:28]}{'…' if len(t) > 28 else ''}" if t else "Text box"

    def _set_block_defaults(self):
        c = QTextCursor(self.document)
        fmt = QTextCharFormat()
        fmt.setFont(self.document.defaultFont())
        fmt.setForeground(QBrush(self.text_color))
        c.setBlockCharFormat(fmt)

    def set_text(self, text: str, family: str = DEFAULT_FAMILY, size: float = DEFAULT_SIZE,
                 bold: bool = False, italic: bool = False, color: Optional[QColor] = None,
                 align: str = "left", line_height: Optional[float] = None):
        """Replace content with uniformly styled text (used by templates)."""
        self.document.clear()
        self.add_paragraphs(text, family, size, bold, italic, color, align, line_height,
                            first=True)

    def add_paragraphs(self, text: str, family: str = DEFAULT_FAMILY,
                       size: float = DEFAULT_SIZE, bold: bool = False, italic: bool = False,
                       color: Optional[QColor] = None, align: str = "left",
                       line_height: Optional[float] = None, first: bool = False,
                       space_after: float = 0.0):
        c = QTextCursor(self.document)
        c.movePosition(QTextCursor.MoveOperation.End)
        cf = QTextCharFormat()
        f = QFont(family)
        f.setPointSizeF(size)
        f.setBold(bold)
        f.setItalic(italic)
        cf.setFont(f)
        cf.setForeground(QBrush(color if color is not None else self.text_color))
        bf = QTextBlockFormat()
        bf.setAlignment(ALIGNS.get(align, Qt.AlignmentFlag.AlignLeft))
        if line_height:
            bf.setLineHeight(line_height * 100, 1)  # ProportionalHeight
        if space_after:
            bf.setBottomMargin(round(space_after))   # Qt HTML stores whole units
        for i, para in enumerate(text.split("\n")):
            if i > 0 or (not first and not self.document.isEmpty()):
                c.insertBlock(bf, cf)
            else:
                c.setBlockFormat(bf)
                c.setBlockCharFormat(cf)
            c.insertText(para, cf)
        self.refit()

    # ── fitting ──────────────────────────────────────────────────────────────
    def inner_rect(self) -> QRectF:
        p = min(self.padding, self._w / 2 - 1, self._h / 2 - 1)
        p = max(p, 0.0)
        return QRectF(p, p, max(self._w - 2 * p, 2.0), max(self._h - 2 * p, 2.0))

    def clip_rect_in_child(self) -> QRectF:
        if self.is_linked():
            a, b = self._slice
            tl = self._ti.pos()
            return QRectF(-tl.x(), a, self._w, max(b - a, 0.0))
        s = self._ti.scale() or 1.0
        tl = self._ti.pos()
        r = self.rect()
        return QRectF((r.left() - tl.x()) / s, (r.top() - tl.y()) / s, r.width() / s, r.height() / s)

    def _height_at(self, scale: float, inner_w: float) -> float:
        doc = self.document
        doc.setTextWidth(max(inner_w / scale, 1.0))
        return doc.size().height() * scale

    def _fit_scale(self, inner: QRectF) -> float:
        if self.is_empty():
            return 1.0
        lo, hi = 0.05, 8.0
        if self._height_at(hi, inner.width()) <= inner.height():
            return hi
        if self._height_at(lo, inner.width()) > inner.height():
            return lo
        for _ in range(22):
            mid = (lo + hi) / 2
            if self._height_at(mid, inner.width()) <= inner.height():
                lo = mid
            else:
                hi = mid
        return lo

    def refit(self):
        if self.is_linked():
            self.chain_root().layout_chain()
            return
        if self._refitting:
            return
        self._refitting = True
        try:
            inner = self.inner_rect()
            s = 1.0
            if self.fit in ("best", "shrink"):
                s = self._fit_scale(inner)
                if self.fit == "shrink":
                    s = min(1.0, s)
            self._scale = s
            self._ti.setScale(s)
            self._ti.setTextWidth(max(inner.width() / s, 1.0))
            text_h = self.document.size().height() * s
            if self.fit == "grow":
                need = max(self.MIN_H, text_h + 2 * inner.top())
                if abs(need - self._h) > 0.25:
                    g = self.geometry()
                    # on_resized() -> refit() is a no-op while _refitting is set
                    self.set_geometry(geo_from_local_rect(g, QRectF(0, 0, g.w, need)))
                    inner = self.inner_rect()
            off = 0.0
            if text_h < inner.height():
                if self.valign == "middle":
                    off = (inner.height() - text_h) / 2
                elif self.valign == "bottom":
                    off = inner.height() - text_h
            self._ti.setPos(inner.left(), inner.top() + off)
            self.overflow = text_h > inner.height() + 0.75
        finally:
            self._refitting = False

    def on_resized(self):
        self.refit()

    def on_prop_changed(self, key: str):
        if key in ("fit", "valign", "padding"):
            self.refit()
        elif key == "text_color":
            self._ti.setDefaultTextColor(self.text_color)

    def _on_contents_changed(self):
        # fired by this item's *own* document, i.e. when it is a story's owner
        if self.is_linked():
            self.layout_chain()
            for f in self.chain():
                f.update()
                if f.editing:
                    f.notify_caret()
            return
        self.refit()
        self.update()
        self.notify_caret()

    def notify_caret(self):
        sc = self.page_scene()
        if sc is not None and self.editing:
            if self.is_linked() and self._follow_caret():
                return
            sc.textFormatChanged.emit(self)

    # ── linked text boxes ────────────────────────────────────────────────────
    def is_linked(self) -> bool:
        return self.link_next is not None or self.link_prev is not None

    def chain_root(self) -> "TextItem":
        t, seen = self, {id(self)}
        while t.link_prev is not None and id(t.link_prev) not in seen:
            t = t.link_prev
            seen.add(id(t))
        return t

    def chain(self) -> List["TextItem"]:
        out, t, seen = [], self.chain_root(), set()
        while t is not None and id(t) not in seen:
            out.append(t)
            seen.add(id(t))
            t = t.link_next
        return out

    def live_chain(self) -> List["TextItem"]:
        return [f for f in self.chain() if f.scene() is not None]

    def story_owner(self) -> "TextItem":
        return self.chain_root()

    def next_live(self) -> Optional["TextItem"]:
        t, seen = self.link_next, set()
        while t is not None and id(t) not in seen:
            if t.scene() is not None:
                return t
            seen.add(id(t))
            t = t.link_next
        return None

    @staticmethod
    def _line_spans(doc: QTextDocument) -> List[Tuple[float, float, int, int]]:
        """(top, bottom, first_char, end_char) for every laid-out line."""
        lay = doc.documentLayout()
        lay.documentSize()                       # make sure layout is current
        spans = []
        b = doc.begin()
        while b.isValid():
            top = lay.blockBoundingRect(b).top()
            bl = b.layout()
            for i in range(bl.lineCount()):
                ln = bl.lineAt(i)
                t = top + ln.y()
                spans.append((t, t + ln.height(), b.position() + ln.textStart(),
                              b.position() + ln.textStart() + ln.textLength()))
            b = b.next()
        return spans

    def layout_chain(self):
        """Flow the story through the live boxes of the chain (call on the root)."""
        frames = self.live_chain()
        if not frames:
            return
        doc = self._own_doc
        doc.setTextWidth(max(frames[0].inner_rect().width(), 1.0))
        lines = self._line_spans(doc)
        k, offset, pos = 0, 0.0, 0
        for f in frames:
            f._scale = 1.0
            f._ti.setScale(1.0)
            inner = f.inner_rect()
            start, end = offset, offset + inner.height()
            cut, first, last = start, pos, pos
            while k < len(lines) and lines[k][1] <= end + 0.5:
                cut, last = lines[k][1], lines[k][3]
                k += 1
            if cut == start and k < len(lines) and inner.height() >= 4:
                # a single line taller than the box: show it rather than stall
                cut, last = lines[k][1], lines[k][3]
                k += 1
            f._slice = (start, cut)
            f._slice_pos = (first, last)
            f._ti.setPos(inner.left(), inner.top() - start)
            f.overflow = False
            f.prepareGeometryChange()
            f.update()
            f._ti.update()
            if k < len(lines):
                offset, pos = lines[k][0], lines[k][2]
            else:
                offset, pos = cut + 1e6, doc.characterCount()
        frames[-1].overflow = k < len(lines)

    def slice_html(self) -> str:
        """HTML of just the text this linked box shows (for copies)."""
        a, b = self._slice_pos
        c = QTextCursor(self.document)
        c.setPosition(min(a, self.document.characterCount() - 1))
        c.setPosition(min(b, self.document.characterCount() - 1),
                      QTextCursor.MoveMode.KeepAnchor)
        return QTextDocumentFragment(c).toHtml()

    def _follow_caret(self) -> bool:
        """Move the editing session to the box that now shows the caret."""
        c = self._ti.textCursor()
        blk = c.block()
        lay = self.document.documentLayout()
        bl = blk.layout()
        ln = bl.lineForTextPosition(c.positionInBlock())
        y = lay.blockBoundingRect(blk).top() + (ln.y() if ln.isValid() else 0.0)
        a, b = self._slice
        if a - 0.5 <= y < b - 0.5 or (b <= a and y >= a):
            return False
        for g in self.live_chain():
            ga, gb = g._slice
            if g is not self and ga - 0.5 <= y < gb - 0.5:
                self._hand_edit_to(g, c)
                return True
        return False

    def _hand_edit_to(self, g: "TextItem", cursor: QTextCursor):
        session = self._edit_html
        self.editing = False
        self._ti.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._ti.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        g.editing = True
        g._edit_html = session
        g._ti.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        g._ti.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        sc = g.page_scene()
        if sc is not None and sc is not self.page_scene() and sc.doc is not None:
            sc.doc.showPageRequested.emit(sc)
        g._ti.setFocus(Qt.FocusReason.OtherFocusReason)
        gc = g._ti.textCursor()
        gc.setPosition(cursor.anchor())
        gc.setPosition(cursor.position(), QTextCursor.MoveMode.KeepAnchor)
        g._ti.setTextCursor(gc)
        self.update()
        g.update()
        if sc is not None:
            sc.textEditingChanged.emit(g)

    # ── editing ──────────────────────────────────────────────────────────────
    def on_double_click(self, e):
        self.begin_edit(e.scenePos())

    def begin_edit(self, scene_pos: Optional[QPointF] = None, select_all: bool = False):
        if self.locked or self.editing:
            return
        sc = self.page_scene()
        self.editing = True
        self._edit_html = self.html()
        self._ti.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._ti.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self._ti.setFocus(Qt.FocusReason.MouseFocusReason)
        c = self._ti.textCursor()
        if select_all:
            c.select(QTextCursor.SelectionType.Document)
        elif scene_pos is not None:
            lp = self._ti.mapFromScene(scene_pos)
            pos = self.document.documentLayout().hitTest(lp, Qt.HitTestAccuracy.FuzzyHit)
            c.setPosition(max(pos, 0))
        else:
            c.movePosition(QTextCursor.MoveOperation.End)
        self._ti.setTextCursor(c)
        self.update()
        if sc is not None:
            sc.textEditingChanged.emit(self)

    def end_edit(self):
        if not self.editing:
            return
        self.editing = False
        self._ti.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._ti.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        c = self._ti.textCursor()
        c.clearSelection()
        self._ti.setTextCursor(c)
        if self._ti.hasFocus():
            self._ti.clearFocus()
        new = self.html()
        sc = self.page_scene()
        if new != self._edit_html and sc is not None:
            sc.push(TextCmd(sc, self, self._edit_html, new))
        self._edit_html = ""
        self.update()
        if sc is not None:
            sc.textEditingChanged.emit(None)

    # ── formatting (used by the format bar) ─────────────────────────────────
    def _apply(self, fn, label: str):
        """Run ``fn(cursor)`` on the editing selection, or the whole text."""
        if self.editing:
            c = self._ti.textCursor()
            fn(c, False)
            self._ti.setTextCursor(c)
            self.refit()
            return
        old = self.html()
        c = QTextCursor(self.document)
        c.select(QTextCursor.SelectionType.Document)
        fn(c, True)
        new = self.html()
        self.refit()
        sc = self.page_scene()
        if sc is not None and new != old:
            sc.push(TextCmd(sc, self, old, new, label))

    def merge_char_format(self, fmt: QTextCharFormat, label: str = "Format text"):
        def f(c: QTextCursor, whole: bool):
            c.mergeCharFormat(fmt)
            if whole:
                c.mergeBlockCharFormat(fmt)
        self._apply(f, label)

    def merge_block_format(self, fmt: QTextBlockFormat, label: str = "Format paragraph"):
        self._apply(lambda c, whole: c.mergeBlockFormat(fmt), label)

    def set_alignment(self, key: str):
        bf = QTextBlockFormat()
        bf.setAlignment(ALIGNS.get(key, Qt.AlignmentFlag.AlignLeft))
        self.merge_block_format(bf, "Align text")

    def set_line_spacing(self, factor: float):
        bf = QTextBlockFormat()
        bf.setLineHeight(factor * 100, 1)
        self.merge_block_format(bf, "Line spacing")

    def set_list(self, style: Optional[QTextListFormat.Style]):
        def f(c: QTextCursor, whole: bool):
            if style is None:
                start, end = c.selectionStart(), c.selectionEnd()
                b = self.document.findBlock(start)
                while b.isValid() and b.position() <= end:
                    lst = b.textList()
                    if lst is not None:
                        lst.remove(b)
                    bc = QTextCursor(b)
                    bf = b.blockFormat()
                    bf.setIndent(0)
                    bc.setBlockFormat(bf)
                    b = b.next()
            else:
                lf = QTextListFormat()
                lf.setStyle(style)
                lf.setIndent(1)
                c.createList(lf)
        self._apply(f, "Bullets")

    def current_char_format(self) -> QTextCharFormat:
        if self.editing:
            return self._ti.textCursor().charFormat()
        c = QTextCursor(self.document)
        if not self.is_empty():
            c.setPosition(1)
            return c.charFormat()
        return c.blockCharFormat()

    def current_block_format(self) -> QTextBlockFormat:
        if self.editing:
            return self._ti.textCursor().blockFormat()
        return QTextCursor(self.document).blockFormat()

    def current_list_style(self):
        c = self._ti.textCursor() if self.editing else QTextCursor(self.document)
        lst = c.currentList()
        return lst.format().style() if lst is not None else None

    def itemChange(self, change, value):
        r = super().itemChange(change, value)
        if (change == self.GraphicsItemChange.ItemSceneHasChanged and self.is_linked()):
            self.chain_root().layout_chain()      # a box left or rejoined the flow
        return r

    # ── painting ─────────────────────────────────────────────────────────────
    def paint_content(self, p: QPainter):
        if self.fill.alpha() or self.stroke_width > 0:
            p.setPen(self.make_pen())
            p.setBrush(self.fill)
            p.drawRect(self.rect())

    def paint_overlay(self, p: QPainter):
        super().paint_overlay(p)
        z = self._zoom()
        if self.is_linked():
            self._paint_link_marks(p, z)
            if self.overflow:
                self._paint_overflow(p, z)
            return
        if self.is_empty() and not self.editing:
            p.save()
            p.setPen(theme.color("c_bounds"))
            f = QFont(theme.tokens()["font"])
            f.setPointSizeF(max(10.0 / z, 1.0))
            p.setFont(f)
            p.drawText(self.inner_rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       "Double-click to type")
            p.restore()
        if self.overflow:
            self._paint_overflow(p, z)

    def _paint_link_marks(self, p: QPainter, z: float):
        if not (self.isSelected() or self.editing):
            return
        s = 15 / z
        col = theme.color("c_select")
        p.save()
        pen = QPen(col, 1.5)
        pen.setCosmetic(True)
        f = QFont(theme.tokens()["font"])
        f.setPointSizeF(max(9.0 / z, 0.5))
        f.setBold(True)
        p.setFont(f)
        for r, label, show in ((QRectF(2 / z, 2 / z, s, s), "\u2190", self.link_prev is not None),
                               (QRectF(self._w - s - 2 / z, self._h - s - 2 / z, s, s), "\u2192",
                                self.link_next is not None and not self.overflow)):
            if not show:
                continue
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255))
            p.drawRect(r)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    def _paint_overflow(self, p: QPainter, z: float):
        s = 16 / z
        r = QRectF(self._w - s - 2 / z, self._h - s - 2 / z, s, s)
        p.save()
        pen = QPen(theme.color("c_snap"), 1.5)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(r)
        p.setBrush(theme.color("c_snap"))
        d = s / 9
        for i in range(3):
            p.drawEllipse(QPointF(r.left() + s * (0.25 + 0.25 * i), r.center().y()), d, d)
        p.restore()

    # ── serialisation ────────────────────────────────────────────────────────
    def writes_story(self) -> bool:
        """The first live box of a chain stores the story; the others store nothing."""
        if not self.is_linked():
            return True
        live = self.live_chain()
        return (live[0] is self) if live else (self.chain_root() is self)

    def extra_to_dict(self) -> Dict[str, Any]:
        d = {"html": self.html() if self.writes_story() else "", "fit": self.fit,
             "valign": self.valign, "padding": self.padding,
             "text_color": color_to_str(self.text_color), "auto": self.auto}
        if self.is_linked():
            d["linked"] = True
            nxt = self.next_live()
            if nxt is not None:
                d["link_next"] = nxt.uid
        return d

    def apply_extra(self, d: Dict[str, Any]):
        self.fit = d.get("fit") if d.get("fit") in FIT_MODES else "none"
        self.valign = d.get("valign") if d.get("valign") in VALIGNS else "top"
        self.padding = num(d, "padding", 5.0, 0, 500)
        a = d.get("auto", "")
        self.auto = a if a in ("page", "page_of", "date") else ""
        self.text_color = color_from(d.get("text_color"), self.text_color)
        self._ti.setDefaultTextColor(self.text_color)
        self._pending_next = str(d.get("link_next") or "")[:64]
        html = d.get("html")
        if isinstance(html, str):
            self.document.setHtml(html)
        elif isinstance(d.get("text"), str):
            self.set_text(d["text"])

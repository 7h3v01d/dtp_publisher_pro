# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""FlowLayout — the text layout behind every text box.

Qt's own document layout puts all text in one column of one width.  Desktop
publishing needs two more things, and this layout provides both:

* **Regions.**  A linked story flows through several boxes, possibly of
  different widths.  Each box is a *region*; regions are stacked one under
  another in the document's coordinates, so a box shows its region simply by
  showing that band of the document (as before).
* **Exclusions.**  Pictures (or anything set to wrap text) in front of a box
  are holes the lines flow around: each line takes the widest free stretch of
  its region at its height, or moves down past the obstacle.

With one region and no exclusions the result is the same as Qt's own layout,
line for line (``tests/test_flowlayout.py`` checks this against Qt on every
template); the arithmetic below deliberately mirrors
``QTextDocumentLayoutPrivate::layoutBlock`` (Qt 6), including its 1/64-point
rounding, so nothing anyone has already made moves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PyQt6.QtCore import QLineF, QPointF, QRectF, QSizeF, Qt
from PyQt6.QtGui import (QAbstractTextDocumentLayout, QFont, QFontMetrics, QPainter, QPalette,
                         QTextBlock, QTextBlockFormat, QTextDocument, QTextFormat, QTextLayout,
                         QTextLine,
                         QTextListFormat, QTextOption)

INF = float("inf")
MIN_LINE_WIDTH = 36.0          # gaps beside a picture narrower than this are skipped (pt)
MIN_LINE_FRACTION = 0.2        # ... or than this share of the column


def fx(v: float) -> float:
    """Convert like Qt's QFixed::fromReal (26.6 fixed point, truncating)."""
    return int(v * 64) / 64 if math.isfinite(v) else v


@dataclass
class Region:
    """One box of a story: its width, height (inf for the last/only one) and the
    rectangles text must avoid, in the region's own coordinates."""
    width: float
    height: float = INF
    exclusions: List[QRectF] = field(default_factory=list)

    def key(self):
        return (round(self.width, 4), self.height if self.height == INF else round(self.height, 4),
                tuple((round(r.x(), 3), round(r.y(), 3), round(r.width(), 3), round(r.height(), 3))
                      for r in self.exclusions))


_SCALE: Optional[float] = None


def _margin_scale(doc: QTextDocument) -> float:
    """Qt scales block margins and list indents by logicalDpiY / qt_defaultDpi (0.75
    on our 72-dpi layout device on Windows/Linux).  qt_defaultDpi isn't exposed,
    so it is measured once from Qt's own layout."""
    global _SCALE
    if _SCALE is None:
        from PyQt6.QtGui import QTextCursor
        probe = QTextDocument()
        lay = probe.documentLayout()
        dev = doc.documentLayout().paintDevice()
        if dev is not None:
            lay.setPaintDevice(dev)
        c = QTextCursor(probe)
        c.insertText("a")
        bf = QTextBlockFormat()
        bf.setTopMargin(64.0)
        c.insertBlock(bf)
        c.insertText("a")
        a = lay.blockBoundingRect(probe.begin())
        b = lay.blockBoundingRect(probe.begin().next())
        _SCALE = (b.top() - a.top() - probe.begin().layout().lineAt(0).height()) / 64.0
        if not (0.2 < _SCALE < 5):
            _SCALE = 1.0
    return _SCALE


class FlowLayout(QAbstractTextDocumentLayout):

    def __init__(self, doc: QTextDocument):
        super().__init__(doc)
        self._doc = doc
        self._regions: Optional[List[Region]] = None
        self._starts: List[Tuple] = []      # per block: layout state at its start
        self._bw: List[float] = []          # per block: its widest line (for the width)
        self._height = 0.0
        self._width = 0.0
        self._overflow_from = -1            # first char laid out beyond the last region
        self._region_tops: List[float] = [0.0]

    # ── configuration ───────────────────────────────────────────────────────
    def set_regions(self, regions: Optional[List[Region]]):
        """None: one region as wide as the document's text width (Qt's behaviour)."""
        new = None if regions is None else [Region(r.width, r.height, list(r.exclusions))
                                            for r in regions]
        old_key = None if self._regions is None else [r.key() for r in self._regions]
        new_key = None if new is None else [r.key() for r in new]
        if old_key == new_key:
            return
        self._regions = new
        self._relayout_all()

    def regions(self) -> List[Region]:
        if self._regions:
            return self._regions
        w = self._doc.textWidth()
        return [Region(w if w > 0 else 1e9, INF, [])]

    def region_tops(self) -> List[float]:
        """Top of each region in document coordinates."""
        return list(self._region_tops)

    def overflow_position(self) -> int:
        """First character that didn't fit in the regions (-1: everything fitted)."""
        return self._overflow_from

    # ── QAbstractTextDocumentLayout ─────────────────────────────────────────
    def documentChanged(self, position: int, charsRemoved: int, charsAdded: int):
        blk = self._doc.findBlock(max(position, 0))
        first = blk.blockNumber() if blk.isValid() else 0
        # the paragraph before can change too (margins collapse with this one)
        self._layout_from(max(first - 1, 0), position + charsAdded)

    def documentSize(self) -> QSizeF:
        return QSizeF(self._width, self._height)

    def pageCount(self) -> int:
        return 1

    def frameBoundingRect(self, frame) -> QRectF:
        if frame is self._doc.rootFrame():
            return QRectF(0, 0, self._width, self._height)
        return QRectF()

    def blockBoundingRect(self, block: QTextBlock) -> QRectF:
        if not block.isValid():
            return QRectF()
        tl = block.layout()
        r = tl.boundingRect()
        r.moveTopLeft(tl.position())
        return r

    def hitTest(self, point: QPointF, accuracy: Qt.HitTestAccuracy) -> int:
        doc = self._doc
        point = QPointF(fx(point.x()), fx(point.y()))      # Qt hit-tests in QFixed
        position = 0
        exact = False
        b = doc.begin()
        while b.isValid():
            tl = b.layout()
            top = tl.position().y() + tl.boundingRect().top()
            bottom = tl.position().y() + tl.boundingRect().bottom()
            position = b.position()
            if point.y() < top - b.blockFormat().topMargin():
                break                                   # before this block
            if point.y() > bottom:
                position = b.position() + b.length()
                b = b.next()
                continue
            pos = point - tl.position()
            off = 0
            for i in range(tl.lineCount()):
                line = tl.lineAt(i)
                lr = line.naturalTextRect()
                if lr.top() > pos.y():
                    off = min(off, line.textStart())
                elif lr.bottom() <= pos.y():
                    off = max(off, line.textStart() + line.textLength())
                else:
                    if lr.left() <= pos.x() <= lr.right():
                        exact = True
                    mode = (QTextLine.CursorPosition.CursorOnCharacter
                            if accuracy == Qt.HitTestAccuracy.ExactHit
                            else QTextLine.CursorPosition.CursorBetweenCharacters)
                    off = line.xToCursor(pos.x(), mode)
                    break
            position = b.position() + off
            break
        if accuracy == Qt.HitTestAccuracy.ExactHit and not exact:
            return -1
        last = doc.rootFrame().lastPosition()
        return max(0, min(position, last))

    def draw(self, painter: QPainter, context):
        clip = context.clip
        b = self._doc.begin()
        sels = context.selections
        width = self.property("cursorWidth")
        cursor_w = int(width) if width else 1
        while b.isValid():
            tl = b.layout()
            r = tl.boundingRect()
            r.translate(tl.position())
            if clip.isValid() and (r.bottom() < clip.y() or r.top() > clip.bottom()):
                if clip.isValid() and r.top() > clip.bottom() and not self._regions:
                    break                      # one column: nothing further down shows
                b = b.next()
                continue
            self._draw_block(painter, context, b, tl, r, sels, cursor_w)
            b = b.next()

    # ── drawing ──────────────────────────────────────────────────────────────
    def _draw_block(self, painter, context, b, tl, r, sels, cursor_w):
        bf = b.blockFormat()
        bg = bf.background()
        if bg.style() != Qt.BrushStyle.NoBrush:
            painter.fillRect(r, bg)
        ranges = []
        blpos, bllen = b.position(), b.length()
        sel_fmt = None
        for s in sels:
            a = s.cursor.selectionStart() - blpos
            e = s.cursor.selectionEnd() - blpos
            if a < bllen and e > 0 and e > a:
                fr = QTextLayout.FormatRange()
                fr.start, fr.length, fr.format = a, e - a, s.format
                ranges.append(fr)
            if a < 0 and e >= 1:
                sel_fmt = s.format
        lst = b.textList()
        if lst is not None and lst.format().intProperty(QTextFormat.Property.ListStyle) != 0:
            self._draw_list_item(painter, context, b, lst, sel_fmt)
        old = painter.pen()
        painter.setPen(context.palette.color(QPalette.ColorRole.Text))
        frame = QRectF(0, 0, self._width, self._height)      # as Qt clips to the root frame
        tl.draw(painter, QPointF(0, 0), ranges,
                context.clip.intersected(frame) if context.clip.isValid() else frame)
        cp = context.cursorPosition
        if blpos <= cp < blpos + bllen:
            tl.drawCursor(painter, QPointF(0, 0), cp - blpos, cursor_w)
        ruler = QTextFormat.Property.BlockTrailingHorizontalRulerWidth
        if bf.hasProperty(ruler):                       # <hr>, drawn as Qt does
            width = bf.lengthProperty(ruler).value(r.width())
            if bf.hasProperty(QTextFormat.Property.BackgroundBrush):
                col = bf.background().color()
            else:
                col = context.palette.color(QPalette.ColorGroup.Inactive,
                                            QPalette.ColorRole.WindowText)
            painter.setPen(col)
            y = r.bottom() if b.length() != 1 else r.top() + r.height() / 2
            mid = r.left() + r.width() / 2
            painter.drawLine(QLineF(mid - width / 2, y, mid + width / 2, y))
        painter.setPen(old)

    def _draw_list_item(self, painter, context, b, lst, sel_fmt):
        cf = b.charFormat()
        font = QFont(cf.font())
        dev = self.paintDevice()
        fm = QFontMetrics(font, dev) if dev is not None else QFontMetrics(font)
        tl = b.layout()
        if tl.lineCount() == 0:
            return
        first = tl.lineAt(0)
        pos = tl.position().toPoint()
        pos = QPointF(pos.x(), pos.y() + round(first.ascent()) - fm.ascent())
        tr = first.naturalTextRect()
        pos += tr.topLeft().toPoint().toPointF()
        style = QTextListFormat.Style(lst.format().intProperty(QTextFormat.Property.ListStyle))
        S = QTextListFormat.Style
        text = ""
        if style in (S.ListDecimal, S.ListLowerAlpha, S.ListUpperAlpha, S.ListLowerRoman,
                     S.ListUpperRoman):
            text = lst.itemText(b)
            size = QSizeF(fm.horizontalAdvance(text), fm.height())
        elif style in (S.ListSquare, S.ListCircle, S.ListDisc):
            w = fm.lineSpacing() // 3
            size = QSizeF(w, w)
        else:
            return
        rect = QRectF(pos, size)
        rect.translate(-fm.horizontalAdvance(" ") - size.width(),
                       fm.height() // 2 - size.height() / 2)      # Qt: int / 2
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = cf.foreground()
        if sel_fmt is not None:
            painter.setPen(sel_fmt.foreground().color())
            painter.fillRect(rect, sel_fmt.background())
        else:
            painter.setPen(fg.color() if fg.style() != Qt.BrushStyle.NoBrush
                           else context.palette.color(QPalette.ColorRole.Text))
        if text:
            lay = QTextLayout(text, font, dev) if dev is not None else QTextLayout(text, font)
            opt = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute)
            lay.setTextOption(opt)
            lay.beginLayout()
            ln = lay.createLine()
            if ln.isValid():
                ln.setLeadingIncluded(True)
            lay.endLayout()
            lay.draw(painter, QPointF(rect.left(), pos.y()))
        elif style == S.ListSquare:
            painter.fillRect(rect, painter.pen().color())
        elif style == S.ListCircle:
            painter.drawEllipse(rect.translated(0.5, 0.5))
        else:
            painter.setBrush(painter.pen().color())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)
        painter.restore()

    # ── layout ───────────────────────────────────────────────────────────────
    def _relayout_all(self):
        self._starts = []
        self._bw = []
        self._layout_from(0, -1)

    def _initial_state(self):
        # (y in document coordinates, region index, previous block's bottom margin,
        #  this block's widest line - filled in by _layout_block, not compared)
        return (0.0, 0, None, 0.0)

    def _layout_from(self, first: int, changed_end: int):
        doc = self._doc
        regions = self.regions()
        tops = [0.0]
        for r in regions[:-1]:          # in Qt's fixed point, like every y it lays out
            tops.append(fx(tops[-1] + (r.height if r.height != INF else 0.0)))
        self._region_tops = tops
        old_size = (self._width, self._height)
        if first >= len(self._starts) or len(self._bw) != len(self._starts):
            first = 0
            self._starts = []
            self._bw = []
        state = self._starts[first] if first < len(self._starts) else self._initial_state()
        old_starts, old_bw = self._starts, self._bw
        self._starts, self._bw = old_starts[:first], old_bw[:first]
        b = doc.findBlockByNumber(first)
        if not b.isValid():
            b, state, self._starts, self._bw = doc.begin(), self._initial_state(), [], []
        update_top = None
        self._overflow_from = -1
        scale = _margin_scale(doc)
        shift = doc.blockCount() - len(old_starts)      # blocks added (+) or removed (-)
        while b.isValid():
            n = b.blockNumber()
            # converged: past the change and starting exactly where this block
            # started before -> it and everything after are laid out already
            o = n - shift
            if (changed_end >= 0 and n > first and b.position() > changed_end
                    and 0 <= o < len(old_starts) and old_starts[o][:3] == state[:3]):
                self._starts.extend(old_starts[o:])
                self._bw.extend(old_bw[o:])
                self._finish(old_size, update_top, regions)     # the height is unchanged
                return
            self._starts.append(state)
            if update_top is None:
                update_top = b.layout().position().y()
            state = self._layout_block(b, state, regions, tops, scale)
            self._bw.append(state[3])
            b = b.next()
        self._height = state[0]
        self._finish(old_size, update_top, regions)

    def _finish(self, old_size, update_top, regions):
        # widest line of *every* block, so the width shrinks again when the widest
        # paragraph does (a running maximum never would)
        self._width = fx(max(self._bw + [r.width for r in regions if r.width < 1e8] + [0.0]))
        if self._overflow_from < 0:
            self._find_overflow()
        top = update_top if update_top is not None else 0.0
        self.update.emit(QRectF(0, min(top, 0.0) if top < 0 else top, 1e9, 1e9))
        if (abs(old_size[0] - self._width) > 1e-6 or abs(old_size[1] - self._height) > 1e-6):
            self.documentSizeChanged.emit(QSizeF(self._width, self._height))

    def _find_overflow(self):
        regions = self.regions()
        if len(regions) < 1 or regions[-1].height == INF:
            self._overflow_from = -1
            return
        limit = self._region_tops[-1] + regions[-1].height
        b = self._doc.begin()
        while b.isValid():
            tl = b.layout()
            for i in range(tl.lineCount()):
                ln = tl.lineAt(i)
                if tl.position().y() + ln.y() + ln.height() > limit + 0.5:
                    self._overflow_from = b.position() + ln.textStart()
                    return
            b = b.next()
        self._overflow_from = -1

    def _layout_block(self, b: QTextBlock, state, regions: List[Region], tops: List[float],
                      scale: float):
        y, ri, prev_bm, _ = state
        widest = 0.0
        bf = b.blockFormat()
        tl = b.layout()
        if not b.isVisible():
            return (y, ri, prev_bm, 0.0)
        if prev_bm is not None:
            margin = max(bf.topMargin(), prev_bm)
            if margin > 0:
                margin *= scale
            y = fx(y + fx(margin))
        doc = self._doc
        direction = b.textDirection()
        indent = self._block_indent(b, bf, scale)
        left_m = fx(bf.leftMargin()) + (0.0 if direction == Qt.LayoutDirection.RightToLeft else indent)
        right_m = fx(bf.rightMargin()) + (indent if direction == Qt.LayoutDirection.RightToLeft else 0.0)

        opt = QTextOption(doc.defaultTextOption())
        opt.setTextDirection(direction)
        opt.setTabs(bf.tabPositions())
        align = doc.defaultTextOption().alignment()
        if bf.hasProperty(QTextFormat.Property.BlockAlignment):
            align = bf.alignment()
        opt.setAlignment(self._visual_alignment(direction, align))
        if bf.nonBreakableLines() or doc.textWidth() < 0 and not self._regions:
            opt.setWrapMode(QTextOption.WrapMode.ManualWrap)
        opt.setUseDesignMetrics(doc.useDesignMetrics())
        tl.setTextOption(opt)

        # move to the region this block starts in
        ri = self._region_at(y, ri, regions, tops)
        cy = y
        tl.setPosition(QPointF(0.0, cy))
        bottom = y
        tl.beginLayout()
        first_line = True
        scaling = scale if abs(scale - 1.0) > 1e-9 else 1.0
        while True:
            line = tl.createLine()
            if not line.isValid():
                break
            line.setLeadingIncluded(True)
            text_indent = fx(bf.textIndent()) if first_line else 0.0
            first_line = False
            y, ri, left = self._place_line(line, y, ri, regions, tops, left_m, right_m,
                                           text_indent, direction, bf, scaling)
            lh, lb, adj, lbreak = self._line_params(bf, line, scaling)
            line.setPosition(QPointF(left, fx(y - cy - adj)))
            bottom = fx(y + lb)
            y = fx(y + lh)
            widest = max(widest, line.x() + line.naturalTextWidth() + right_m)
        tl.endLayout()
        y = max(y, bottom)
        return (y, ri, bf.bottomMargin(), widest)

    @staticmethod
    def _visual_alignment(direction, align):
        a = Qt.AlignmentFlag(align)
        if direction == Qt.LayoutDirection.RightToLeft and not (a & Qt.AlignmentFlag.AlignAbsolute):
            if a & Qt.AlignmentFlag.AlignLeft:
                a = (a & ~Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignRight
            elif a & Qt.AlignmentFlag.AlignRight:
                a = (a & ~Qt.AlignmentFlag.AlignRight) | Qt.AlignmentFlag.AlignLeft
        return a

    def _block_indent(self, b, bf, scale) -> float:
        ind = bf.indent()
        lst = b.textList()
        if lst is not None:
            ind += lst.format().indent()
        if not ind:
            return 0.0
        return fx(ind * scale * self._doc.indentWidth())

    @staticmethod
    def _line_params(bf: QTextBlockFormat, line, scaling: float):
        height = line.height()
        t = bf.lineHeightType()
        raw = math.ceil(line.ascent() + line.descent() + line.leading())
        lh = fx(bf.lineHeight(raw, scaling))
        lb = fx(bf.lineHeight(height, scaling))
        if t in (QTextBlockFormat.LineHeightTypes.FixedHeight.value,
                 QTextBlockFormat.LineHeightTypes.MinimumHeight.value):
            lbreak = lb
            if t == QTextBlockFormat.LineHeightTypes.FixedHeight.value:
                adj = fx(line.ascent() + max(line.leading(), 0.0)) - fx(lh * 4 / 5)
            else:
                adj = fx(height) - lh
        else:
            lbreak = fx(height)
            adj = 0.0
        return lh, lb, adj, lbreak

    @staticmethod
    def _region_at(y: float, ri: int, regions: List[Region], tops: List[float]) -> int:
        while ri < len(regions) - 1 and y >= tops[ri] + regions[ri].height - 1e-9:
            ri += 1
        return ri

    def _place_line(self, line, y, ri, regions, tops, left_m, right_m, text_indent,
                    direction, bf, scaling):
        """Find where this line goes: (y, region index, x).  Mirrors Qt for a plain
        region; around exclusions it takes the widest free stretch at its height."""
        for _guard in range(10_000):
            reg = regions[ri]
            l = left_m
            r = fx(reg.width) - right_m
            if direction == Qt.LayoutDirection.RightToLeft:
                r -= text_indent
            else:
                l += text_indent
            line.setLineWidth(max(r - l, 0.0))
            lh, lb, adj, lbreak = self._line_params(bf, line, scaling)
            local = y - tops[ri]
            if reg.exclusions:
                span = self._free_span(reg, local, max(lbreak, lh), l, r,
                                       direction == Qt.LayoutDirection.RightToLeft)
                if span is None:
                    nxt = self._below_obstacles(reg, local, max(lbreak, lh))
                    if nxt is None:
                        span = (l, r)            # (can't happen: something blocked it)
                    elif nxt >= reg.height and ri < len(regions) - 1:
                        y, ri = tops[ri + 1], ri + 1     # carry on in the next box
                        continue
                    else:
                        # below the obstacle - in the last box that may be past its
                        # bottom (the text overflows), never on top of the picture
                        y = tops[ri] + nxt
                        continue
                sl, sr = span
                if (sl, sr) != (l, r):
                    line.setLineWidth(max(sr - sl, 0.0))
                    lh, lb, adj, lbreak = self._line_params(bf, line, scaling)
                    # taller now (a bigger word came onto the line)?  check again
                    again = self._free_span(reg, local, max(lbreak, lh), l, r,
                                       direction == Qt.LayoutDirection.RightToLeft)
                    if again is not None and (again[0] > sl + 1e-6 or again[1] < sr - 1e-6):
                        sl, sr = again
                        line.setLineWidth(max(sr - sl, 0.0))
                        lh, lb, adj, lbreak = self._line_params(bf, line, scaling)
                l = sl
            # past the bottom of this region?  carry on in the next one
            if (ri < len(regions) - 1 and local + lbreak > reg.height + 1e-6
                    and local > 1e-6):
                y, ri = tops[ri + 1], ri + 1
                continue
            return y, ri, l
        return y, ri, left_m

    @staticmethod
    def _free_span(reg: Region, y: float, h: float, l: float, r: float, rtl: bool = False):
        """Widest stretch of [l, r] not covered by an exclusion over [y, y + h].

        Equally wide stretches: the one a reader meets first - the leftmost for
        left-to-right text, the rightmost for right-to-left."""
        blocked = []
        for e in reg.exclusions:
            if e.top() < y + h and e.bottom() > y + 1 / 64:
                blocked.append((e.left(), e.right()))
        if not blocked:
            return (l, r)
        blocked.sort()
        best, cur = None, l
        for a, bb in blocked:
            if a > cur:
                seg = (cur, min(a, r))
                if best is None or _better(seg, best, rtl):
                    best = seg
            cur = max(cur, bb)
            if cur >= r:
                break
        if cur < r:
            seg = (cur, r)
            if best is None or _better(seg, best, rtl):
                best = seg
        if best is None or best[1] - best[0] < max(MIN_LINE_WIDTH, MIN_LINE_FRACTION * (r - l)):
            return None
        return (fx(best[0]), fx(best[1]))

    @staticmethod
    def _below_obstacles(reg: Region, y: float, h: float) -> Optional[float]:
        """The nearest obstacle bottom below ``y`` (always moves down by > 1/64 pt,
        so float rounding can never leave a line stuck on an obstacle's edge)."""
        bottoms = [e.bottom() for e in reg.exclusions
                   if e.top() < y + h and e.bottom() > y + 1 / 32]
        return math.ceil(min(bottoms) * 64) / 64 + 1 / 64 if bottoms else None


def _better(seg, best, rtl: bool) -> bool:
    """Is ``seg`` (found later, i.e. further right) a better place for a line?"""
    d = (seg[1] - seg[0]) - (best[1] - best[0])
    return d > 1e-6 or (rtl and abs(d) <= 1e-6)


def install(doc: QTextDocument) -> FlowLayout:
    """Give ``doc`` a FlowLayout (keeping its paint device)."""
    dev = doc.documentLayout().paintDevice()
    lay = FlowLayout(doc)
    if dev is not None:
        lay.setPaintDevice(dev)
    doc.setDocumentLayout(lay)
    return lay

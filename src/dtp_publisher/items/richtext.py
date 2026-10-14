# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""The text model a text box supports, and keeping pasted text inside it.

A text box holds a *story*: paragraphs and their formatting (alignment,
indents, spacing, lists, tabs, direction) and character formatting (font,
size, colour, bold/italic/underline, highlight).  That is what FlowLayout lays
out and draws.

Rich text pasted from Word, a browser or an email can carry more than that:
tables, framed blocks (``<div>`` boxes) and inline pictures.  Qt would accept
them into the document, but the layout doesn't support them, so they are
turned into the story model as they arrive:

* a table becomes one paragraph per row, the cells separated by tabs;
* a framed block becomes ordinary paragraphs;
* an inline picture is removed (pictures are separate objects on the page,
  as in Publisher - use Insert ▸ Picture).

Their text and character formatting are kept.

Frames are unwrapped innermost first: asking Qt for the extent of a table cell
that still holds another table can crash it, and a leaf frame holds none.  The
work is budgeted (``MAX_RICH_STRUCTURES`` frames, ``MAX_INLINE_OBJECTS``
pictures).  Past the budget - or if anything unsupported were somehow left -
the story falls back to its plain text, so ``flatten`` never returns a
document outside the model.
"""

from __future__ import annotations

from PyQt6.QtGui import (QTextCursor, QTextDocument, QTextDocumentFragment, QTextFrame,
                         QTextTable)

OBJECT_CHAR = "\ufffc"          # what an inline object (picture) occupies in the text
PARAGRAPH_SEPARATOR = "\u2029"
MAX_RICH_STRUCTURES = 5000      # tables and boxes converted with their formatting kept
MAX_INLINE_OBJECTS = 20_000     # inline pictures removed one by one


def flatten(doc: QTextDocument) -> bool:
    """Bring ``doc`` into the story model.  Returns True if anything changed.

    Afterwards ``in_story_model(doc)`` always holds."""
    if in_story_model(doc):
        return False
    whole = QTextCursor(doc)
    whole.beginEditBlock()                    # one change notification, one undo step
    try:
        _flatten(doc)
    finally:
        whole.endEditBlock()
    return True


def _flatten(doc: QTextDocument):
    # children before their parent: by the time a frame is unwrapped, the
    # frames inside it have been, so it is a leaf (see the module docstring)
    frames = _frames_inside_out(doc.rootFrame())
    for f in frames[:MAX_RICH_STRUCTURES]:
        _unwrap(doc, f)
    if not doc.rootFrame().childFrames():
        _drop_objects(doc)
    if not in_story_model(doc):
        _to_plain_text(doc)                   # over budget: keep the words, lose the rest


def in_story_model(doc: QTextDocument) -> bool:
    """True if ``doc`` holds only what a text box supports: no frames, no objects."""
    if doc.rootFrame().childFrames():
        return False
    return _next_object(doc, 0) is None


def _frames_inside_out(root: QTextFrame) -> list:
    """Every frame below ``root``, each after all the frames inside it."""
    out, todo = [], [(f, False) for f in reversed(root.childFrames())]
    while todo:
        f, expanded = todo.pop()
        if expanded:
            out.append(f)
        else:
            todo.append((f, True))
            todo.extend((k, False) for k in reversed(f.childFrames()))
    return out


def _to_plain_text(doc: QTextDocument):
    text = doc.toPlainText().replace(OBJECT_CHAR, "")
    c = QTextCursor(doc)
    c.select(QTextCursor.SelectionType.Document)
    c.insertText(text)
    if not in_story_model(doc):                # never expected; make certain
        doc.setPlainText(text)


def _fragment(doc: QTextDocument, a: int, b: int) -> QTextDocumentFragment:
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(max(a, b), QTextCursor.MoveMode.KeepAnchor)
    return QTextDocumentFragment(c)


def _unwrap(doc: QTextDocument, frame: QTextFrame):
    start = frame.firstPosition() - 1
    end = frame.lastPosition() + 1
    if isinstance(frame, QTextTable):
        rows = []
        for r in range(frame.rows()):
            cells = []
            for col in range(frame.columns()):
                cell = frame.cellAt(r, col)
                if cell.row() != r or cell.column() != col:
                    continue                          # covered by a merged cell
                cells.append(_fragment(doc, cell.firstCursorPosition().position(),
                                       cell.lastCursorPosition().position()))
            rows.append(cells)
    else:
        rows = None
        body = _fragment(doc, frame.firstPosition(), frame.lastPosition())
    c = QTextCursor(doc)
    c.beginEditBlock()
    c.setPosition(max(start, 0))
    c.setPosition(min(end, doc.characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
    c.removeSelectedText()
    if rows is None and body.isEmpty():
        c.endEditBlock()                      # an empty object (e.g. a floating picture)
        return
    if not c.atBlockStart():
        c.insertBlock()                       # the table was its own paragraph(s)
    if rows is None:
        c.insertFragment(body)
    else:
        for i, cells in enumerate(rows):
            if i:
                c.insertBlock()
            for j, frag in enumerate(cells):
                if j:
                    c.insertText("\t")
                # a cell's own paragraphs are joined with line breaks within the row
                text_cursor_pos = c.position()
                c.insertFragment(frag)
                _join_blocks(doc, text_cursor_pos, c.position())
    if not c.atBlockEnd():
        c.insertBlock()
    c.endEditBlock()


def _join_blocks(doc: QTextDocument, a: int, b: int):
    """Turn paragraph breaks in [a, b) into line breaks (one row stays one paragraph)."""
    blk = doc.findBlock(max(b - 1, 0))
    while blk.isValid() and blk.position() > a:
        start = blk.position()
        if doc.characterAt(start - 1) != PARAGRAPH_SEPARATOR:
            break                             # a frame's edge: never merge into it
        c = QTextCursor(doc)
        c.setPosition(start - 1)
        c.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
        c.insertText("\u2028")
        # ``blk`` has just been merged away: look again from the joined text
        blk = doc.findBlock(start - 1)


def _next_object(doc: QTextDocument, pos: int):
    """Cursor selecting the next inline object at or after ``pos``, or None."""
    while True:
        found = doc.find(OBJECT_CHAR, pos)
        if found.isNull():
            return None
        fmt = found.charFormat()
        if fmt.isImageFormat() or fmt.objectType():
            return found
        pos = found.position()                # a plain U+FFFC typed as text


def _drop_objects(doc: QTextDocument):
    """Remove inline objects; leaves any past ``MAX_INLINE_OBJECTS`` for the caller."""
    pos = 0
    for _ in range(MAX_INLINE_OBJECTS):
        found = _next_object(doc, pos)
        if found is None:
            return
        pos = found.selectionStart()
        found.removeSelectedText()

# DTP Publisher Pro

A friendly desktop publishing program in the spirit of Microsoft Publisher, for
flyers, signs, posters, newsletters, greeting cards, invitations, postcards,
address labels, business cards and photo albums.

Python 3.11+ · PyQt6 · Windows (also runs on Linux/macOS) · Apache 2.0

---

## Starting it

Double-click **`runme.bat`**. The first time, it sets itself up (this needs an
internet connection and takes a minute or two); after that it opens straight
away.

If Python isn't installed, get it from <https://www.python.org/downloads/> and
tick **"Add python.exe to PATH"** during setup.

You can also open a publication directly: drag a `.dtpub` file onto
`runme.bat`, or run `python run.py myfile.dtpub`.

## Quick guide

**Making something new.** The start screen shows ready-made designs. Pick one
(or a blank page) and press **Create**. You can change everything afterwards.

**Typing.** Double-click a text box and type. Click outside the box (or press
**Esc**) when you're done. Select words and use the text bar under the ribbon
to change the font, size, colour, bold and so on. With a text box selected but
not being typed in, the text bar changes all of its text.

**Pictures.** Double-click a grey *picture frame* to choose a photo, or drag a
photo from a folder straight onto the page or onto a frame. Phone photos are
turned the right way up automatically. On the **Format** panel you can choose
whether a photo fills the frame (trimming the edges) or fits inside it, and
slide it to show a different part.

**Moving and sizing.** Drag an object to move it. Drag the round corner
handles to resize; pictures keep their shape. Drag the circle above an object
to rotate it. Red lines show when something lines up with the page, the
margins or another object.

| Hold while dragging | Effect |
|---|---|
| Shift | Move in a straight line / resize freely |
| Ctrl | Resize from the centre |
| Alt | Turn off snapping |

**Undo.** Made a mistake? **Ctrl+Z** undoes it (or the Undo button on the Home
tab). It works for everything, including deleting pages.

**Saving.** **Ctrl+S** saves. A recovery copy is saved every few minutes too,
so after a power cut the program offers to bring your work back. When you save,
the previous version is kept next to it as `name.dtpub.bak`.

**Printing and sharing.**
- **File ▸ Print** prints. A page that matches the paper size prints at exact
  size, so label and business-card sheets line up.
- **File ▸ Save as PDF** makes a file you can email or take to a print shop.
- **File ▸ Save as Picture** saves a JPEG or PNG.

**Labels and business cards.** Design one card (or label), select it, then
choose **Arrange ▸ Fill Page with Copies**.

**Greeting cards.** Print the *Outside* page, put the paper back in the printer
turned over, then print the *Inside* page.

**Bigger buttons and text.** Open **File ▸ Preferences**. The *Size of buttons
and text* setting goes up to 200%. You can also choose a *High contrast* look
there.

### Handy keys

| Keys | Does |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S | New / Open / Save |
| Ctrl+Z / Ctrl+Y | Undo / Redo |
| Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+D | Copy / Cut / Paste / Duplicate |
| Delete | Delete the selected object |
| Arrow keys (Shift for bigger steps) | Nudge the selected object |
| F2 | Type in the selected text box |
| Ctrl+B / Ctrl+I / Ctrl+U | Bold / Italic / Underline |
| Ctrl+L / Ctrl+E / Ctrl+R / Ctrl+J | Align left / centre / right / justify |
| Ctrl+G / Ctrl+Shift+G | Group / Ungroup |
| Ctrl+mouse wheel, Ctrl+0 | Zoom, whole page |
| Space + drag, or middle mouse | Scroll around the page |
| Ctrl+PgUp / Ctrl+PgDn | Previous / next page |

---

## For developers

```
src/dtp_publisher/
  app.py            start-up: UI scale, theme, crash recovery, start screen, error log
  document.py       Document (pages + one QUndoStack) and shared ViewOptions
  scene.py          PageScene (one QGraphicsScene per page), guides, snapping, group moves
  commands.py       every undoable change (items, text, guides, pages, page setup)
  geometry.py       pure maths: Geo(x, y, w, h, rot), local<->parent mapping
  items/            BaseItem + text, picture, shape, table, WordArt, group
  serialize.py      .dtpub JSON load/save (atomic, .bak), v3 migration, clipboard
  export.py         PDF / picture / print rendering
  templates.py      built-in designs (built with the normal item API)
  blocks.py         building blocks (header, footer, coupon, page number…)
  fields.py         automatic page numbers and dates
  autosave.py       recovery copies written on a worker QThread
  settings.py       per-user JSON preferences
  theme.py          light / dark / high-contrast palettes + QSS
  ui/               main window, ribbon, canvas + rulers, panels, dialogs, icons
```

Design rules that the bugs taught us:

- **One scene per page.** Each undo command holds its page's scene, so undoing a
  change on page 3 while viewing page 1 can never touch page 1.
- **Items have local rect `(0, 0, w, h)`.** `pos()` is the unrotated top-left
  and rotation is about the centre. `Geo` is exactly what gets saved.
- **Scene units are points.** Text layout is pinned to a 72-dpi device with
  design metrics, so 11 pt is 11 pt on every computer and in every PDF.
- **Every QAction exists once.** Ribbon buttons only *display* actions. Canvas
  keys (Delete, arrows, Esc) use a widget-scoped shortcut context, so they never
  steal keys from text boxes or lists.
- **Live change, then push.** The UI applies a change, then pushes a command
  whose `redo()` is idempotent.

### Tests

```
run_tests.bat            (or: python -m pytest -q   with QT_QPA_PLATFORM=offscreen)
revert_proofs.bat        (or: python tools/revert_proofs.py)
```

132 tests run headless in about 15 seconds. `tools/revert_proofs.py`
re-introduces each fixed bug in a temporary copy of `src/` and checks that its
regression test fails (see `REVIEW.md`).

### File format

`.dtpub` is UTF-8 JSON: `{"format": "dtpub", "version": 5, "view": {...},
"pages": [{"name", "setup", "guides", "items": [...]}]}`. Text is stored as Qt
rich-text HTML and pictures as base64. Photos larger than 3000 px are scaled
down when inserted, so files stay a sensible size. The March prototype's
`.json` layouts (format v3) open and are converted. Save them as `.dtpub`
afterwards.

---

© 2026 Leon Priest (GitHub: [7h3v01d](https://github.com/7h3v01d)). Licensed
under the Apache License, Version 2.0 — see `LICENSE`.

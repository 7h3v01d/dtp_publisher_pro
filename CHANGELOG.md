# Changelog

## 5.1.1 — 2026-10-14 (hardening)

A defensive release after an adversarial review. No new features; every
finding was reproduced against the 5.1.0 code first (see `REVIEW.md`), and
each fix has a regression test and a revert proof.

### Fixed
- **Oversized input no longer exhausts memory.** All limits live in one place
  (`limits.py`) and are far above any real publication:
  - Publisher import: each embedded picture and all pictures together are
    checked before being decompressed; the XML is streamed with size and
    element limits; the converted file and LibreOffice's temp folder are
    size-checked; absurd lengths (`1e30mm`) are clamped.
  - Picture files are size-checked before reading, and very large photos are
    decoded straight from the file at reduced size.
  - Page sizes, margins, gutters and guides read from a file are clamped.
  - *Save as Picture* never asks for a bitmap above 150 megapixels; the
    resolution is lowered automatically and you are told.
  - Opening a file counts its pages, objects and text *before* any object is
    made, and refuses files beyond the limits with a plain explanation.
    Pasting is held to the same budget.
- **Autosave could bring back an out-of-date recovery file** if Save happened
  while an autosave was queued or being written. Autosave requests now carry a
  generation number; Save/close makes older ones stale and waits for a write
  in progress.
- **Autosave no longer stalls typing**: JSON encoding and writing happen on the
  worker thread, and pictures keep their encoded form, so after the first
  autosave the GUI-thread part takes about a millisecond even with 50 large
  photos (it was about 2 seconds).
- **A failed `.bak` copy is reported.** The save still succeeds, but you are
  told the backup could not be updated.
- **Damaged picture data** is decoded strictly; slightly damaged data is
  repaired only if the result is a real picture (with a note), and anything
  else becomes an empty frame with a warning.
- **Duplicate object ids in a file** are renumbered in file order, so a copied
  box can never take over a linked story.

### Installing
- `requirements.txt` now pins the exact PyQt6 / Qt versions the program is
  tested with (text layout, PDF and printing all come from Qt);
  `requirements-range.txt` keeps the wider developer range. `runme.bat` no
  longer upgrades pip on first run.
- `build_exe.bat` makes a stand-alone Windows program (PyInstaller) in
  `dist\DTP Publisher\` that runs without Python installed.

## 5.1.0 — 2026-10-14

### New
- **Open Microsoft Publisher files (.pub).** File ▸ Open, drag and drop, or
  double-click in Recent. LibreOffice (free) reads the file in the background;
  the pages are rebuilt as normal, editable DTP Publisher pages: text boxes
  with their fonts and paragraph formatting, photos, shapes, lines, gradients,
  page backgrounds and master-page backgrounds. A progress window with
  **Cancel** shows while it works, then a summary of what was opened. The
  original .pub file is never changed; saving makes a new `.dtpub` file in the
  same folder.
  - Old photos stored as WMF/EMF are unwrapped to the original bitmap; simple
    WMF clip art is drawn.
  - Linked Publisher stories are put back together so the text flows from box
    to box (LibreOffice gives every box a copy of the whole story).
- **Linked text boxes.** *Insert ▸ Continue Text…* then click an empty box:
  text that doesn't fit flows on into it, across columns and pages. Editing,
  undo, copy/paste and saving all follow the story. *Break Link* separates
  them again.
- **Label sheets.** *Page Setup ▸ Print several pages on each sheet* — each
  page is one label; choose the Avery sheet and whether each page fills a sheet
  or the pages follow one another. Printing and Save as PDF lay the labels out
  on the sheet. Publisher label files set this up automatically.
- **Drawings** (free-form vector shapes with optional gradient), used by the
  importer for lines, borders and clip art.

### Fixed during development (each has a regression test and a revert proof)
- Publisher's box height was applied to every imported box, clipping titles
  (only linked boxes need it).
- Gradient transparency was ignored, so a see-through gradient hid the text
  underneath.
- A story split by LibreOffice could be joined to the wrong box (an address
  line); continuations must now have the same column width.
- A `META_ESCAPE` record made Publisher photos count as vector art.

### Known limits
- Text does not yet wrap around pictures; in imported newsletters a photo can
  sit over a column of text. Move or resize the picture or the box.
- `.pub` files can be opened but not saved back as `.pub` (no program other
  than Publisher can write them, and Publisher itself was retired in
  October 2026). Save as `.dtpub` or PDF.

## 5.0.0 — 2026-10-14

Rebuilt the core of the March prototype (v4). See `REVIEW.md` for the bugs
fixed and how each is proven.

### New
- **Start screen** with 12 templates and 8 blank sizes:
  - Flyers & posters: event flyer, notice/sign, A3 poster, certificate.
  - Newsletters: 2-page, 3-column newsletter with page numbers.
  - Cards & invitations: fold-in-half greeting card, party invitation, postcard.
  - Labels & business cards: Avery L7163 address labels, 10-up business cards.
  - Photo albums: album pages, 12 × 12 collage.
- **Rich text**: per-word fonts, sizes, colours, bold/italic/underline,
  alignment, bullets and numbering, line spacing, vertical alignment.
  Autofit (shrink, best fit, grow box) scales the text and keeps your
  formatting. An overflow marker shows when text doesn't fit.
- **Picture frames**: empty frames act as placeholders; fill/fit/stretch
  modes; adjustable crop position; rounded corners. Phone photos are turned
  upright automatically, and large photos are scaled down. Drag and drop from
  Explorer and paste from the clipboard both work.
- **Shapes**: rectangle, rounded rectangle, oval, triangle, diamond, pentagon,
  hexagon, star, arrow, heart, line. Dashed and dotted outlines; transparency.
- **WordArt** with arch, wave and bulge shapes, gradient fill, outline,
  shadow and quick styles.
- **Tables** edited in a spreadsheet-style dialog.
- **Building blocks**: heading band, footer with page number, story, pull
  quote, sidebar, coupon, page number, today's date. These can be added to
  every page in one step.
- **Pages**: add, duplicate, delete, reorder by dragging thumbnails, rename,
  per-page background colour. Page setup covers size presets, orientation,
  margins, column/row guides and the gap between them.
- **Arrange**: align (to the margins for a single object), distribute,
  rotate 90°, flip, group and ungroup (groups can be resized and rotated, and
  you can still edit the text inside them), lock, z-order, and *Fill page with
  copies* for labels and cards.
- **Undo/redo for everything**, including page operations. Undo takes you to
  the page the change happened on.
- **Files**: Save / Save As, unsaved-changes prompt, recent files, atomic
  saves with `.bak`, and autosave with crash recovery. Old v4 `.json` layouts
  are converted.
- **Output**: PDF (vector, correct size for each page), print (exact size on
  matching paper), and PNG/JPEG at 96/150/300 dpi.
- **Accessibility**: light (Publisher-style), dark (Obsidian/Teal) and
  high-contrast themes; 100–200 % UI size; large handles; labelled ribbon
  buttons; the text bar stays in a fixed place.
- Rulers in mm, inches or points; guides drag out of the rulers; snapping to
  margins, columns, guides, objects and an optional grid. Hold Alt to turn
  snapping off.
- Unexpected errors are logged to `crash.log` instead of closing the program.

### Fixed
All seven prototype bugs (positions on reload, blank PDF/print, dead
shortcuts, rotation pivot, deleted objects saved, grid settings ignored,
ruler guides), plus six found during the rebuild.

### Tooling
- `src/` layout; `runme.bat` (venv on first run, starts without a console);
  `run_tests.bat`; `revert_proofs.bat`.
- 132 headless tests; `tools/revert_proofs.py`.

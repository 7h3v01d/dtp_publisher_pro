# Changelog

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

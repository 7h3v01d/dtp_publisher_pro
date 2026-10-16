# Changelog

## 5.3.5 — 2026-10-16 (licence)

### Changed
- **New licence: Restricted Use Software Licence v1.1** (was Apache 2.0).
  Free for personal, educational, hobby and other non-commercial use;
  commercial use, redistribution, changed versions and reuse of substantial
  parts need the author's written permission. Every file's notice, `NOTICE`,
  the README and the About box say so, and a test keeps them consistent.

## 5.3.4 — 2026-10-16

### Changed
- The one-file program's copy of the manual (about 2 MB, in the settings
  folder) now replaces the copy made by an earlier version instead of
  adding another. First Windows run of the one-file build: self-test passed.

## 5.3.3 — 2026-10-16 (single-file build)

### Added
- **`build_onefile.bat`** builds the program as one file,
  `dist-single\DTP Publisher.exe`, as well as the existing folder build. The
  same recipe (`packaging/dtp_publisher.spec`) makes both (`DTP_ONEFILE=1`).
  While the one file unpacks itself, PyInstaller shows the welcome picture
  (when the building Python has Tcl/Tk, as the python.org one does); the
  program closes it as its own picture appears.
- **`DTP Publisher.exe --self-test=result.json`** checks a built program has
  what it needs: reading photos (Qt's JPEG/PNG/GIF/BMP plug-ins), the manual
  and its pictures, the welcome picture and PDF export. Both build scripts
  run it and stop if anything fails.

### Fixed (for the one-file build)
- The manual was opened from the one-file program's temporary folder, which is
  deleted when the program closes; it is now copied (once per version) to the
  settings folder and opened from there.

## 5.3.2 — 2026-10-16 (welcome picture)

### Added
- **A welcome picture while the program starts.** It appears as soon as
  possible (before the slow part of starting), stays at least 3 seconds or
  until the program is ready if that takes longer, and a click or any key
  closes it at once. The version number is shown on it. *File ▸ Preferences ▸
  Show the welcome picture while the program starts* turns it off. The main
  window and start screen appear when it goes, never behind it.

## 5.3.1 — 2026-10-14 (user manual)

### Added
- **A user manual**, with pictures of the real program: opens from
  **File ▸ User Manual** or **F1** (in the web browser, no internet needed), and
  as **User Manual.pdf** next to the program for printing (`build_exe.bat`
  copies it there). It covers every part of the program, step by step for
  flyers, newsletters, cards, labels and albums, plus a "when something goes
  wrong" chapter.
- Tests keep the manual true to the program: every "Tab ▸ Button" it names
  must be on that tab, every shortcut it lists must exist, every picture must
  be present, and the manual must state the current version.
- Developer tools: `tools/manual_screens.py` retakes the screenshots;
  `tools/build_manual_pdf.py` prints the PDF.

### Fixed
- The Pages panel's buttons were cut off ("Ad...ge") in a window less than
  about 1,450 pixels wide; they now sit one above the other.
- In the WordArt window, the *White outline* quick style was white text on a
  white button, and *Classic black* disappeared on the dark theme; the style
  buttons now always show on white, like the preview.
- `build_exe.bat` and `runme.bat` now have Windows line endings (cmd can
  misread `goto` labels in files without them).

## 5.3.0 — 2026-10-14 (double-click to open)

### Added
- **Open `.dtpub` and `.pub` files by double-clicking them** (Windows 10/11).
  *File ▸ Preferences ▸ Double-click to open* has a tick box for each. It is
  set for the current Windows account only (no administrator rights), adds
  the program to Settings ▸ Default apps, and removing it puts back whatever
  program opened those files before.
- Where Windows insists the user confirm it (a program was already chosen for
  that file type, as is common for `.pub`), the program says so and opens
  Settings ▸ Default apps; on Windows 11, at DTP Publisher Pro's own page. It
  never forges that choice itself.
- If the program folder is moved or deleted, the next start points the file
  types at the copy that's running. A different copy that still exists (for
  example one run from the source) is left alone.

## 5.2.3 — 2026-10-14 (pasted-text hardening, fourth review)

### Fixed
- **Pasting a table that has another table inside a cell could crash the
  program** (for example, a cell with a line of text, then a small table, then
  more text, as web pages and emails often have). The tables are now taken
  apart from the innermost outwards, so this can't happen.
- **Pasting more than 64 tables or boxed sections left the rest unconverted**,
  so they were drawn wrongly. There is now no such cutoff: up to 5,000 are
  converted with their formatting; anything bigger, or more than 20,000
  pictures in one paste, is pasted as plain text instead. Either way, a text
  box never ends up holding a table, box or picture.
- **A table cell with three or more paragraphs** was only partly joined into
  its row; every paragraph of the cell now joins the row.
- Converting a large paste is now one step (one Undo) and much quicker:
  5,000 tables take about a quarter of a second instead of six.

## 5.2.2 — 2026-10-14 (text layout consolidation, third review)

### Fixed
- **Pasting from Word, a browser or an email** could bring tables, boxed
  sections and inline pictures into a text box, which the text layout doesn't
  draw (a table came out as a stack of loose cells). They are now turned into
  ordinary story text as they arrive: a table becomes one paragraph per row
  with the cells separated by tabs, a boxed section becomes plain paragraphs,
  and inline pictures are removed (pictures are separate objects on the page).
  Text and formatting are kept. Files made earlier that contain them are
  converted when opened.
- **Text could be drawn over a picture near the bottom of the last box** in a
  story: when the picture reached past the box's bottom, the line was placed
  across it instead of below it. Found by a new test that lays out thousands
  of random arrangements of pictures.
- **Lines could start a fraction of a point above their box** in a linked story
  (box positions weren't rounded like the lines).
- **Right-to-left text** now takes the right-hand gap when a picture leaves two
  equal gaps (the side a reader meets first).
- **Horizontal rules** (`<hr>`, from pasted text) are drawn again.
- The text's overall width now shrinks when its widest line does, and a size
  change in either direction is reported.
- The safety check on opening files now counts dictionary keys too; a file
  made of large dictionaries got through at about two-thirds of its real cost.

### What a text box holds (now stated)
A text box holds a *story*: paragraphs (alignment, indents, spacing, lists,
tabs, direction, rules) and character formatting (font, size, colour, bold,
italic, underline, highlight). Tables, boxed sections and pictures are their
own objects on the page, as in Publisher. See `items/richtext.py`.

## 5.2.1 — 2026-10-14 (first Windows test run)

### Fixed
- **Template text overflowed on Windows.** Six templates (flyer, poster,
  newsletter, card, invitation, business cards) had text boxes sized snugly for
  the fonts used in development; Windows' real Calibri and Georgia have taller
  lines, so the text overflowed (red "more text" markers). A template box that
  would overflow now shrinks its text just enough instead. Tested by building
  every template with a font whose lines are 1.5 em tall (Calibri's are 1.22).
- **The crash handler could crash.** When a program has no usable console
  (some Windows set-ups, a packaged program) writing the error to it raised a
  new error inside the handler, so the "please save" message never appeared.

## 5.2.0 — 2026-10-14

### New
- **Text wraps around pictures.** Text in a box flows around any picture (or
  other object set to wrap) in front of it, the way Publisher's "Square"
  wrapping works: each line takes the widest free stretch beside the picture,
  or carries on below it; slivers too narrow to read are skipped. Choose
  *No Wrapping*, *Wrap Square* or *Wrap Top and Bottom* on the Arrange tab, in
  the right-click menu, or under **Text wrap** on the Format panel. New
  pictures wrap text; shapes, WordArt and text boxes don't unless you ask.
  Publications made before 5.2 open exactly as they were (nothing wraps until
  you turn it on).
- **Imported Publisher files wrap** pictures and text boxes that sit in front
  of a story, as they did in Publisher (decorations that cover a whole text
  box, and master-page items, don't).
- **Linked boxes can have different widths**: the story now flows into each
  box at that box's own width (it used to use the first box's width).
- **Smaller, faster PDFs**: photos go into PDFs and prints at 300 dpi (the
  print-shop standard) instead of at full size. The 150-photo album's PDF went
  from 323 MB in 53 s to 11 MB in 25 s. *Save as Picture* still uses every
  pixel.

### How the wrapping is built
Text layout is now done by DTP Publisher's own layout (`items/flowlayout.py`)
instead of Qt's. With nothing in the way it reproduces Qt's layout exactly —
line breaks, positions, spacing, list markers, cursor and hit testing are
compared with Qt's on every template (and, with `DTP_PUB_SAMPLES`, on real
Publisher files) — so existing publications don't move by even a pixel.

## 5.1.2 — 2026-10-14 (hardening, second review)

### Fixed
- **Photo albums no longer run out of memory.** Pictures keep only their
  compressed bytes and a preview sized to their frame, made when first shown;
  full size is decoded only for printing and PDFs. A 150-photo, 100-page album
  now opens in about 2 seconds using 750 MB; before, it could not be built on
  an 8 GB computer.
- **Long linked stories open quickly**: each story is laid out once while a
  file opens or a Publisher file is imported (it was once per link: 22 s for a
  story through 100 pages, now under 3 s).
- **Saving streams the file** instead of building it in memory first.
- **Hostile files** (from the second review):
  - The structure of a file is checked before it is parsed, so a small file
    can't make the program use gigabytes.
  - Pictures inside a file are budgeted and never decoded above the insert
    size; absurdly large ones are left as empty frames with a message.
  - Publisher files are size-checked before being copied, LibreOffice's
    temporary files are kept in (and counted against) one folder, and that
    folder is always removed afterwards.
  - Very detailed drawings are drawn without smoothing or, beyond that, shown
    as a labelled box, so no page can take minutes to draw. Their data is
    kept unchanged.
  - At most 20,000 objects in a file and 2,000 on a page.
- **Save no longer waits for an autosave in progress.**

### Added
- `tools/benchmark.py`: open/save/autosave/paint/PDF times and peak memory for
  a large ordinary publication.

## 5.1.1 — 2026-10-14 (hardening)

A defensive release after an adversarial review. No new features; every
finding was reproduced against the 5.1.0 code first (see `REVIEW.md`), and
each behavioural fix has a regression test and a revert proof (the version
pins and the Windows build are checked by hand).

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
- (Fixed in 5.2: text did not wrap around pictures.)
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

# Review of the March prototype (v4) and the v5 rebuild

Every finding below was reproduced against real code before it was fixed: the
original seven with a probe script run against the prototype, the later ones
with a failing test or a measurement.

**Revert proof** means one thing only: `tools/revert_proofs.py` puts the bug
back into a temporary copy of `src/` with an exact text substitution and the
named tests must then fail (and pass on the real code). Behavioural fixes have
one. Packaging and environment changes (pinned versions, the Windows build)
cannot be proven that way and are marked "—" in the Tests column; they are
checked by hand as described in their row.

## Bugs confirmed in the prototype

| # | Bug | Evidence on the prototype | Root cause | Fix | Test |
|---|---|---|---|---|---|
| 1 | Objects moved when a saved file was reopened | A text box at (65, 65) reopened at (−15, −15) | Items were created with a rect offset inside the item (`QRectF(80,80,…)`), but only `pos()` and size were saved | Local rect is always `(0,0,w,h)`; `pos()` is the top-left; `Geo` is saved as-is | `test_r1_positions_survive_save_and_reload` |
| 2 | PDF export and print were essentially blank | A full-page black box covered 0.4 % of the PDF page | Page drawn in points onto a 1200-dpi `QPrinter` (device pixels); one page layout used for all pages; selection handles printed | Targets computed in device units; page layout set per page; `rendering` flag hides handles, guides and grid | `test_r2_*` (3 tests) |
| 3 | No keyboard shortcut worked; typing T/R/E/I inserted objects | 19 shortcuts registered twice; bare-letter shortcuts T, R, E, I | The ribbon created a second `QAction` for each shortcut, so Qt treated them as ambiguous and fired neither | One action registry; ribbon buttons use `setDefaultAction`; canvas-only keys use `WidgetWithChildrenShortcut`; no bare-letter shortcuts | `test_r3_*` |
| 4 | Rotating flung objects off the page | Centre moved from (350, 350) to (−350, 350) on a 90° turn | Transform origin left at (0, 0) | Origin is the box centre, updated on every resize | `test_r4_rotation_pivots_on_centre` |
| 5 | Deleted objects were still written to the file | Deleted shape present in `objects` | Separate `_item_map` never pruned | Pages are serialised straight from their scene | `test_r5_deleted_objects_not_saved` |
| 6 | Grid size / snap distance settings did nothing | `base.GRID_SZ` stayed 12 after setting 50 | Module constants copied with `from … import` at import time | Live `ViewOptions` object read at the moment of use | `test_r6_*` (2 tests) |
| 7 | Guide dragged from the top ruler landed in the wrong place | Drop at x=200 produced a horizontal line at y=200 | Ruler emitted the x coordinate with orientation "H" | The guide follows the mouse onto the page; top ruler gives a horizontal guide at the drop y | `test_r7_*` |

Structural problems also fixed: undo across pages could re-add an item to the
wrong page (`test_undo_on_other_page_stays_on_that_page`); only plain text was
saved; resizing, rotating and text edits could not be undone; there was no
unsaved-changes prompt; and Save always asked for a filename. A pen width of 0
still drew a 1 px hairline round "borderless" boxes, and table text was sized
for the screen's DPI.

## Bugs found during the rebuild

| Bug | How it showed | Fix | Test |
|---|---|---|---|
| Text laid out at screen DPI (96, or 120 at 125 % Windows scaling) in a points-based scene | 11 pt text was about 33 % too big; line breaks would differ between computers | Layout pinned to a 72-dpi paint device with design metrics; painter fonts sized per device | `test_text_point_size_is_true_points` |
| Undo of Ungroup rebuilt the group frame from scratch | After rotating a group, ungrouping, then undoing twice, members ended up in the wrong place | Group commands snapshot and restore the exact frame and member geometry | `test_group_ungroup_preserves_positions_and_rotation` |
| Qt's HTML import rounds paragraph spacing | A newsletter changed slightly after its first save and reload | Spacing rounded to whole units when created | `test_template_roundtrips_without_warnings[newsletter]` |
| Print fit scaled every page into the printable area | Label and business-card sheets would print about 97 % size and miss the pre-cut labels | Pages matching the paper print at exact size from the paper corner; others fit inside the real margins (read before full-page mode resets them) | `test_label_sheet_prints_at_exact_size_on_matching_paper` |
| Hidden guides still caught mouse clicks | Clicks near an invisible guide went to the guide | Guides' visibility follows the view option | `test_hidden_guides_do_not_catch_clicks` |
| Uncaught exceptions in slots abort PyQt6 apps | Any bug would close the app and lose work | `sys.excepthook` writes to `crash.log` and shows a "please save" message | `test_unexpected_errors_are_logged_not_fatal` |

Two weak tests were also found by the revert-proof run and tightened:

- The PDF-coverage test counted QtPdf's transparent background as "dark".
- The print-fit proof exposed that full-page mode zeroes the printer margins.

## 5.1: Publisher import, linked text, label sheets

Found while importing three real Publisher files (kept out of the
repository; `DTP_PUB_SAMPLES` runs them locally):

| Bug | How it showed | Fix | Test |
|---|---|---|---|
| Publisher's box height applied to every box | The diary's title was cut in half | Only boxes that turn out to be linked get Publisher's height back; others keep LibreOffice's | `test_odg_relinks_duplicated_story_and_restores_box_heights` |
| Gradient opacity ignored | A see-through gradient over the diary cover hid the word "Diary" | `draw:opacity` / `draw:opacity-name` applied to both gradient colours | `test_odg_builds_page_master_background_text_and_shapes` |
| Split story joined to the wrong box | The newsletter story carried on into the address line ("DEC 1997") | The continuation must start lower-case, be later in reading order on the same page and have the same column width | `test_odg_joins_split_story_to_same_width_box` |
| `META_ESCAPE` counted as drawing | Publisher photos (WMF-wrapped bitmaps) were redrawn as vector art at low quality | 0x0626 removed from the drawing records | `test_wmf_photo_with_escape_record_is_unwrapped_as_bitmap` |

LibreOffice's Publisher reader (libmspub) gives every box of a linked story
the whole story and grows each box to fit. The importer groups boxes with
identical text, links them in reading order (page, column, top), and restores
Publisher's box height from `fo:min-height`.

## 5.1.1: adversarial review (resource limits and autosave)

Every finding was reproduced against the 5.1.0 code before anything was
changed. Memory figures are peak resident memory of a fresh process.

| # | Finding | Reproduced on 5.1.0 | Fix | Tests |
|---|---|---|---|---|
| A1 | Embedded ODG pictures decompressed with no limit | A 2 MB converted file peaked at **4 GB** and failed with `MemoryError` | Per-picture and whole-file budgets checked from the zip header *and* while streaming; each picture read once | `test_odg_picture_bomb_is_not_decompressed`, `test_odg_total_picture_budget`, `test_odg_repeated_picture_is_read_once` |
| A2 | Picture files read whole before checking | A 2.6 MB pixel-bomb PNG peaked at **3 GB**; large files were slurped | Size checked before reading; big photos decoded from the file at reduced size; bytes kept only when used as-is | `test_huge_picture_file_is_refused_without_reading_it`, `test_unreadable_big_file_is_not_slurped`, `test_very_large_photo_is_decoded_at_reduced_size` |
| A3 | Raster export sized only by the page | A 14,400 pt page at 150 dpi peaked at **3.5 GB**; page sizes in files were not clamped | Pixel budget checked before allocating; Save as Picture lowers the dpi and says so; page size, margins, gutter, guides clamped on load | `test_raster_export_budget_is_checked_before_allocating`, `test_page_size_from_file_is_clamped`, `test_save_as_picture_lowers_dpi_instead_of_failing` |
| A4 | No complexity budget | 100,000 objects in a 30 MB file took **13 s** to open; 20,000 pages opened | `LoadBudget` counts pages, objects (in groups too) and text before any Qt object is made; same for paste | `test_too_many_*`, `test_clipboard_over_budget_pastes_nothing` |
| A5 | Autosave write racing Save | Holding the writer, then saving: the stale recovery file **reappeared** | Generation numbers; discard makes earlier requests stale under a lock (5.1.2: the lock now covers only the final rename, see B4) | `tests/test_autosave_races.py` |
| A6 | Autosave serialised on the GUI thread | 50 × 5 MB photos: **2.4 s** freeze per autosave | JSON encoding moved to the worker; pictures keep their encoded text. Now ~1 ms after the first autosave (the first encodes each new photo once) | measured; docstring corrected |
| A7 | Qt loosely pinned | `PyQt6>=6.5,<7` | Exact tested versions pinned; Windows wheels verified to exist for Python 3.11 | — |
| A8 | Bootstrap needs Python + internet | — | PyInstaller build (`build_exe.bat`), checked on Linux | — |
| A9 | `.bak` failure swallowed | Save reported success; no `.bak` | `write_atomic` returns whether the backup worked; the window warns | `test_backup_failure_is_reported_but_save_succeeds`, `test_window_tells_the_user_when_the_backup_failed` |
| A10 | Lenient base64 | Junk characters were silently accepted | Strict decode first. **Deviation from the review:** rather than always rejecting, damaged text is retried leniently and kept only if Qt decodes a real picture, with a "please check it" note; otherwise an empty frame and a warning | `test_damaged_picture_text_is_repaired_with_a_warning`, `test_garbage_picture_becomes_empty_frame_with_a_warning` |
| A11 | 200 MB XML allowance | 50 MB of XML peaked at **1.7 GB** (expat already rejects entity expansion) | 48 MB per XML part and 1.5 M elements, streamed into a counting tree builder. Real converted files: 0.06–0.38 MB | `test_odg_xml_size_and_element_limits`, `test_odg_entity_expansion_is_rejected` |
| A12 | No output budget for LibreOffice | Only "size > 0" was checked | Converted file and temp folder size-checked (temp folder while it runs) | `test_converted_output_too_large_is_refused` |

Found while doing the above:

- Duplicate ids in a file: whichever box Qt listed last won, so a copied box
  could take over a linked story (`test_duplicate_uid_cannot_hijack_a_text_link`).
  Ids are now made unique in file order before anything is built.
- ODG lengths such as `1e30mm` reached Qt unclamped (`test_odg_absurd_dimensions_do_not_crash`).
- The first version of `LoadBudget` copied the limits as default arguments at
  import time — the prototype's grid-size bug again — so the limits could not
  be changed at run time. Found by its own tests; now read when used.

All of these are in `tools/revert_proofs.py` (32 proofs).

## 5.1.2: second review (B1–B6) and a large-document benchmark

All six findings reproduced. The benchmark the reviewer asked for
(`tools/benchmark.py`: 100 pages, 950 objects, 150 photos at the 3000-pixel
insert size, a story linked through all 100 pages) found a bigger problem than
any of them, listed first.

| # | Finding | Reproduced on 5.1.1 | Fix | Tests |
|---|---|---|---|---|
| — | **Photo albums ran out of memory** (benchmark) | Each picture kept its full decode plus a 1600 px preview: about 35 MB per 1.2 MB photo. 40 photos used 1.5 GB; building the 150-photo album was **killed for lack of memory** on an 8 GB machine | Only the compressed bytes are kept; the screen preview is sized to the frame (≈ 600 px for a 150 pt frame) and made when first drawn; full size is decoded only to print or export | `test_pictures_keep_only_bytes_and_a_frame_sized_preview`, `test_preview_survives_save_and_reload_without_reencoding` |
| — | Opening a long linked story was quadratic (benchmark) | 22 s to open, 20 s of it laying the story out once per link | Links made during loading and import share one layout per story (`deferred_layout`) | `test_opening_lays_out_each_story_once`, `test_import_lays_out_each_story_once` |
| B1 | JSON parsed before any budget | 64 MB of `{}` used **+1.5 GB** and opened | Values are counted outside strings before parsing (no copy of the file); the file bytes are released before parsing. The 512 MB file limit is **kept**: a 150-photo album is 236 MB, and size was never what multiplied | `test_json_structure_refused_before_parsing`, `test_json_structure_counts_only_outside_strings`, `test_clipboard_structure_bomb_pastes_nothing` |
| B2 | Embedded pictures not budgeted | Worse than reported: a **2 MB** file with eight 8000 × 8000 PNGs used 1.8 GB (each held at full size); 40 of them in 10 MB took 35 s | Per-picture and total budgets before decoding; pictures over 50 MP refused with a plain message; nothing decoded above 3000 px | `test_embedded_picture_budget_checked_before_decoding`, `test_total_embedded_pictures_budget`, `test_embedded_picture_beyond_pixel_limit_is_refused`, `test_huge_embedded_picture_is_never_decoded_full_size` |
| B3 | `.pub` copied before any check | A 3 GB file reached `copyfile` unchecked; a failed copy also **left its temp folder behind** | Source size checked before copying (1 GB); copy capped; any failure removes the work folder; LibreOffice's own temp files are kept inside it and the whole folder is watched | `test_pub_source_size_checked_before_copying`, `test_failed_conversion_leaves_no_temp_folder`, `test_libreoffice_temp_files_count_against_the_budget` |
| B4 | Save waits for a running autosave | Save waited 0.86 s for a large autosave | The writer encodes and writes to a temporary file with no lock held; under the lock it only renames, and only if still current. Leftovers from a crash are cleaned up | `test_save_does_not_wait_for_a_running_autosave`, `test_crashed_write_leftovers_are_cleaned_up` |
| B5 | Only text-box HTML counted | Much worse than "low-medium": a 76 MB file with **20 drawings took 382 s to draw one page**. Qt's smoothed drawing costs roughly (edges crossed per pixel row) × rows, and more once the pen is wider than a pixel | Budget counts drawing data per page and per file, table cells and pictures. Each drawing's *edge density* is measured once; dense drawings are drawn without smoothing, very dense ones (or beyond the page's allowance) as a labelled box. On screen a page shares one smoothing allowance that shrinks with zoom²; printing smooths up to a higher limit. Data is never changed | `test_drawing_detail_on_a_hostile_page`, `test_screen_smoothing_shares_one_allowance_per_page`, `test_smoothed_drawings_per_page_are_capped`, `test_simple_drawings_stay_smooth`, `test_page_drawing_detail_budget_refuses_file`, `test_table_cells_count_as_text` |
| B6 | 50,000 objects too many | 50,000 objects: 16 s to open, 5 s to paint one page | 20,000 objects (6.8 s to open spread over pages); 2,000 per page | `test_objects_per_page_limit` |

**Worst cases now** (this machine; a home PC may be 1.5–2× slower):

| Case | 5.1.1 | 5.1.2 |
|---|---|---|
| 150-photo, 100-page album (236 MB) | killed: out of memory | opens in 2.4 s, peak 753 MB; saves in 1.5 s |
| 40-photo, 20-page newsletter (63 MB) | opens 4.8 s, 1,494 MB | opens 0.7 s, 232 MB |
| 64 MB of `{}` | 1.5 GB, opened | refused in 0.3 s at 232 MB |
| 2 MB file, 8 × 8000² PNG | 1.8 GB | refused per picture, 0.1 s |
| 20 dense drawings on a page | 382 s to draw | file refused (page drawing budget) |
| Densest page the budgets allow | — | 3.4 s to redraw at 200 % (2,000 overlapping drawings); 2.3 s for 2,000 full-page plain shapes, which is the floor any editor has for that much overdraw |

Remaining, on purpose: PDFs embed photos at full resolution (the 150-photo
album makes a 323 MB PDF in 47 s); downsampling to 300 dpi would make them
smaller and faster. Loaded pictures keep both their bytes and their base64
text (about 1.8 × the photo data) so autosave never re-encodes them.

All of these are in `tools/revert_proofs.py` (49 proofs at 5.1.2; 64 at 5.2; 66 at 5.2.1; 76 at 5.2.2; 82 at 5.2.3; 87 at 5.3; 90 at 5.3.1).

## 5.2: text wrap, a layout of our own

Qt's document layout can't flow text around a hole or through boxes of
different widths, so 5.2 lays text out itself (`items/flowlayout.py`). The
risk is that everything already made shifts, so the layout copies Qt's
arithmetic (`QTextDocumentLayoutPrivate::layoutBlock`, Qt 6) including its
fixed-point rounding, and is compared with Qt's own layout:

- line by line (position, width, characters, height) on every template and
  nine synthetic cases (lists, margins, every line-height type, indents,
  alignment, right-to-left, tabs, unbreakable words): identical;
- pixel by pixel when drawn, with a cursor and with selections, and position
  by position when hit-testing, including points 0.0015 pt from line edges:
  identical (one deliberate difference: Qt hides the number of a selected list
  item, this layout shows it);
- after each of 250 random edits (typing, deleting, new paragraphs, spacing
  and size changes), checking the incremental relayout: identical;
- on real Publisher files (`DTP_PUB_SAMPLES`): identical.

Bugs found while building it, each revert-proven:

| Bug | How it showed | Fix | Test |
|---|---|---|---|
| Qt's QFixed truncates; rounding was used | 114 of 126 boxes 1/64 pt narrower in Qt | Truncate like `QFixed::fromReal` | `test_layout_matches_qt_line_for_line` |
| Incremental relayout compared paragraphs by number | After inserting a paragraph the rest of the story was 27–40 pt out | Map paragraphs across insertions/removals | `test_incremental_layout_matches_qt_while_editing` |
| Convergence compared the widest line too | Typing in a 170,000-character story relaid it all (36 ms a key) | Compare position only (9 ms) | (speed; measured) |
| Hit test in floating point | Clicks 0.0015 pt above a line went to the start of the story | Hit-test in Qt's fixed point | `test_drawing_and_hit_testing_match_qt` |
| List marker offset `int / 2` | Bullets one pixel off | Integer division as in Qt | same |
| Selection not clipped to the frame | A selected justified paragraph's highlight ran past the box | Clip to the root frame as Qt does | real files only (`test_real_publisher_text_lays_out_exactly_as_qt`); proven by hand, as no synthetic text reproduced it |
| A line stuck at an obstacle's edge | Importing the Christmas newsletter hung: a line at y = 183.546875 against an obstacle ending at 183.546875000001 | Steps past an obstacle always move down; an obstacle ending at a line's top doesn't block it | `test_step_past_an_obstacle_always_moves_down`, `test_obstacle_ending_at_the_line_top_does_not_block_it` |
| Slivers used | "Life / in / Austr / alia / is / gre" one word a line beside a picture; "Fro" left of a banner | Gaps under 36 pt or 20 % of the column are skipped | `test_narrow_gaps_are_skipped` |
| Import: stacking compared by z inside groups | A column was taken for a decoration covering a grouped text box | Use the page's real stacking order | `test_imported_pictures_wrap_unless_they_cover_the_text` |
| Template: tilted album photos reach their captions | Captions pushed out of their boxes | Those photos don't wrap | `test_no_template_text_is_pushed_by_its_own_pictures` |

Speed: a keystroke in a 20,000-character box with a picture takes 8 ms; each
step of dragging a picture over it 7 ms. The 100-page benchmark album opens
in 3.1 s (2.4 s with Qt's layout).

PDF photos: drawn at 300 dpi for PDFs and printers (checked with `pdfimages`:
625 × 467 pixels for a 150 × 112 pt frame), full resolution for picture
exports (`test_pdf_photos_are_embedded_at_print_resolution`).

## 5.2.1: first run of the tests on Windows

Leon ran the suite on Windows (Python 3.11.5): 7 of 259 failed; both causes
were real and are fixed with revert-proven tests.

| Bug | How it showed | Fix | Test |
|---|---|---|---|
| Template text boxes sized for one set of font metrics | 6 templates overflowed on Windows (real Calibri/Georgia have taller lines than Carlito/DejaVu used in development) | A template box that would overflow shrinks its text to fit | `test_templates_fit_on_computers_with_taller_fonts` (simulated with 1.5 em lines) |
| Crash handler wrote to an invalid console | `OSError: [WinError 6] The handle is invalid` inside the handler, so no message and no chance to save | Console output is best-effort | `test_error_handler_survives_a_missing_console` |

The layout equivalence tests (`tests/test_flowlayout.py`) passed on Windows
with its real fonts, so the new text layout matches Qt there too.

## 5.2.2: third review (C1–C5) and wrap torture tests

| # | Finding | Checked against 5.2.1 | Fix | Tests |
|---|---|---|---|---|
| C1 | Nested frames / tables not supported by the layout | **Confirmed.** Pasting a table gave a stack of loose cells; a `<div>` box lost its border; an inline picture became an invisible character | Pasted (and loaded) text is brought into the story model (`items/richtext.py`): table → one paragraph per row, cells tab-separated (a cell's own paragraphs become line breaks); boxed sections → paragraphs; inline pictures removed; formatting kept | `test_pasted_tables_frames_and_pictures_become_story_text`, `test_pasting_in_the_editor_flattens`, `test_old_file_with_a_table_is_flattened_on_load` |
| C2 | JSON precheck undercounts dictionaries | **Confirmed.** A 30 MB file of 2.4 M `"k":[]` entries counted 4.8 M (limit 5 M) but made 7.2 M objects and opened | Colons (one key each) are counted too; it is now refused | `test_dictionary_keys_count_towards_the_json_budget` |
| C3 | `documentSizeChanged` emitted twice | **Not reproduced**: the shipped file emits it once (`flowlayout.py`, `_finish`). Checked anyway with a signal counter; found instead that width-only changes were *not* signalled | Signal on any size change | `test_document_size_signal_once_per_change`, `test_width_shrinks_when_the_widest_paragraph_does` |
| C4 | Width stale after the widest line shrinks | **Confirmed** with an unbreakable line (pasted `<pre>`): Qt 160 pt, FlowLayout still 1,010 pt | Each paragraph's widest line is kept; the width is their maximum | `test_width_shrinks_when_the_widest_paragraph_does` |
| C5 | Declare the text model | Agreed | Stated in `items/richtext.py`, README and CHANGELOG | — |

The suggested torture cases (several, touching and overlapping pictures,
right-to-left text, rotated pictures, linked boxes each with their own
pictures) became a randomised test: 400 random arrangements in the suite,
3,000 run once. It checks that every character is laid out once and in order,
no line crosses an obstacle, and every line fits its box. It found two real bugs:

- **Text over a picture at the bottom of the last box.** When a picture
  reached past the last box's bottom, the line was laid across it instead of
  below it (overflowing). Visible when the picture sat near the box's bottom.
- **Box tops not in fixed point.** Lines placed at a box's top came out up to
  1/64 pt above it, in the previous box's band.

Also from the review: right-to-left text now takes the right-hand gap on a tie
(`test_right_to_left_text_takes_the_right_hand_gap`), horizontal rules are
drawn as Qt draws them (added to the equivalence set), and the real-file test
now does `.pub` → import → save → reopen → PDF (`test_real_publisher_round_trip`).

## 5.2.3: fourth review (D1–D2)

| # | Finding | Checked against 5.2.2 | Fix | Tests |
|---|---|---|---|---|
| D1 | `flatten()` stops after 64 frames | **Confirmed.** 100 pasted tables left 36 in place; 1,000 left 936. While reproducing it, nesting turned out to be worse: a cell holding text, then a table, then text **crashed Qt** (segfault) at 2 levels. Cause: the outer table was taken apart first, so the inner table was re-inserted inside a row and the paragraph join turned its frame-edge characters into line breaks, corrupting it | Frames are unwrapped inside-out in one walk (a frame is reached only after the frames inside it, so a cell never holds a frame when it is copied); the join only replaces real paragraph separators; budget `MAX_RICH_STRUCTURES` = 5,000; over budget, the story falls back to its plain text; `flatten` re-checks the invariant before returning | `test_a_hundred_tables_keep_their_formatting`, `test_cell_with_text_round_a_nested_table_does_not_crash` (in a separate process), `test_joining_paragraphs_never_merges_into_a_table`, `test_over_the_structure_budget_falls_back_to_plain_text` |
| D2 | Inline-object stripping stops at 100,000 | **Confirmed by reading** (the loop simply ends) | Budget `MAX_INLINE_OBJECTS` = 20,000, then the plain-text fallback | `test_over_the_picture_budget_falls_back_to_plain_text` |
| — | `assert_story_model` over every input path | Agreed | One check (no frames, no picture or object formats) run after `insertHtml`, a real Ctrl+V into the editor (with Undo), and loading an old file then save/reopen, each with Word-style HTML (MsoNormal, VML pictures, nested and merged cells, list markup), browser-style HTML (article/figure/nested boxes/thead/inline images), 70-deep nesting and 100 tables | `tests/test_richtext.py` (12 corpus cases) |

Found while checking D1: a table cell with three or more paragraphs was only
partly joined into its row (`_join_blocks` kept a handle to a paragraph it had
just merged away) — `test_every_paragraph_of_a_cell_joins_its_row`. And the
conversion was slow (each step relaid and notified separately: 5,000 tables
took 6.3 s); it is now one edit block, 0.22 s and one Undo step
(`test_flatten_is_one_undo_step`). Qt's own HTML parsing of 20,000 inline
pictures takes about a minute before any of our code runs; that is outside
the program's control.

## Not done yet (candidates for a later version)

- Saving back to `.pub` (not possible: no program but Publisher writes it).
- Master pages, as a shared background for every page. Headers, footers and
  page numbers can already be added to every page in one step.
- Spell checking.
- On Windows the native print dialog does not show the extra "fit to paper"
  option; matching paper sizes print exact, others fit automatically.

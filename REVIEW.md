# Review of the March prototype (v4) and the v5 rebuild

Every finding below was reproduced against real code before it was fixed: the
original seven with a probe script run against the prototype, the later ones
with a failing test. Each fix has a regression test, and
`tools/revert_proofs.py` puts each bug back into a temporary copy of `src/` and
confirms that its test fails.

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
| A5 | Autosave write racing Save | Holding the writer, then saving: the stale recovery file **reappeared** | Generation numbers; discard makes earlier requests stale under a lock and waits for a write in progress | `tests/test_autosave_races.py` |
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

## Not done yet (candidates for a later version)

- Text wrap around pictures. Imported newsletters can have a photo sitting
  over a column; LibreOffice has the same gap.
- Saving back to `.pub` (not possible: no program but Publisher writes it).
- Master pages, as a shared background for every page. Headers, footers and
  page numbers can already be added to every page in one step.
- Spell checking.
- On Windows the native print dialog does not show the extra "fit to paper"
  option; matching paper sizes print exact, others fit automatically.

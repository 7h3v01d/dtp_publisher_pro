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

## Not done yet (candidates for a later version)

- Linked text boxes, so overflowing text flows into the next column or page.
  Newsletters use separate boxes per column for now.
- Master pages, as a shared background for every page. Headers, footers and
  page numbers can already be added to every page in one step.
- Spell checking.
- On Windows the native print dialog does not show the extra "fit to paper"
  option; matching paper sizes print exact, others fit automatically.

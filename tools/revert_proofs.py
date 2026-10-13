# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Revert-proof the regression tests.

For every fix: copy src/ to a temp folder, re-introduce the bug with an exact
text substitution, and run the matching tests against the broken copy.  A
proof PASSES when those tests FAIL on the broken code (and pass on the real
code).  Usage:  python tools/revert_proofs.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
PKG = "dtp_publisher"

# (name, file, original text, bug re-introduced, tests that must fail)
PROOFS = [
    ("#1 positions not preserved on reload",
     "items/base.py",
     '"x": round(g.x, 4), "y": round(g.y, 4),',
     '"x": round(self.scene_box().left(), 4), "y": round(self.scene_box().top(), 4),',
     ["tests/test_regressions.py::test_r1_positions_survive_save_and_reload"]),
    ("#2 PDF drawn in points on a 1200-dpi device",
     "export.py",
     "target = QRectF(0, 0, sc.page_w / 72.0 * dpi, sc.page_h / 72.0 * dpi)",
     "target = QRectF(0, 0, sc.page_w, sc.page_h)",
     ["tests/test_regressions.py::test_r2_pdf_fills_the_page"]),
    ("#2b selection handles printed",
     "export.py",
     "    scene.rendering = True\n",
     "    scene.rendering = False\n",
     ["tests/test_regressions.py::test_r2_selection_handles_not_printed"]),
    ("#3 every shortcut registered twice (ambiguous)",
     "ui/window.py",
     "            a.setShortcuts(seqs)\n",
     "            a.setShortcuts(seqs)\n            _dup = QAction(self)\n"
     "            _dup.setShortcuts(seqs)\n            self.addAction(_dup)\n",
     ["tests/test_regressions.py::test_r3_no_duplicate_or_bare_letter_shortcuts",
      "tests/test_regressions.py::test_r3_shortcut_actually_fires"]),
    ("#4 rotation about the top-left corner",
     "items/base.py",
     "        self.setTransformOriginPoint(self._w / 2, self._h / 2)\n        self.setPos(QPointF(g.x, g.y))",
     "        self.setTransformOriginPoint(0, 0)\n        self.setPos(QPointF(g.x, g.y))",
     ["tests/test_regressions.py::test_r4_rotation_pivots_on_centre"]),
    ("#5 deleted objects still saved",
     "commands.py",
     "class DeleteItemsCmd(SceneCommand):\n    def __init__(self, scene: \"PageScene\", items: Iterable[\"BaseItem\"], text: str = \"Delete\"):\n        super().__init__(text, scene)\n        self.items = list(items)\n\n    def redo(self):\n        for it in self.items:\n            it.setSelected(False)\n            if it.scene() is self.scene:\n                self.scene.removeItem(it)",
     "class DeleteItemsCmd(SceneCommand):\n    def __init__(self, scene: \"PageScene\", items: Iterable[\"BaseItem\"], text: str = \"Delete\"):\n        super().__init__(text, scene)\n        self.items = list(items)\n\n    def redo(self):\n        for it in self.items:\n            it.setSelected(False)\n            it.setVisible(False)",
     ["tests/test_regressions.py::test_r5_deleted_objects_not_saved"]),
    ("#6 grid/snap settings copied as constants",
     "scene.py",
     "                c = round(val / v.grid_size) * v.grid_size",
     "                c = round(val / 14.17) * 14.17",
     ["tests/test_regressions.py::test_r6_grid_size_setting_changes_snapping"]),
    ("#6b snap distance copied as a constant",
     "scene.py",
     "        return self.doc.view.snap_px / max(self.zoom, 0.05)",
     "        return 8 / max(self.zoom, 0.05)",
     ["tests/test_regressions.py::test_r6_snap_distance_setting_changes_tolerance"]),
    ("#7 top-ruler guide uses the x coordinate",
     "ui/canvas.py",
     "        self._drag.set_position(sp.y() if self._drag.orient == \"H\" else sp.x())",
     "        self._drag.set_position(sp.x() if self._drag.orient == \"H\" else sp.y())",
     ["tests/test_regressions.py::test_r7_top_ruler_creates_horizontal_guide_where_dropped"]),
    ("new: text laid out at screen DPI",
     "items/text.py",
     "        doc.documentLayout().setPaintDevice(layout_device())\n",
     "",
     ["tests/test_core.py::test_text_point_size_is_true_points"]),
    ("new: undo of ungroup loses group rotation",
     "commands.py",
     "        self.group.restore(self.snap)\n        self._changed()\n\n\nclass TextCmd",
     "        self.group.adopt(self.children)\n        self._changed()\n\n\nclass TextCmd",
     ["tests/test_core.py::test_group_ungroup_preserves_positions_and_rotation"]),
    ("new: label sheets shrunk to the printable area",
     "export.py",
     "            if same_size(sc.page_w, sc.page_h, paper.width(), paper.height()):",
     "            if False:",
     ["tests/test_templates_export.py::test_label_sheet_prints_at_exact_size_on_matching_paper"]),
    ("new: hidden guides still catch clicks",
     "scene.py",
     "            g.setVisible(show)          # hidden guides must not catch clicks either\n",
     "",
     ["tests/test_core.py::test_hidden_guides_do_not_catch_clicks"]),
    ("new: Qt HTML rounding drifts paragraph spacing",
     "items/text.py",
     "bf.setBottomMargin(round(space_after))",
     "bf.setBottomMargin(space_after)",
     ["tests/test_templates_export.py::test_template_roundtrips_without_warnings[newsletter]"]),
    ("pub: Publisher box height forced onto every imported box",
     "importers/odg.py",
     "        for frames in chains:\n            for t, *_ in frames:\n                ph = getattr(t, \"_publisher_h\", None)",
     "        for frames in chains + [[f] for f in self._frames]:\n            for t, *_ in frames:\n                ph = getattr(t, \"_publisher_h\", None)",
     ["tests/test_import.py::test_odg_relinks_duplicated_story_and_restores_box_heights"]),
    ("pub: gradient opacity ignored (hides text underneath)",
     "importers/odg.py",
     "            if op is not None:\n                c1.setAlphaF(max(0.0, min(op, 1.0)))\n",
     "            if False:\n                c1.setAlphaF(max(0.0, min(op, 1.0)))\n",
     ["tests/test_import.py::test_odg_builds_page_master_background_text_and_shapes"]),
    ("pub: split story joined to a box of a different width",
     "importers/odg.py",
     "                if abs(t.w - last[0].w) > 0.1 * max(t.w, last[0].w):   # same column width\n                    continue\n",
     "",
     ["tests/test_import.py::test_odg_joins_split_story_to_same_width_box"]),
    ("pub: META_ESCAPE counted as vector drawing",
     "importers/metafile.py",
     "0x0521, 0x081A, 0x0830, 0x0A24}",
     "0x0521, 0x081A, 0x0830, 0x0A24, 0x0626}",
     ["tests/test_import.py::test_wmf_photo_with_escape_record_is_unwrapped_as_bitmap"]),
]


def run(tests, src) -> int:
    env = dict(os.environ, DTP_SRC=src, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                       cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=600)
    return r.returncode


def main() -> int:
    ok = True
    for name, rel, old, new, tests in PROOFS:
        if run(tests, SRC) != 0:
            print(f"FAIL  {name}: tests do not pass on the real code")
            ok = False
            continue
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "src")
            shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
            path = os.path.join(dst, PKG, rel)
            text = open(path, encoding="utf-8").read()
            if text.count(old) != 1:
                print(f"FAIL  {name}: patch anchor found {text.count(old)} times in {rel}")
                ok = False
                continue
            open(path, "w", encoding="utf-8").write(text.replace(old, new))
            code = run(tests, dst)
        if code == 0:
            print(f"FAIL  {name}: tests still pass with the bug put back")
            ok = False
        else:
            print(f"ok    {name}")
    print("\nAll fixes are revert-proven." if ok else "\nSome proofs failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

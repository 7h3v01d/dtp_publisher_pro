# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Document: an ordered list of pages (one QGraphicsScene each) + undo stack."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QUndoStack

from .units import DEFAULT_PAGE, mm


class ViewOptions(QObject):
    """Grid / guide / snapping options shared by every page of a document.

    These used to be module-level constants that other modules copied at
    import time, so changing them in the UI had no effect (bug #6).  They are
    now live attributes read at the moment they are used.
    """

    changed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.show_grid = False
        self.show_guides = True
        self.show_boundaries = True
        self.grid_size = mm(5)        # points
        self.snap_grid = False
        self.snap_objects = True
        self.snap_guides = True
        self.snap_px = 8              # screen pixels

    FIELDS = ("show_grid", "show_guides", "show_boundaries", "grid_size",
              "snap_grid", "snap_objects", "snap_guides", "snap_px")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.FIELDS}

    def update_from(self, d: dict):
        for k in self.FIELDS:
            if k in d:
                v = d[k]
                cur = getattr(self, k)
                if isinstance(cur, bool):
                    v = bool(v)
                elif isinstance(cur, (int, float)):
                    try:
                        v = type(cur)(v)
                    except (TypeError, ValueError):
                        continue
                    if k == "grid_size":
                        v = min(max(v, 1.0), 500.0)
                    if k == "snap_px":
                        v = min(max(int(v), 1), 50)
                setattr(self, k, v)
        self.changed.emit()

    def set(self, key: str, value):
        if key not in self.FIELDS:
            raise KeyError(key)
        setattr(self, key, value)
        self.changed.emit()


class Document(QObject):
    pagesChanged = pyqtSignal()           # structure: add/remove/move/rename
    pageContentChanged = pyqtSignal(object)  # PageScene whose content changed

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.undo_stack = QUndoStack(self)
        self.view = ViewOptions(self)
        self.pages: List["PageScene"] = []
        self.path: Optional[str] = None
        self.title = ""
        self.view.changed.connect(self._view_changed)

    # ── page factory / structure (raw; undoable wrappers live in commands) ──
    def make_page(self, width: float = DEFAULT_PAGE.width, height: float = DEFAULT_PAGE.height,
                  name: str = "", **setup) -> "PageScene":
        from .scene import PageScene
        sc = PageScene(self, width, height)
        sc.name = name
        if setup:
            st = sc.setup_state()
            st.update(setup)
            sc.apply_setup(st)
        return sc

    def add_page(self, scene: "PageScene") -> "PageScene":
        self.insert_page(len(self.pages), scene)
        return scene

    def insert_page(self, index: int, scene: "PageScene"):
        index = max(0, min(index, len(self.pages)))
        scene.doc = self
        self.pages.insert(index, scene)
        self.pagesChanged.emit()

    def take_page(self, index: int) -> "PageScene":
        sc = self.pages.pop(index)
        self.pagesChanged.emit()
        return sc

    def move_page(self, src: int, dst: int):
        if src == dst:
            return
        sc = self.pages.pop(src)
        dst = max(0, min(dst, len(self.pages)))
        self.pages.insert(dst, sc)
        self.pagesChanged.emit()

    def index_of(self, scene: "PageScene") -> int:
        for i, s in enumerate(self.pages):
            if s is scene:
                return i
        return -1

    def page_label(self, scene: "PageScene") -> str:
        i = self.index_of(scene)
        base = f"Page {i + 1}"
        return f"{base} — {scene.name}" if scene.name else base

    # ── state ────────────────────────────────────────────────────────────────
    def is_modified(self) -> bool:
        return not self.undo_stack.isClean()

    def mark_saved(self):
        self.undo_stack.setClean()

    def all_items(self):
        for sc in self.pages:
            yield from sc.all_design_items()

    def _view_changed(self):
        for sc in self.pages:
            sc.view_options_changed()

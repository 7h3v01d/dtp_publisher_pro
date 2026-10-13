# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Undo/redo commands.

Convention: the UI applies a change live, then pushes a command describing
it.  ``QUndoStack.push`` calls ``redo()`` immediately, so every ``redo`` is
idempotent (it re-applies the new state, which is already in place).

Every command that touches a page keeps a reference to that page's scene.
Because each page owns its own scene, undoing a change made on page 3 while
viewing page 1 modifies page 3 — never the page currently on screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QUndoCommand

from .geometry import Geo

if TYPE_CHECKING:  # pragma: no cover
    from .document import Document
    from .items.base import BaseItem
    from .items.group import GroupItem
    from .scene import GuideItem, PageScene

# Merge ids for commands that coalesce (QUndoCommand.id()).
ID_NUDGE = 1001
ID_PROP = 1002


class SceneCommand(QUndoCommand):
    """Base for commands that belong to one page; lets the UI follow undo."""

    scene: "PageScene | None" = None

    def __init__(self, text: str, scene: "PageScene | None"):
        super().__init__(text)
        self.scene = scene

    def _changed(self):
        if self.scene is not None:
            self.scene.content_changed()


# ── items ────────────────────────────────────────────────────────────────────
class AddItemsCmd(SceneCommand):
    def __init__(self, scene: "PageScene", items: Iterable["BaseItem"], text: str = "Add object"):
        super().__init__(text, scene)
        self.items = list(items)

    def redo(self):
        for it in self.items:
            if it.scene() is not self.scene:
                self.scene.addItem(it)
        self._changed()

    def undo(self):
        for it in self.items:
            it.setSelected(False)
            if it.scene() is self.scene:
                self.scene.removeItem(it)
        self._changed()


class DeleteItemsCmd(SceneCommand):
    def __init__(self, scene: "PageScene", items: Iterable["BaseItem"], text: str = "Delete"):
        super().__init__(text, scene)
        self.items = list(items)

    def redo(self):
        for it in self.items:
            it.setSelected(False)
            if it.scene() is self.scene:
                self.scene.removeItem(it)
        self._changed()

    def undo(self):
        for it in self.items:
            if it.scene() is not self.scene:
                self.scene.addItem(it)
        self._changed()


class MoveItemsCmd(SceneCommand):
    def __init__(self, scene, moves: Dict["BaseItem", Tuple[QPointF, QPointF]],
                 text: str = "Move", nudge: bool = False):
        super().__init__(text, scene)
        self.moves = {it: (QPointF(a), QPointF(b)) for it, (a, b) in moves.items()}
        self.nudge = nudge

    def id(self):
        return ID_NUDGE if self.nudge else -1

    def mergeWith(self, other):
        if not (self.nudge and getattr(other, "nudge", False)):
            return False
        if set(other.moves) != set(self.moves):
            return False
        for it, (_, new) in other.moves.items():
            self.moves[it] = (self.moves[it][0], QPointF(new))
        return True

    def redo(self):
        for it, (_, new) in self.moves.items():
            it.setPos(new)
        self._changed()

    def undo(self):
        for it, (old, _) in self.moves.items():
            it.setPos(old)
        self._changed()


class GeometryCmd(SceneCommand):
    """Size/position/rotation change of one or more items."""

    def __init__(self, scene, changes: Dict["BaseItem", Tuple[Geo, Geo]], text: str = "Resize"):
        super().__init__(text, scene)
        self.changes = dict(changes)

    def redo(self):
        for it, (_, new) in self.changes.items():
            it.set_geometry(new)
        self._changed()

    def undo(self):
        for it, (old, _) in self.changes.items():
            it.set_geometry(old)
        self._changed()


class PropCmd(SceneCommand):
    """Change of one named property on one or more items."""

    def __init__(self, scene, items: Iterable["BaseItem"], key: str, new_value: Any,
                 old_values: Optional[Dict["BaseItem", Any]] = None,
                 text: str = "Change property", merge: bool = False):
        super().__init__(text, scene)
        self.items = list(items)
        self.key = key
        self.new = new_value
        self.old = old_values if old_values is not None else {
            it: it.get_prop(key) for it in self.items
        }
        self.merge = merge

    def id(self):
        return ID_PROP if self.merge else -1

    def mergeWith(self, other):
        if not (self.merge and getattr(other, "merge", False)):
            return False
        if other.key != self.key or other.items != self.items:
            return False
        self.new = other.new
        return True

    def redo(self):
        for it in self.items:
            it.set_prop(self.key, self.new)
        self._changed()

    def undo(self):
        for it in self.items:
            it.set_prop(self.key, self.old[it])
        self._changed()


class MultiPropCmd(SceneCommand):
    """Several (item, key, old, new) changes as one undo step."""

    def __init__(self, scene, changes: List[Tuple["BaseItem", str, Any, Any]], text: str):
        super().__init__(text, scene)
        self.changes = list(changes)

    def redo(self):
        for it, key, _, new in self.changes:
            it.set_prop(key, new)
        self._changed()

    def undo(self):
        for it, key, old, _ in reversed(self.changes):
            it.set_prop(key, old)
        self._changed()


class ZOrderCmd(SceneCommand):
    def __init__(self, scene, old: Dict["BaseItem", float], new: Dict["BaseItem", float],
                 text: str = "Arrange"):
        super().__init__(text, scene)
        self.old = dict(old)
        self.new = dict(new)

    def redo(self):
        for it, z in self.new.items():
            it.setZValue(z)
        self._changed()

    def undo(self):
        for it, z in self.old.items():
            it.setZValue(z)
        self._changed()


class GroupCmd(SceneCommand):
    def __init__(self, scene, group: "GroupItem", children: List["BaseItem"]):
        super().__init__("Group", scene)
        self.group = group
        self.children = list(children)
        self.snap = None

    def redo(self):
        if self.group.scene() is not self.scene:
            self.scene.addItem(self.group)
        if self.snap is None:
            self.group.adopt(self.children)
            self.snap = self.group.snapshot()
        else:
            self.group.restore(self.snap)
        self._changed()

    def undo(self):
        self.group.setSelected(False)
        self.group.release()
        if self.group.scene() is self.scene:
            self.scene.removeItem(self.group)
        self._changed()


class UngroupCmd(SceneCommand):
    def __init__(self, scene, group: "GroupItem"):
        super().__init__("Ungroup", scene)
        self.group = group
        self.children = list(group.members())
        self.snap = group.snapshot()

    def redo(self):
        self.group.setSelected(False)
        self.group.release()
        if self.group.scene() is self.scene:
            self.scene.removeItem(self.group)
        self._changed()

    def undo(self):
        if self.group.scene() is not self.scene:
            self.scene.addItem(self.group)
        self.group.restore(self.snap)
        self._changed()


class TextCmd(SceneCommand):
    """Rich-text content change of a text frame (stored as HTML)."""

    def __init__(self, scene, item, old_html: str, new_html: str, text: str = "Edit text"):
        super().__init__(text, scene)
        self.item = item
        self.old_html = old_html
        self.new_html = new_html

    def redo(self):
        self.item.set_html(self.new_html)
        self._changed()

    def undo(self):
        self.item.set_html(self.old_html)
        self._changed()


# ── guides ───────────────────────────────────────────────────────────────────
class AddGuideCmd(SceneCommand):
    def __init__(self, scene, guide: "GuideItem"):
        super().__init__("Add guide", scene)
        self.guide = guide

    def redo(self):
        self.scene.attach_guide(self.guide)

    def undo(self):
        self.scene.detach_guide(self.guide)


class RemoveGuideCmd(SceneCommand):
    def __init__(self, scene, guides: Iterable["GuideItem"], text: str = "Remove guide"):
        super().__init__(text, scene)
        self.guides = list(guides)

    def redo(self):
        for g in self.guides:
            self.scene.detach_guide(g)

    def undo(self):
        for g in self.guides:
            self.scene.attach_guide(g)


class MoveGuideCmd(SceneCommand):
    def __init__(self, scene, guide: "GuideItem", old: float, new: float):
        super().__init__("Move guide", scene)
        self.guide, self.old, self.new = guide, old, new

    def redo(self):
        self.guide.set_position(self.new)

    def undo(self):
        self.guide.set_position(self.old)


# ── pages ────────────────────────────────────────────────────────────────────
class PageSetupCmd(SceneCommand):
    def __init__(self, scenes: List["PageScene"], old: List[dict], new: List[dict],
                 text: str = "Page setup"):
        super().__init__(text, scenes[0] if scenes else None)
        self.scenes = list(scenes)
        self.old = list(old)
        self.new = list(new)

    def redo(self):
        for sc, st in zip(self.scenes, self.new):
            sc.apply_setup(st)
            sc.content_changed()

    def undo(self):
        for sc, st in zip(self.scenes, self.old):
            sc.apply_setup(st)
            sc.content_changed()


class AddPageCmd(SceneCommand):
    def __init__(self, doc: "Document", index: int, scene: "PageScene", text: str = "Add page"):
        super().__init__(text, scene)
        self.doc = doc
        self.index = index

    def redo(self):
        self.doc.insert_page(self.index, self.scene)

    def undo(self):
        self.doc.take_page(self.doc.index_of(self.scene))


class RemovePageCmd(SceneCommand):
    def __init__(self, doc: "Document", scene: "PageScene"):
        super().__init__("Delete page", scene)
        self.doc = doc
        self.index = doc.index_of(scene)

    def redo(self):
        self.doc.take_page(self.doc.index_of(self.scene))

    def undo(self):
        self.doc.insert_page(self.index, self.scene)


class MovePageCmd(SceneCommand):
    def __init__(self, doc: "Document", scene: "PageScene", new_index: int):
        super().__init__("Move page", scene)
        self.doc = doc
        self.old_index = doc.index_of(scene)
        self.new_index = new_index

    def redo(self):
        self.doc.move_page(self.doc.index_of(self.scene), self.new_index)

    def undo(self):
        self.doc.move_page(self.doc.index_of(self.scene), self.old_index)


class RenamePageCmd(SceneCommand):
    def __init__(self, doc: "Document", scene: "PageScene", old: str, new: str):
        super().__init__("Rename page", scene)
        self.doc, self.old, self.new = doc, old, new

    def redo(self):
        self.scene.name = self.new
        self.doc.pagesChanged.emit()

    def undo(self):
        self.scene.name = self.old
        self.doc.pagesChanged.emit()

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Load/save ``.dtpub`` documents (JSON) and migrate the old v3 ``.json`` files.

Saves are atomic: the new file is written next to the target, flushed to
disk, and only then swapped in with ``os.replace``.  The previous version is
kept as ``<name>.bak`` so a bad save can never cost the only copy.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsItem

from . import __version__, limits
from .document import Document
from .geometry import rotate_vec
from .items import ITEM_TYPES, BaseItem, GroupItem
from .scene import GuideItem, PageScene

FORMAT = "dtpub"
FORMAT_VERSION = 5
MAX_FILE_BYTES = limits.MAX_FILE_BYTES


class DocumentError(Exception):
    """Raised for files that cannot be opened."""


# ── items ────────────────────────────────────────────────────────────────────
def item_to_dict(it: BaseItem) -> Dict[str, Any]:
    return it.to_dict()


def item_from_dict(d: Dict[str, Any], warnings: Optional[List[str]] = None,
                   depth: int = 0) -> Optional[BaseItem]:
    if not isinstance(d, dict) or depth > limits.MAX_GROUP_DEPTH:
        return None
    cls = ITEM_TYPES.get(d.get("kind"))
    if cls is None:
        if warnings is not None:
            warnings.append(f"Skipped unknown object type {d.get('kind')!r}")
        return None
    try:
        it = cls()
        it.apply_dict(d)
    except Exception as ex:  # noqa: BLE001 - one bad object must not sink the file
        if warnings is not None:
            warnings.append(f"Skipped a damaged {cls.DISPLAY.lower()}: {ex}")
        return None
    notes = getattr(it, "_load_notes", None)
    if notes and warnings is not None:
        warnings.extend(notes)
    if isinstance(it, GroupItem):
        for cd in d.get("children", []) or []:
            child = item_from_dict(cd, warnings, depth + 1)
            if child is not None:
                child.setParentItem(it)
                child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        if not it.members():
            return None
    return it


# ── pages / documents ───────────────────────────────────────────────────────
def page_to_dict(sc: PageScene, standalone: bool = False) -> Dict[str, Any]:
    conv = standalone_dict if standalone else item_to_dict
    return {
        "name": sc.name,
        "setup": sc.setup_state(),
        "guides": sc.guide_state(),
        "items": [conv(it) for it in sc.top_items()],
    }


def standalone_dict(it: BaseItem) -> Dict[str, Any]:
    """Item dict for a copy: a linked text box keeps just the text it shows."""
    from .items.text import TextItem
    d = it.to_dict()
    if isinstance(it, TextItem) and it.is_linked():
        d["html"] = it.slice_html()
        d.pop("linked", None)
        d.pop("link_next", None)
    elif isinstance(it, GroupItem):
        d["children"] = [standalone_dict(m) for m in it.members()]
    return d


def page_from_dict(doc: Document, d: Dict[str, Any], warnings: List[str]) -> PageScene:
    setup = d.get("setup", {}) if isinstance(d.get("setup"), dict) else {}
    sc = doc.make_page(_f(setup.get("width"), 595.0), _f(setup.get("height"), 842.0),
                       str(d.get("name", ""))[:120])
    sc.apply_setup(setup)
    guides = d.get("guides", []) or []
    if isinstance(guides, list) and len(guides) > limits.MAX_GUIDES_PER_PAGE:
        warnings.append(f"Only the first {limits.MAX_GUIDES_PER_PAGE} guides on a page "
                        "were kept.")
        guides = guides[:limits.MAX_GUIDES_PER_PAGE]
    for g in guides if isinstance(guides, list) else []:
        if isinstance(g, dict) and g.get("orient") in ("H", "V"):
            sc.attach_guide(GuideItem(g["orient"], _f(g.get("pos"), 0.0)))
    for idict in d.get("items", []) or []:
        it = item_from_dict(idict, warnings)
        if it is not None:
            sc.addItem(it)
    return sc


def document_to_dict(doc: Document) -> Dict[str, Any]:
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "app_version": __version__,
        "title": doc.title,
        "view": doc.view.to_dict(),
        "sheet": doc.sheet,
        "pages": [page_to_dict(sc) for sc in doc.pages],
    }


def document_from_dict(data: Dict[str, Any], doc: Optional[Document] = None
                       ) -> Tuple[Document, List[str]]:
    warnings: List[str] = []
    if not isinstance(data, dict):
        raise DocumentError("This file does not contain a publication.")
    if data.get("format") != FORMAT:
        if "objects" in data and "pages" in data:
            data = migrate_v3(data, warnings)
        else:
            raise DocumentError("This file is not a DTP Publisher document.")
    try:
        limits.LoadBudget().check_document(data)    # before any Qt object is made
    except limits.TooBig as ex:
        raise DocumentError(str(ex)) from ex
    ver = data.get("version", 0)
    if isinstance(ver, int) and ver > FORMAT_VERSION:
        warnings.append("This file was made by a newer version; some features may be missing.")
    doc = doc or Document()
    if isinstance(data.get("sheet"), dict):
        doc.sheet = dict(data["sheet"])
    if isinstance(data.get("view"), dict):
        doc.view.update_from(data["view"])
    doc.title = str(data.get("title", ""))[:200]
    pages = data.get("pages", []) or []
    pages = _dedupe_uid_data(pages, warnings) if isinstance(pages, list) else []
    for pd in pages:
        if isinstance(pd, dict):
            doc.add_page(page_from_dict(doc, pd, warnings))
    if not doc.pages:
        doc.add_page(doc.make_page())
    _dedupe_uids(doc, warnings)
    from .textflow import resolve_links
    resolve_links(doc.text_items())
    doc.undo_stack.clear()
    return doc, warnings


def _dedupe_uid_data(pages: list, warnings: List[str]) -> list:
    """Duplicate uids in the file: the first in *file order* keeps it (text links
    point at uids, so a later copy must never be able to take a link over).
    Works on copies; the caller's data is left alone."""
    from .items.base import new_uid
    seen: set = set()
    changed = 0

    def fix(items, depth):
        nonlocal changed
        if not isinstance(items, list) or depth > limits.MAX_GROUP_DEPTH:
            return items
        out = []
        for d in items:
            if isinstance(d, dict):
                d = dict(d)
                uid = d.get("uid")
                if isinstance(uid, str) and uid:
                    if uid in seen:
                        d["uid"] = new_uid()
                        changed += 1
                    seen.add(d["uid"])
                if "children" in d:
                    d["children"] = fix(d["children"], depth + 1)
            out.append(d)
        return out
    res = [dict(pd, items=fix(pd["items"], 0)) if isinstance(pd, dict) and "items" in pd else pd
           for pd in pages]
    if changed:
        warnings.append(f"{changed} object(s) had a duplicate id and were given a new one.")
    return res


def _dedupe_uids(doc: Document, warnings: List[str]) -> None:
    """Every object needs its own uid (text links refer to them); the first keeps it."""
    from .items.base import new_uid
    seen = set()
    changed = 0

    def walk(it):
        nonlocal changed
        if it.uid in seen or not it.uid:
            it.uid = new_uid()
            changed += 1
        seen.add(it.uid)
        if isinstance(it, GroupItem):
            for m in it.members():
                walk(m)
    for sc in doc.pages:
        for it in sc.top_items():
            walk(it)
    if changed:
        warnings.append(f"{changed} object(s) had a duplicate id and were given a new one.")


def save_document(doc: Document, path: str, keep_backup: bool = True) -> bool:
    """Save; returns False when the save worked but the .bak copy could not be made."""
    data = document_to_dict(doc)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    backup_ok = write_atomic(path, text.encode("utf-8"), keep_backup)
    doc.path = path
    doc.mark_saved()
    return backup_ok


def write_atomic(path: str, payload: bytes, keep_backup: bool = True) -> bool:
    """Write ``payload`` to ``path`` atomically.  Raises OSError if the file could not
    be written.  Returns False when it was written but the previous version could not
    be kept as ``.bak`` (the save itself must not fail over that)."""
    backup_ok = True
    folder = os.path.dirname(os.path.abspath(path)) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if keep_backup and os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                backup_ok = False
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return backup_ok


def read_json_file(path: str) -> Dict[str, Any]:
    try:
        size = os.path.getsize(path)
    except OSError as ex:
        raise DocumentError(f"Cannot open the file:\n{ex}") from ex
    if size > MAX_FILE_BYTES:
        raise DocumentError("The file is too large to open.")
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise DocumentError(f"The file is damaged or not a publication:\n{ex}") from ex


def load_document(path: str) -> Tuple[Document, List[str]]:
    doc, warnings = document_from_dict(read_json_file(path))
    doc.path = path if path.lower().endswith(".dtpub") else None
    if doc.path is None and not doc.title:
        doc.title = os.path.splitext(os.path.basename(path))[0]
    return doc, warnings


# ── v3 migration (the March prototype's .json layout files) ─────────────────
_V3_FIT = {"best_fit": "best", "shrink_overflow": "shrink", "grow_box": "grow", "none": "none"}


def _f(v: Any, default: float) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _v3_geom(o: dict) -> Tuple[float, float, float, float, float]:
    x, y = _f(o.get("x"), 0), _f(o.get("y"), 0)
    w, h = max(_f(o.get("w"), 100), 1), max(_f(o.get("h"), 100), 1)
    rot = _f(o.get("rot"), 0)
    if rot:
        # v3 rotated about the box's top-left; we rotate about its centre
        rx, ry = rotate_vec(w / 2, h / 2, rot)
        x, y = x + rx - w / 2, y + ry - h / 2
    return x, y, w, h, rot


def _v3_item(o: dict, by_uid: Dict[str, dict], warnings: List[str]) -> Optional[dict]:
    t = o.get("type")
    x, y, w, h, rot = _v3_geom(o)
    base = {"uid": o.get("uid"), "name": o.get("label", ""), "x": x, "y": y, "w": w, "h": h,
            "rot": rot, "z": _f(o.get("z"), 1), "fill": o.get("fill"), "stroke": o.get("stroke"),
            "stroke_width": _f(o.get("strokeW"), 0), "locked": bool(o.get("locked")),
            "hidden": bool(o.get("hidden"))}
    if t == "TextBoxItem":
        from .items.text import TextItem
        ti = TextItem(w, h)
        f = QFont()
        if o.get("font"):
            f.fromString(str(o["font"]))
        col = QColor(o.get("textColor") or "#ff14141e")
        ti.set_text(str(o.get("text", "")), f.family() or "Calibri",
                    f.pointSizeF() if f.pointSizeF() > 0 else 12.0, f.bold(), f.italic(), col)
        base.update(kind="text", html=ti.html(), fit=_V3_FIT.get(o.get("autofit"), "none"),
                    padding=_f(o.get("padding"), 8), text_color=col.name(QColor.NameFormat.HexArgb))
        return base
    if t == "ShapeItem":
        base.update(kind="shape", shape=o.get("shape", "rect"))
        return base
    if t == "TableItem":
        rows, cols = int(_f(o.get("rows"), 3)), int(_f(o.get("cols"), 3))
        base.update(kind="table", table={"rows": rows, "cols": cols, "cells": o.get("cells", {}),
                                         "header": True, "header_fill": o.get("headerColor")})
        return base
    if t == "ImageItem":
        base.update(kind="image", fit_mode="stretch" if not o.get("keepAspect", True) else "fit",
                    data=o.get("imageData", ""), format="png",
                    source_name=os.path.basename(str(o.get("sourcePath", ""))))
        return base
    if t == "GroupItem":
        kids = []
        for cuid in o.get("children", []):
            co = by_uid.get(cuid)
            if co is None:
                continue
            cd = _v3_item(co, by_uid, warnings)
            if cd is not None:
                cd["x"] -= x
                cd["y"] -= y
                kids.append(cd)
        if len(kids) < 2:
            return None
        base.update(kind="group", children=kids, rot=0.0, x=_f(o.get("x"), 0), y=_f(o.get("y"), 0))
        return base
    warnings.append(f"Skipped unknown object type {t!r}")
    return None


def migrate_v3(data: dict, warnings: List[str]) -> dict:
    warnings.append("Converted from the older layout format (v3). Please check object "
                    "positions; v3 did not save them reliably.")
    objs = [o for o in data.get("objects", []) if isinstance(o, dict)]
    by_uid = {o.get("uid"): o for o in objs}
    grouped = {c for o in objs if o.get("type") == "GroupItem" for c in o.get("children", [])}
    sd = data.get("scene", {}) if isinstance(data.get("scene"), dict) else {}
    margin = _f(sd.get("margin"), 36)
    pages = []
    for pg in data.get("pages", []):
        if not isinstance(pg, dict):
            continue
        items = []
        for uid in pg.get("item_ids", []):
            if uid in grouped or uid not in by_uid:
                continue
            it = _v3_item(by_uid[uid], by_uid, warnings)
            if it is not None:
                items.append(it)
        pages.append({
            "name": "" if str(pg.get("name", "")).startswith("Page ") else pg.get("name", ""),
            "setup": {"width": _f(pg.get("width"), 595), "height": _f(pg.get("height"), 842),
                      "margins": [margin] * 4, "columns": int(_f(sd.get("columns"), 1)),
                      "rows": int(_f(sd.get("rows"), 1)), "gutter": 0},
            "guides": [{"orient": "H" if g.get("orientation") == "H" else "V",
                        "pos": _f(g.get("position"), 0)} for g in pg.get("guides", [])
                       if isinstance(g, dict)],
            "items": items,
        })
    return {"format": FORMAT, "version": 3,
            "view": {"show_grid": bool(sd.get("showGrid", False)),
                     "show_guides": bool(sd.get("showGuides", True)),
                     "snap_grid": bool(sd.get("snapGrid", False)),
                     "snap_objects": bool(sd.get("snapItems", True)),
                     "snap_guides": bool(sd.get("snapGuides", True)),
                     "grid_size": _f(sd.get("gridSize"), 12),
                     "snap_px": int(_f(sd.get("snapDistance"), 8))},
            "pages": pages}


# ── clipboard helpers ───────────────────────────────────────────────────────
CLIP_MIME = "application/x-dtpub-items"


def items_to_clip(items: List[BaseItem]) -> bytes:
    return json.dumps({"format": FORMAT, "items": [standalone_dict(it) for it in items]}
                      ).encode("utf-8")


def items_from_clip(raw: bytes) -> List[BaseItem]:
    if len(raw) > MAX_FILE_BYTES:
        return []
    try:
        data = json.loads(bytes(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    try:
        limits.LoadBudget().check_items(data.get("items") if isinstance(data, dict) else None)
    except limits.TooBig:
        return []
    out = []
    for d in data.get("items", []) if isinstance(data, dict) else []:
        it = item_from_dict(d)
        if it is not None:
            out.append(it)
    return out


def fresh_uids(it: BaseItem):
    """Give an item (and its members) new uids — used for paste/duplicate."""
    from .items.base import new_uid
    it.uid = new_uid()
    if isinstance(it, GroupItem):
        for m in it.members():
            fresh_uids(m)


def clone_item(it: BaseItem, offset: QPointF = QPointF(0, 0)) -> Optional[BaseItem]:
    c = item_from_dict(standalone_dict(it))
    if c is None:
        return None
    fresh_uids(c)
    c.setPos(c.pos() + offset)
    return c

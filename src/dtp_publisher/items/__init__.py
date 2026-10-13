# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Design item classes and the kind -> class registry."""

from .base import BaseItem
from .group import GroupItem
from .image import ImageItem
from .shape import ShapeItem
from .table import TableItem
from .text import TextItem
from .wordart import WordArtItem

ITEM_TYPES = {cls.KIND: cls for cls in
              (TextItem, ShapeItem, ImageItem, TableItem, WordArtItem, GroupItem)}

__all__ = ["BaseItem", "TextItem", "ShapeItem", "ImageItem", "TableItem", "WordArtItem",
           "GroupItem", "ITEM_TYPES"]

# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""MainWindow — ribbon, canvas, panels, file handling."""

from __future__ import annotations

import math
import os
from typing import Callable, Dict, List, Optional

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QGuiApplication,
                         QImage, QKeySequence, QTextListFormat)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout, QInputDialog,
                             QLabel, QMainWindow, QMenu, QMessageBox, QSlider, QStatusBar,
                             QTabWidget, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, FILE_EXT, __version__, blocks, theme, winassoc
from .. import settings as settings_mod
from ..autosave import Autosaver
from ..commands import (AddItemsCmd, AddPageCmd, DeleteItemsCmd, GeometryCmd, GroupCmd,
                        MoveItemsCmd, MovePageCmd, PageSetupCmd, PropCmd, RemoveGuideCmd,
                        RemovePageCmd, RenamePageCmd, UngroupCmd, ZOrderCmd)
from ..document import Document
from ..export import export_images, export_pdf, page_layout, print_document
from ..fields import refresh_fields
from ..geometry import Geo, normalize_angle
from ..items import (BaseItem, GroupItem, ImageItem, ShapeItem, TableItem, TextItem,
                     WordArtItem)
from ..items.image import encode_image, image_file_problem, load_image_file, prepare_image_bytes
from ..items.shape import SHAPES
from ..scene import PageScene
from ..serialize import (CLIP_MIME, DocumentError, clone_item, fresh_uids, item_from_dict,
                         items_from_clip, items_to_clip, load_document, page_from_dict,
                         page_to_dict, save_document)
from ..units import PAGE_SIZES, describe_size, from_pt, mm, UNIT_DECIMALS
from .canvas import IMAGE_EXTS, CanvasView, RulerWidget
from .dialogs.editors import TableDialog, WordArtDialog
from .dialogs.misc import ExportPicturesDialog, FillPageDialog, PreferencesDialog, about_text
from .dialogs.page_setup import PageSetupDialog
from .formatbar import FormatBar
from .icons import clear_cache, icon
from .panels.layers import LayersPanel
from .panels.properties import PropertiesPanel
from .panels.thumbs import ThumbPanel
from .ribbon import Ribbon

PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
DOC_FILTER = (f"Everything I can open (*{FILE_EXT} *.pub *.json);;"
              f"Publications (*{FILE_EXT});;Microsoft Publisher files (*.pub);;"
              "Older layouts from version 4 (*.json)")
NUDGE, NUDGE_BIG = 1.0, mm(5)


def manual_path() -> str:
    """help/manual.html inside the package (also inside the built .exe)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "help", "manual.html")


def manual_for_browser() -> str:
    """The manual file to hand to the web browser.  The one-file .exe unpacks
    itself into a temporary folder that disappears when the program closes, so
    there the manual is copied (once per version) to the settings folder."""
    import shutil
    import tempfile
    src = manual_path()
    tmp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    here = os.path.normcase(os.path.realpath(src))
    if not here.startswith(tmp + os.sep):
        return src
    dst_dir = os.path.join(settings_mod.config_dir(), f"manual-{__version__}")
    dst = os.path.join(dst_dir, "manual.html")
    if not os.path.isfile(dst):
        shutil.copytree(os.path.dirname(src), dst_dir, dirs_exist_ok=True)
        _remove_old_manuals(dst_dir)
    return dst


def _remove_old_manuals(keep: str):
    """Copies made by earlier versions (about 2 MB each).  Only folders named
    like ``manual-5.3.3`` that hold a manual.html are touched."""
    import re
    import shutil
    base = os.path.dirname(keep)
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if (re.fullmatch(r"manual-\d+\.\d+\.\d+", name) and path != keep
                and os.path.isfile(os.path.join(path, "manual.html"))):
            shutil.rmtree(path, ignore_errors=True)


class MainWindow(QMainWindow):
    def __init__(self, s: Optional[settings_mod.Settings] = None, doc: Optional[Document] = None):
        super().__init__()
        self.settings = s or settings_mod.get()
        self.doc: Optional[Document] = None
        self.scene: Optional[PageScene] = None
        self.acts: Dict[str, QAction] = {}
        self._last_index = 0
        self._prev_undo_index = 0
        self._paste_count = 0
        self._copy_scene: Optional[PageScene] = None
        self._link_from: Optional[TextItem] = None
        self._pub_source: Optional[str] = None
        self.assoc_registry = None          # Windows registry (tests put a fake here)
        self.setWindowIcon(icon("wordart", 64))
        self.resize(1500, 950)
        self.setAcceptDrops(False)

        self.view = CanvasView()
        self._build_actions()
        self._build_ui()
        self._build_ribbon()
        self.autosaver = Autosaver(lambda: self.doc, self)
        QApplication.clipboard().dataChanged.connect(self._update_actions)
        self.set_document(doc or self._blank_doc())
        geo = self.settings.window_geometry
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except ValueError:
                pass

    # ═══════════════════════════════════════════════════════════════════════
    # actions
    # ═══════════════════════════════════════════════════════════════════════
    def _act(self, key: str, text: str, slot: Callable, icon_name: Optional[str] = None,
             shortcut=None, tip: str = "", checkable: bool = False, canvas: bool = False) -> QAction:
        a = QAction(text, self)
        a.setObjectName(key)
        if icon_name:
            a.setIcon(icon(icon_name))
            a.setProperty("icon_name", icon_name)
        seqs = []
        if shortcut:
            for sc in (shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]):
                seqs.append(QKeySequence(sc))
            a.setShortcuts(seqs)
        tiptext = tip or text.replace("&", "").rstrip("…")
        if seqs:
            tiptext += f"  ({seqs[0].toString(QKeySequence.SequenceFormat.NativeText)})"
        a.setToolTip(tiptext)
        a.setStatusTip(tip or "")
        a.setCheckable(checkable)
        if checkable:
            a.triggered.connect(lambda on: slot(on))
        else:
            a.triggered.connect(lambda _=False: slot())
        if canvas:
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.view.addAction(a)
        else:
            self.addAction(a)
        self.acts[key] = a
        return a

    def _build_actions(self):
        A = self._act
        # file
        A("new", "New", self.new_document, "new", "Ctrl+N", "Start a new publication")
        A("open", "Open", self.open_dialog, "open", "Ctrl+O", "Open a saved publication")
        A("save", "Save", self.save, "save", "Ctrl+S", "Save your work")
        A("save_as", "Save As", self.save_as, "save_as", "Ctrl+Shift+S",
          "Save a copy under a new name")
        A("pdf", "Save as PDF", self.export_pdf, "pdf", None,
          "Make a PDF to email or take to a print shop")
        A("export_pic", "Save as Picture", self.export_pictures, "picture_export", None,
          "Save the page as a JPEG or PNG picture")
        A("print", "Print", self.print_doc, "print", "Ctrl+P", "Print the publication")
        A("prefs", "Preferences", self.preferences, "settings", None,
          "Change the look, button size and measurements")
        A("manual", "User Manual", self.open_manual, "manual", "F1",
          "How to use the program, with pictures")
        A("about", "About", self.about, "help")
        A("quit", "Exit", self.close, "close", "Ctrl+Q")
        # edit
        A("undo", "Undo", self.undo, "undo", "Ctrl+Z", "Undo the last change")
        A("redo", "Redo", self.redo, "redo", ["Ctrl+Y", "Ctrl+Shift+Z"], "Redo")
        A("cut", "Cut", self.cut, "cut", "Ctrl+X")
        A("copy", "Copy", self.copy, "copy", "Ctrl+C")
        A("paste", "Paste", self.paste, "paste", "Ctrl+V")
        A("duplicate", "Duplicate", self.duplicate, "duplicate", "Ctrl+D",
          "Make a copy of the selected objects")
        A("delete", "Delete", self.delete, "delete", ["Del", "Backspace"],
          "Delete the selected objects", canvas=True)
        A("select_all", "Select All", self.select_all, "select_all", "Ctrl+A", canvas=True)
        A("deselect", "Deselect", self.deselect, None, "Esc", canvas=True)
        A("edit_text", "Edit Text", self.edit_text, "edit", "F2", "Type in the selected text box",
          canvas=True)
        # insert
        A("ins_text", "Text Box", self.insert_text, "text", None, "Add a box to type in")
        A("ins_picture", "Picture", self.insert_picture, "picture", None,
          "Add a photo or picture from your computer")
        A("ins_placeholder", "Picture Frame", self.insert_placeholder, "placeholder", None,
          "Add an empty frame to put a picture in later")
        A("ins_table", "Table", self.insert_table, "table", None, "Add a table")
        A("link_text", "Continue Text…", self.start_link, "link", None,
          "Let the text in this box flow on into another box (on any page)")
        A("unlink_text", "Break Text Link", self.break_link, "unlink", None,
          "Stop the text flowing from this box into the next one")
        A("ins_wordart", "WordArt", self.insert_wordart, "wordart", None,
          "Add a decorative headline")
        for k, name in SHAPES.items():
            A(f"shape_{k}", name, lambda k=k: self.insert_shape(k),
              {"rect": "rect", "rounded": "rect", "ellipse": "ellipse", "line": "line",
               "star": "star"}.get(k, "shapes"))
        for k, name in blocks.BLOCKS.items():
            A(f"block_{k}", name, lambda k=k: self.insert_block(k),
              {"header": "header", "footer": "footer", "story": "story", "quote": "quote",
               "sidebar": "sidebar", "coupon": "coupon", "pagenum": "pagenum",
               "date": "date"}[k])
        # page
        A("page_add", "Add Page", self.page_add, "page_add", None, "Add a page after this one")
        A("page_dup", "Duplicate Page", self.page_duplicate, "page_dup", None,
          "Copy this page and everything on it")
        A("page_del", "Delete Page", self.page_delete, "page_del", None, "Delete this page")
        A("page_up", "Move Page Earlier", lambda: self.page_move(-1), "move_up")
        A("page_down", "Move Page Later", lambda: self.page_move(1), "move_down")
        A("page_rename", "Rename Page…", self.page_rename, "rename")
        A("page_setup", "Page Setup", self.page_setup, "page_setup", None,
          "Paper size, margins, guides and page colour")
        A("page_next", "Next Page", lambda: self.show_page(self.page_index() + 1), None,
          "Ctrl+PgDown")
        A("page_prev", "Previous Page", lambda: self.show_page(self.page_index() - 1), None,
          "Ctrl+PgUp")
        A("portrait", "Portrait", lambda: self.set_orientation(False), "orientation", None,
          "Tall pages")
        A("landscape", "Landscape", lambda: self.set_orientation(True), "orientation", None,
          "Wide pages")
        # arrange
        for k, label in (("left", "Align Left"), ("hcenter", "Align Centre"),
                         ("right", "Align Right"), ("top", "Align Top"),
                         ("vcenter", "Align Middle"), ("bottom", "Align Bottom")):
            A(f"align_{k}", label, lambda k=k: self.align(k), f"align_{k}", None,
              f"{label} (one object: to the page margins)")
        A("dist_h", "Distribute Across", lambda: self.distribute("h"), "dist_h", None,
          "Space 3 or more objects evenly across")
        A("dist_v", "Distribute Down", lambda: self.distribute("v"), "dist_v", None,
          "Space 3 or more objects evenly down")
        A("rot_l", "Rotate Left 90°", lambda: self.rotate_by(-90), "rotate_left")
        A("rot_r", "Rotate Right 90°", lambda: self.rotate_by(90), "rotate_right")
        A("flip_h", "Flip Horizontal", lambda: self.flip("flip_h"), "flip_h")
        A("flip_v", "Flip Vertical", lambda: self.flip("flip_v"), "flip_v")
        A("group", "Group", self.group, "group", "Ctrl+G", "Join objects so they move together")
        A("ungroup", "Ungroup", self.ungroup, "ungroup", "Ctrl+Shift+G", "Split a group apart")
        A("front", "Bring to Front", lambda: self.arrange("front"), "front", "Ctrl+Shift+]")
        A("back", "Send to Back", lambda: self.arrange("back"), "back", "Ctrl+Shift+[")
        A("forward", "Bring Forward", lambda: self.arrange("forward"), "forward", "Ctrl+]")
        A("backward", "Send Backward", lambda: self.arrange("backward"), "backward", "Ctrl+[")
        A("lock", "Lock", self.toggle_lock, "lock", None, "Lock objects so they can't be moved")
        from PyQt6.QtGui import QActionGroup
        self._wrap_group = QActionGroup(self)
        for k, label, tip in (("none", "No Wrapping", "Text behind this object is not moved"),
                              ("square", "Wrap Square",
                               "Text in boxes behind this object flows around it"),
                              ("top_bottom", "Wrap Top and Bottom",
                               "Text stops above this object and carries on below it")):
            act = A(f"wrap_{k}", label, lambda on, k=k: self.set_wrap(k) if on else None,
                    f"wrap_{k}", None, tip, checkable=True)
            self._wrap_group.addAction(act)
        A("fill_page", "Fill Page with Copies", self.fill_page, "fill_page", None,
          "Repeat the selected object across the page (labels, cards, tickets)")
        # view
        A("zoom_in", "Zoom In", lambda: self.view.zoom_by(1.25), "zoom_in",
          ["Ctrl+=", "Ctrl++"])
        A("zoom_out", "Zoom Out", lambda: self.view.zoom_by(0.8), "zoom_out", "Ctrl+-")
        A("zoom_fit", "Whole Page", self.view.fit_page, "zoom_fit", "Ctrl+0",
          "Show the whole page")
        A("zoom_width", "Page Width", self.view.fit_width, "zoom_fit", None)
        A("zoom_100", "Actual Size", lambda: self.view.set_zoom(QGuiApplication.primaryScreen()
                                                               .logicalDotsPerInch() / 72.0),
          "zoom_100", "Ctrl+1")
        A("show_grid", "Grid", lambda on: self._view_opt("show_grid", on), "grid", None,
          "Show a grid on the page", checkable=True)
        A("show_guides", "Guides", lambda on: self._view_opt("show_guides", on), "guides", None,
          "Show margin, column and ruler guides", checkable=True)
        A("show_bounds", "Boundaries", lambda on: self._view_opt("show_boundaries", on),
          "boundaries", None, "Show dotted outlines around text boxes and picture frames",
          checkable=True)
        A("snap_objects", "Snap to Objects", lambda on: self._view_opt("snap_objects", on),
          "snap", None, checkable=True)
        A("snap_guides", "Snap to Guides", lambda on: self._view_opt("snap_guides", on),
          "snap", None, checkable=True)
        A("snap_grid", "Snap to Grid", lambda on: self._view_opt("snap_grid", on), "snap",
          None, checkable=True)
        A("clear_guides", "Remove Ruler Guides", self.clear_guides, "guides", None,
          "Remove all guides dragged from the rulers on this page")
        tg = QActionGroup(self)
        for k, t in theme.THEMES.items():
            a = A(f"theme_{k}", t["label"], lambda on, k=k: on and self.set_theme(k), "theme",
                  checkable=True)
            tg.addAction(a)
        # text
        A("bold", "Bold", lambda on: self.fmt.set_bold(on), "bold", "Ctrl+B", checkable=True)
        A("italic", "Italic", lambda on: self.fmt.set_italic(on), "italic", "Ctrl+I",
          checkable=True)
        A("underline", "Underline", lambda on: self.fmt.set_underline(on), "underline",
          "Ctrl+U", checkable=True)
        ag = QActionGroup(self)
        for k, sc, lbl in (("left", "Ctrl+L", "Align Text Left"), ("center", "Ctrl+E", "Centre Text"),
                           ("right", "Ctrl+R", "Align Text Right"),
                           ("justify", "Ctrl+J", "Justify")):
            a = A(f"talign_{k}", lbl, lambda on, k=k: on and self.fmt.set_align(k),
                  f"talign_{k}", sc, checkable=True)
            ag.addAction(a)
        A("bullets", "Bullets", lambda on: self.fmt.set_list(
            QTextListFormat.Style.ListDisc if on else None), "bullets", None, checkable=True)
        A("numbering", "Numbering", lambda on: self.fmt.set_list(
            QTextListFormat.Style.ListDecimal if on else None), "numbering", None, checkable=True)
        A("font_grow", "Bigger Text", lambda: self.fmt.step_size(True), "font_grow")
        A("font_shrink", "Smaller Text", lambda: self.fmt.step_size(False), "font_shrink")
        # nudging (canvas only, so arrow keys still work in lists and boxes)
        for key, dx, dy, seq in (("left", -1, 0, "Left"), ("right", 1, 0, "Right"),
                                 ("up", 0, -1, "Up"), ("down", 0, 1, "Down")):
            A(f"nudge_{key}", f"Nudge {key}", lambda dx=dx, dy=dy: self.nudge(dx, dy, False),
              None, seq, canvas=True)
            A(f"nudge_{key}_big", f"Nudge {key} more",
              lambda dx=dx, dy=dy: self.nudge(dx, dy, True), None, f"Shift+{seq}", canvas=True)

    # ═══════════════════════════════════════════════════════════════════════
    # layout
    # ═══════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        rv = QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.ribbon = Ribbon()
        rv.addWidget(self.ribbon)
        self.fmt = FormatBar(self.text_targets, self.editing_item,
                             lambda: self.doc.undo_stack)
        self.fmt.add_actions([
            [self.acts["bold"], self.acts["italic"], self.acts["underline"]],
            [self.acts["font_grow"], self.acts["font_shrink"]],
            [self.acts[f"talign_{k}"] for k in ("left", "center", "right", "justify")],
            [self.acts["bullets"], self.acts["numbering"]],
        ])
        rv.addWidget(self.fmt)

        body = QHBoxLayout()
        body.setSpacing(0)
        rv.addLayout(body, 1)
        self.thumbs = ThumbPanel()
        self.thumbs.pageClicked.connect(self.show_page)
        self.thumbs.moveRequested.connect(self._thumb_move)
        self.thumbs.addRequested.connect(self.page_add)
        self.thumbs.deleteRequested.connect(self.page_delete)
        self.thumbs.contextRequested.connect(self._thumb_menu)
        body.addWidget(self.thumbs)

        canvas = QWidget()
        cg = QVBoxLayout(canvas)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(0)
        corner = QToolButton()
        corner.setFixedSize(24, 24)
        corner.setText(self.settings.units)
        corner.setToolTip("Click to change the ruler units")
        corner.setAutoRaise(True)
        corner.clicked.connect(self._cycle_units)
        self._units_btn = corner
        self.ruler_h = RulerWidget("H", self.view, lambda: self.settings.units)
        self.ruler_v = RulerWidget("V", self.view, lambda: self.settings.units)
        top.addWidget(corner)
        top.addWidget(self.ruler_h)
        cg.addLayout(top)
        mid = QHBoxLayout()
        mid.setSpacing(0)
        mid.addWidget(self.ruler_v)
        mid.addWidget(self.view, 1)
        cg.addLayout(mid, 1)
        body.addWidget(canvas, 1)

        self.right = QTabWidget()
        self.right.setMinimumWidth(300)
        self.right.setMaximumWidth(360)
        self.props = PropertiesPanel(lambda: self.settings.units)
        self.props.actionRequested.connect(self._panel_action)
        self.layers = LayersPanel()
        self.layers.arrangeRequested.connect(self.arrange)
        self.right.addTab(self.props, "Format")
        self.right.addTab(self.layers, "Objects")
        body.addWidget(self.right)

        self.view.mouseScenePos.connect(self._mouse_pos)
        self.view.zoomChanged.connect(self._zoom_changed)
        self.view.contextRequested.connect(self._canvas_menu)
        self.view.filesDropped.connect(self._files_dropped)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_page = QLabel("")
        self.lbl_pos = QLabel("")
        self.lbl_sel = QLabel("")
        sb.addWidget(self.lbl_page)
        sb.addWidget(self.lbl_pos)
        sb.addWidget(self.lbl_sel, 1)
        zw = QWidget()
        zl = QHBoxLayout(zw)
        zl.setContentsMargins(0, 0, 6, 0)
        b_out = QToolButton()
        b_out.setDefaultAction(self.acts["zoom_out"])
        b_out.setAutoRaise(True)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setFixedWidth(160)
        self.zoom_slider.valueChanged.connect(self._slider_zoom)
        b_in = QToolButton()
        b_in.setDefaultAction(self.acts["zoom_in"])
        b_in.setAutoRaise(True)
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setMinimumWidth(46)
        b_fit = QToolButton()
        b_fit.setDefaultAction(self.acts["zoom_fit"])
        b_fit.setAutoRaise(True)
        for w in (b_out, self.zoom_slider, b_in, self.lbl_zoom, b_fit):
            zl.addWidget(w)
        sb.addPermanentWidget(zw)

    def _menu(self, keys: List[Optional[str]]) -> QMenu:
        m = QMenu(self)
        for k in keys:
            if k is None:
                m.addSeparator()
            else:
                m.addAction(self.acts[k])
        return m

    def _build_ribbon(self):
        R = self.ribbon
        a = self.acts
        # File
        p = R.page("File")
        g = p.group("Publication")
        for k in ("new", "open"):
            g.add_large(a[k])
        self.recent_menu = QMenu(self)
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        g.add_menu_large("Recent", icon("recent"), self.recent_menu, "Open a recent publication")
        g = p.group("Save")
        g.add_large(a["save"])
        g.add_large(a["save_as"])
        g = p.group("Share")
        g.add_large(a["pdf"])
        g.add_large(a["export_pic"])
        g.add_large(a["print"])
        g = p.group("Options")
        g.add_large(a["prefs"])
        g = p.group("Help")
        g.add_large(a["manual"])
        g.add_large(a["about"])
        # Home
        p = R.page("Home")
        g = p.group("Clipboard")
        g.add_large(a["paste"])
        g.add_smalls([a["cut"], a["copy"], a["duplicate"]])
        g = p.group("Undo")
        g.add_large(a["undo"])
        g.add_large(a["redo"])
        g = p.group("Add")
        g.add_large(a["ins_text"])
        g.add_large(a["ins_picture"])
        g.add_menu_large("Shapes", icon("shapes"), self._menu([f"shape_{k}" for k in SHAPES]),
                         "Add a shape")
        g = p.group("Arrange")
        g.add_smalls([a["front"], a["back"], a["group"]])
        g.add_smalls([a["forward"], a["backward"], a["ungroup"]])
        g = p.group("Editing")
        g.add_large(a["delete"])
        g.add_smalls([a["select_all"], a["edit_text"], a["lock"]])
        # Insert
        p = R.page("Insert")
        g = p.group("Text")
        g.add_large(a["ins_text"])
        g.add_large(a["ins_wordart"])
        g.add_large(a["ins_table"])
        g.add_smalls([a["link_text"], a["unlink_text"]])
        g = p.group("Pictures")
        g.add_large(a["ins_picture"])
        g.add_large(a["ins_placeholder"])
        g = p.group("Shapes")
        g.add_menu_large("Shapes", icon("shapes"), self._menu([f"shape_{k}" for k in SHAPES]))
        g.add_smalls([a["shape_rect"], a["shape_ellipse"], a["shape_line"]])
        g = p.group("Building blocks")
        g.add_large(a["block_header"])
        g.add_large(a["block_footer"])
        g.add_smalls([a["block_story"], a["block_quote"], a["block_sidebar"]])
        g.add_smalls([a["block_coupon"], a["block_pagenum"], a["block_date"]])
        # Page design
        p = R.page("Page Design")
        g = p.group("Page")
        g.add_large(a["page_setup"])
        sizes = QMenu(self)
        for ps in PAGE_SIZES:
            act = sizes.addAction(ps.name)
            act.triggered.connect(lambda _=False, ps=ps: self.set_page_size(ps.width, ps.height))
        sizes.addSeparator()
        sizes.addAction("Custom size…").triggered.connect(self.page_setup)
        g.add_menu_large("Size", icon("page_setup"), sizes, "Choose the paper size")
        g.add_menu_large("Orientation", icon("orientation"),
                         self._menu(["portrait", "landscape"]), "Tall or wide pages")
        margins = QMenu(self)
        for label, v in (("None (0 mm)", 0.0), ("Narrow (6 mm)", mm(6)),
                         ("Normal (12.7 mm)", mm(12.7)), ("Wide (25 mm)", mm(25))):
            act = margins.addAction(label)
            act.triggered.connect(lambda _=False, v=v: self.set_margins(v))
        g.add_menu_large("Margins", icon("margins"), margins, "Set the page margins")
        bg = QMenu(self)
        for label, c in (("White", "#ffffff"), ("Cream", "#fffaf0"), ("Pale blue", "#eef4fb"),
                         ("Pale green", "#eef7ee"), ("Pale pink", "#fdf0f4"),
                         ("Pale yellow", "#fffbe6"), ("Light grey", "#f2f2f2")):
            act = bg.addAction(label)
            act.triggered.connect(lambda _=False, c=c: self.set_background(QColor(c)))
        bg.addSeparator()
        bg.addAction("More colours…").triggered.connect(self._pick_background)
        g.add_menu_large("Page Colour", icon("background"), bg, "Colour the whole page")
        g = p.group("Pages")
        g.add_large(a["page_add"])
        g.add_large(a["page_dup"])
        g.add_large(a["page_del"])
        g.add_smalls([a["page_up"], a["page_down"], a["page_rename"]])
        g = p.group("Guides")
        g.add_smalls([a["show_guides"], a["clear_guides"], a["show_grid"]])
        # Arrange
        p = R.page("Arrange")
        g = p.group("Align")
        g.add_smalls([a["align_left"], a["align_hcenter"], a["align_right"]])
        g.add_smalls([a["align_top"], a["align_vcenter"], a["align_bottom"]])
        g.add_smalls([a["dist_h"], a["dist_v"]])
        g = p.group("Order")
        for k in ("front", "back"):
            g.add_large(a[k])
        g.add_smalls([a["forward"], a["backward"]])
        g = p.group("Group")
        g.add_large(a["group"])
        g.add_large(a["ungroup"])
        g = p.group("Rotate and flip")
        g.add_smalls([a["rot_l"], a["rot_r"]])
        g.add_smalls([a["flip_h"], a["flip_v"]])
        g = p.group("Text wrap")
        g.add_smalls([a["wrap_none"], a["wrap_square"], a["wrap_top_bottom"]])
        g = p.group("Tools")
        g.add_large(a["lock"])
        g.add_large(a["fill_page"])
        # View
        p = R.page("View")
        g = p.group("Zoom")
        g.add_large(a["zoom_fit"])
        g.add_large(a["zoom_100"])
        g.add_smalls([a["zoom_in"], a["zoom_out"], a["zoom_width"]])
        g = p.group("Show")
        g.add_smalls([a["show_guides"], a["show_bounds"], a["show_grid"]])
        g = p.group("Snap")
        g.add_smalls([a["snap_objects"], a["snap_guides"], a["snap_grid"]])
        g = p.group("Look")
        g.add_menu_large("Theme", icon("theme"),
                         self._menu([f"theme_{k}" for k in theme.THEMES]),
                         "Light, dark or high-contrast look")
        g.add_large(a["prefs"])
        R.finalize()
        R.show_tab("Home")

    # ═══════════════════════════════════════════════════════════════════════
    # document / page plumbing
    # ═══════════════════════════════════════════════════════════════════════
    def _blank_doc(self) -> Document:
        from ..templates import blank
        return blank(mm(210), mm(297))

    def set_document(self, doc: Document):
        self._detach_doc()
        self._pub_source = None
        self.doc = doc
        st = doc.undo_stack
        self._doc_conns = [
            (st.cleanChanged, self._update_title),
            (st.indexChanged, self._undo_index),
            (st.canUndoChanged, self._update_actions),
            (st.canRedoChanged, self._update_actions),
            (st.undoTextChanged, self._undo_texts),
            (st.redoTextChanged, self._undo_texts),
            (doc.pagesChanged, self._pages_changed),
            (doc.pageContentChanged, self._content_changed),
            (doc.view.changed, self._view_changed),
            (doc.showPageRequested, self._show_scene),
        ]
        for sig, slot in self._doc_conns:
            sig.connect(slot)
        self._prev_undo_index = st.index()
        self.scene = None
        refresh_fields(doc)
        self.thumbs.set_document(doc, 0)
        self.show_page(0)
        self._view_changed()
        self._update_title()
        QTimer.singleShot(0, self.view.fit_page)

    def _detach_doc(self):
        """Disconnect from the current document (QUndoStack emits while dying)."""
        if self.doc is None:
            return
        self._end_edits()
        for sig, slot in getattr(self, "_doc_conns", []) + getattr(self, "_scene_conns", []):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._doc_conns, self._scene_conns = [], []
        self.layers.set_scene(None)
        self.props.set_items(None, [])
        self.view.setScene(None)
        self.scene = None

    def _show_scene(self, sc):
        if self.doc is not None and sc in self.doc.pages and sc is not self.scene:
            self.show_page(self.doc.index_of(sc))

    def page_index(self) -> int:
        return self.doc.index_of(self.scene) if self.doc and self.scene else 0

    def show_page(self, idx: int):
        doc = self.doc
        if doc is None or not doc.pages:
            return
        idx = max(0, min(idx, len(doc.pages) - 1))
        sc = doc.pages[idx]
        if sc is self.scene:
            self._last_index = idx
            self.thumbs.set_current(idx)
            return
        if self.scene is not None:
            self._end_edits()
            for sig, slot in self._scene_conns:
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            self.scene.clearSelection()
        self.scene = sc
        self._scene_conns = [
            (sc.selectionChanged, self._selection_changed),
            (sc.textEditingChanged, self._editing_changed),
            (sc.textFormatChanged, self._format_changed),
            (sc.itemActivated, self._item_activated),
        ]
        for sig, slot in self._scene_conns:
            sig.connect(slot)
        self.view.set_page(sc)
        self._last_index = idx
        self.thumbs.set_current(idx)
        self.layers.set_scene(sc)
        self._selection_changed()
        self._update_page_label()

    def _end_edits(self):
        if self.scene is None:
            return
        for it in self.scene.all_design_items():
            if isinstance(it, TextItem) and it.editing:
                it.end_edit()

    def _pages_changed(self):
        doc = self.doc
        refresh_fields(doc)
        if self.scene not in doc.pages:
            old = self.scene
            if old is not None:
                for sig, slot in self._scene_conns:
                    try:
                        sig.disconnect(slot)
                    except (TypeError, RuntimeError):
                        pass
            self.scene = None
            idx = min(self._last_index, len(doc.pages) - 1)
            self.thumbs.rebuild(idx)
            self.show_page(idx)
        else:
            self._last_index = doc.index_of(self.scene)
            self.thumbs.rebuild(self._last_index)
        self._update_page_label()
        self._update_actions()

    def _content_changed(self, sc: PageScene):
        self.thumbs.mark_dirty(sc)
        if sc is self.scene:
            self.layers.schedule()
            self.props.schedule()
            self._update_actions()

    def _undo_index(self, idx: int):
        """After undo/redo, show the page the change happened on."""
        st = self.doc.undo_stack
        prev, self._prev_undo_index = self._prev_undo_index, idx
        cmd_i = idx if idx < prev else idx - 1
        if 0 <= cmd_i < st.count() and idx != prev:
            cmd = st.command(cmd_i)
            sc = getattr(cmd, "scene", None)
            if sc is None and cmd is not None and cmd.childCount():
                sc = getattr(cmd.child(0), "scene", None)
            if sc is not None and sc is not self.scene and sc in self.doc.pages:
                self.show_page(self.doc.index_of(sc))
        self._update_title()
        self._update_actions()
        self.props.schedule()

    def _undo_texts(self, _=None):
        st = self.doc.undo_stack
        u, r = st.undoText(), st.redoText()
        self.acts["undo"].setToolTip(f"Undo {u}  (Ctrl+Z)" if u else "Nothing to undo")
        self.acts["redo"].setToolTip(f"Redo {r}  (Ctrl+Y)" if r else "Nothing to redo")

    def _update_title(self, *_):
        doc = self.doc
        name = os.path.basename(doc.path) if doc.path else (doc.title or "Untitled publication")
        self.setWindowTitle(f"{name}[*]  —  {APP_NAME}")
        self.setWindowModified(doc.is_modified())

    def _update_page_label(self):
        if self.doc and self.scene:
            sc = self.scene
            from .. import labels
            lay = labels.from_dict(self.doc.sheet)
            extra = f"   ·   labels: {lay.per_sheet} per sheet" if lay else ""
            self.lbl_page.setText(f"Page {self.page_index() + 1} of {len(self.doc.pages)}"
                                  f"   ·   {describe_size(sc.page_w, sc.page_h, self.settings.units)}"
                                  + extra)

    # ═══════════════════════════════════════════════════════════════════════
    # selection & state
    # ═══════════════════════════════════════════════════════════════════════
    def selected(self) -> List[BaseItem]:
        if self.scene is None or sip.isdeleted(self.scene):
            return []
        return self.scene.selected_top()

    def editing_item(self) -> Optional[TextItem]:
        if self.scene is None:
            return None
        for it in self.scene.all_design_items():
            if isinstance(it, TextItem) and it.editing:
                return it
        return None

    def text_targets(self) -> List[TextItem]:
        ed = self.editing_item()
        if ed is not None:
            return [ed]
        return [i for i in self.selected() if isinstance(i, TextItem) and not i.locked]

    def _selection_changed(self):
        if self.scene is None or sip.isdeleted(self.scene) or sip.isdeleted(self):
            return
        items = self.selected()
        self.props.set_items(self.scene, items)
        self.layers.sync_selection()
        self.fmt.refresh()
        self._sync_text_actions()
        self._update_actions()
        if items:
            r = items[0].scene_box()
            for it in items[1:]:
                r = r.united(it.scene_box())
            self.ruler_h.set_selection(r)
            self.ruler_v.set_selection(r)
            if len(items) == 1:
                self.lbl_sel.setText(f"Selected: {items[0].display_name()}")
            else:
                self.lbl_sel.setText(f"{len(items)} objects selected")
        else:
            self.ruler_h.set_selection(None)
            self.ruler_v.set_selection(None)
            self.lbl_sel.setText("")

    def _editing_changed(self, item):
        self.fmt.refresh()
        self._sync_text_actions()
        self._update_actions()
        if item is not None:
            self.lbl_sel.setText("Typing — click outside the box (or press Esc) when finished")
        else:
            self._selection_changed()

    def _format_changed(self, _item):
        self.fmt.refresh()
        self._sync_text_actions()

    def _sync_text_actions(self):
        st = self.fmt.state()
        keys = ["bold", "italic", "underline", "bullets", "numbering", "font_grow", "font_shrink"
                ] + [f"talign_{k}" for k in ("left", "center", "right", "justify")]
        for k in keys:
            self.acts[k].setEnabled(st is not None)
        if st is None:
            return
        bold, italic, underline, align, lst = st
        for k, v in (("bold", bold), ("italic", italic), ("underline", underline),
                     ("bullets", lst == QTextListFormat.Style.ListDisc),
                     ("numbering", lst == QTextListFormat.Style.ListDecimal)):
            a = self.acts[k]
            a.blockSignals(True)
            a.setChecked(bool(v))
            a.blockSignals(False)
        for k in ("left", "center", "right", "justify"):
            a = self.acts[f"talign_{k}"]
            a.blockSignals(True)
            a.setChecked(k == align)
            a.blockSignals(False)

    def _update_actions(self, *_):
        if self.doc is None:
            return
        a = self.acts
        items = self.selected()
        n = len(items)
        unlocked = [i for i in items if not i.locked]
        editing = self.editing_item() is not None
        st = self.doc.undo_stack
        a["undo"].setEnabled(st.canUndo())
        a["redo"].setEnabled(st.canRedo())
        for k in ("cut", "copy", "duplicate"):
            a[k].setEnabled(n > 0 and not editing)
        a["delete"].setEnabled(bool(unlocked) and not editing)
        md = QApplication.clipboard().mimeData()
        a["paste"].setEnabled(bool(md) and (md.hasFormat(CLIP_MIME) or md.hasImage()
                                            or md.hasText() or md.hasUrls()))
        for k in ("front", "back", "forward", "backward", "rot_l", "rot_r", "lock"):
            a[k].setEnabled(n > 0)
        a["flip_h"].setEnabled(any(i.CAN_FLIP for i in unlocked))
        a["flip_v"].setEnabled(any(i.CAN_FLIP for i in unlocked))
        a["group"].setEnabled(len(unlocked) >= 2)
        a["ungroup"].setEnabled(any(isinstance(i, GroupItem) for i in items))
        for k in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            a[f"align_{k}"].setEnabled(bool(unlocked))
        a["dist_h"].setEnabled(len(unlocked) >= 3)
        a["dist_v"].setEnabled(len(unlocked) >= 3)
        a["fill_page"].setEnabled(len(unlocked) == 1)
        a["edit_text"].setEnabled(n == 1 and isinstance(items[0], TextItem))
        one_text = items[0] if n == 1 and isinstance(items[0], TextItem) else None
        a["link_text"].setEnabled(one_text is not None and one_text.link_next is None
                                  and not one_text.auto)
        a["unlink_text"].setEnabled(one_text is not None and one_text.link_next is not None)
        a["page_del"].setEnabled(len(self.doc.pages) > 1)
        idx = self.page_index()
        a["page_up"].setEnabled(idx > 0)
        a["page_down"].setEnabled(idx < len(self.doc.pages) - 1)
        lock_txt = "Unlock" if items and all(i.locked for i in items) else "Lock"
        a["lock"].setText(lock_txt)
        wraps = {getattr(i, "wrap", "none") for i in items}
        for k in ("none", "square", "top_bottom"):
            act = a[f"wrap_{k}"]
            act.setEnabled(bool(unlocked) and not editing)
            act.blockSignals(True)
            act.setChecked(wraps == {k})
            act.blockSignals(False)
        if len(wraps) != 1:                       # mixed: nothing ticked
            self._wrap_group.setExclusive(False)
            for k in ("none", "square", "top_bottom"):
                a[f"wrap_{k}"].setChecked(False)
            self._wrap_group.setExclusive(True)

    def _view_changed(self):
        v = self.doc.view
        for key, attr in (("show_grid", "show_grid"), ("show_guides", "show_guides"),
                          ("show_bounds", "show_boundaries"), ("snap_objects", "snap_objects"),
                          ("snap_guides", "snap_guides"), ("snap_grid", "snap_grid")):
            a = self.acts[key]
            a.blockSignals(True)
            a.setChecked(bool(getattr(v, attr)))
            a.blockSignals(False)
        for k in theme.THEMES:
            a = self.acts[f"theme_{k}"]
            a.blockSignals(True)
            a.setChecked(k == theme.current_name())
            a.blockSignals(False)

    def _view_opt(self, key: str, on: bool):
        # view options are display preferences, not edits: no undo entry
        self.doc.view.set(key, on)
        self.view.viewport().update()

    def _mouse_pos(self, sp: QPointF):
        u = self.settings.units
        d = UNIT_DECIMALS[u]
        self.lbl_pos.setText(f"{from_pt(sp.x(), u):.{d}f}, {from_pt(sp.y(), u):.{d}f} {u}")

    def _zoom_changed(self, z: float):
        pct = round(z * 100)
        self.lbl_zoom.setText(f"{pct}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(10, min(400, pct)))
        self.zoom_slider.blockSignals(False)

    def _slider_zoom(self, v: int):
        self.view.set_zoom(v / 100.0)

    def _cycle_units(self):
        order = ["mm", "in", "pt"]
        self.settings.units = order[(order.index(self.settings.units) + 1) % 3]
        self.settings.save()
        self._units_changed()

    def _units_changed(self):
        self._units_btn.setText(self.settings.units)
        self.props.units_changed()
        self.ruler_h.update()
        self.ruler_v.update()
        self._update_page_label()

    # ═══════════════════════════════════════════════════════════════════════
    # edit commands
    # ═══════════════════════════════════════════════════════════════════════
    def undo(self):
        self._end_edits()
        self.doc.undo_stack.undo()

    def redo(self):
        self._end_edits()
        self.doc.undo_stack.redo()

    def push(self, cmd):
        self.scene.push(cmd)

    def _select(self, items: List[BaseItem]):
        sc = self.scene
        sc.blockSignals(True)
        sc.clearSelection()
        for it in items:
            it.setSelected(True)
        sc.blockSignals(False)
        self._selection_changed()

    def select_all(self):
        self._select([i for i in self.scene.top_items() if i.isVisible()])

    def deselect(self):
        if getattr(self, "_link_from", None) is not None:
            self._end_link_mode("Cancelled.")
            return
        ed = self.editing_item()
        if ed is not None:
            ed.end_edit()
            self._select([ed] if not ed.in_group() else [])
            self.view.setFocus()
            return
        self._select([])

    def delete(self):
        items = [i for i in self.selected() if not i.locked]
        if items:
            self.push(DeleteItemsCmd(self.scene, items))

    def copy(self):
        items = self.selected()
        if not items:
            return
        md = QMimeData()
        md.setData(CLIP_MIME, items_to_clip(items))
        if len(items) == 1 and isinstance(items[0], TextItem):
            md.setText(items[0].plain_text())
        elif len(items) == 1 and isinstance(items[0], ImageItem) and items[0].has_image():
            md.setImageData(items[0].image())
        QApplication.clipboard().setMimeData(md)
        self._paste_count = 0
        self._copy_scene = self.scene
        self.statusBar().showMessage(f"Copied {len(items)} object(s)", 3000)

    def cut(self):
        self.copy()
        items = [i for i in self.selected() if not i.locked]
        if items:
            self.push(DeleteItemsCmd(self.scene, items, "Cut"))

    def paste(self):
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        if md.hasFormat(CLIP_MIME):
            items = items_from_clip(bytes(md.data(CLIP_MIME)))
            if not items:
                return
            self._paste_count += 1
            off = mm(5) * self._paste_count if self._copy_scene is self.scene else 0.0
            for it in items:
                fresh_uids(it)
                it.setPos(it.pos() + QPointF(off, off))
            self._insert(items, "Paste")
            from ..items.path import limit_page_drawings
            limit_page_drawings(self.scene.all_design_items())
            return
        if md.hasImage():
            img = QImage(md.imageData())
            if not img.isNull():
                data, fmt = encode_image(img)
                self._add_picture(data, fmt, img, "Pasted picture")
                return
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()
                     and os.path.splitext(u.toLocalFile())[1].lower() in IMAGE_EXTS]
            if paths:
                self._files_dropped(paths, self._center_point())
                return
        if md.hasText() and md.text().strip():
            t = self._new_text_box()
            t.set_text(md.text(), self.settings.default_font, self.settings.default_size)
            t.fit = "grow"
            t.refit()
            self._insert([t], "Paste text")

    def duplicate(self):
        clones = [c for c in (clone_item(i, QPointF(mm(5), mm(5))) for i in self.selected())
                  if c is not None]
        if clones:
            self._insert(clones, "Duplicate")

    def edit_text(self):
        items = self.selected()
        if len(items) == 1 and isinstance(items[0], TextItem):
            self.view.setFocus()
            items[0].begin_edit()

    def nudge(self, dx: int, dy: int, big: bool):
        items = [i for i in self.selected() if not i.locked]
        if not items:
            return
        step = NUDGE_BIG if big else NUDGE
        moves = {i: (QPointF(i.pos()), i.pos() + QPointF(dx * step, dy * step)) for i in items}
        self.push(MoveItemsCmd(self.scene, moves, "Nudge", nudge=True))
        self.props.schedule()

    # ═══════════════════════════════════════════════════════════════════════
    # insert
    # ═══════════════════════════════════════════════════════════════════════
    def _center_point(self) -> QPointF:
        c = self.view.mapToScene(self.view.viewport().rect().center())
        pr = self.scene.page_rect()
        return QPointF(min(max(c.x(), pr.left() + 20), pr.right() - 20),
                       min(max(c.y(), pr.top() + 20), pr.bottom() - 20))

    def _place_center(self, it: BaseItem, at: Optional[QPointF] = None):
        c = at or self._center_point()
        pr = self.scene.page_rect()
        w, h = it.w, it.h
        x = min(max(c.x() - w / 2, pr.left()), max(pr.right() - w, pr.left()))
        y = min(max(c.y() - h / 2, pr.top()), max(pr.bottom() - h, pr.top()))
        it.set_geometry(Geo(x, y, w, h, it.rotation()))

    def _insert(self, items: List[BaseItem], label: str, group_name: str = ""):
        sc = self.scene
        z = sc.next_z()
        for it in sorted(items, key=lambda i: i.zValue()):
            it.setZValue(z)
            z += 1
        st = self.doc.undo_stack
        if group_name:
            st.beginMacro(label)
        sc.push(AddItemsCmd(sc, items, label))
        if group_name:
            g = GroupItem()
            g.name = group_name
            sc.push(GroupCmd(sc, g, items))
            st.endMacro()
            items = [g]
        self.view.setFocus()
        self._select(items)
        return items

    def _new_text_box(self) -> TextItem:
        t = TextItem(mm(80), mm(25))
        t.set_text("", self.settings.default_font, self.settings.default_size)
        return t

    def insert_text(self):
        t = self._new_text_box()
        self._place_center(t)
        self._insert([t], "Add text box")
        t.begin_edit()

    def insert_shape(self, kind: str):
        if kind == "line":
            s = ShapeItem(mm(60), mm(3), "line")
        else:
            s = ShapeItem(mm(50), mm(50) if kind in ("ellipse", "star", "pentagon", "hexagon",
                                                     "heart", "diamond") else mm(35), kind)
        self._place_center(s)
        self._insert([s], f"Add {SHAPES[kind].lower()}")

    def insert_placeholder(self):
        im = ImageItem(mm(80), mm(60))
        self._place_center(im)
        self._insert([im], "Add picture frame")

    def _choose_picture(self) -> Optional[tuple]:
        start = self.settings.last_folder or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", start, PICTURE_FILTER)
        if not path:
            return None
        self.settings.last_folder = os.path.dirname(path)
        res = load_image_file(path)
        if res is None:
            why = image_file_problem(path) or ("It may be damaged, in a format that isn't "
                                               "supported, or too big to open.")
            QMessageBox.warning(self, "Picture", f"Sorry, that picture could not be opened.\n\n{why}")
            return None
        return (*res, os.path.basename(path))

    def insert_picture(self):
        items = self.selected()
        if len(items) == 1 and isinstance(items[0], ImageItem) and not items[0].locked:
            self.change_picture(items[0])
            return
        res = self._choose_picture()
        if res:
            data, fmt, img, name = res
            self._add_picture(data, fmt, img, name)

    def _add_picture(self, data: bytes, fmt: str, img: QImage, name: str,
                     at: Optional[QPointF] = None) -> ImageItem:
        pr = self.scene.page_rect()
        aspect = img.width() / max(img.height(), 1)
        w = pr.width() * 0.6
        h = w / aspect
        if h > pr.height() * 0.6:
            h = pr.height() * 0.6
            w = h * aspect
        im = ImageItem(w, h)
        im.set_image_data(data, fmt, name, img)
        self._place_center(im, at)
        self._insert([im], "Add picture")
        return im

    def change_picture(self, item: Optional[ImageItem] = None):
        if item is None:
            sel = self.selected()
            item = sel[0] if len(sel) == 1 and isinstance(sel[0], ImageItem) else None
        if item is None:
            return
        res = self._choose_picture()
        if res:
            data, fmt, _img, name = res
            sc = item.page_scene()
            sc.push(PropCmd(sc, [item], "image", (data, fmt, name), text="Change picture"))

    def frame_to_picture(self):
        items = [i for i in self.selected() if isinstance(i, ImageItem) and i.has_image()]
        for it in items:
            g = it.geometry()
            h = g.w / it.natural_aspect()
            new = Geo(g.x, g.y + (g.h - h) / 2, g.w, h, g.rot)
            self.push(PropCmd(self.scene, [it], "geometry", new, text="Fit frame to picture"))

    def insert_table(self):
        tmp = TableItem()
        dlg = TableDialog(tmp.table_state(), self, "New table")
        if not dlg.exec():
            return
        st = dlg.state()
        m = self.scene.margin_rect()
        t = TableItem(min(m.width(), mm(30) * st["cols"]), mm(9) * st["rows"], st["rows"],
                      st["cols"])
        t.apply_table_state(st)
        self._place_center(t)
        self._insert([t], "Add table")

    def edit_table(self, item: TableItem):
        dlg = TableDialog(item.table_state(), self)
        if dlg.exec():
            sc = item.page_scene()
            sc.push(PropCmd(sc, [item], "table", dlg.state(), text="Edit table"))

    def insert_wordart(self):
        tmp = WordArtItem()
        dlg = WordArtDialog(tmp.wordart_state(), self, "New WordArt")
        if not dlg.exec():
            return
        wa = WordArtItem(mm(120), mm(30))
        wa.apply_wordart_state(dlg.state())
        self._place_center(wa)
        self._insert([wa], "Add WordArt")

    def edit_wordart(self, item: WordArtItem):
        dlg = WordArtDialog(item.wordart_state(), self)
        if dlg.exec():
            sc = item.page_scene()
            sc.push(PropCmd(sc, [item], "wordart", dlg.state(), text="Edit WordArt"))

    def insert_block(self, kind: str):
        every = False
        if kind in ("header", "footer", "pagenum") and len(self.doc.pages) > 1:
            r = QMessageBox.question(self, "Add to every page?",
                                     "Add this to every page of the publication?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            every = r == QMessageBox.StandardButton.Yes
        name = blocks.BLOCKS[kind]
        group_name = blocks.GROUPED.get(kind, "")
        if not every:
            items = blocks.make_block(kind, self.scene)
            self._insert(items, f"Add {name.lower()}", group_name)
        else:
            st = self.doc.undo_stack
            st.beginMacro(f"Add {name.lower()} to every page")
            for sc in self.doc.pages:
                items = blocks.make_block(kind, sc)
                z = sc.next_z()
                for it in items:
                    it.setZValue(z)
                    z += 1
                sc.push(AddItemsCmd(sc, items, name))
            st.endMacro()
        refresh_fields(self.doc)

    # ── linked text boxes ────────────────────────────────────────────────────
    def start_link(self):
        items = self.selected()
        if len(items) != 1 or not isinstance(items[0], TextItem):
            return
        self._link_from = items[0]
        self.view.viewport().installEventFilter(self)
        self.view.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.statusBar().showMessage(
            "Click the box the text should continue in — you can change page first. "
            "Press Esc to cancel.")

    def _end_link_mode(self, msg: str = ""):
        self._link_from = None
        self.view.viewport().removeEventFilter(self)
        self.view.viewport().unsetCursor()
        self.statusBar().showMessage(msg, 5000)

    def link_boxes(self, a: TextItem, b: TextItem) -> bool:
        from ..textflow import LinkCmd, can_connect
        why = can_connect(a, b)
        if why:
            QMessageBox.information(self, "Continue text", why)
            return False
        if not b.chain_root().is_empty():
            r = QMessageBox.question(self, "Continue text",
                                     "That box already has text in it. Its text will be added "
                                     "to the end of the story. Carry on?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return False
        self.doc.undo_stack.push(LinkCmd(b.page_scene() or a.page_scene(), a, b))
        return True

    def break_link(self):
        from ..textflow import UnlinkCmd
        items = self.selected()
        if len(items) == 1 and isinstance(items[0], TextItem) and items[0].link_next is not None:
            self.doc.undo_stack.push(UnlinkCmd(self.scene, items[0]))
            self._update_actions()

    def eventFilter(self, obj, e):
        from PyQt6.QtCore import QEvent
        src = getattr(self, "_link_from", None)
        if src is not None and obj is self.view.viewport():
            if e.type() == QEvent.Type.MouseButtonPress:
                if e.button() != Qt.MouseButton.LeftButton:
                    self._end_link_mode("Cancelled.")
                    return True
                sp = self.view.mapToScene(e.position().toPoint())
                target = next((i for i in self.scene.items(sp)
                               if isinstance(i, TextItem)), None)
                if target is None:
                    self.statusBar().showMessage("That isn't a text box — click a text box, "
                                                 "or press Esc to cancel.")
                    return True
                ok = self.link_boxes(src, target)
                self._end_link_mode("The text now continues in that box." if ok else "")
                if ok:
                    self._select([target])
                return True
            if e.type() == QEvent.Type.KeyPress and e.key() == Qt.Key.Key_Escape:
                self._end_link_mode("Cancelled.")
                return True
        return super().eventFilter(obj, e)

    def _item_activated(self, item):
        if isinstance(item, ImageItem):
            if not item.locked:
                self.change_picture(item)
        elif isinstance(item, TableItem):
            self.edit_table(item)
        elif isinstance(item, WordArtItem):
            self.edit_wordart(item)

    def _panel_action(self, what: str):
        sel = self.selected()
        one = sel[0] if len(sel) == 1 else None
        if what == "page_setup":
            self.page_setup()
        elif what == "edit_text":
            self.edit_text()
        elif what == "change_picture" and isinstance(one, ImageItem):
            self.change_picture(one)
        elif what == "frame_to_picture":
            self.frame_to_picture()
        elif what == "edit_table" and isinstance(one, TableItem):
            self.edit_table(one)
        elif what == "edit_wordart" and isinstance(one, WordArtItem):
            self.edit_wordart(one)

    def _files_dropped(self, paths: List[str], at: QPointF):
        docs = [p for p in paths if p.lower().endswith((".dtpub", ".json", ".pub"))]
        if docs:
            self.open_path(docs[0])
            return
        target = None
        for it in self.scene.items(at):
            if isinstance(it, ImageItem) and not it.locked:
                target = it
                break
            if isinstance(it, BaseItem) and not isinstance(it, GroupItem):
                break
        failed = []
        for n, p in enumerate(paths):
            res = load_image_file(p)
            if res is None:
                failed.append(f"{os.path.basename(p)}: "
                              + (image_file_problem(p) or "could not be read"))
                continue
            data, fmt, img = res
            if target is not None and n == 0:
                sc = target.page_scene()
                sc.push(PropCmd(sc, [target], "image", (data, fmt, os.path.basename(p)),
                                text="Change picture"))
            else:
                self._add_picture(data, fmt, img, os.path.basename(p),
                                  at + QPointF(mm(8) * n, mm(8) * n))
        if failed:
            QMessageBox.warning(self, "Pictures", "Some pictures could not be added:\n\n"
                                + "\n".join(failed[:10]))

    # ═══════════════════════════════════════════════════════════════════════
    # arrange
    # ═══════════════════════════════════════════════════════════════════════
    def align(self, mode: str):
        items = [i for i in self.selected() if not i.locked]
        if not items:
            return
        if len(items) == 1:
            ref = self.scene.margin_rect()
        else:
            ref = items[0].scene_box()
            for it in items[1:]:
                ref = ref.united(it.scene_box())
        moves = {}
        for it in items:
            r = it.scene_box()
            dx = dy = 0.0
            if mode == "left":
                dx = ref.left() - r.left()
            elif mode == "hcenter":
                dx = ref.center().x() - r.center().x()
            elif mode == "right":
                dx = ref.right() - r.right()
            elif mode == "top":
                dy = ref.top() - r.top()
            elif mode == "vcenter":
                dy = ref.center().y() - r.center().y()
            elif mode == "bottom":
                dy = ref.bottom() - r.bottom()
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                moves[it] = (QPointF(it.pos()), it.pos() + QPointF(dx, dy))
        if moves:
            self.push(MoveItemsCmd(self.scene, moves, "Align"))

    def distribute(self, axis: str):
        items = [i for i in self.selected() if not i.locked]
        if len(items) < 3:
            return
        key = (lambda i: i.scene_box().left()) if axis == "h" else (lambda i: i.scene_box().top())
        items.sort(key=key)
        boxes = [i.scene_box() for i in items]
        if axis == "h":
            span = boxes[-1].right() - boxes[0].left()
            total = sum(b.width() for b in boxes)
        else:
            span = boxes[-1].bottom() - boxes[0].top()
            total = sum(b.height() for b in boxes)
        gap = (span - total) / (len(items) - 1)
        cur = boxes[0].left() if axis == "h" else boxes[0].top()
        moves = {}
        for it, b in zip(items, boxes):
            d = cur - (b.left() if axis == "h" else b.top())
            if abs(d) > 1e-6:
                off = QPointF(d, 0) if axis == "h" else QPointF(0, d)
                moves[it] = (QPointF(it.pos()), it.pos() + off)
            cur += (b.width() if axis == "h" else b.height()) + gap
        if moves:
            self.push(MoveItemsCmd(self.scene, moves, "Distribute"))

    def rotate_by(self, deg: float):
        items = [i for i in self.selected() if not i.locked]
        changes = {}
        for it in items:
            g = it.geometry()
            changes[it] = (g, g._replace(rot=normalize_angle(g.rot + deg)))
        if changes:
            self.push(GeometryCmd(self.scene, changes, "Rotate"))

    def flip(self, key: str):
        items = [i for i in self.selected() if not i.locked and i.CAN_FLIP]
        if items:
            changes = [(i, key, getattr(i, key), not getattr(i, key)) for i in items]
            from ..commands import MultiPropCmd
            self.push(MultiPropCmd(self.scene, changes, "Flip"))

    def arrange(self, mode: str):
        sc = self.scene
        tops = sc.top_items()
        sel = [i for i in tops if i.isSelected()]
        if not sel:
            return
        order = list(tops)
        if mode == "front":
            order = [i for i in order if i not in sel] + sel
        elif mode == "back":
            order = sel + [i for i in order if i not in sel]
        elif mode == "forward":
            for i in range(len(order) - 2, -1, -1):
                if order[i] in sel and order[i + 1] not in sel:
                    order[i], order[i + 1] = order[i + 1], order[i]
        elif mode == "backward":
            for i in range(1, len(order)):
                if order[i] in sel and order[i - 1] not in sel:
                    order[i], order[i - 1] = order[i - 1], order[i]
        old = {i: i.zValue() for i in tops}
        new = {i: float(n + 1) for n, i in enumerate(order)}
        if any(abs(old[i] - new[i]) > 1e-9 for i in tops) and order != tops:
            self.push(ZOrderCmd(sc, old, new, {"front": "Bring to front", "back": "Send to back",
                                               "forward": "Bring forward",
                                               "backward": "Send backward"}[mode]))
        elif order == tops:
            self.statusBar().showMessage("Already there.", 2000)

    def group(self):
        items = [i for i in self.selected() if not i.locked]
        if len(items) < 2:
            return
        g = GroupItem()
        self.push(GroupCmd(self.scene, g, items))
        self._select([g])

    def ungroup(self):
        groups = [i for i in self.selected() if isinstance(i, GroupItem)]
        if not groups:
            return
        st = self.doc.undo_stack
        st.beginMacro("Ungroup")
        members = []
        for g in groups:
            members += g.members()
            self.push(UngroupCmd(self.scene, g))
        st.endMacro()
        self._select(members)

    def set_wrap(self, mode: str):
        """How text in boxes behind the selected objects flows round them."""
        items = [i for i in self.selected() if not i.locked]
        targets = []
        for it in items:                       # a group's members carry the setting
            targets.extend(it.members() if isinstance(it, GroupItem) else [it])
        targets = [t for t in targets if t.wrap != mode]
        if not targets:
            return
        labels = {"none": "No text wrap", "square": "Wrap text", "top_bottom": "Wrap text"}
        self.push(PropCmd(self.scene, targets, "wrap", mode, text=labels[mode]))
        self.scene.flush_wrap()
        self._update_actions()

    def toggle_lock(self):
        items = self.selected()
        if not items:
            return
        lock = not all(i.locked for i in items)
        self.push(PropCmd(self.scene, items, "locked", lock, text="Lock" if lock else "Unlock"))
        self._selection_changed()

    def fill_page(self):
        items = [i for i in self.selected() if not i.locked]
        if len(items) != 1:
            return
        dlg = FillPageDialog(self.settings.units, self)
        if not dlg.exec():
            return
        gx, gy = dlg.gap_x.pt(), dlg.gap_y.pt()
        src = items[0]
        m = self.scene.margin_rect()
        box = src.scene_box()
        cols = max(1, int((m.width() + gx + 1e-6) // (box.width() + gx)))
        rows = max(1, int((m.height() + gy + 1e-6) // (box.height() + gy)))
        if cols * rows > 200:
            QMessageBox.warning(self, "Fill page", "That would make too many copies.")
            return
        off0 = QPointF(m.left() - box.left(), m.top() - box.top())
        st = self.doc.undo_stack
        st.beginMacro("Fill page with copies")
        self.push(MoveItemsCmd(self.scene, {src: (QPointF(src.pos()), src.pos() + off0)}))
        clones = []
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue
                cl = clone_item(src, QPointF(c * (box.width() + gx), r * (box.height() + gy)))
                if cl is not None:
                    clones.append(cl)
        if clones:
            z = self.scene.next_z()
            for cl in clones:
                cl.setZValue(z)
                z += 1
            self.push(AddItemsCmd(self.scene, clones, "Copies"))
        st.endMacro()
        self.statusBar().showMessage(f"Made {len(clones) + 1} copies ({cols} across × {rows} "
                                     "down).", 5000)

    # ═══════════════════════════════════════════════════════════════════════
    # pages
    # ═══════════════════════════════════════════════════════════════════════
    def page_add(self):
        cur = self.scene
        st = cur.setup_state()
        st["background"] = "#ffffffff"
        sc = self.doc.make_page(cur.page_w, cur.page_h)
        sc.apply_setup(st)
        idx = self.page_index() + 1
        self.doc.undo_stack.push(AddPageCmd(self.doc, idx, sc))
        self.show_page(idx)

    def page_duplicate(self):
        self._end_edits()
        data = page_to_dict(self.scene, standalone=True)
        sc = page_from_dict(self.doc, data, [])
        for it in sc.top_items():
            fresh_uids(it)
        idx = self.page_index() + 1
        self.doc.undo_stack.push(AddPageCmd(self.doc, idx, sc, "Duplicate page"))
        self.show_page(idx)

    def page_delete(self, index: Optional[int] = None):
        if len(self.doc.pages) <= 1:
            return
        idx = self.page_index() if index is None else index
        sc = self.doc.pages[idx]
        if sc.top_items():
            r = QMessageBox.question(self, "Delete page",
                                     f"Delete page {idx + 1} and everything on it?\n"
                                     "(You can undo this.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        self._last_index = idx
        self.doc.undo_stack.push(RemovePageCmd(self.doc, sc))

    def page_move(self, delta: int, index: Optional[int] = None):
        idx = self.page_index() if index is None else index
        dst = idx + delta
        if 0 <= dst < len(self.doc.pages):
            self.doc.undo_stack.push(MovePageCmd(self.doc, self.doc.pages[idx], dst))

    def _thumb_move(self, src: int, dst: int):
        self.doc.undo_stack.push(MovePageCmd(self.doc, self.doc.pages[src], dst))

    def page_rename(self, index: Optional[int] = None):
        idx = self.page_index() if index is None else index
        sc = self.doc.pages[idx]
        name, ok = QInputDialog.getText(self, "Rename page",
                                        "Page name (for example \"Front cover\"):", text=sc.name)
        if ok and name != sc.name:
            self.doc.undo_stack.push(RenamePageCmd(self.doc, sc, sc.name, name.strip()))

    def _thumb_menu(self, row: int, gpos: QPoint):
        if row < 0:
            return
        self.show_page(row)
        m = self._menu(["page_add", "page_dup", "page_del", None, "page_up", "page_down",
                        "page_rename", None, "page_setup"])
        m.exec(gpos)

    def _scenes_for_setup(self, all_pages: bool) -> List[PageScene]:
        return list(self.doc.pages) if all_pages else [self.scene]

    def page_setup(self):
        sc = self.scene
        dlg = PageSetupDialog(sc.setup_state(), self.settings.units, len(self.doc.pages) > 1, self,
                              sheet=self.doc.sheet)
        if not dlg.exec():
            return
        new = dlg.result_state(sc.setup_state())
        new_sheet = dlg.result_sheet()
        st = self.doc.undo_stack
        st.beginMacro("Page setup")
        if new_sheet != self.doc.sheet:
            from ..commands import SheetCmd
            st.push(SheetCmd(self.doc, self.doc.sheet, new_sheet))
        scenes = self._scenes_for_setup(dlg.apply_all())
        olds = [s.setup_state() for s in scenes]
        news = []
        for s, o in zip(scenes, olds):
            n = dict(o)
            for k in ("width", "height", "margins", "columns", "rows", "gutter"):
                n[k] = new[k]
            if s is sc:
                n["background"] = new["background"]
            news.append(n)
        self.doc.undo_stack.push(PageSetupCmd(scenes, olds, news))
        st.endMacro()
        self._after_setup()

    def _after_setup(self):
        self.view.set_page(self.scene)
        self._update_page_label()
        self.props.refresh()
        QTimer.singleShot(0, self.view.fit_page)

    def _setup_all(self, label: str, fn):
        scenes = list(self.doc.pages)
        olds = [s.setup_state() for s in scenes]
        news = []
        for o in olds:
            n = dict(o)
            fn(n)
            news.append(n)
        self.doc.undo_stack.push(PageSetupCmd(scenes, olds, news, label))
        self._after_setup()

    def set_page_size(self, w: float, h: float):
        landscape = self.scene.page_w > self.scene.page_h

        def fn(n):
            lo, hi = sorted((w, h))
            n["width"], n["height"] = (hi, lo) if landscape else (lo, hi)
        self._setup_all("Page size", fn)

    def set_orientation(self, landscape: bool):
        def fn(n):
            lo, hi = sorted((n["width"], n["height"]))
            n["width"], n["height"] = (hi, lo) if landscape else (lo, hi)
        self._setup_all("Orientation", fn)

    def set_margins(self, v: float):
        self._setup_all("Margins", lambda n: n.__setitem__("margins", [v] * 4))

    def set_background(self, c: QColor):
        sc = self.scene
        o = sc.setup_state()
        n = dict(o)
        n["background"] = c.name(QColor.NameFormat.HexArgb)
        self.doc.undo_stack.push(PageSetupCmd([sc], [o], [n], "Page colour"))
        self.props.refresh()

    def _pick_background(self):
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.scene.background, self, "Page colour")
        if c.isValid():
            self.set_background(c)

    def clear_guides(self):
        if self.scene.guides:
            self.push(RemoveGuideCmd(self.scene, list(self.scene.guides), "Remove guides"))

    # ═══════════════════════════════════════════════════════════════════════
    # context menus
    # ═══════════════════════════════════════════════════════════════════════
    def _canvas_menu(self, gpos: QPoint, sp: QPointF):
        items = self.selected()
        under = [i for i in self.scene.items(sp) if isinstance(i, BaseItem)]
        m = QMenu(self)
        if items and under:
            one = items[0] if len(items) == 1 else None
            if isinstance(one, TextItem):
                m.addAction(self.acts["edit_text"])
                m.addAction(self.acts["link_text"])
                if one.link_next is not None:
                    m.addAction(self.acts["unlink_text"])
            if isinstance(one, ImageItem):
                m.addAction(icon("picture", 18), "Change Picture…", lambda: self.change_picture(one))
            if isinstance(one, TableItem):
                m.addAction(icon("table", 18), "Edit Table…", lambda: self.edit_table(one))
            if isinstance(one, WordArtItem):
                m.addAction(icon("wordart", 18), "Edit WordArt…", lambda: self.edit_wordart(one))
            if one is not None and not m.isEmpty():
                m.addSeparator()
            for k in ("cut", "copy", "paste", "duplicate", "delete"):
                m.addAction(self.acts[k])
            m.addSeparator()
            order = m.addMenu(icon("front", 18), "Order")
            for k in ("front", "forward", "backward", "back"):
                order.addAction(self.acts[k])
            al = m.addMenu(icon("align_left", 18), "Align")
            for k in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
                al.addAction(self.acts[f"align_{k}"])
            rot = m.addMenu(icon("rotate_right", 18), "Rotate and flip")
            for k in ("rot_l", "rot_r", "flip_h", "flip_v"):
                rot.addAction(self.acts[k])
            m.addSeparator()
            if len(items) >= 2:
                m.addAction(self.acts["group"])
            if any(isinstance(i, GroupItem) for i in items):
                m.addAction(self.acts["ungroup"])
            wr = m.addMenu(icon("wrap_square", 18), "Wrap Text")
            for k in ("none", "square", "top_bottom"):
                wr.addAction(self.acts[f"wrap_{k}"])
            m.addAction(self.acts["lock"])
            m.addSeparator()
            m.addAction("Format…", lambda: self.right.setCurrentWidget(self.props))
        else:
            m.addAction(self.acts["paste"])
            m.addSeparator()
            ins = m.addMenu(icon("text", 18), "Add")
            for k in ("ins_text", "ins_picture", "ins_placeholder", "ins_table", "ins_wordart"):
                ins.addAction(self.acts[k])
            shp = m.addMenu(icon("shapes", 18), "Shapes")
            for k in SHAPES:
                shp.addAction(self.acts[f"shape_{k}"])
            m.addSeparator()
            m.addAction(self.acts["page_setup"])
            m.addAction(icon("background", 18), "Page Colour…", self._pick_background)
            m.addAction(self.acts["page_add"])
        m.exec(gpos)

    def _fill_recent(self):
        m = self.recent_menu
        m.clear()
        rec = self.settings.existing_recent()
        if not rec:
            a = m.addAction("(no recent publications)")
            a.setEnabled(False)
        for p in rec:
            a = m.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, p=p: self.open_path(p))

    # ═══════════════════════════════════════════════════════════════════════
    # files
    # ═══════════════════════════════════════════════════════════════════════
    def maybe_save(self) -> bool:
        """True if it's OK to discard the current document."""
        if self.doc is None:
            return True
        self._end_edits()
        if not self.doc.is_modified():
            return True
        name = os.path.basename(self.doc.path) if self.doc.path else "this publication"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Save changes?")
        box.setText(f"Do you want to save the changes to {name}?")
        box.setInformativeText("If you don't save, your changes will be lost.")
        b_save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        b_dont = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_save:
            return self.save()
        return clicked is b_dont

    def new_document(self):
        if not self.maybe_save():
            return
        from .dialogs.start import StartDialog
        dlg = StartDialog(self.settings.existing_recent(), self.settings.show_start, self)
        if not dlg.exec():
            return
        self.settings.show_start = dlg.cb_show.isChecked()
        self.settings.save()
        if dlg.document is not None:
            self._adopt_new(dlg.document)
        elif dlg.open_path:
            self.open_path(dlg.open_path, ask=False)
        elif dlg.open_other:
            self.open_dialog(ask=False)

    # ── Microsoft Publisher import ───────────────────────────────────────────
    def import_publisher(self, path: str) -> bool:
        from PyQt6.QtWidgets import QProgressDialog
        from ..importers.pub import (LIBREOFFICE_URL, PubConverter, build_from_odg,
                                     find_soffice)
        if not find_soffice():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("Open a Publisher file")
            box.setText("To open Microsoft Publisher files, the free LibreOffice program "
                        "needs to be installed on this computer.")
            box.setInformativeText("Install LibreOffice, then try again. It is only used in "
                                   "the background to read the file.")
            get = box.addButton("Get LibreOffice", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is get:
                QDesktopServices.openUrl(QUrl(LIBREOFFICE_URL))
            return False
        dlg = QProgressDialog(f"Opening {os.path.basename(path)}…\n"
                              "Big publications can take a minute.", "Cancel", 0, 0, self)
        dlg.setWindowTitle("Open a Publisher file")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        conv = PubConverter(path, self)
        result = {}
        conv.converted.connect(lambda p: (result.__setitem__("odg", p), dlg.reset()))
        conv.failed.connect(lambda m: (result.__setitem__("err", m), dlg.reset()))
        dlg.canceled.connect(conv.cancel)
        conv.start()
        dlg.exec()
        conv._stop()
        conv.deleteLater()
        if "odg" not in result:
            msg = result.get("err", "Cancelled.")
            if msg != "Cancelled.":
                QMessageBox.warning(self, "Open a Publisher file",
                                    f"Sorry, that Publisher file could not be opened.\n\n{msg}")
            return False
        odg = result["odg"]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            doc, rep = build_from_odg(odg, path)
        except Exception as ex:  # noqa: BLE001 - damaged conversions must not crash
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Open a Publisher file",
                                f"Sorry, that Publisher file could not be read.\n\n{ex}")
            return False
        finally:
            import shutil
            shutil.rmtree(os.path.dirname(os.path.dirname(odg)), ignore_errors=True)
        QApplication.restoreOverrideCursor()
        self.autosaver.discard()
        self.set_document(doc)
        doc.undo_stack.resetClean()                 # it still needs saving as .dtpub
        self._update_title()
        self._pub_source = path
        self.settings.add_recent(path)
        self.settings.last_folder = os.path.dirname(path)
        self.settings.save()
        notes = "\n".join(f"• {w}" for w in rep.warnings[:10])
        QMessageBox.information(
            self, "Publisher file opened",
            f"Opened {os.path.basename(path)}: {rep.summary()}.\n\n"
            "Please check it over — fonts, spacing and text wrapping can differ a little "
            "from Publisher. When you save, it will be saved as a new DTP Publisher file; "
            "your original .pub file is not changed." + (f"\n\nNotes:\n{notes}" if notes else ""))
        return True

    def _adopt_new(self, doc: Document):
        self.autosaver.discard()
        self.set_document(doc)

    def open_dialog(self, ask: bool = True):
        if ask and not self.maybe_save():
            return
        start = self.settings.last_folder or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Open a publication", start, DOC_FILTER)
        if path:
            self.open_path(path, ask=False)

    def open_path(self, path: str, ask: bool = True) -> bool:
        if ask and not self.maybe_save():
            return False
        if path.lower().endswith(".pub"):
            return self.import_publisher(path)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            doc, warnings = load_document(path)
        except DocumentError as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Open", str(ex))
            return False
        QApplication.restoreOverrideCursor()
        self.autosaver.discard()
        self.set_document(doc)
        if doc.path:
            self.settings.add_recent(path)
        self.settings.last_folder = os.path.dirname(path)
        self.settings.save()
        if warnings:
            QMessageBox.information(self, "Opened with notes", "\n".join(warnings[:12]))
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 4000)
        return True

    def save(self) -> bool:
        if not self.doc.path:
            return self.save_as()
        return self._save_to(self.doc.path)

    def save_as(self) -> bool:
        self._end_edits()
        start = self.doc.path or os.path.join(self.settings.last_folder or
                                              os.path.expanduser("~"),
                                              (self.doc.title or "My publication") + FILE_EXT)
        if not self.doc.path and getattr(self, "_pub_source", None) and self.doc.title:
            start = os.path.join(os.path.dirname(self._pub_source), self.doc.title + FILE_EXT)
        path, _ = QFileDialog.getSaveFileName(self, "Save publication", start,
                                              f"Publications (*{FILE_EXT})")
        if not path:
            return False
        if not path.lower().endswith(FILE_EXT):
            path += FILE_EXT
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        self._end_edits()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup_ok = save_document(self.doc, path, keep_backup=self.settings.keep_backup)
        except OSError as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Save", f"Sorry, the publication could not be saved:\n{ex}")
            return False
        QApplication.restoreOverrideCursor()
        self.autosaver.discard()
        self.settings.add_recent(path)
        self.settings.last_folder = os.path.dirname(path)
        self.settings.save()
        self._update_title()
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}", 4000)
        if not backup_ok:
            QMessageBox.warning(
                self, "Save",
                f"{os.path.basename(path)} was saved.\n\nThe backup copy of the previous "
                f"version ({os.path.basename(path)}.bak) could not be updated — the folder "
                "may be read-only or the backup file may be open in another program.")
        return True

    def _default_export_name(self, ext: str) -> str:
        base = (os.path.splitext(os.path.basename(self.doc.path))[0] if self.doc.path
                else (self.doc.title or "publication"))
        folder = (os.path.dirname(self.doc.path) if self.doc.path
                  else self.settings.last_folder or os.path.expanduser("~"))
        return os.path.join(folder, base + ext)

    def export_pdf(self):
        self._end_edits()
        path, _ = QFileDialog.getSaveFileName(self, "Save as PDF", self._default_export_name(".pdf"),
                                              "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        refresh_fields(self.doc)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            n = export_pdf(self.doc, path)
        except (OSError, ValueError) as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "PDF", f"Sorry, the PDF could not be made:\n{ex}")
            return
        QApplication.restoreOverrideCursor()
        r = QMessageBox.question(self, "PDF saved",
                                 f"Saved {n} page(s) to\n{path}\n\nOpen it now?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_pictures(self):
        self._end_edits()
        dlg = ExportPicturesDialog(len(self.doc.pages), self)
        if not dlg.exec():
            return
        ext = "." + dlg.fmt.currentData()
        path, _ = QFileDialog.getSaveFileName(self, "Save as picture",
                                              self._default_export_name(ext),
                                              "PNG (*.png)" if ext == ".png" else "JPEG (*.jpg)")
        if not path:
            return
        base = os.path.splitext(os.path.basename(path))[0]
        pages = None if dlg.rb_all.isChecked() else [self.page_index()]
        refresh_fields(self.doc)
        from ..export import export_dpi
        from ..limits import TooBig
        want = dlg.dpi.currentData()
        got = export_dpi(self.doc, pages, want)
        if got < want:
            r = QMessageBox.question(
                self, "Save as picture",
                f"This page is too big to save as a picture at {want:g} dots per inch. "
                f"It can be saved at {got:g} dots per inch instead.\n\n"
                "For printing big posters, Save as PDF keeps full quality.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out = export_images(self.doc, os.path.dirname(path), base, dlg.fmt.currentData(),
                                want, pages)
        except (OSError, TooBig) as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Save as picture", str(ex))
            return
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"Saved {len(out)} picture(s)", 5000)

    def print_doc(self):
        self._end_edits()
        refresh_fields(self.doc)
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        first = self.doc.pages[0]
        pr.setPageLayout(page_layout(first.page_w, first.page_h))
        pr.setFromTo(1, len(self.doc.pages))
        dlg = QPrintDialog(pr, self)
        dlg.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, True)
        dlg.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage, True)
        fit = QCheckBox("Shrink or enlarge to fit the paper")
        fit.setChecked(True)
        opts = QWidget()
        opts.setWindowTitle("Fitting")
        ol = QVBoxLayout(opts)
        ol.addWidget(fit)
        ol.addStretch(1)
        dlg.setOptionTabs([opts])
        if not dlg.exec():
            return
        rng = pr.printRange()
        if rng == QPrinter.PrintRange.PageRange:
            pages = list(range(max(pr.fromPage(), 1) - 1, min(pr.toPage(), len(self.doc.pages))))
        elif rng == QPrinter.PrintRange.CurrentPage:
            pages = [self.page_index()]
        else:
            pages = list(range(len(self.doc.pages)))
        copies = 1 if pr.supportsMultipleCopies() else max(1, pr.copyCount())
        pages = pages * copies
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            n = print_document(self.doc, pr, pages, fit_to_paper=fit.isChecked())
        except OSError as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Print", str(ex))
            return
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"Sent {n} page(s) to the printer", 5000)

    # ═══════════════════════════════════════════════════════════════════════
    # preferences / theme
    # ═══════════════════════════════════════════════════════════════════════
    def preferences(self):
        s = self.settings
        old_scale, old_units = s.ui_scale, s.units
        dlg = PreferencesDialog(s, self, assoc_registry=self.assoc_registry)
        if not dlg.exec():
            return
        dlg.apply_to(s)
        s.sanitize()
        s.save()
        self._apply_file_types(dlg.assoc_wanted())
        self.set_theme(s.theme)
        self.autosaver.set_interval(s.autosave_minutes)
        if s.units != old_units:
            self._units_changed()
        if abs(s.ui_scale - old_scale) > 1e-6:
            QMessageBox.information(self, "Preferences", "The new button and text size will be "
                                    "used the next time you start the program.")

    def _apply_file_types(self, wanted):
        """Windows file associations, from the Preferences check boxes."""
        if wanted is None:
            return
        reg = self.assoc_registry
        if sorted(wanted) == sorted(winassoc.registered_types(reg)) and \
                not any(winassoc.status(e, reg).stale for e in wanted):
            return
        try:
            result = winassoc.apply(wanted, reg)
        except OSError as ex:
            QMessageBox.warning(self, "Preferences", f"Windows didn't accept the change:\n{ex}")
            return
        waiting = [st.ext for st in result if st.needs_confirming]
        if waiting:
            ans = QMessageBox.question(
                self, "Double-click to open",
                "DTP Publisher Pro is set up to open " + " and ".join(waiting) + " files.\n\n"
                "Windows asks you to confirm this yourself, because another program was "
                "chosen for them before. Open Windows Settings now and choose "
                "DTP Publisher Pro?")
            if ans == QMessageBox.StandardButton.Yes:
                winassoc.open_default_apps_settings()
        elif wanted:
            self.statusBar().showMessage("Double-clicked files now open in DTP Publisher Pro",
                                         5000)

    def set_theme(self, name: str):
        theme.apply(QApplication.instance(), name)
        self.settings.theme = name
        self.settings.save()
        clear_cache()
        for a in self.acts.values():
            n = a.property("icon_name")
            if n:
                a.setIcon(icon(n))
        self.thumbs.refresh_icons()
        self.layers.refresh_icons()
        self.fmt.refresh_icons()
        self.setWindowIcon(icon("wordart", 64))
        for sc in self.doc.pages:
            sc.update()
        self.ruler_h.update()
        self.ruler_v.update()
        self._view_changed()

    def open_manual(self):
        """The user manual, in the web browser (it works without the internet)."""
        path = manual_path()
        if os.path.isfile(path):
            try:
                path = manual_for_browser()
            except OSError:
                pass                            # the original still opens for now
        if not os.path.isfile(path):
            QMessageBox.warning(self, "User Manual",
                                f"The manual is missing from the program folder:\n{path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.information(self, "User Manual",
                                    f"Open this file in your web browser:\n{path}")

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}", about_text())

    # ═══════════════════════════════════════════════════════════════════════
    # lifecycle
    # ═══════════════════════════════════════════════════════════════════════
    def closeEvent(self, e):
        if not self.maybe_save():
            e.ignore()
            return
        self.settings.window_geometry = bytes(self.saveGeometry()).hex()
        self.settings.save()
        self.autosaver.shutdown()
        self._detach_doc()
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            QTimer.singleShot(0, self.view.fit_page)

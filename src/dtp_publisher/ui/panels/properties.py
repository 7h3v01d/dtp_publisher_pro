# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Format panel: position, colours and type-specific options for the selection.

Every change goes through an undo command; spin-box and slider drags merge
into one undo step per property.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
                             QVBoxLayout, QWidget)

from ...commands import PropCmd
from ...geometry import Geo, normalize_angle
from ...items import BaseItem, ImageItem, ShapeItem, TableItem, TextItem, WordArtItem
from ...items.image import FIT_MODES as IMG_FIT
from ...items.shape import SHAPES
from ...items.text import FIT_MODES as TXT_FIT, VALIGNS
from ...items.wordart import WARPS
from ...scene import PageScene
from ...units import describe_size
from ..widgets import ColorButton, UnitSpin, header_label, hint_label

LINE_STYLES = {"solid": "Solid", "dash": "Dashed", "dot": "Dotted", "dashdot": "Dash-dot"}


def _combo(options: dict) -> QComboBox:
    c = QComboBox()
    for k, v in options.items():
        c.addItem(v, k)
    return c


def _set_combo(c: QComboBox, key):
    i = c.findData(key)
    c.blockSignals(True)
    c.setCurrentIndex(max(i, 0))
    c.blockSignals(False)


class PropertiesPanel(QWidget):
    actionRequested = pyqtSignal(str)   # change_picture, edit_table, edit_wordart, page_setup,
                                        # edit_text, frame_to_picture

    def __init__(self, units_getter: Callable[[], str], parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self._units = units_getter
        self.scene: Optional[PageScene] = None
        self.items: List[BaseItem] = []
        self._building = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("SidePanel")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)
        self.title = header_label("Page")
        v.addWidget(self.title)
        self.hint = hint_label("")
        v.addWidget(self.hint)

        # page ---------------------------------------------------------------
        self.g_page = QGroupBox("Page")
        f = QFormLayout(self.g_page)
        self.lbl_size = QLabel("")
        f.addRow("Size:", self.lbl_size)
        self.btn_bg = ColorButton("Background", allow_none=False, alpha=False)
        self.btn_bg.colorPicked.connect(self._page_bg)
        f.addRow(self.btn_bg)
        b = QPushButton("Page setup…")
        b.clicked.connect(lambda: self.actionRequested.emit("page_setup"))
        f.addRow(b)
        v.addWidget(self.g_page)

        # geometry ---------------------------------------------------------------
        self.g_geo = QGroupBox("Position and size")
        f = QFormLayout(self.g_geo)
        self.sp_x, self.sp_y = UnitSpin(), UnitSpin()
        self.sp_w, self.sp_h = UnitSpin(lo_pt=1), UnitSpin(lo_pt=1)
        self.sp_rot = QDoubleSpinBox()
        self.sp_rot.setRange(-180, 180)
        self.sp_rot.setWrapping(True)
        self.sp_rot.setSuffix("°")
        self.sp_rot.setDecimals(1)
        self.sp_rot.setKeyboardTracking(False)
        for lbl, w in (("Across (X):", self.sp_x), ("Down (Y):", self.sp_y),
                       ("Width:", self.sp_w), ("Height:", self.sp_h), ("Rotation:", self.sp_rot)):
            f.addRow(lbl, w)
            w.valueChanged.connect(self._geo_changed)
        self.cb_aspect = QCheckBox("Keep proportions")
        f.addRow(self.cb_aspect)
        self.cb_lock = QCheckBox("Lock in place")
        self.cb_lock.toggled.connect(lambda on: self._prop("locked", on, text="Lock"))
        f.addRow(self.cb_lock)
        v.addWidget(self.g_geo)

        # fill / line -----------------------------------------------------------
        self.g_style = QGroupBox("Colour and line")
        f = QFormLayout(self.g_style)
        self.btn_fill = ColorButton()
        self.btn_fill.colorPicked.connect(lambda c: self._prop("fill", c, text="Fill colour"))
        f.addRow("Fill:", self.btn_fill)
        self.btn_line = ColorButton()
        self.btn_line.colorPicked.connect(self._line_color)
        f.addRow("Line:", self.btn_line)
        self.sp_lw = QDoubleSpinBox()
        self.sp_lw.setRange(0, 72)
        self.sp_lw.setSingleStep(0.25)
        self.sp_lw.setSuffix(" pt")
        self.sp_lw.setKeyboardTracking(False)
        self.sp_lw.valueChanged.connect(
            lambda val: self._prop("stroke_width", float(val), merge=True, text="Line width"))
        f.addRow("Line width:", self.sp_lw)
        self.cmb_ls = _combo(LINE_STYLES)
        self.cmb_ls.currentIndexChanged.connect(
            lambda _: self._prop("stroke_style", self.cmb_ls.currentData(), text="Line style"))
        f.addRow("Line style:", self.cmb_ls)
        self.sl_op = QSlider(Qt.Orientation.Horizontal)
        self.sl_op.setRange(0, 100)
        self.sl_op.valueChanged.connect(
            lambda val: self._prop("opacity", 1 - val / 100.0, merge=True, text="Transparency"))
        self.lbl_op = QLabel("0%")
        row = QHBoxLayout()
        row.addWidget(self.sl_op, 1)
        row.addWidget(self.lbl_op)
        f.addRow("Transparency:", row)
        from ...items.base import WRAP_MODES
        self.cmb_wrap = _combo(WRAP_MODES)
        self.cmb_wrap.setToolTip("How text in boxes behind this object flows round it")
        self.cmb_wrap.currentIndexChanged.connect(
            lambda _: self._prop("wrap", self.cmb_wrap.currentData(), text="Wrap text"))
        f.addRow("Text wrap:", self.cmb_wrap)
        v.addWidget(self.g_style)

        # text ---------------------------------------------------------------
        self.g_text = QGroupBox("Text box")
        f = QFormLayout(self.g_text)
        self.cmb_fit = _combo(TXT_FIT)
        self.cmb_fit.currentIndexChanged.connect(
            lambda _: self._prop("fit", self.cmb_fit.currentData(), text="Text fit",
                                 only=TextItem))
        f.addRow("Fit:", self.cmb_fit)
        self.cmb_valign = _combo(VALIGNS)
        self.cmb_valign.currentIndexChanged.connect(
            lambda _: self._prop("valign", self.cmb_valign.currentData(),
                                 text="Vertical alignment", only=TextItem))
        f.addRow("Vertical:", self.cmb_valign)
        self.sp_pad = UnitSpin(lo_pt=0, hi_pt=200)
        self.sp_pad.valueChanged.connect(
            lambda _: self._prop("padding", self.sp_pad.pt(), merge=True, text="Text margin",
                                 only=TextItem))
        f.addRow("Inner margin:", self.sp_pad)
        b = QPushButton("Edit text")
        b.clicked.connect(lambda: self.actionRequested.emit("edit_text"))
        f.addRow(b)
        v.addWidget(self.g_text)

        # picture -------------------------------------------------------------
        self.g_pic = QGroupBox("Picture")
        f = QFormLayout(self.g_pic)
        b = QPushButton("Change picture…")
        b.setObjectName("Primary")
        b.clicked.connect(lambda: self.actionRequested.emit("change_picture"))
        f.addRow(b)
        self.cmb_imgfit = _combo(IMG_FIT)
        self.cmb_imgfit.currentIndexChanged.connect(
            lambda _: self._prop("fit_mode", self.cmb_imgfit.currentData(), text="Picture fit",
                                 only=ImageItem))
        f.addRow("Fit:", self.cmb_imgfit)
        self.sl_cx = QSlider(Qt.Orientation.Horizontal)
        self.sl_cy = QSlider(Qt.Orientation.Horizontal)
        for s, key, lbl in ((self.sl_cx, "crop_x", "Show left ↔ right:"),
                            (self.sl_cy, "crop_y", "Show top ↕ bottom:")):
            s.setRange(-100, 100)
            s.valueChanged.connect(lambda val, k=key: self._prop(k, val / 100.0, merge=True,
                                                                 text="Crop position",
                                                                 only=ImageItem))
            f.addRow(lbl, s)
        self.sp_corner = UnitSpin(lo_pt=0, hi_pt=2000)
        self.sp_corner.valueChanged.connect(
            lambda _: self._prop("corner", self.sp_corner.pt(), merge=True,
                                 text="Rounded corners", only=ImageItem))
        f.addRow("Round corners:", self.sp_corner)
        b = QPushButton("Make frame match picture shape")
        b.clicked.connect(lambda: self.actionRequested.emit("frame_to_picture"))
        f.addRow(b)
        v.addWidget(self.g_pic)

        # shape ---------------------------------------------------------------
        self.g_shape = QGroupBox("Shape")
        f = QFormLayout(self.g_shape)
        self.cmb_shape = _combo(SHAPES)
        self.cmb_shape.currentIndexChanged.connect(
            lambda _: self._prop("shape_kind", self.cmb_shape.currentData(), text="Change shape",
                                 only=ShapeItem))
        f.addRow("Shape:", self.cmb_shape)
        self.sp_radius = UnitSpin(lo_pt=0, hi_pt=2000)
        self.sp_radius.valueChanged.connect(
            lambda _: self._prop("radius", self.sp_radius.pt(), merge=True, text="Corner radius",
                                 only=ShapeItem))
        f.addRow("Corner radius:", self.sp_radius)
        v.addWidget(self.g_shape)

        # table / wordart -------------------------------------------------------
        self.g_table = QGroupBox("Table")
        f = QFormLayout(self.g_table)
        b = QPushButton("Edit table…")
        b.setObjectName("Primary")
        b.clicked.connect(lambda: self.actionRequested.emit("edit_table"))
        f.addRow(b)
        f.addRow(hint_label("Tip: double-click the table to edit it."))
        v.addWidget(self.g_table)

        self.g_wa = QGroupBox("WordArt")
        f = QFormLayout(self.g_wa)
        b = QPushButton("Edit WordArt…")
        b.setObjectName("Primary")
        b.clicked.connect(lambda: self.actionRequested.emit("edit_wordart"))
        f.addRow(b)
        self.cmb_warp = _combo(WARPS)
        self.cmb_warp.currentIndexChanged.connect(self._warp)
        f.addRow("Shape:", self.cmb_warp)
        v.addWidget(self.g_wa)
        v.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.refresh)
        self.set_items(None, [])

    # ── wiring ───────────────────────────────────────────────────────────────
    def set_items(self, scene: Optional[PageScene], items: List[BaseItem]):
        for it in self.items:
            try:
                it.geometryChanged.disconnect(self.schedule)
            except (TypeError, RuntimeError):
                pass
        self.scene = scene
        self.items = list(items)
        for it in self.items:
            it.geometryChanged.connect(self.schedule)
        self.refresh()

    def schedule(self):
        self._timer.start()

    def units_changed(self):
        for s in (self.sp_x, self.sp_y, self.sp_w, self.sp_h, self.sp_pad, self.sp_corner,
                  self.sp_radius):
            s.set_unit(self._units())
        self.refresh()

    # ── refresh ──────────────────────────────────────────────────────────────
    def refresh(self):
        self._building = True
        try:
            self._refresh()
        finally:
            self._building = False

    def _refresh(self):
        items = [i for i in self.items if i.scene() is not None]
        sc = self.scene
        none = not items
        self.g_page.setVisible(none and sc is not None)
        for g in (self.g_geo, self.g_style):
            g.setVisible(not none)
        kinds = {type(i) for i in items}
        self.g_text.setVisible(bool(items) and kinds <= {TextItem})
        self.g_pic.setVisible(bool(items) and kinds <= {ImageItem})
        self.g_shape.setVisible(bool(items) and kinds <= {ShapeItem})
        self.g_table.setVisible(len(items) == 1 and kinds == {TableItem})
        self.g_wa.setVisible(len(items) == 1 and kinds == {WordArtItem})
        if none:
            self.title.setText("Page")
            self.hint.setText("Nothing is selected. Click an object on the page to change it, "
                              "or use the Insert tab to add something new.")
            if sc is not None:
                self.lbl_size.setText(describe_size(sc.page_w, sc.page_h, self._units()))
                self.btn_bg.set_color(sc.background)
            return
        it = items[0]
        self.title.setText(it.display_name() if len(items) == 1 else f"{len(items)} objects")
        self.hint.setText("Locked: unlock to move or resize." if it.locked else "")
        self.hint.setVisible(it.locked)
        single = len(items) == 1
        for w in (self.sp_x, self.sp_y, self.sp_w, self.sp_h, self.sp_rot):
            w.setEnabled(single and not it.locked)
        g = it.geometry()
        self.sp_x.set_pt(g.x)
        self.sp_y.set_pt(g.y)
        self.sp_w.set_pt(g.w)
        self.sp_h.set_pt(g.h)
        self.sp_rot.blockSignals(True)
        self.sp_rot.setValue(g.rot)
        self.sp_rot.blockSignals(False)
        self.cb_aspect.setChecked(it.KEEP_ASPECT)
        self.cb_lock.blockSignals(True)
        self.cb_lock.setChecked(it.locked)
        self.cb_lock.blockSignals(False)
        self.btn_fill.set_color(it.fill)
        self.btn_line.set_color(it.stroke if it.stroke_width > 0 else QColor(0, 0, 0, 0))
        self._quiet(self.sp_lw, lambda: self.sp_lw.setValue(it.stroke_width))
        _set_combo(self.cmb_ls, it.stroke_style)
        op = round((1 - it.opacity()) * 100)
        self._quiet(self.sl_op, lambda: self.sl_op.setValue(op))
        self.lbl_op.setText(f"{op}%")
        _set_combo(self.cmb_wrap, getattr(it, "wrap", "none"))
        self.cmb_wrap.setEnabled(it.KIND != "group")
        if isinstance(it, TextItem):
            _set_combo(self.cmb_fit, it.fit)
            self.cmb_fit.setEnabled(not it.is_linked())
            self.cmb_fit.setToolTip("Linked boxes flow text from one to the next instead of "
                                    "fitting it." if it.is_linked() else "")
            _set_combo(self.cmb_valign, it.valign)
            self.sp_pad.set_pt(it.padding)
        if isinstance(it, ImageItem):
            _set_combo(self.cmb_imgfit, it.fit_mode)
            self._quiet(self.sl_cx, lambda: self.sl_cx.setValue(round(it.crop_x * 100)))
            self._quiet(self.sl_cy, lambda: self.sl_cy.setValue(round(it.crop_y * 100)))
            self.sl_cx.setEnabled(it.fit_mode == "fill")
            self.sl_cy.setEnabled(it.fit_mode == "fill")
            self.sp_corner.set_pt(it.corner)
        if isinstance(it, ShapeItem):
            _set_combo(self.cmb_shape, it.shape_kind)
            self.sp_radius.set_pt(it.radius)
            self.sp_radius.setEnabled(it.shape_kind == "rounded")
        if isinstance(it, WordArtItem):
            _set_combo(self.cmb_warp, it.warp)

    @staticmethod
    def _quiet(w, fn):
        w.blockSignals(True)
        fn()
        w.blockSignals(False)

    # ── changes ──────────────────────────────────────────────────────────────
    def _targets(self, key: str, only=None) -> List[BaseItem]:
        out = []
        for it in self.items:
            if it.scene() is None or (only is not None and not isinstance(it, only)):
                continue
            if key in ("geometry", "opacity", "locked") or hasattr(it, key):
                out.append(it)
        return out

    def _prop(self, key: str, value: Any, merge: bool = False, text: str = "Change", only=None):
        if self._building or self.scene is None:
            return
        targets = self._targets(key, only)
        if key not in ("locked",):
            targets = [t for t in targets if not t.locked or key in ("fill", "stroke")]
        if not targets:
            return
        if all(t.get_prop(key) == value for t in targets):
            return
        self.scene.push(PropCmd(self.scene, targets, key, value, text=text, merge=merge))
        if key == "opacity":
            self.lbl_op.setText(f"{round((1 - value) * 100)}%")
        if key in ("fit_mode", "shape_kind"):
            self.refresh()

    def _line_color(self, c: QColor):
        if self.scene is None:
            return
        targets = self._targets("stroke")
        if not targets:
            return
        doc = self.scene.doc
        doc.undo_stack.beginMacro("Line colour")
        self.scene.push(PropCmd(self.scene, targets, "stroke", c, text="Line colour"))
        if c.alpha() and any(t.stroke_width <= 0 for t in targets):
            self.scene.push(PropCmd(self.scene, [t for t in targets if t.stroke_width <= 0],
                                    "stroke_width", 1.0, text="Line width"))
        doc.undo_stack.endMacro()
        self.refresh()

    def _geo_changed(self):
        if self._building or len(self.items) != 1 or self.scene is None:
            return
        it = self.items[0]
        old = it.geometry()
        w, h = self.sp_w.pt(), self.sp_h.pt()
        if self.cb_aspect.isChecked() and old.w > 0 and old.h > 0:
            if abs(w - old.w) > 1e-6:
                h = w * old.h / old.w
            elif abs(h - old.h) > 1e-6:
                w = h * old.w / old.h
        # keep the centre fixed when the size changes (matches rotation pivot)
        cx = self.sp_x.pt() + old.w / 2
        cy = self.sp_y.pt() + old.h / 2
        new = Geo(cx - w / 2, cy - h / 2, w, h, normalize_angle(self.sp_rot.value()))
        if abs(w - old.w) < 1e-6 and abs(h - old.h) < 1e-6:
            new = Geo(self.sp_x.pt(), self.sp_y.pt(), w, h, new.rot)
        if new.close_to(old, 1e-4):
            return
        self.scene.push(PropCmd(self.scene, [it], "geometry", new, text="Position and size",
                                merge=True))
        self.refresh()

    def _page_bg(self, c: QColor):
        if self.scene is None:
            return
        from ...commands import PageSetupCmd
        sc = self.scene
        old = sc.setup_state()
        new = dict(old)
        new["background"] = c.name(QColor.NameFormat.HexArgb)
        sc.push(PageSetupCmd([sc], [old], [new], "Page background"))
        self.refresh()

    def _warp(self, _):
        if self._building or self.scene is None or len(self.items) != 1:
            return
        it = self.items[0]
        if not isinstance(it, WordArtItem):
            return
        st = it.wordart_state()
        st["warp"] = self.cmb_warp.currentData()
        self.scene.push(PropCmd(self.scene, [it], "wordart", st, text="WordArt shape"))

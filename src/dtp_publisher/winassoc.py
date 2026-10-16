# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Windows 10/11 file associations: double-click a .dtpub or .pub to open it here.

Everything is written for the current user only (``HKEY_CURRENT_USER``), so no
administrator rights are needed and other accounts are not affected:

* a ProgID per file type (``DTPPublisher.Document``, ``DTPPublisher.PubFile``)
  with its icon and open command;
* the extension's default set to that ProgID - the program it replaced in
  ``HKCU`` is remembered and put back on removal - and the ProgID added to
  the extension's *Open with* list;
* a ``Capabilities`` entry under ``RegisteredApplications``, which is what
  makes "DTP Publisher Pro" appear in Settings ▸ Apps ▸ Default apps.

Windows 10 and 11 deliberately don't let a program make itself the default
when the user has already picked one for that extension (the *UserChoice*,
protected by a hash).  ``status`` reports that case, and
``open_default_apps_settings`` takes the user to the page where they confirm
it with one click.  The program never writes ``UserChoice``.

If the program folder is moved, ``repair`` (run at start-up) points the
command and icon at the new place - but only for types the user registered.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from . import APP_NAME

CLASSES = r"Software\Classes"
APP_KEY = r"Software\DTP Publisher"
CAPABILITIES = APP_KEY + r"\Capabilities"
REGISTERED_APPS = r"Software\RegisteredApplications"
FILE_EXTS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
PREVIOUS = "PreviousDefault"            # value name prefix, in APP_KEY + "\Associations"
ASSOC_KEY = APP_KEY + r"\Associations"

TYPES: Dict[str, Dict[str, str]] = {
    ".dtpub": {"progid": "DTPPublisher.Document",
               "label": "DTP Publisher publication",
               "choice": "DTP Publisher publications (.dtpub)"},
    ".pub": {"progid": "DTPPublisher.PubFile",
             "label": "Microsoft Publisher file",
             "choice": "Microsoft Publisher files (.pub)"},
}


# ── registry access (a tiny interface, so tests can use a fake) ─────────────
class Registry:
    """HKEY_CURRENT_USER through ``winreg``.  Values are strings; ``None``
    means absent.  The name ``""`` is a key's default value.  ``base`` puts
    every key under a sandbox key (used by the Windows-only test)."""

    def __init__(self, base: str = ""):
        import winreg
        self._w = winreg
        self.base = base.strip("\\")

    def _k(self, key: str) -> str:
        key = key.strip("\\")
        if not self.base:
            return key
        return f"{self.base}\\{key}" if key else self.base

    def get(self, key: str, name: str = "") -> Optional[str]:
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self._k(key)) as k:
                v, _ = w.QueryValueEx(k, name)
        except OSError:
            return None
        return v if isinstance(v, str) else ("" if v is None else str(v))

    def has_key(self, key: str) -> bool:
        w = self._w
        try:
            w.OpenKey(w.HKEY_CURRENT_USER, self._k(key)).Close()
            return True
        except OSError:
            return False

    def set(self, key: str, name: str, value: str):
        w = self._w
        with w.CreateKeyEx(w.HKEY_CURRENT_USER, self._k(key), 0, w.KEY_WRITE) as k:
            w.SetValueEx(k, name, 0, w.REG_SZ, value)

    def delete_value(self, key: str, name: str):
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self._k(key), 0, w.KEY_WRITE) as k:
                w.DeleteValue(k, name)
        except OSError:
            pass

    def delete_tree(self, key: str):
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self._k(key), 0, w.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        sub = w.EnumKey(k, 0)
                    except OSError:
                        break
                    self.delete_tree(key + "\\" + sub)
                    if self.has_key(key + "\\" + sub):
                        return                      # Windows refused: don't loop for ever
            w.DeleteKey(w.HKEY_CURRENT_USER, self._k(key))
        except OSError:
            pass

    def is_empty(self, key: str) -> bool:
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self._k(key)) as k:
                n_sub, n_val, _ = w.QueryInfoKey(k)
                return n_sub == 0 and n_val == 0
        except OSError:
            return False


def supported() -> bool:
    return sys.platform == "win32"


_default_registry = Registry           # the tests replace this with a fake


def _registry(reg: Optional[Registry]) -> Registry:
    return reg if reg is not None else _default_registry()


# ── what to run ─────────────────────────────────────────────────────────────
def launcher() -> List[str]:
    """The program to start for a double-clicked file (without the file)."""
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable)]          # DTP Publisher.exe
    exe = os.path.abspath(sys.executable)
    windowed = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(windowed):
        exe = windowed                                      # no console window
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run = os.path.join(root, "run.py")
    if os.path.isfile(run):
        return [exe, run]
    return [exe, "-m", "dtp_publisher"]


def command_line(parts: Optional[List[str]] = None) -> str:
    parts = launcher() if parts is None else parts
    return " ".join(f'"{p}"' if not p.startswith("-") else p for p in parts) + ' "%1"'


def icon_location(parts: Optional[List[str]] = None) -> str:
    parts = launcher() if parts is None else parts
    if getattr(sys, "frozen", False):
        return f'"{parts[0]}",0'
    from .settings import config_dir
    ico = os.path.join(config_dir(), "app.ico")
    if os.path.isfile(ico) or _write_icon(ico):
        return f'"{ico}"'
    return f'"{parts[0]}",0'


def _write_icon(path: str) -> bool:
    try:
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is None:
            return False
        from .ui.icons import icon
        return icon("wordart", 256).pixmap(256, 256).save(path, "ICO")
    except Exception:                       # no ICO writer: fall back to the exe icon
        return False


# ── state ───────────────────────────────────────────────────────────────────
@dataclass
class Status:
    ext: str
    registered: bool            # our ProgID is set up for this extension
    default: bool               # ... and Windows will use it on double-click
    other_choice: str = ""      # the program the user picked earlier, if not us
    stale: bool = False         # set up for a program that is no longer there

    @property
    def needs_confirming(self) -> bool:
        return self.registered and not self.default


def status(ext: str, reg: Optional[Registry] = None) -> Status:
    r = _registry(reg)
    progid = TYPES[ext]["progid"]
    cmd_key = f"{CLASSES}\\{progid}\\shell\\open\\command"
    have = r.get(cmd_key)
    registered = have is not None and r.get(f"{CLASSES}\\{ext}\\OpenWithProgids", progid) \
        is not None
    if not registered:
        return Status(ext, False, False)
    stale = not os.path.isfile(_program_in(have))
    choice = r.get(f"{FILE_EXTS}\\{ext}\\UserChoice", "ProgId")
    if choice and choice != progid:
        return Status(ext, True, False, other_choice=choice, stale=stale)
    is_default = choice == progid or r.get(f"{CLASSES}\\{ext}") == progid
    return Status(ext, True, is_default, stale=stale)


def registered_types(reg: Optional[Registry] = None) -> List[str]:
    return [e for e in TYPES if status(e, reg).registered]


def _program_in(command: str) -> str:
    """The program a registered command starts (its first, quoted, part)."""
    command = command.strip()
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    return command.split(" ", 1)[0]


# ── changes ─────────────────────────────────────────────────────────────────
def register(exts: Iterable[str], reg: Optional[Registry] = None,
             parts: Optional[List[str]] = None) -> List[Status]:
    r = _registry(reg)
    exts = list(exts)
    parts = launcher() if parts is None else parts
    cmd, ico = command_line(parts), icon_location(parts)
    out = []
    for ext in exts:
        t = TYPES[ext]
        progid, base = t["progid"], f"{CLASSES}\\{t['progid']}"
        r.set(base, "", t["label"])
        r.set(base, "FriendlyTypeName", t["label"])
        r.set(base + r"\DefaultIcon", "", ico)
        r.set(base + r"\shell", "", "open")
        r.set(base + r"\shell\open", "FriendlyAppName", APP_NAME)
        r.set(base + r"\shell\open\command", "", cmd)
        key = f"{CLASSES}\\{ext}"
        cur = r.get(key)
        if cur != progid:
            # remember what this user had, to put back on removal
            r.set(ASSOC_KEY, PREVIOUS + ext, cur if cur is not None else "")
            r.set(key, "", progid)
        r.set(key + r"\OpenWithProgids", progid, "")
        r.set(CAPABILITIES + r"\FileAssociations", ext, progid)
    if exts:
        r.set(CAPABILITIES, "ApplicationName", APP_NAME)
        r.set(CAPABILITIES, "ApplicationDescription",
              "Make newsletters, cards, labels, photo albums and posters.")
        r.set(REGISTERED_APPS, APP_NAME, CAPABILITIES)
    _notify(r)
    for ext in exts:
        out.append(status(ext, r))
    return out


def unregister(exts: Iterable[str], reg: Optional[Registry] = None):
    r = _registry(reg)
    exts = list(exts)
    for ext in exts:
        progid = TYPES[ext]["progid"]
        key = f"{CLASSES}\\{ext}"
        r.delete_value(key + r"\OpenWithProgids", progid)
        if r.get(key) == progid:                        # only undo what we set
            prev = r.get(ASSOC_KEY, PREVIOUS + ext)
            if prev:
                r.set(key, "", prev)
            else:
                r.delete_value(key, "")
        r.delete_value(ASSOC_KEY, PREVIOUS + ext)
        if r.is_empty(key + r"\OpenWithProgids"):
            r.delete_tree(key + r"\OpenWithProgids")
        if r.is_empty(key):
            r.delete_tree(key)
        r.delete_tree(f"{CLASSES}\\{progid}")
        r.delete_value(CAPABILITIES + r"\FileAssociations", ext)
    if not any(r.get(CAPABILITIES + r"\FileAssociations", e) for e in TYPES):
        r.delete_value(REGISTERED_APPS, APP_NAME)
        r.delete_tree(APP_KEY)
    _notify(r)


def apply(wanted: Iterable[str], reg: Optional[Registry] = None) -> List[Status]:
    """Make the registered types exactly ``wanted``; returns their status."""
    r = _registry(reg)
    wanted = [e for e in TYPES if e in set(wanted)]
    gone = [e for e in registered_types(r) if e not in wanted]
    if gone:
        unregister(gone, r)
    return register(wanted, r) if wanted else []


def repair(reg: Optional[Registry] = None) -> List[str]:
    """Point registered types at this copy of the program if the one they
    name is no longer there (the folder was moved or deleted).  A different
    copy that still exists is left alone: the user chose it."""
    if reg is None and not supported():
        return []
    r = _registry(reg)
    moved = [e for e in TYPES if status(e, r).stale]
    if moved:
        register(moved, r)
    return moved


def _notify(r):
    if not supported() or type(r) is not Registry or r.base:
        return                              # a fake or sandbox: nothing to tell Explorer
    try:
        import ctypes
        SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def default_apps_uri() -> str:
    """Settings ▸ Default apps; on Windows 11 straight to this program's page."""
    from urllib.parse import quote
    build = sys.getwindowsversion().build if supported() else 0
    if build >= 22000:
        return "ms-settings:defaultapps?registeredAppUser=" + quote(APP_NAME, safe="")
    return "ms-settings:defaultapps"


def open_default_apps_settings():
    os.startfile(default_apps_uri())       # noqa: S606 - a fixed settings URI

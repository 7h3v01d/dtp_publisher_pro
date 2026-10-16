# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""User preferences, stored as JSON in the per-user config folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional

UI_SCALES = [1.0, 1.25, 1.5, 1.75, 2.0]


def config_dir() -> str:
    override = os.environ.get("DTP_PUBLISHER_HOME")
    if override:
        base = override
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DTP Publisher")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME") or
                            os.path.join(os.path.expanduser("~"), ".config"), "dtp-publisher")
    os.makedirs(base, exist_ok=True)
    return base


def autosave_dir() -> str:
    d = os.path.join(config_dir(), "autosave")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Settings:
    theme: str = "light"
    ui_scale: float = 1.25
    units: str = "mm"
    autosave_minutes: int = 3
    keep_backup: bool = True
    show_start: bool = True
    show_splash: bool = True
    default_font: str = "Calibri"
    default_size: float = 14.0
    recent: List[str] = field(default_factory=list)
    last_folder: str = ""
    window_geometry: str = ""

    MAX_RECENT = 12

    @classmethod
    def path(cls) -> str:
        return os.path.join(config_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            with open(cls.path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return s
        if not isinstance(data, dict):
            return s
        for fl in fields(cls):
            if fl.name in data:
                v = data[fl.name]
                cur = getattr(s, fl.name)
                if isinstance(cur, bool):
                    v = bool(v)
                elif isinstance(cur, (int, float)) and not isinstance(cur, bool):
                    try:
                        v = type(cur)(v)
                    except (TypeError, ValueError):
                        continue
                elif isinstance(cur, list):
                    v = [str(x) for x in v] if isinstance(v, list) else cur
                elif isinstance(cur, str):
                    v = str(v)
                setattr(s, fl.name, v)
        s.sanitize()
        return s

    def sanitize(self):
        from .theme import THEMES
        from .units import UNITS
        if self.theme not in THEMES:
            self.theme = "light"
        if self.units not in UNITS:
            self.units = "mm"
        self.ui_scale = min(UI_SCALES, key=lambda x: abs(x - self.ui_scale))
        self.autosave_minutes = max(0, min(int(self.autosave_minutes), 60))
        self.default_size = min(max(self.default_size, 6.0), 96.0)
        self.recent = self.recent[: self.MAX_RECENT]

    def save(self) -> None:
        from .serialize import write_atomic
        data = {k: v for k, v in asdict(self).items()}
        try:
            write_atomic(self.path(), json.dumps(data, indent=2).encode("utf-8"), keep_backup=False)
        except OSError:
            pass

    def add_recent(self, path: str):
        p = os.path.abspath(path)
        self.recent = [r for r in self.recent if os.path.normcase(r) != os.path.normcase(p)]
        self.recent.insert(0, p)
        self.recent = self.recent[: self.MAX_RECENT]

    def existing_recent(self) -> List[str]:
        return [r for r in self.recent if os.path.isfile(r)]


_settings: Optional[Settings] = None


def get() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def set_current(s: Settings) -> None:
    global _settings
    _settings = s

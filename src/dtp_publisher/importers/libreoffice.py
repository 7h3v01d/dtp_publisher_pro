# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Find LibreOffice and run a headless conversion.

* A private LibreOffice profile is used, so the conversion works even while
  the user has LibreOffice open, and never touches their own settings.
* The source is copied to a temp folder under a plain ASCII name first
  (LibreOffice on Windows dislikes some characters in paths).
* The process can be cancelled and is killed after a timeout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, List, Optional

from .. import limits
from .. import settings as settings_mod


class ConversionError(Exception):
    pass


def _windows_candidates() -> List[str]:
    out: List[str] = []
    try:
        import winreg  # type: ignore
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\LibreOffice\UNO\InstallPath",
                        r"SOFTWARE\WOW6432Node\LibreOffice\UNO\InstallPath"):
                try:
                    with winreg.OpenKey(root, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        out.append(os.path.join(val, "soffice.exe"))
                except OSError:
                    pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")):
        if base:
            out.append(os.path.join(base, "LibreOffice", "program", "soffice.exe"))
    return out


def find_soffice() -> Optional[str]:
    override = os.environ.get("DTP_SOFFICE")
    if override and os.path.isfile(override):
        return override
    cands: List[str] = []
    if os.name == "nt":
        cands += _windows_candidates()
    elif sys.platform == "darwin":
        cands.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    for name in ("soffice", "soffice.exe", "libreoffice"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def dir_size(path: str, stop_at: Optional[int] = None) -> int:
    """Bytes in a folder tree (stops counting once past ``stop_at``)."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
            if stop_at is not None and total > stop_at:
                return total
    return total


def _copy_capped(src: str, dst: str, cap: int) -> None:
    """Copy at most ``cap`` bytes (the file may grow after its size was checked)."""
    done = 0
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            chunk = fi.read(1 << 20)
            if not chunk:
                return
            done += len(chunk)
            if done > cap:
                raise ConversionError("The file is too large to open.")
            fo.write(chunk)


def profile_dir() -> str:
    d = os.path.join(settings_mod.config_dir(), "lo-profile")
    os.makedirs(d, exist_ok=True)
    return d


def convert(src: str, fmt: str = "odg", timeout: float = 900.0,
            cancelled: Callable[[], bool] = lambda: False,
            soffice: Optional[str] = None) -> str:
    """Convert ``src`` and return the path of the output file (in a temp folder
    that the caller owns and should delete with ``shutil.rmtree``)."""
    exe = soffice or find_soffice()
    if not exe:
        raise ConversionError("LibreOffice was not found on this computer.")
    try:
        size = os.path.getsize(src)
    except OSError as ex:
        raise ConversionError(f"The file could not be opened:\n{ex}") from ex
    if not os.path.isfile(src):
        raise ConversionError("That is not a file.")
    if size > limits.MAX_PUB_SOURCE_BYTES:
        raise ConversionError(f"The file is {limits.describe_bytes(size)}; Publisher files up "
                              f"to {limits.describe_bytes(limits.MAX_PUB_SOURCE_BYTES)} "
                              "can be opened.")
    work = tempfile.mkdtemp(prefix="dtp-import-")
    try:
        return _convert_in(work, src, fmt, timeout, cancelled, exe)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)      # nothing is left behind on failure
        raise


def _convert_in(work: str, src: str, fmt: str, timeout: float,
                cancelled: Callable[[], bool], exe: str) -> str:
    ext = os.path.splitext(src)[1].lower() or ".pub"
    local = os.path.join(work, "input" + ext)
    _copy_capped(src, local, limits.MAX_PUB_SOURCE_BYTES)
    out_dir = os.path.join(work, "out")
    os.makedirs(out_dir)
    tmp_dir = os.path.join(work, "tmp")              # LibreOffice's own temp files
    os.makedirs(tmp_dir)
    env = dict(os.environ, TMP=tmp_dir, TEMP=tmp_dir, TMPDIR=tmp_dir)
    cmd = [exe, f"-env:UserInstallation={Path(profile_dir()).as_uri()}", "--headless",
           "--invisible", "--norestore", "--nologo", "--nodefault", "--nolockcheck",
           "--convert-to", fmt, "--outdir", out_dir, local]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    expected = os.path.join(out_dir, "input." + fmt.split(":")[0])
    last_err = ""
    for attempt in range(2):          # the very first run only creates the profile
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=flags, env=env)
        t0 = time.monotonic()
        next_size_check = t0 + 2.0
        while proc.poll() is None:
            if time.monotonic() >= next_size_check:      # runaway output fills the disk
                next_size_check = time.monotonic() + 2.0
                if dir_size(work, limits.MAX_CONVERT_DIR_BYTES) > limits.MAX_CONVERT_DIR_BYTES:
                    proc.kill()
                    proc.wait()
                    shutil.rmtree(work, ignore_errors=True)
                    raise ConversionError("The converted publication is too large to open.")
            if cancelled():
                proc.kill()
                proc.wait()
                shutil.rmtree(work, ignore_errors=True)
                raise ConversionError("Cancelled.")
            if time.monotonic() - t0 > timeout:
                proc.kill()
                proc.wait()
                shutil.rmtree(work, ignore_errors=True)
                raise ConversionError("LibreOffice took too long to open the file.")
            time.sleep(0.1)
        out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
        if os.path.isfile(expected) and os.path.getsize(expected) > 0:
            if os.path.getsize(expected) > limits.MAX_CONVERTED_BYTES:
                shutil.rmtree(work, ignore_errors=True)
                raise ConversionError("The converted publication is too large to open.")
            return expected
        last_err = out.strip()[-400:]
    shutil.rmtree(work, ignore_errors=True)
    raise ConversionError("LibreOffice could not read this file."
                          + (f"\n\n{last_err}" if last_err else ""))

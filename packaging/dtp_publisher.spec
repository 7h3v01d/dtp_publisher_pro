# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
# PyInstaller recipe: a self-contained folder with "DTP Publisher.exe" in it.
# Build with build_exe.bat (or: pyinstaller packaging/dtp_publisher.spec).
import os

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(HERE)
ico = os.path.join(HERE, "app.ico")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[(os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "NOTICE"), "."),
           (os.path.join(ROOT, "README.md"), ".")],
    hiddenimports=["PyQt6.QtPrintSupport"],
    excludes=["tkinter", "pytest", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtMultimedia", "PyQt6.QtNetwork",
              "PyQt6.QtSql", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DTP Publisher",
    console=False,
    icon=ico if os.path.exists(ico) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DTP Publisher")

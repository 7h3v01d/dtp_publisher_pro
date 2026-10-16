# SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
# PyInstaller recipe.
#   build_exe.bat      -> dist\DTP Publisher\  a folder with "DTP Publisher.exe" in it
#                         (starts fastest)
#   build_onefile.bat  -> dist-single\DTP Publisher.exe  one file (DTP_ONEFILE=1);
#                         it unpacks itself to a temporary folder each time it
#                         starts, so it starts a few seconds slower.
import os

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(HERE)
ico = os.path.join(HERE, "app.ico")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[(os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "NOTICE"), "."),
           (os.path.join(ROOT, "README.md"), "."),
           # the user manual opened by Help > User Manual (F1), with its pictures
           (os.path.join(ROOT, "src", "dtp_publisher", "help"), "dtp_publisher/help"),
           # the welcome picture shown while the program starts
           (os.path.join(ROOT, "src", "dtp_publisher", "art"), "dtp_publisher/art")],
    hiddenimports=["PyQt6.QtPrintSupport"],
    excludes=["tkinter", "pytest", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtMultimedia", "PyQt6.QtNetwork",
              "PyQt6.QtSql", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = ico if os.path.exists(ico) else None

if os.environ.get("DTP_ONEFILE") == "1":
    # The welcome picture during unpacking, before Python starts (the program
    # closes it when its own picture appears).  PyInstaller draws it with
    # Tcl/Tk, which the python.org Windows Python has; without it, no picture.
    boot = []
    try:
        import _tkinter  # noqa: F401
        splash = Splash(os.path.join(HERE, "boot_splash.png"), binaries=a.binaries,
                        datas=a.datas, text_pos=None, always_on_top=True)
        boot = [splash, splash.binaries]
    except Exception as ex:                       # noqa: BLE001 - optional nicety
        print(f"(no start-up picture while unpacking: {ex})")
    exe = EXE(
        pyz, a.scripts, *boot, a.binaries, a.datas, [],
        name="DTP Publisher",
        console=False,
        icon=icon,
        upx=False,                                # UPX-packed files upset virus checkers
        runtime_tmpdir=None,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="DTP Publisher",
        console=False,
        icon=icon,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="DTP Publisher")

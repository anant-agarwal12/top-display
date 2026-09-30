# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec. Build with:  pyinstaller packaging/top_display.spec --noconfirm
# One-folder, windowed build: starts faster than one-file, is less likely to
# trip antivirus, and keeps the Qt DLLs as separate files (PySide6 is LGPL).
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "src" / "app.py")],
    pathex=[str(root), str(root / "src")],
    hiddenimports=[
        # imported inside functions in app.py
        "main", "launcher", "single_instance",
        # WinRT bindings used by media_session.py
        "winsdk.windows.media.control",
        "winsdk.windows.foundation",
        "winsdk.windows.foundation.collections",
        "winsdk.windows.storage.streams",
    ],
    excludes=["tkinter", "unittest", "test", "pydoc"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TopDisplay",
    console=False,
    icon=str(root / "packaging" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="TopDisplay",
)

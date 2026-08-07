# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TE Measurement (one-folder, windowed).

Build:  pyinstaller TE-Measurement.spec --noconfirm
Output: dist/TE-Measurement/TE-Measurement.exe  (+ dependency folder)

Notes
-----
* One-FOLDER (not one-file): the app spawns an IR-camera subprocess via
  multiprocessing 'spawn', which relaunches the same .exe. One-file would
  re-extract the whole bundle to %TEMP% on every spawn — slow and fragile.
  One-folder launches instantly and spawns cleanly. main.py already calls
  multiprocessing.freeze_support().
* pyOptris is imported lazily inside the worker → declared as a hidden import.
* The Optris SDK DLLs (C:\\IrDirectSDK, C:\\Program Files\\Optris) and NI-VISA
  are SYSTEM installs resolved at runtime by absolute path / GPIB — they are
  intentionally NOT bundled (installer README lists them as prerequisites).
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("app")          # all app.* modules (some imported lazily)
hiddenimports += collect_submodules("sqlalchemy")   # dialects/drivers
hiddenimports += ["pyOptris", "bcrypt", "pyvisa", "openpyxl", "PIL", "pyqtgraph", "numpy"]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "PyQt5", "PySide6", "PySide2", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TE-Measurement",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # GUI app — no console window
    disable_windowed_traceback=False,
    icon="installer/app.ico",
    version="installer/version_info.txt",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TE-Measurement",
)

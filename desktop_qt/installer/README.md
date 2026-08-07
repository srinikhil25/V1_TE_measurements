# Building the TE Measurement installer

Produces a Windows `setup.exe` (Start-Menu shortcut, Program Files install,
uninstaller) from the PyQt6 app.

## One-time prerequisite

Install **Inno Setup 6** (free): https://jrsoftware.org/isdl.php
PyInstaller is already in the project venv — no separate install needed.

## Build (one command)

From the project root (`desktop_qt/`):

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1
```

This:
1. regenerates the app icon,
2. freezes the app with PyInstaller → `dist\TE-Measurement\`,
3. compiles the installer → `installer\Output\TE-Measurement-Setup-1.0.0.exe`.

If Inno Setup isn't installed, step 3 is skipped with a message; install it and
re-run with `-SkipBuild` to compile the installer without re-freezing:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -SkipBuild
```

## Files

| File | Purpose |
|------|---------|
| `../TE-Measurement.spec` | PyInstaller config (one-folder, windowed, hidden imports) |
| `make_icon.py`           | Generates `app.ico` (thermoelectric motif) |
| `version_info.txt`       | Windows file-properties resource embedded in the .exe |
| `TE-Measurement.iss`     | Inno Setup script |
| `PREREQUISITES.txt`      | Shipped in the install dir — NI-VISA / Optris SDK notes |
| `build_installer.ps1`    | Runs the whole build |

## What is NOT bundled (system prerequisites on the measurement PC)

- **NI-VISA** + GPIB driver — required for the Keithley/Matsusada instruments.
- **Optris IR camera SDK** (OTC 10.x or legacy IrDirectSDK) — only if using the
  thermal camera; resolved at runtime by absolute path.

See `PREREQUISITES.txt` for details. The app runs without these; only the
corresponding hardware features are unavailable.

## Versioning

To release a new version, update the version in three places:
- `TE-Measurement.iss`  → `#define AppVersion`
- `version_info.txt`    → `filevers` / `FileVersion` / `ProductVersion`
- `main.py`             → `app.setApplicationVersion(...)`

Keep the `AppId` GUID in the `.iss` unchanged so upgrades replace cleanly.

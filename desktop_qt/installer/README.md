# TE Measurement — Packaging & Installation Guide

This folder turns the PyQt6 app into something you can hand to the lab:

- a **`setup.exe`** installer (Start-Menu shortcut, Program Files install, uninstaller), and/or
- a **portable ZIP** (unzip and run — no install).

There are two audiences below. **Part A** is for whoever *builds* the package
(the developer). **Part B** is for whoever *installs and runs* it (the lab PC).

---

## Part A — Building the package (developer)

### A0. Prerequisites (one time)

| Need | How |
|------|-----|
| Python venv with deps | already set up in `desktop_qt\venv\` (`pip install -r requirements.txt`) |
| PyInstaller | already in the venv (`pyinstaller>=6`) |
| **Inno Setup 6** (only for `setup.exe`) | Install from https://jrsoftware.org/isdl.php |

> The portable ZIP needs **only** PyInstaller. Inno Setup is required **only**
> for the `setup.exe`.

### A1. Build the `setup.exe` — the easy way (one command)

From the project root (`desktop_qt\`):

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1
```

This does everything in order:

1. regenerates the app icon,
2. freezes the app with PyInstaller → `dist\TE-Measurement\`,
3. compiles the installer → `installer\Output\TE-Measurement-Setup-1.0.0.exe`.

If Inno Setup isn't installed, steps 1–2 still run (you get the frozen app) and
step 3 is skipped with a message. Install Inno Setup, then finish with:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -SkipBuild
```

`-SkipBuild` reuses the already-frozen `dist\TE-Measurement\`, so it only
recompiles the installer (a few seconds).

**Result:** `installer\Output\TE-Measurement-Setup-1.0.0.exe` — this is the file
you give to the lab.

### A2. Build the portable ZIP (no Inno Setup needed)

If you only want the unzip-and-run version:

```powershell
# 1. Freeze the app
venv\Scripts\python.exe -m PyInstaller TE-Measurement.spec --noconfirm --clean

# 2. Zip the output folder
Compress-Archive -Path dist\TE-Measurement `
  -DestinationPath installer\Output\TE-Measurement-1.0.0-portable.zip -Force
```

**Result:** `installer\Output\TE-Measurement-1.0.0-portable.zip`.

### A3. Do the two steps manually (if you skip the script)

```powershell
# freeze
venv\Scripts\python.exe -m PyInstaller TE-Measurement.spec --noconfirm --clean
# compile installer
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\TE-Measurement.iss
```

### A4. Releasing a new version

Bump the version in **three** places, then rebuild:

| File | Field |
|------|-------|
| `installer\TE-Measurement.iss` | `#define AppVersion` |
| `installer\version_info.txt`   | `filevers`, `FileVersion`, `ProductVersion` |
| `main.py`                      | `app.setApplicationVersion(...)` |

> Keep the `AppId` GUID in `TE-Measurement.iss` **unchanged** so upgrades
> replace the old version cleanly instead of installing side-by-side.

---

## Part B — Installing & running (lab PC)

### Option 1 — Installer (`setup.exe`)

1. Copy `TE-Measurement-Setup-1.0.0.exe` to the PC.
2. Double-click it. If a "Windows protected your PC" SmartScreen prompt appears
   (the exe is unsigned), click **More info → Run anyway**.
3. Approve the admin prompt (it installs to `C:\Program Files\TE Measurement`).
4. **Read the prerequisite popup** — the installer checks for NI-VISA and the
   Optris SDK and tells you what's missing (see step B3 below). Click **OK**;
   installation continues regardless.
5. Finish the wizard. Launch from the **Start Menu → TE Measurement** (or the
   desktop icon if you ticked that box).

To remove it later: **Settings → Apps → TE Measurement → Uninstall** (your data
is kept — see B4).

### Option 2 — Portable ZIP

1. Copy `TE-Measurement-1.0.0-portable.zip` to the PC.
2. Right-click → **Extract All…** to any folder (e.g. Desktop).
3. Open the extracted `TE-Measurement` folder and double-click
   **`TE-Measurement.exe`**.

> Keep the whole folder together — the `.exe` needs the `_internal` folder next
> to it. To move the app, move the entire folder.

### B3. Hardware prerequisites (install these for instrument features)

The app is self-contained (no Python needed), but the **instrument drivers are
separate system installs** and are *not* bundled:

| Prerequisite | Needed for | Get it |
|--------------|-----------|--------|
| **NI-VISA** + GPIB driver | All GPIB instruments: Keithley 2401 / 2182A / 2700, Matsusada P4K-80M. **Without it, nothing connects.** | ni.com — search "NI-VISA download" |
| **Optris IR SDK** (OTC 10.x *or* legacy IrDirectSDK) | The thermal camera only | Optris installer |

The app **runs without them** — only the matching hardware features are
unavailable. On **first login** it checks both and warns you about anything
missing (tick "Don't remind me again" to silence it). Full detail is in
`PREREQUISITES.txt` inside the install folder.

### B4. Your data (survives uninstall & upgrades)

The database and logs live here, created automatically on first run:

```
%APPDATA%\TEMeasurement\
    te_measurement.db     measurements + user accounts
    app.log               diagnostic log
    prereq_ack.json       "don't remind me" state for the prereq warning
```

Uninstalling or deleting the app does **not** touch this folder, so your data
carries across upgrades. Delete it manually for a clean slate.

### B5. Default login accounts

| Username | Password | Role |
|----------|----------|------|
| `superadmin` | `superadmin` | Super Admin |
| `labadmin`   | `labadmin`   | Lab Admin |
| `researcher` | `researcher` | Researcher |

> These are development seed accounts. Change them before any shared/production
> deployment.

---

## Files in this folder

| File | Purpose |
|------|---------|
| `../TE-Measurement.spec` | PyInstaller config (one-folder, windowed, hidden imports) |
| `build_installer.ps1`    | One-command build (freeze → compile installer) |
| `TE-Measurement.iss`     | Inno Setup script (+ install-time prereq check) |
| `make_icon.py`           | Generates `app.ico` (thermoelectric motif) |
| `version_info.txt`       | Windows file-properties resource embedded in the `.exe` |
| `PREREQUISITES.txt`      | Shipped in the install dir — NI-VISA / Optris notes |
| `Output\`                | Build output: `setup.exe` and/or portable ZIP |

## How it works (quick notes for maintainers)

- **One-folder, not one-file.** The app spawns the IR-camera worker with
  `multiprocessing` *spawn*, which relaunches the same `.exe`. One-file would
  re-extract the whole bundle to `%TEMP%` on every spawn; one-folder launches
  instantly. `main.py` calls `multiprocessing.freeze_support()` so spawned
  workers run the worker code instead of opening a second GUI.
- **`pyOptris`** is imported lazily inside the worker, so it's declared as a
  hidden import in the spec.
- **Prereq detection** lives in `app/core/prereqs.py` (runtime, post-login) and
  is mirrored in the Inno Setup `[Code]` block (install-time). Both use the same
  probes: NI-VISA via `System32\visa*.dll` / registry, Optris via the OTC
  bindings dir or the legacy `libirimager.dll`.

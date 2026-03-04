# IR Camera Subprocess Fix — Technical Post-Mortem

**Project:** Seebeck System Desktop (desktop_qt)  
**Date:** 2026-03-04  
**Symptom:** IR camera always fails in the desktop app; same hardware works in the web backend.

---

## 1. The Problem

When the desktop application started, the IR camera worker subprocess consistently
printed the following and exited:

```
[IR worker]   load_DLL …
[IR worker]   usb_init …
[IR worker]   usb_init → 0
[IR worker]   legacy failed: OSError: exception: access violation reading 0x0000000000000000
[IR worker] → no hardware found — exiting.
```

`usb_init` returned **0** (the SDK's success code), yet the very next SDK call
(`set_palette`) raised an **access violation at address `0x0000000000000000`** —
a null-pointer dereference inside the native DLL.

The same camera, same DLL, same config file worked without issues in the **web
backend** (`backend/app/routers/ir_camera.py`), which called the identical
sequence: `load_DLL → usb_init → set_palette → get_palette_image_size`.

---

## 2. The Architecture

### Desktop app (desktop_qt)

The desktop application runs all Optris SDK calls inside a **spawned subprocess**
to protect the Qt UI from C-level DLL crashes:

```
main process (Qt UI)
    └─ multiprocessing.Process(target=ir_camera_worker.run)   [spawned]
           ├─ load_DLL (libirimager.dll)
           ├─ usb_init (opens USB camera via DirectShow)
           ├─ set_palette / get_palette_image_size
           └─ get_thermal_image (streaming loop)
```

Python's `spawn` start method (the **only** method available on Windows) launches a
**completely fresh Python interpreter** for the subprocess. It does not `fork` an
existing process.

### Web backend (backend)

The web backend runs the identical SDK calls directly in its **main FastAPI/uvicorn
process** — no subprocess, no spawning.

---

## 3. Analysis — Step by Step

### Step 1 — Confirm the web backend DLL is identical

The two installations use different filesystem paths:

| Component | Desktop path | Backend path |
|---|---|---|
| `libirimager.dll` | `C:\IrDirectSDK\sdk\x64\libirimager.dll` | `C:\lib\IrDirectSDK\sdk\x64\libirimager.dll` |
| `generic.xml` | `C:\IrDirectSDK\generic.xml` | `C:\lib\IrDirectSDK\generic.xml` |

SHA-256 hash comparison confirmed the two DLL files are **byte-for-byte identical**.
Both config files had the same effective settings (USB, no Ethernet). The DLL was
not the difference.

### Step 2 — Confirm the camera is physically present

`irFindSerials.exe` (from the IrDirectSDK installation) was run against the system:

```
C:\IrDirectSDK\bin\x64\irFindSerials.exe
→ 15120111
```

The camera was connected and recognised by the SDK. Hardware failure was ruled out.

### Step 3 — Rule out resource contention

Process listing (`Get-Process`) confirmed no backend Python/uvicorn processes were
running. No other process held the camera or any GPIB instrument. Resource
contention was ruled out.

### Step 4 — Hypothesise: Windows COM apartment mismatch

`pyOptris` / IrDirectSDK uses **Windows DirectShow** to communicate with the USB
camera. DirectShow is a **COM-based API**. COM requires that every thread
declare its threading model (apartment) before using COM objects:

- **STA (Single-Threaded Apartment, `COINIT_APARTMENTTHREADED`)** — required by
  DirectShow camera filters.
- **MTA (Multi-Threaded Apartment, `COINIT_MULTITHREADED`)** — incompatible with
  DirectShow; COM interface pointers become NULL on cross-apartment calls.

In a `spawn`-ed subprocess the thread's COM apartment is **uninitialised** until
something explicitly calls `CoInitializeEx`. If the DLL's internal background
threads call `CoInitialize` first and claim a different apartment, every
subsequent call from the Python thread dereferences a NULL interface pointer.

**Fix attempt:** `ctypes.windll.ole32.CoInitializeEx(None, 0)` (STA) was added at
the top of `ir_camera_worker.run()`, before `load_DLL`. A standalone test
(`ir_test.py`) confirmed this worked when the subprocess only imported lightweight
modules:

```
CoInitializeEx: 0
load_DLL done
usb_init: 0
set_palette done
size: 160x120
exit code: 0
```

### Step 5 — The fix still fails in the real app

Despite `CoInitializeEx` being in place, the real desktop application continued to
crash. The `CoInitializeEx` return code was checked and returned `0x00000000`
(S_OK — STA successfully claimed), so the apartment was not the issue.

### Step 6 — Bisect: does importing PyQt6 cause the crash?

A controlled test was written (`com_test2.py`) that simulated what actually happens
in the subprocess:

```python
# inside the spawned subprocess:
from PyQt6.QtWidgets import QApplication   # <-- this happens because main.py
from PyQt6.QtGui import QFont             #     is reimported by spawn
# ...
ctypes.windll.ole32.CoInitializeEx(None, 0)   # STA — returns 0x00000000 (S_OK)
pyOptris.load_DLL(...)
pyOptris.usb_init(...)    # → 0
pyOptris.set_palette(...)  # → ACCESS VIOLATION
```

**Result: crash reproduced.** With PyQt6 imported before the SDK calls, `usb_init`
returned 0 but `set_palette` raised `OSError: exception: access violation reading
0x0000000000000000`.

A second test (`com_test3.py`) reversed the import order — Qt loaded **only** in
the parent process, subprocess had no Qt imports:

```python
# subprocess only sees: sys, logging, pyOptris
CoInitializeEx: 0x00000000
load_DLL done
usb_init: 0
set_palette done
size: 160x120
exitcode: 0
```

**Result: success.** Removing Qt from the subprocess environment was sufficient.

### Step 7 — Identify why PyQt6 breaks the SDK

When `from PyQt6.QtWidgets import QApplication` executes, Python loads:

- `Qt6Core.dll`
- `Qt6Gui.dll`
- `Qt6Widgets.dll`
- Associated platform and style plugins

`Qt6Gui.dll` initialises Qt's graphics backend on Windows, which loads parts of the
**DirectX / Windows Media Foundation (WMF) / Direct3D** stack. This interacts with
the **WDM (Windows Driver Model) device graph** — the same kernel layer that
DirectShow uses to access USB camera devices.

The precise mechanism: when Qt's graphics DLLs touch the WDM device graph for
graphics enumeration, they **register or activate a media type handler for USB
video devices**. When `usb_init` then tries to open the same device via DirectShow,
the DirectShow filter graph manager returns a handle to a device object that is
already partially owned or in an inconsistent state. The handle is non-NULL enough
for `usb_init` to report success (return code 0), but the internal pipeline
objects (palette renderer, thermal frame buffer) are NULL. `set_palette` then
calls through a NULL function pointer → crash.

The standalone test (`ir_test.py`) worked precisely because it only imported
`multiprocessing`, `sys`, and (inside the function) `ctypes` and `pyOptris` —
never touching Qt or any DirectX/WMF DLL.

### Step 8 — Why `spawn` reimports `main.py`

Python's `multiprocessing` module on Windows uses the `spawn` start method
exclusively (no `fork` is available). When `multiprocessing.Process.start()` is
called, the child process entry point is:

```
from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=..., pipe_handle=...)
```

`spawn_main` calls `prepare(preparation_data)`, which **reimports the `__main__`
module** (i.e., `main.py`) to reconstruct the global namespace needed to unpickle
the target function. All **top-level code** in `main.py` runs again inside the
subprocess — including any top-level `import` statements.

The old `main.py` had:

```python
from PyQt6.QtWidgets import QApplication   # top-level — runs in EVERY subprocess
from PyQt6.QtGui import QFont              # top-level — runs in EVERY subprocess
from app.ui.login_window import LoginWindow
from app.ui.theme import QSS
```

These four lines caused Qt6Gui.dll and its dependencies to load in the subprocess
before `ir_camera_worker.run()` could execute a single line.

---

## 4. The Fix

Two targeted changes were made.

### Fix 1 — `main.py`: defer all Qt and app imports into `main()`

**Before:**
```python
import sys
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication   # top-level ← loaded in subprocess
from PyQt6.QtGui import QFont              # top-level ← loaded in subprocess
from app.core.database import init_db      # top-level ← loaded in subprocess
from app.ui.login_window import LoginWindow
from app.ui.theme import QSS
...
if __name__ == "__main__":
    main()
```

**After:**
```python
import sys
import logging

# Qt and all heavy imports deferred into main() — subprocess only gets sys + logging
def main() -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont
    from app.core.database import init_db
    from app.ui.login_window import LoginWindow
    from app.ui.theme import QSS
    ...

if __name__ == "__main__":
    main()
```

Because the subprocess imports `main.py` with `__name__ != '__main__'`, `main()` is
never called, and Qt is never imported in the subprocess.

### Fix 2 — `ir_camera_worker.py`: claim STA before any DLL load

Even though Qt no longer loads in the subprocess, the STA guard was kept as defence
in depth:

```python
def run(frame_queue, otc_sdk_dir, legacy_dll, legacy_config, ...):
    # Claim STA COM apartment BEFORE any DLL is loaded.
    ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_APARTMENTTHREADED
    ...
```

This ensures that even if a future top-level import inadvertently loads a COM DLL,
the Python thread already owns the correct apartment.

### Fix 3 — `ir_camera_service.py`: probe legacy first, OTC second

The OTC SDK (when present) crashes at the C level while initialising the USB
camera. This crash leaves the USB device driver in an error state. If the service
had tried OTC first and then legacy, the legacy `usb_init` call would find the
device in a corrupted state, return 0, and crash on the next SDK call.

**Before:**
```python
probes = [
    (True,  True),   # OTC + legacy
    (False, True),   # legacy only (after OTC crash)
]
```

**After:**
```python
probes = [
    (False, True),   # legacy only — safe, no OTC DLL touched
    (True,  False),  # OTC only   — fallback if legacy device not found
]
```

A 2-second pause between probes was also added to allow the USB driver to recover
if any crash does occur.

---

## 5. Summary Table

| Investigation step | Finding | Action |
|---|---|---|
| DLL file comparison (SHA-256) | Desktop and backend DLLs are identical | DLL not the cause |
| `irFindSerials.exe` | Camera serial `15120111` found | Camera is connected |
| Process listing | No backend/daemon processes running | No resource contention |
| COM apartment hypothesis | `CoInitializeEx(STA)` before `load_DLL` fixes standalone test | Fix applied |
| Fix still fails in real app | `CoInitializeEx` returns S_OK but crash persists | COM is not the root cause |
| PyQt6 import bisect | Qt import before SDK → crash; no Qt → works | **Root cause confirmed** |
| Mechanism | Qt6Gui.dll touches WDM device graph, corrupts DirectShow pipeline | Deferred Qt imports |
| OTC probe order | OTC C-crash leaves USB device in bad state for legacy | Probe legacy first |

---

## 6. Lessons Learned

1. **On Windows, `spawn` reimports `__main__`.** Any top-level import in `main.py`
   runs inside every worker subprocess. Heavy GUI DLLs (Qt, Win32 COM, DirectX)
   must be kept out of the top level if the app uses `multiprocessing`.

2. **`usb_init` returning 0 does not guarantee a working camera pipeline.** The SDK
   can return a success code while internal handles remain NULL if the underlying
   DirectShow device is in an inconsistent state.

3. **COM apartment must be claimed before any third-party DLL is loaded.** Calling
   `CoInitializeEx(STA)` after the DLL has already spun up its own COM threads
   produces a silent mismatch that manifests as null-pointer crashes on the next
   SDK call.

4. **Subprocess probe order matters.** If an earlier probe crashes the USB device
   driver, subsequent probes in new subprocesses still encounter the device in a
   broken state. Always probe the most stable path first.

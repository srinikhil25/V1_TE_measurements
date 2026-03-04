"""IR camera worker — spawned subprocess.

ALL Optris SDK calls live here, isolated inside a spawned subprocess.
A C-level crash (abort / access violation) from any Optris DLL kills only
this subprocess — the Qt application is never affected.

Entry point
-----------
run(frame_queue, otc_sdk_dir, legacy_dll, legacy_config,
    try_otc=True, try_legacy=True)

Backends tried in order:
  1. OTC SDK 10.x   — import optris.otcsdk
  2. Legacy SDK      — pyOptris / IrDirectSDK via usb_init (DirectShow)

Each backend pushes ``(name: str, frame: np.ndarray[float32, °C])`` tuples
into frame_queue until the subprocess is terminated by the parent.
If no hardware is found the subprocess exits cleanly (exitcode 0).

IMPORTANT — COM apartment on Windows
--------------------------------------
pyOptris / IrDirectSDK uses DirectShow (COM) internally.  In a spawned
subprocess the COM apartment is uninitialised until explicitly set.  If the
DLL is allowed to call CoInitialize on its own internal threads first, a
COM apartment mismatch is created and every subsequent SDK call from the
Python thread dereferences a null interface pointer (access violation).

Fix: call CoInitializeEx(NULL, COINIT_APARTMENTTHREADED) on the subprocess
main thread BEFORE loading the DLL.  This claims the thread for STA and
prevents the mismatch.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

import numpy as np


def _log(msg: str) -> None:
    print(f"[IR worker] {msg}", file=sys.stderr, flush=True)


def _push(q, backend: str, frame: np.ndarray) -> None:
    """Non-blocking put — silently drop the frame if the queue is full."""
    try:
        q.put_nowait((backend, frame))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# OTC SDK 10.x
# ─────────────────────────────────────────────────────────────────────────────

def _run_otc(q, otc_sdk_dir: str) -> None:
    """Connect via Optris OTC SDK 10.x and stream frames.

    The SDK Python bindings live under <sdk_root>/bindings/python3/.
    OTC_SDK_DIR must point at <sdk_root> so the bindings can find the
    native DLLs under <sdk_root>/bin/.  The Optris installer sets this
    env-var automatically; we honour a user-configured override here.
    """
    bindings = os.path.join(otc_sdk_dir, "bindings", "python3")
    if not os.path.isdir(bindings):
        raise FileNotFoundError(f"OTC bindings not found: {bindings}")

    if bindings not in sys.path:
        sys.path.insert(0, bindings)
    os.environ.setdefault("OTC_SDK_DIR", otc_sdk_dir)

    import optris.otcsdk as otc  # may raise or crash — isolated in this subprocess

    # ── IRImagerClient subclass ──────────────────────────────────────────────
    # Defined after the import so the class can close over `otc` to check the
    # FlagState.  The base class may or may not exist in older binding versions.
    _base = getattr(otc, "IRImagerClient", object)

    class _Client(_base):
        def __init__(self, imager):
            if _base is not object:
                try:
                    super().__init__()
                except Exception:
                    pass
            self._lock    = threading.Lock()
            self._frame   = None
            self._updated = False
            self._running = True
            imager.connect(0)       # serial=0 → first available device
            imager.addClient(self)

        def onThermalFrame(self, thermal, meta):
            # Keep this callback fast — FailSafeWatchdog fires at ~150 ms.
            # Frames during startup calibration have unreliable temperatures;
            # discard them until the flag leaves the Initializing state.
            try:
                if meta.flagState == otc.FlagState_Initializing:
                    return
            except Exception:
                pass
            with self._lock:
                self._frame   = thermal
                self._updated = True

        def onFlagStateChange(self, _):
            pass

        def onConnectionLost(self):
            self._running = False

        def onConnectionTimeout(self):
            self._running = False

        def pop_frame(self):
            with self._lock:
                if not self._updated or self._frame is None:
                    return None
                try:
                    if self._frame.isEmpty():
                        return None
                except Exception:
                    pass
                self._updated = False
                return self._frame.clone()

    # ── Init ────────────────────────────────────────────────────────────────
    otc.Sdk.init(otc.Verbosity_Warning, otc.Verbosity_Off, "seebeck_ir")
    try:
        otc.EnumerationManager.getInstance().addEthernetDetector("192.168.0.0/24")
    except Exception:
        pass

    imager = otc.IRImagerFactory.getInstance().create("native")
    client = _Client(imager)
    threading.Thread(target=imager.run, daemon=True).start()

    # ── Acquisition loop ─────────────────────────────────────────────────────
    # Exit when the SDK signals connection lost so the parent can detect it.
    while client._running:
        thermal = client.pop_frame()
        if thermal is not None:
            try:
                if not thermal.isEmpty():
                    w, h = thermal.getWidth(), thermal.getHeight()
                    buf  = np.empty(thermal.getSize(), dtype=np.float32)
                    thermal.copyTemperaturesTo(buf)
                    _push(q, "otc", buf.reshape(h, w))
            except Exception:
                pass
        time.sleep(0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy IrDirectSDK / pyOptris
# ─────────────────────────────────────────────────────────────────────────────

def _run_legacy(q, dll_path: str, config_path: str) -> None:
    """Connect via pyOptris / IrDirectSDK (usb_init / DirectShow) and stream thermal frames.

    Init sequence
    -------------
    1. CoInitializeEx(STA) — must run before any DLL load.
       DirectShow is a COM-based API.  In a spawned subprocess the apartment is
       uninitialised; if the DLL calls CoInitialize on its own background
       threads first, a thread-apartment mismatch is created and every SDK call
       from the Python thread raises an access violation.  Claiming STA on the
       main subprocess thread first prevents the mismatch.
    2. Validate paths.
    3. load_DLL — loads libirimager.dll.
    4. usb_init(config) — opens the USB camera via DirectShow.
    5. set_palette + get_palette_image_size → stream with get_thermal_image.

    Temperature decoding (IrDirectSDK docs)::

        °C = raw_uint16 / 10 − 100  ≡  (raw − 1000) / 10
    """
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(f"Legacy DLL not found: {dll_path}")
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Legacy config not found: {config_path}")

    import pyOptris

    _log("  load_DLL …")
    pyOptris.load_DLL(dll_path)

    _log("  usb_init …")
    ret = pyOptris.usb_init(config_path)
    _log(f"  usb_init → {ret}")
    if ret != 0:
        raise RuntimeError(f"usb_init failed (code {ret}) — camera not found or in use")

    pyOptris.set_palette(pyOptris.ColouringPalette.IRON)
    w, h = pyOptris.get_palette_image_size()
    if w == 0 or h == 0:
        raise RuntimeError("get_palette_image_size returned 0 — camera not streaming")
    _log(f"  streaming {w}×{h} …")

    while True:
        try:
            raw = pyOptris.get_thermal_image(w, h)
            _push(q, "legacy", (raw.astype(np.float32) - 1000.0) / 10.0)
        except Exception:
            pass
        time.sleep(0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(
    frame_queue,
    otc_sdk_dir:   str,
    legacy_dll:    str,
    legacy_config: str,
    try_otc:       bool = True,
    try_legacy:    bool = True,
) -> None:
    """Worker subprocess entry point (called by multiprocessing.Process).

    Tries OTC → legacy in order and streams frames forever.
    """
    # Claim STA COM apartment on this thread before any DLL is loaded.
    # DirectShow (used by IrDirectSDK/pyOptris) requires the calling thread to
    # own an STA apartment.  Doing this here — before even the OTC attempt —
    # guarantees the apartment is set regardless of which backend succeeds.
    ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_APARTMENTTHREADED

    _log(f"started  (try_otc={try_otc}, try_legacy={try_legacy})")
    _log(f"  OTC SDK : {otc_sdk_dir}")
    _log(f"  DLL     : {legacy_dll}")
    _log(f"  config  : {legacy_config}")

    if try_otc:
        _log("→ trying OTC SDK …")
        try:
            _run_otc(frame_queue, otc_sdk_dir)
            return
        except Exception as e:
            _log(f"  OTC failed: {type(e).__name__}: {e}")

    if try_legacy:
        _log("→ trying legacy SDK …")
        try:
            _run_legacy(frame_queue, legacy_dll, legacy_config)
            return
        except Exception as e:
            _log(f"  legacy failed: {type(e).__name__}: {e}")

    _log("→ no hardware found — exiting.")

"""IR camera service — Qt desktop singleton.

All Optris SDK calls are isolated inside a spawned subprocess (ir_camera_worker).
The main Qt process never loads any Optris DLL directly.

Why a subprocess?
-----------------
- The legacy IrDirectSDK DLL calls abort() on connection errors.  abort() in
  a thread kills the whole Qt app; in a subprocess it kills only the subprocess.
- The OTC SDK COM/threading model is incompatible with PyQt6 and crashes the
  main process when loaded in-process.

Connection priority (resolved inside the worker)
------------------------------------------------
1. OTC SDK 10.x
2. Legacy pyOptris / IrDirectSDK

If no hardware is found the worker exits cleanly and connect() returns False.

Usage
-----
    svc = IrCameraService()
    ok    = svc.connect()          # blocks until first frame or timeout
    frame = svc.get_frame()        # np.ndarray (H, W) float32 °C, or None
    svc.disconnect()
"""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IrCameraConfig:
    """Mutable SDK path config owned by the IrCameraService singleton.

    Update fields here at any time; changes take effect on the next connect().
    Accessible via ``IrCameraService().config``.
    """
    otc_sdk_dir:   str = field(
        default_factory=lambda: os.environ.get(
            "OTC_SDK_DIR", r"C:\Program Files\Optris\otcsdk"
        )
    )
    legacy_dll:    str = r"C:\IrDirectSDK\sdk\x64\libirimager.dll"
    legacy_config: str = r"C:\IrDirectSDK\generic.xml"


_CONNECT_TIMEOUT = 20.0   # seconds to wait for first frame after usb_init
_QUEUE_SIZE      = 3      # max frames buffered between worker and service


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class IrCameraService:
    """Singleton service — manages the worker subprocess and exposes frames."""

    _instance:   Optional["IrCameraService"] = None
    _class_lock: threading.Lock              = threading.Lock()

    def __new__(cls) -> "IrCameraService":
        with cls._class_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst.config         = IrCameraConfig()
                inst._connected     = False
                inst._backend       = None   # "otc" | "legacy"
                inst._proc          = None   # worker subprocess
                inst._queue         = None   # multiprocessing.Queue
                inst._probe_info    = {}     # diagnostic info from last connect()
                cls._instance = inst
        return cls._instance

    # ── public properties ────────────────────────────────────────────────────

    @property
    def backend(self) -> Optional[str]:
        """Active backend name, or None when disconnected."""
        return self._backend

    @property
    def probe_info(self) -> dict:
        """Diagnostic dict populated by the last connect() call.

        Keys: backend, otc_crashed, legacy_crashed, otc_failed, legacy_failed.
        """
        return self._probe_info

    def is_connected(self) -> bool:
        return self._connected

    # ── connect / disconnect ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """Spawn the worker subprocess and wait for the first frame.

        Probe order: legacy-first, then OTC-only fallback.

        Trying OTC before legacy is dangerous: the OTC SDK crashes (C-level)
        while accessing the USB camera, leaving the USB driver in an error
        state.  Subsequent legacy usb_init calls return 0 but all SDK handles
        are NULL, causing access violations.  Legacy-first avoids that entirely
        since the legacy path works and OTC is never touched.

        If no hardware is found the worker exits cleanly (exitcode 0) and
        connect() returns False immediately.

        Returns True once a frame arrives, False when no camera is found.
        """
        from ..instruments.ir_camera_worker import run as _worker_run

        ctx = mp.get_context("spawn")
        cfg = self.config

        probes = [
            (False, True),   # legacy only  — try this first (safe, proven to work)
            (True,  False),  # OTC only     — fallback if legacy not found
        ]

        otc_crashed = legacy_crashed = False

        for try_otc, try_legacy in probes:
            q    = ctx.Queue(maxsize=_QUEUE_SIZE)
            proc = ctx.Process(
                target=_worker_run,
                args=(q, cfg.otc_sdk_dir, cfg.legacy_dll, cfg.legacy_config,
                      try_otc, try_legacy),
                daemon=True,
            )
            proc.start()

            result   = None
            deadline = time.monotonic() + _CONNECT_TIMEOUT
            while time.monotonic() < deadline:
                if not proc.is_alive():
                    break
                try:
                    result = q.get(timeout=0.25)
                    break
                except Exception:
                    pass

            if result is not None:
                backend, _first_frame = result
                self._proc      = proc
                self._queue     = q
                self._backend   = backend
                self._connected = True
                self._probe_info = {
                    "backend":        backend,
                    "otc_crashed":    otc_crashed,
                    "legacy_crashed": legacy_crashed,
                }
                return True

            proc.join(timeout=2)
            exitcode = proc.exitcode

            # exitcode 0 → worker found no hardware and exited cleanly.
            # Stop probing — retrying won't help.
            if exitcode == 0:
                break

            # Non-zero exitcode → C-level crash; record which backend crashed.
            if try_otc and not otc_crashed:
                otc_crashed = True
            elif try_legacy and not legacy_crashed:
                legacy_crashed = True

            try:
                proc.terminate()
            except Exception:
                pass

            # Brief pause between probes so the USB driver can recover from
            # any crash-induced device state corruption before the next probe
            # attempts usb_init.
            time.sleep(2.0)

        return False

    def disconnect(self) -> None:
        """Terminate the worker subprocess and reset state."""
        self._connected = False
        self._backend   = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.join(timeout=2)
            except Exception:
                pass
            self._proc = None
        self._queue = None

    # ── frame access ─────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the latest (H, W) float32 °C frame, or None.

        Also detects worker subprocess death and marks the service as
        disconnected so the widget can update its UI.
        """
        if not self._connected or self._queue is None:
            return None
        if self._proc is not None and not self._proc.is_alive():
            self._connected = False
            self._backend   = None
            return None
        try:
            _name, frame = self._queue.get_nowait()
            return frame
        except Exception:
            return None

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

Simulated camera
----------------
With ``TE_VISA_BACKEND=sim`` (the simulated rig) connect() starts a synthetic
382 × 288 camera instead of the worker, so the live view, regions and their
recording can be used and tested without hardware. Its sample temperatures
follow the simulated run (``set_sim_temperatures``).

Usage
-----
    svc = IrCameraService()
    ok    = svc.connect()          # blocks until first frame or timeout
    frame = svc.get_frame()        # newest unseen frame (H, W) °C, or None
    frame, age_s = svc.latest()    # newest frame and its age, for any reader
    svc.disconnect()

Frames come off a queue once; ``latest()`` keeps the newest one so the live
view and the run recorder can both read it without taking frames from each
other.
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
    # Defaults come from [ir_camera] in the rig config; OTC_SDK_DIR overrides.
    otc_sdk_dir:   str = field(
        default_factory=lambda: os.environ.get("OTC_SDK_DIR", _cfg_ir().otc_sdk_dir)
    )
    legacy_dll:    str = field(default_factory=lambda: _cfg_ir().legacy_dll)
    legacy_config: str = field(default_factory=lambda: _cfg_ir().legacy_config)


def _cfg_ir():
    from ..core.config import get_config
    return get_config().ir_camera


_CONNECT_TIMEOUT = 20.0   # seconds to wait for first frame after usb_init
_QUEUE_SIZE      = 3      # max frames buffered between worker and service


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class IrCameraService:
    """Singleton service — manages the worker subprocess and exposes frames."""

    _instance:   Optional["IrCameraService"] = None
    _class_lock: threading.Lock              = threading.Lock()

    # Set once in __new__ (singleton).
    config: IrCameraConfig
    _frame_lock: threading.Lock

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
                inst._frame_lock    = threading.Lock()
                inst._latest        = None   # newest frame (H, W) float32 °C
                inst._latest_t      = 0.0    # time.monotonic() it arrived
                inst._seen_t        = 0.0    # what get_frame() last returned
                inst._sim           = None   # _SimCamera when simulated
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
        from ..instruments.visa_backend import is_simulated
        if is_simulated():
            return self._connect_sim()

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

    def _connect_sim(self) -> bool:
        self._sim = _SimCamera(self._store)
        self._sim.start()
        self._backend, self._connected = "sim", True
        self._probe_info = {"backend": "sim"}
        return True

    def set_sim_temperatures(self, hot: Optional[float], cold: Optional[float]) -> None:
        """Simulated camera only: the sample's hot / cold end temperatures."""
        if self._sim is not None and hot is not None and cold is not None:
            self._sim.hot, self._sim.cold = float(hot), float(cold)

    def disconnect(self) -> None:
        """Terminate the worker subprocess and reset state."""
        self._connected = False
        self._backend   = None
        if self._sim is not None:
            self._sim.stop()
            self._sim = None
        with self._frame_lock:
            self._latest, self._latest_t, self._seen_t = None, 0.0, 0.0
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.join(timeout=2)
            except Exception:
                pass
            self._proc = None
        self._queue = None

    # ── frame access ─────────────────────────────────────────────────────────

    def _store(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._latest, self._latest_t = frame, time.monotonic()

    def _pull(self) -> None:
        """Move every queued frame out of the worker queue, keeping the newest.

        Also detects worker subprocess death and marks the service as
        disconnected so the widget can update its UI.
        """
        if not self._connected or self._queue is None:
            return
        if self._proc is not None and not self._proc.is_alive():
            self._connected = False
            self._backend   = None
            return
        newest = None
        for _ in range(_QUEUE_SIZE + 1):
            try:
                _name, newest = self._queue.get_nowait()
            except Exception:
                break
        if newest is not None:
            self._store(newest)

    def get_frame(self) -> Optional[np.ndarray]:
        """The newest frame not yet returned by get_frame(), or None."""
        self._pull()
        with self._frame_lock:
            if self._latest is None or self._latest_t <= self._seen_t:
                return None
            self._seen_t = self._latest_t
            return self._latest

    def latest(self) -> tuple[Optional[np.ndarray], float]:
        """(newest frame, its age in s) for any reader; (None, inf) if none."""
        self._pull()
        with self._frame_lock:
            if self._latest is None or not self._connected:
                return None, float("inf")
            return self._latest, time.monotonic() - self._latest_t


# ─────────────────────────────────────────────────────────────────────────────
# Simulated camera (TE_VISA_BACKEND=sim)
# ─────────────────────────────────────────────────────────────────────────────

SIM_SHAPE = (288, 382)        # (H, W) of the Optris PI 450i


def sim_scene(hot: float, cold: float, ambient: float = 22.5,
              shape: tuple = SIM_SHAPE, rng: Optional[np.random.Generator] = None
              ) -> np.ndarray:
    """A plausible thermal frame: sample bar from the heater block (left, hot)
    to the heat sink (right, cold) on a holder, on a room background."""
    h, w = shape
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    f = ambient + 2.0 * y / h + 0.4 * np.sin(x * 0.025 + y * 0.015)
    holder = (y > h * .28) & (y < h * .72) & (x > w * .07) & (x < w * .93)
    f[holder] = ambient + 2.5
    heater = (x > w * .09) & (x <= w * .2) & (y > h * .31) & (y < h * .69)
    f[heater] = hot + 8.0
    sink = (x >= w * .8) & (x < w * .9) & (y > h * .33) & (y < h * .67)
    f[sink] = cold - 0.8
    bar = (y > h * .42) & (y < h * .58) & (x > w * .2) & (x < w * .8)
    frac = (x - w * .2) / (w * .6)
    f[bar] = (hot - (hot - cold) * frac)[bar]
    if rng is not None:
        f += rng.normal(0.0, 0.06, size=f.shape).astype(np.float32)
    return f.astype(np.float32)


class _SimCamera:
    """Background thread producing sim_scene() frames at ~8 fps."""

    def __init__(self, sink):
        self._sink = sink
        self._stop = threading.Event()
        self._rng = np.random.default_rng(0)
        self.hot, self.cold = 24.5, 23.5
        self._thread = threading.Thread(target=self._run, name="sim-ir-camera", daemon=True)

    def start(self) -> None:
        self._sink(sim_scene(self.hot, self.cold, rng=self._rng))   # first frame now
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(0.125):
            self._sink(sim_scene(self.hot, self.cold, rng=self._rng))

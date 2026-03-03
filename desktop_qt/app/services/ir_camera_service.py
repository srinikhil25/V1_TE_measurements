"""IR Camera service — Qt desktop singleton.

Connection priority
-------------------
1. Optris OTC SDK 10.x  — via desktop_qt/app/instruments/optris_otc.py
2. Legacy pyOptris / IrDirectSDK  — via pyOptris Python bindings
3. Simulation  — animated thermal scene (no hardware required)

``get_frame()`` always returns a (H, W) float32 numpy array of temperatures
in °C, or None while not connected / no frame ready yet.
The Qt widget owns all false-colour rendering; no cv2/JPEG is needed here.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import numpy as np

# Legacy IrDirectSDK DLL + config paths (edit if your installation differs)
_LEGACY_DLL    = r"C:\lib\IrDirectSDK\sdk\x64\libirimager.dll"
_LEGACY_CONFIG = r"C:\lib\IrDirectSDK\generic.xml"


class IrCameraService:
    """Singleton service for IR camera frame acquisition."""

    BACKEND_OTC    = "otc"
    BACKEND_LEGACY = "legacy"
    BACKEND_SIM    = "simulation"

    _instance: Optional["IrCameraService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "IrCameraService":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._connected  = False
                inst._backend: Optional[str] = None
                inst._tick       = 0
                # OTC handles
                inst._otc_client  = None
                inst._otc_imager  = None
                inst._otc_thread  = None
                # Legacy handle
                inst._pyOptris    = None
                inst._py_w        = 0
                inst._py_h        = 0
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ public

    def connect(self) -> bool:
        """Attempt to open the camera. Returns True on success (any backend)."""

        # ── 1. OTC SDK ────────────────────────────────────────────────────
        # Guard: only attempt if the SDK bindings directory actually exists.
        # A missing SDK raises a clean ImportError; a present-but-broken SDK
        # can segfault — so we check the path first.
        try:
            from ..instruments.optris_otc import (
                _BINDINGS_PATH, is_available, create_otc_camera_manager,
            )
            if os.path.isdir(_BINDINGS_PATH) and is_available():
                client, imager, thread = create_otc_camera_manager(0)
                self._otc_client = client
                self._otc_imager = imager
                self._otc_thread = thread
                self._backend    = self.BACKEND_OTC
                self._connected  = True
                self._tick       = 0
                return True
        except Exception:
            pass

        # ── 2. Legacy pyOptris / IrDirectSDK ─────────────────────────────
        # Guard: only attempt if the DLL file is physically present.
        # Trying to load a missing DLL can hard-crash the process.
        try:
            if os.path.isfile(_LEGACY_DLL):
                import pyOptris
                pyOptris.load_DLL(_LEGACY_DLL)
                pyOptris.usb_init(_LEGACY_CONFIG)
                w, h = pyOptris.get_palette_image_size()
                self._pyOptris   = pyOptris
                self._py_w       = w
                self._py_h       = h
                self._backend    = self.BACKEND_LEGACY
                self._connected  = True
                self._tick       = 0
                return True
        except Exception:
            pass

        # ── 3. Simulation fallback ────────────────────────────────────────
        self._backend   = self.BACKEND_SIM
        self._connected = True
        self._tick      = 0
        return True

    def disconnect(self) -> None:
        """Close the camera connection and release resources."""
        if self._backend == self.BACKEND_OTC and self._otc_client:
            try:
                self._otc_client.stop()
            except Exception:
                pass
            self._otc_client = None
            self._otc_imager = None
            self._otc_thread = None

        elif self._backend == self.BACKEND_LEGACY and self._pyOptris:
            try:
                self._pyOptris.terminate()
            except Exception:
                pass
            self._pyOptris = None

        self._connected = False
        self._backend   = None

    def is_connected(self) -> bool:
        return self._connected

    @property
    def backend(self) -> Optional[str]:
        """Active backend: ``'otc'``, ``'legacy'``, ``'simulation'``, or None."""
        return self._backend

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the latest frame as a (H, W) float32 temperature array in °C.

        Returns ``None`` when not connected or no frame is ready yet.
        """
        if not self._connected:
            return None
        self._tick += 1
        if self._backend == self.BACKEND_OTC:
            return self._get_frame_otc()
        if self._backend == self.BACKEND_LEGACY:
            return self._get_frame_legacy()
        return self._simulate_frame()

    # ---------------------------------------------------------------- backends

    def _get_frame_otc(self) -> Optional[np.ndarray]:
        from ..instruments.optris_otc import frame_to_celsius
        thermal = self._otc_client.get_latest_frame()
        return frame_to_celsius(thermal)

    def _get_frame_legacy(self) -> Optional[np.ndarray]:
        try:
            raw   = self._pyOptris.get_thermal_image(self._py_w, self._py_h)
            return (raw.astype(np.float32) - 1000.0) / 10.0
        except Exception:
            return None

    # ---------------------------------------------------------------- simulation

    def _simulate_frame(self) -> np.ndarray:
        """Animated simulated thermal scene — used when no hardware is present."""
        h, w = 120, 160
        t    = self._tick
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)

        cx    = w * 0.5 + 22.0 * np.sin(t * 0.04)
        cy    = h * 0.5 + 15.0 * np.cos(t * 0.033)
        hot   = 55.0 * np.exp(-((x - cx)**2 + (y - cy)**2) / (2.0 * 16.0**2))

        cx2   = w * 0.25 + 10.0 * np.cos(t * 0.025)
        cy2   = h * 0.70 +  8.0 * np.sin(t * 0.020)
        warm  = 18.0 * np.exp(-((x - cx2)**2 + (y - cy2)**2) / (2.0 * 22.0**2))

        ambient = 24.0 + 4.0 * (y / h) + 1.5 * (x / w)
        noise   = np.random.normal(0.0, 0.35, (h, w)).astype(np.float32)

        return (ambient + hot + warm + noise).astype(np.float32)

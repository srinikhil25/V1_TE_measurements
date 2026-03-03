"""IR Camera service — singleton wrapping Optris SDK or simulation mode.

Real integration
----------------
Replace the simulation block in ``connect()`` / ``get_frame()`` with actual
Optris PIL / SDK calls, e.g.::

    from optris_bindings import OptrisCamera
    self._cam = OptrisCamera()
    self._cam.start()
    ...
    return self._cam.get_temperature_array()  # (H, W) float32 in °C
"""

from __future__ import annotations

import threading
from typing import Optional

import numpy as np


class IrCameraService:
    """Singleton service for IR camera frame acquisition."""

    _instance: Optional["IrCameraService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "IrCameraService":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._connected = False
                inst._tick = 0
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ public

    def connect(self) -> bool:
        """Open camera connection. Returns True on success."""
        try:
            # ── Real SDK hook ────────────────────────────────────────────────
            # from optris_bindings import OptrisCamera
            # self._cam = OptrisCamera()
            # self._cam.start()
            # ────────────────────────────────────────────────────────────────
            self._connected = True
            self._tick = 0
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close camera connection."""
        # ── Real SDK hook ────────────────────────────────────────────────────
        # if hasattr(self, "_cam"):
        #     self._cam.stop()
        # ────────────────────────────────────────────────────────────────────
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the latest frame as a (H, W) float32 temperature array in °C.

        Returns ``None`` when not connected.
        """
        if not self._connected:
            return None
        self._tick += 1
        # ── Real SDK hook ────────────────────────────────────────────────────
        # return self._cam.get_temperature_array()
        # ────────────────────────────────────────────────────────────────────
        return self._simulate_frame()

    # ---------------------------------------------------------------- private

    def _simulate_frame(self) -> np.ndarray:
        """Animated simulated thermal scene for UI development / demo."""
        h, w = 120, 160
        t = self._tick
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)

        # Primary hot spot — slow elliptical drift
        cx = w * 0.5 + 22.0 * np.sin(t * 0.04)
        cy = h * 0.5 + 15.0 * np.cos(t * 0.033)
        dist2 = (x - cx) ** 2 + (y - cy) ** 2
        hot = 55.0 * np.exp(-dist2 / (2.0 * 16.0 ** 2))

        # Secondary cooler region
        cx2 = w * 0.25 + 10.0 * np.cos(t * 0.025)
        cy2 = h * 0.70 + 8.0 * np.sin(t * 0.020)
        dist2b = (x - cx2) ** 2 + (y - cy2) ** 2
        warm = 18.0 * np.exp(-dist2b / (2.0 * 22.0 ** 2))

        # Warm ambient gradient (bottom slightly warmer — heatsink effect)
        ambient = 24.0 + 4.0 * (y / h) + 1.5 * (x / w)

        # Sensor noise
        noise = np.random.normal(0.0, 0.35, (h, w)).astype(np.float32)

        return (ambient + hot + warm + noise).astype(np.float32)

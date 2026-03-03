"""
Singleton wrappers around the instrument layer.

SeebeckService  — wraps MeasurementSessionManager (runs its own thread).
IVService       — runs a blocking IV sweep; intended to be called from a QThread.
"""

import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of instrument layer (requires pyvisa at runtime)
# ---------------------------------------------------------------------------

def _get_session_manager():
    from ..instruments.session_manager import MeasurementSessionManager
    return MeasurementSessionManager


def _get_seebeck_system():
    from ..instruments.instrument import SeebeckSystem
    return SeebeckSystem


# ---------------------------------------------------------------------------
# Seebeck Service
# ---------------------------------------------------------------------------

class SeebeckService:
    """
    Singleton wrapper around MeasurementSessionManager.
    The session manager already runs its measurement loop in a background
    thread; this service is polled by the UI via a QTimer.
    """

    _instance: Optional["SeebeckService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._mgr = None
        return cls._instance

    def _manager(self):
        if self._mgr is None:
            cls = _get_session_manager()
            self._mgr = cls()
        return self._mgr

    def start(self, params: Dict) -> bool:
        mgr = self._manager()
        if mgr.session_active:
            return False
        return mgr.start_session(params)

    def stop(self) -> None:
        if self._mgr and self._mgr.session_active:
            self._mgr.stop_session()

    def is_active(self) -> bool:
        return bool(self._mgr and self._mgr.session_active)

    def get_status(self) -> Dict:
        return self._manager().get_status()

    def get_data(self) -> List[Dict]:
        return self._manager().get_data()

    def get_analysis(self) -> List[Dict]:
        return self._manager().get_binned_analysis()


# ---------------------------------------------------------------------------
# IV Sweep Service (blocking — run from QThread)
# ---------------------------------------------------------------------------

def run_iv_sweep(
    start_voltage: float,
    stop_voltage: float,
    points: int,
    delay_ms: float = 50.0,
    current_limit: float = 0.1,
    voltage_limit: float = 21.0,
    length: Optional[float] = None,
    width: Optional[float] = None,
    thickness: Optional[float] = None,
) -> List[Dict]:
    """
    Perform a blocking IV sweep and return a list of point dicts.
    Raises RuntimeError on connection / instrument failure.
    """
    if points < 2:
        raise ValueError("points must be >= 2")

    SeebeckSystem = _get_seebeck_system()
    system = SeebeckSystem()

    step = (stop_voltage - start_voltage) / (points - 1)
    voltages = [start_voltage + i * step for i in range(points)]

    if not system.connect_all():
        raise RuntimeError("Failed to connect to instruments.")

    results: List[Dict] = []
    try:
        vmax = max(abs(start_voltage), abs(stop_voltage), abs(voltage_limit))
        system.k2401.configure_voltage_source(
            voltage_limit=vmax, current_limit=current_limit
        )
        system.k2401.output_on()

        for v in voltages:
            system.k2401.set_voltage(v)
            time.sleep(delay_ms / 1000.0)
            meas = system.k2401.read_measurement()

            if meas is None:
                results.append({"voltage": v, "current": None,
                                 "resistance": None, "resistivity": None})
                continue

            i = meas.get("current")
            mv = meas.get("voltage", v)
            r = meas.get("resistance")

            resistivity = conductivity = None
            if r and length and width and thickness:
                area = width * thickness
                if area > 0 and length > 0:
                    resistivity = r * area / length
                    conductivity = 1.0 / resistivity if resistivity else None

            results.append({
                "voltage": mv, "current": i, "resistance": r,
                "resistivity": resistivity, "conductivity": conductivity,
            })

        return results

    except Exception as exc:
        logger.error("IV sweep error: %s", exc)
        raise
    finally:
        try:
            system.k2401.output_off()
        finally:
            system.disconnect_all()

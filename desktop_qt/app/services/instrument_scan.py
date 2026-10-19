"""Instrument list (from the rig config) and a non-blocking GPIB presence scan.

``list_resources()`` can block for seconds on a GPIB bus, so it runs on a
worker thread and the result is delivered to the GUI thread through a Qt
signal. The scan is skipped while a measurement is running: enumerating the
bus during a run can knock the heater supply out of remote control.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional, Set, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.config import get_config

logger = logging.getLogger(__name__)

# (config key, short label, full name, role)
INSTRUMENTS: List[Tuple[str, str, str, str]] = [
    ("k2182a", "2182A",   "Keithley 2182A",    "Nanovoltmeter (thermovoltage)"),
    ("k2700",  "2700",    "Keithley 2700",     "DMM / scanner (thermocouples)"),
    ("pk480m", "P4K-80M", "Matsusada P4K-80M", "Heater power supply"),
    ("k2401",  "2401",    "Keithley 2401",     "SourceMeter (I-V)"),
]


def instrument_addresses() -> List[Tuple[str, str, str, str]]:
    """[(key, short label, full name, address)] using the current config."""
    addrs = get_config().instruments
    return [(key, short, full, getattr(addrs, key)) for key, short, full, _ in INSTRUMENTS]


class _ScanSignal(QObject):
    done = pyqtSignal(object)   # set of visible resource names, or None on failure


_active_scans: list = []     # keep signal objects alive until delivered


def start_resource_scan(on_done: Callable[[Optional[Set[str]]], None]) -> bool:
    """Scan for visible VISA resources in the background.

    ``on_done`` is called on the GUI thread with a set of resource names, or
    ``None`` if VISA is unavailable. Returns False (and does not scan) while a
    measurement is running.
    """
    from .measurement_service import any_measurement_running
    if any_measurement_running():
        return False

    sig = _ScanSignal()
    _active_scans.append(sig)

    def _deliver(found):
        # Runs on the GUI thread; release the signal object only after delivery.
        try:
            on_done(found)
        except RuntimeError:
            pass    # receiving widget already deleted
        finally:
            if sig in _active_scans:
                _active_scans.remove(sig)

    sig.done.connect(_deliver)

    def _work():
        found: Optional[Set[str]] = None
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            try:
                found = set(rm.list_resources())
            finally:
                rm.close()
        except Exception as exc:
            logger.info("VISA resource scan unavailable: %s", exc)
        sig.done.emit(found)

    threading.Thread(target=_work, name="visa-scan", daemon=True).start()
    return True

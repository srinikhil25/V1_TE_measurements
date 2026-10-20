"""RunStateMonitor — one place that knows whether a measurement is running.

Polls the measurement services once a second on the GUI thread and emits a
small state dict that the top bar, status footer and overview subscribe to.
"""

from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class RunStateMonitor(QObject):
    changed = pyqtSignal(dict)

    def __init__(self, parent: Optional[QObject] = None, interval_ms: int = 1000):
        super().__init__(parent)
        self._iv_started: Optional[float] = None
        self.state: dict = {"kind": "idle", "running": False}
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        QTimer.singleShot(0, self.poll)

    def poll(self) -> None:
        st = {"kind": "idle", "running": False, "elapsed_s": None,
              "phase": None, "measurement_id": None, "label": "Idle",
              "invalid_reads": 0, "db_warning": None}
        try:
            from ...services.measurement_service import SeebeckService, iv_running
            svc = SeebeckService()
            if svc.is_active():
                s = svc.get_status()
                start = s.get("start_time")
                st.update(kind="seebeck", running=True, label="Seebeck run",
                          phase=s.get("phase"),
                          measurement_id=s.get("measurement_id"),
                          invalid_reads=s.get("invalid_reads") or 0,
                          db_warning=s.get("db_warning"),
                          elapsed_s=(time.time() - start) if isinstance(start, (int, float)) else None)
                self._iv_started = None
            elif iv_running():
                if self._iv_started is None:
                    self._iv_started = time.time()
                st.update(kind="iv", running=True, label="I-V sweep",
                          elapsed_s=time.time() - self._iv_started)
            else:
                self._iv_started = None
        except Exception:
            pass
        self.state = st
        self.changed.emit(st)


class InstrumentStatus(QObject):
    """Last result of the background GPIB presence scan, shared by all views.

    ``available`` is None before the first scan (or when VISA is missing),
    else the set of visible resource names.
    """

    updated = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.available = None
        self.scanned_at: Optional[float] = None
        self.scanning = False

    def refresh(self) -> bool:
        if self.scanning:
            return False
        from ...services import instrument_scan
        started = instrument_scan.start_resource_scan(self._on_done)
        self.scanning = bool(started)
        return self.scanning

    def _on_done(self, available):
        self.scanning = False
        self.available = available
        self.scanned_at = time.time()
        self.updated.emit(available)

    def state_of(self, address: str) -> str:
        """'online' · 'offline' · 'unknown'."""
        if self.available is None:
            return "unknown"
        return "online" if address in self.available else "offline"


_instrument_status: Optional[InstrumentStatus] = None


def instrument_status() -> InstrumentStatus:
    global _instrument_status
    if _instrument_status is None:
        _instrument_status = InstrumentStatus()
    return _instrument_status


def fmt_elapsed(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

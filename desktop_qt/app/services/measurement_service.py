"""
Singleton wrappers around the instrument layer.

SeebeckService  — wraps MeasurementSessionManager (runs its own thread).
IV sweep        — blocking run with progress/abort, DB persistence, linear fit.
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

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
        """Start a new Seebeck session for the current user.

        Enriches the params dict with DB user/lab ids so the instrument layer
        can persist the run to the SQLite database.
        """
        # Attach current user context for DB persistence
        try:
            from .auth_service import get_current_user

            user = get_current_user()
            if user is not None:
                params = dict(params)  # shallow copy so callers aren't mutated
                params["_user_id"] = getattr(user, "id", None)
                params["_lab_id"] = getattr(user, "lab_id", None)
        except Exception:
            # If anything goes wrong here, fall back to running without DB linkage.
            pass

        mgr = self._manager()
        if mgr.session_active:
            return False
        return mgr.start_session(params)

    def stop(self) -> None:
        if self._mgr and self._mgr.session_active:
            self._mgr.stop_session()

    def reset(self) -> None:
        """Force a clean slate: stop any run, release every instrument.

        Safe to call when idle — disconnect is a no-op on already-disconnected
        instruments. Lets the operator redo a measurement without restarting
        the app or the devices.
        """
        if self._mgr is not None:
            try:
                self._mgr.cleanup()
            except Exception as e:
                logger.error("SeebeckService.reset failed: %s", e)

    def is_active(self) -> bool:
        return bool(self._mgr and self._mgr.session_active)

    def get_status(self) -> Dict:
        return self._manager().get_status()

    def get_data(self) -> List[Dict]:
        return self._manager().get_data()

    def get_analysis(self) -> List[Dict]:
        return self._manager().get_binned_analysis()


# ---------------------------------------------------------------------------
# IV sweep: linear fit and ohmic status
# ---------------------------------------------------------------------------

def _linear_fit_resistance(points: List[Dict]) -> tuple:
    """
    Fit V = R*I (through origin). Returns (R, R_squared).
    points: list of dicts with "current" and "voltage" keys.
    """
    import numpy as np
    valid = [
        (p["current"], p["voltage"])
        for p in points
        if p.get("current") is not None and p.get("voltage") is not None
        and abs(p["current"]) > 1e-12
    ]
    if len(valid) < 2:
        return None, None
    I = np.array([x[0] for x in valid])
    V = np.array([x[1] for x in valid])
    # V = R*I  =>  R = sum(I*V) / sum(I^2)
    II = I * I
    IV = I * V
    R = float(np.sum(IV) / np.sum(II)) if np.sum(II) > 0 else None
    if R is None:
        return None, None
    V_fit = R * I
    ss_res = np.sum((V - V_fit) ** 2)
    ss_tot = np.sum((V - np.mean(V)) ** 2)
    R_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else None
    return R, R_squared


def _ohmic_status(R_squared: Optional[float]) -> str:
    if R_squared is None:
        return "unknown"
    if R_squared >= 0.999:
        return "ohmic"
    if R_squared >= 0.99:
        return "check_contacts"
    return "non_ohmic"


# ---------------------------------------------------------------------------
# IV Sweep (blocking — run from QThread)
# ---------------------------------------------------------------------------

def run_iv_sweep(
    # Sweep definition
    source_mode: str = "current",  # "current" = 4-probe (6221 + 2182A), "voltage" = 2-probe
    start: float = -0.01,
    stop: float = 0.01,
    points: int = 21,
    bidirectional: bool = False,
    delay_ms: float = 50.0,
    current_limit: float = 0.1,
    voltage_limit: float = 21.0,
    nplc: float = 5.0,
    # Dimensions (m) for resistivity
    length: Optional[float] = None,
    width: Optional[float] = None,
    thickness: Optional[float] = None,
    # DB and metadata
    sample_id: Optional[str] = None,
    operator: Optional[str] = None,
    notes: Optional[str] = None,
    _user_id: Optional[int] = None,
    _lab_id: Optional[int] = None,
    # Callbacks
    progress_callback: Optional[Callable[[int, Dict], None]] = None,
    abort_check: Optional[Callable[[], bool]] = None,
) -> Dict:
    """
    Run IV sweep and return full result dict.

    - source_mode "current": 4-probe (6221 current source, 2182A voltmeter).
    - source_mode "voltage": 2-probe (6221 voltage source, read I from 6221).

    Returns:
        {
            "points": [{"voltage", "current", "resistance", "resistivity", "conductivity"}, ...],
            "fit_R": float or None,
            "fit_R_squared": float or None,
            "ohmic_status": "ohmic" | "check_contacts" | "non_ohmic" | "unknown",
            "temperature_C": float or None,
            "measurement_id": int or None,
            "aborted": bool,
        }
    """
    if points < 2:
        raise ValueError("points must be >= 2")

    SeebeckSystem = _get_seebeck_system()
    system = SeebeckSystem()

    # Build sweep sequence (current or voltage values)
    step = (stop - start) / (points - 1)
    forward = [start + i * step for i in range(points)]
    if bidirectional:
        # forward then reverse, avoid duplicating the last point
        sequence = forward + [start + i * step for i in range(points - 2, -1, -1)]
    else:
        sequence = forward

    if not system.connect_all():
        raise RuntimeError("Failed to connect to instruments.")

    # Optional: configure 2700 for temperature and read once at start
    temperature_C: Optional[float] = None
    try:
        if system.k2700.connected:
            system.k2700.configure_measurement()
        temperature_C = system.get_temperature_avg_c()
    except Exception:
        pass

    results: List[Dict] = []
    measurement_id: Optional[int] = None
    db = None
    measurement_obj = None

    try:
        # Create DB record if user/lab provided
        if _user_id is not None and _lab_id is not None:
            try:
                from ..core.database import get_session
                from ..models.db_models import Measurement

                db = get_session()
                measurement_obj = Measurement(
                    user_id=_user_id,
                    lab_id=_lab_id,
                    type="iv",
                    status="running",
                    sample_id=sample_id,
                    operator=operator,
                    notes=notes,
                    params_json=json.dumps({
                        "source_mode": source_mode,
                        "start": start,
                        "stop": stop,
                        "points": points,
                        "bidirectional": bidirectional,
                        "delay_ms": delay_ms,
                        "current_limit": current_limit,
                        "voltage_limit": voltage_limit,
                        "nplc": nplc,
                        "length": length,
                        "width": width,
                        "thickness": thickness,
                    }, default=str),
                    started_at=datetime.utcnow(),
                )
                db.add(measurement_obj)
                db.commit()
                db.refresh(measurement_obj)
                measurement_id = measurement_obj.id
            except Exception as e:
                logger.error("IV: failed to create Measurement: %s", e)
                if db:
                    db.rollback()
                    db.close()
                db = None

        if source_mode == "current":
            # 4-probe: 6221 sources current, 2182A measures voltage
            system.prepare_iv_4probe(
                voltage_limit=voltage_limit,
                current_limit=current_limit,
                nplc=nplc,
            )
            delay_s = delay_ms / 1000.0
            for idx, current_A in enumerate(sequence):
                if abort_check and abort_check():
                    break
                pt = system.measure_iv_point_4probe(current_A, delay_s)
                if pt is None:
                    pt = {"current": current_A, "voltage": None, "resistance": None}
                _enrich_point(pt, length, width, thickness)
                results.append(pt)
                if progress_callback:
                    progress_callback(idx, pt)
        else:
            # 2-probe: 6221 voltage source, read I from 6221
            vmax = max(abs(start), abs(stop), abs(voltage_limit))
            system.k6221.configure_voltage_source(
                voltage_limit=vmax, current_limit=current_limit
            )
            system.k6221.output_on()
            delay_s = delay_ms / 1000.0
            for idx, voltage_V in enumerate(sequence):
                if abort_check and abort_check():
                    break
                system.k6221.set_voltage(voltage_V)
                time.sleep(delay_s)
                meas = system.k6221.read_measurement()
                if meas is None:
                    pt = {"voltage": voltage_V, "current": None, "resistance": None}
                else:
                    i = meas.get("current")
                    v = meas.get("voltage", voltage_V)
                    r = v / i if i and abs(i) > 1e-12 else None
                    pt = {"voltage": v, "current": i, "resistance": r}
                _enrich_point(pt, length, width, thickness)
                results.append(pt)
                if progress_callback:
                    progress_callback(idx, pt)
            system.k6221.output_off()

        system.disconnect_all()
    except Exception as exc:
        logger.error("IV sweep error: %s", exc)
        if system.k6221.connected:
            try:
                system.k6221.output_off()
            except Exception:
                pass
        system.disconnect_all()
        raise
    finally:
        if db is not None and measurement_obj is not None:
            try:
                from ..models.db_models import MeasurementRow, MeasurementIntegrity

                # Persist all rows
                for seq, row in enumerate(results, start=1):
                    mr = MeasurementRow(
                        measurement_id=measurement_obj.id,
                        seq=seq,
                        elapsed_s=None,
                        data_json=json.dumps(row, default=str),
                    )
                    db.add(mr)
                # Integrity hash
                if results:
                    canonical = json.dumps(
                        results, sort_keys=True, separators=(",", ":")
                    )
                    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    integ = (
                        db.query(MeasurementIntegrity)
                        .filter_by(measurement_id=measurement_obj.id)
                        .first()
                    )
                    if integ is None:
                        db.add(
                            MeasurementIntegrity(
                                measurement_id=measurement_obj.id,
                                data_hash=digest,
                            )
                        )
                    else:
                        integ.data_hash = digest
                measurement_obj.status = "finished"
                measurement_obj.finished_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                logger.error("IV: failed to finalise DB: %s", e)
                db.rollback()
            finally:
                db.close()

    # Fit and ohmic status
    fit_R, fit_R_squared = _linear_fit_resistance(results)
    ohmic = _ohmic_status(fit_R_squared)

    return {
        "points": results,
        "fit_R": fit_R,
        "fit_R_squared": fit_R_squared,
        "ohmic_status": ohmic,
        "temperature_C": temperature_C,
        "measurement_id": measurement_id,
        "aborted": bool(abort_check and abort_check()),
    }


def _enrich_point(
    pt: Dict,
    length: Optional[float],
    width: Optional[float],
    thickness: Optional[float],
) -> None:
    """Add resistivity and conductivity to point if dimensions given."""
    r = pt.get("resistance")
    if r is None or not (length and width and thickness):
        pt.setdefault("resistivity", None)
        pt.setdefault("conductivity", None)
        return
    area = width * thickness
    if area > 0 and length > 0:
        rho = r * area / length
        pt["resistivity"] = rho
        pt["conductivity"] = 1.0 / rho if rho else None
    else:
        pt["resistivity"] = None
        pt["conductivity"] = None

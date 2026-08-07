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
    Fit V = R*I + V0 (slope + intercept). Returns (R, R_squared).

    The slope R is the resistance; the intercept V0 absorbs the thermoelectric
    offset voltage (tens of µV from dissimilar-metal/temperature junctions),
    which on a sub-mV signal would otherwise masquerade as non-ohmic behaviour
    when forcing the fit through the origin. A genuinely curved (non-ohmic) I-V
    still drops R_squared, so this only removes the offset confound — it does not
    hide real non-linearity.
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
    # Least-squares V = R*I + V0.
    A = np.vstack([I, np.ones_like(I)]).T
    try:
        (R, V0), *_ = np.linalg.lstsq(A, V, rcond=None)
    except Exception:
        return None, None
    R = float(R)
    V_fit = R * I + V0
    ss_res = float(np.sum((V - V_fit) ** 2))
    ss_tot = float(np.sum((V - V.mean()) ** 2))
    R_squared = (1.0 - ss_res / ss_tot) if ss_tot > 0 else None
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
    source_mode: str = "current",  # "current" = source I/measure V, "voltage" = source V/measure I
    start: float = -0.01,
    stop: float = 0.01,
    points: int = 21,
    bidirectional: bool = False,
    delay_ms: float = 50.0,
    current_limit: float = 0.1,
    voltage_limit: float = 21.0,
    nplc: float = 5.0,
    four_wire: bool = False,        # True = 4-wire remote sense (needs sense leads)
    # Dimensions (cm) for resistivity, and sample geometry
    length: Optional[float] = None,
    width: Optional[float] = None,
    thickness: Optional[float] = None,
    geometry: str = "bar",          # "bar", "vdp", or "4pp" (in-line 4-point probe)
    spacing: Optional[float] = None,  # 4pp probe spacing (cm)
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

    Uses the Keithley 2401 SourceMeter (sources and measures in one box):
    - source_mode "current": 2401 sources current, measures voltage.
    - source_mode "voltage": 2401 sources voltage, measures current.
    four_wire selects 4-wire remote sense (true 4-probe) vs 2-wire.

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
                        "four_wire": four_wire,
                        "geometry": geometry,
                        "spacing": spacing,
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

        # Single SourceMeter (2401) handles both source modes. Compliance is the
        # limit on the MEASURED quantity: volts when sourcing current, amps when
        # sourcing voltage.
        is_current = source_mode == "current"
        compliance = voltage_limit if is_current else current_limit
        system.k2401.configure(
            source_mode=source_mode,
            compliance=compliance,
            nplc=nplc,
            four_wire=four_wire,
        )
        system.k2401.output_on()
        delay_s = delay_ms / 1000.0
        # Finite-sheet geometric correction for the in-line 4-point probe
        # (computed once; depends only on geometry, not on the data points).
        size_factor = 1.0
        if geometry == "4pp":
            size_factor = collinear_4pp_size_factor(spacing, length, width)
        for idx, level in enumerate(sequence):
            if abort_check and abort_check():
                break
            system.k2401.set_level(level)
            time.sleep(delay_s)
            meas = system.k2401.read_point()
            if meas is None:
                pt = {"voltage": None, "current": None, "resistance": None}
                pt["current" if is_current else "voltage"] = level
            else:
                v = meas["voltage"]
                i = meas["current"]
                r = (v / i) if (i and abs(i) > 1e-12) else None
                pt = {"voltage": v, "current": i, "resistance": r}
            _enrich_point(pt, length, width, thickness, geometry, spacing, size_factor)
            results.append(pt)
            if progress_callback:
                progress_callback(idx, pt)
        system.k2401.output_off()

        system.disconnect_all()
    except Exception as exc:
        logger.error("IV sweep error: %s", exc)
        if system.k2401.connected:
            try:
                system.k2401.output_off()
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


def collinear_4pp_size_factor(s, length, width, n_terms: int = 60) -> float:
    """Finite-sample geometric correction for a collinear 4-point probe centered
    on a rectangular thin sheet.

    s        : probe spacing (cm)
    length   : sample dimension ALONG the probe line (cm)
    width    : sample dimension ACROSS the probe line (cm)
    Returns C such that  ρ_true = ρ_infinite · C   (C → 1 for a large sheet,
    C < 1 when the probes are near the edges). Uses the method of images
    (Neumann/insulating edges). Returns 1.0 if not computable.
    """
    import math
    if not (s and length and width) or s <= 0 or length <= 0 or width <= 0:
        return 1.0
    if length <= 3.0 * s:          # the 4-probe array (span 3·s) doesn't fit
        return 1.0
    xs = [-1.5 * s, -0.5 * s, 0.5 * s, 1.5 * s]   # probe x-positions, y = 0
    L, W, N = length, width, int(n_terms)

    def pot(px, sx, sign):
        # Sum −ln(distance) over the image lattice (truncated to ±N).
        tot = 0.0
        for m in range(-N, N + 1):
            for x_img in (sx + 2 * m * L, -sx + (2 * m + 1) * L):
                dx2 = (px - x_img) ** 2
                for k in range(-N, N + 1):
                    y_img = k * W
                    d2 = dx2 + y_img * y_img
                    if d2 > 1e-30:
                        tot += -0.5 * math.log(d2)
        return sign * tot

    # Current +I at outer probe 1, −I at outer probe 4; sense at inner 2 & 3.
    v2 = pot(xs[1], xs[0], 1.0) + pot(xs[1], xs[3], -1.0)
    v3 = pot(xs[2], xs[0], 1.0) + pot(xs[2], xs[3], -1.0)
    g = (v2 - v3) / (2.0 * math.pi)
    g_inf = math.log(2) / math.pi
    if g <= 0:
        return 1.0
    return g_inf / g


def _enrich_point(
    pt: Dict,
    length: Optional[float],
    width: Optional[float],
    thickness: Optional[float],
    geometry: str = "bar",
    spacing: Optional[float] = None,
    size_factor: float = 1.0,
) -> None:
    """Add resistivity (Ω·cm) and conductivity (S/cm). Dimensions are in cm.

    geometry "bar": rectangular bar — uniform unidirectional current,
                    ρ = R·(W·t)/L  (needs length, width, thickness).
    geometry "vdp": van der Pauw — arbitrary flat shape of uniform thickness,
                    ρ = (π·t / ln 2)·R  (needs thickness only).
    geometry "4pp": in-line 4-point probe (collinear) — radial current.
                    ρ = (π/ln 2)·t·R · F_t · size_factor, where F_t is a smooth
                    thickness factor (bridges thin↔bulk via t/s) and size_factor
                    is the finite-sheet geometric correction (collinear_4pp_size_factor).
    """
    import math
    r = pt.get("resistance")
    pt.setdefault("resistivity", None)
    pt.setdefault("conductivity", None)
    if r is None or r <= 0:
        return
    rho = None
    if geometry == "vdp":
        if thickness and thickness > 0:
            rho = (math.pi * thickness / math.log(2)) * r
    elif geometry == "4pp":
        if thickness and thickness > 0:
            base = (math.pi / math.log(2)) * thickness * r       # thin, infinite sheet
            f_t = 1.0
            if spacing and spacing > 0:                          # smooth thickness factor
                ts = thickness / spacing
                denom = math.log(math.sinh(ts) / math.sinh(ts / 2.0))
                if denom > 0:
                    f_t = math.log(2) / denom                    # →1 thin, →bulk for large t/s
            rho = base * f_t * (size_factor or 1.0)              # × finite-sheet correction
    else:  # rectangular bar
        if length and width and thickness and length > 0:
            area = width * thickness
            if area > 0:
                rho = r * area / length
    pt["resistivity"] = rho
    pt["conductivity"] = (1.0 / rho) if rho else None

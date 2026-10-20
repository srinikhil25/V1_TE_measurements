"""
Singleton wrappers around the instrument layer.

SeebeckService  — wraps MeasurementSessionManager (runs its own thread).
IV sweep        — blocking run with progress/abort, DB persistence, linear fit.
"""

import hashlib
import json
import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# I-V run control: set while a sweep is driving the 2401, plus an abort
# request the app can raise from any thread (logout / exit).
_iv_active = threading.Event()
_iv_abort = threading.Event()

# Held while checking for, and claiming, the instruments for a new run. The
# Seebeck run and the I-V sweep open their own sessions to the same GPIB
# instruments (2700, GPIB 24), so only one of them may run at a time.
_run_claim = threading.Lock()

IV_BLOCKS_SEEBECK = ("An I-V sweep is running. Wait for it to finish — the Seebeck "
                     "run and the sweep share the GPIB instruments.")
SEEBECK_BLOCKS_IV = ("A Seebeck run is in progress. Stop it first — the Seebeck run "
                     "and the sweep share the GPIB instruments.")

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
            cls._instance.last_error = None
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

        self.last_error = None
        with _run_claim:
            if _iv_active.is_set():
                self.last_error = IV_BLOCKS_SEEBECK
                return False
            mgr = self._manager()
            if mgr.session_active:
                self.last_error = "A Seebeck run is already active."
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


#: Below this many valid points R² is trivially high, so no ohmic verdict
#: is given (CALC-4).
MIN_OHMIC_POINTS = 5


def _valid_iv_count(points: List[Dict]) -> int:
    return sum(1 for p in points
               if p.get("current") is not None and p.get("voltage") is not None
               and abs(p["current"]) > 1e-12)


def _ohmic_status(R_squared: Optional[float], n_points: Optional[int] = None) -> str:
    """"ohmic" · "check_contacts" · "non_ohmic" · "too_few_points" · "unknown".

    ``n_points`` is the number of valid (I, V) points behind the fit; with
    fewer than MIN_OHMIC_POINTS the linearity can't be judged.
    """
    if n_points is not None and n_points < MIN_OHMIC_POINTS:
        return "too_few_points"
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

def iv_running() -> bool:
    """True while an I-V sweep is driving the 2401."""
    return _iv_active.is_set()


def request_iv_abort() -> None:
    """Ask a running I-V sweep to stop at the next point (thread-safe)."""
    _iv_abort.set()


def _seebeck_running() -> bool:
    try:
        from ..instruments.session_manager import _managers
        return any(m.is_running() for m in list(_managers))
    except Exception:
        return False


def any_measurement_running() -> bool:
    """True while a Seebeck run or an I-V sweep is active."""
    return _seebeck_running() or _iv_active.is_set()


def stop_all_measurements(timeout_s: float = 30.0) -> bool:
    """Stop every running measurement and switch the sources off.

    Called on logout and application exit. Returns True if everything stopped
    within the timeout.
    """
    ok = True
    try:
        from ..instruments.session_manager import shutdown_all_sessions
        ok = shutdown_all_sessions(timeout_s=timeout_s)
    except Exception as exc:
        logger.critical("Stopping Seebeck run failed: %s", exc)
        ok = False
    if _iv_active.is_set():
        logger.warning("Stopping running I-V sweep")
        _iv_abort.set()
        deadline = time.monotonic() + timeout_s
        while _iv_active.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)
        if _iv_active.is_set():
            logger.critical("I-V sweep did not stop within %.0f s", timeout_s)
            ok = False
    return ok


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

    Each point is saved to the database as soon as it is measured, so an
    abort or crash keeps every point taken so far. The stored status is
    "finished", "stopped" (aborted by the operator) or "error".

    Returns:
        {
            "points": [{"voltage", "current", "resistance", "resistivity", "conductivity"}, ...],
            "fit_R": float or None,
            "fit_R_squared": float or None,
            "ohmic_status": "ohmic" | "check_contacts" | "non_ohmic" | "unknown",
            "temperature_C": float or None,
            "measurement_id": int or None,
            "aborted": bool,
            "db_warning": str or None,   # set when the sweep was NOT (fully) saved
        }
    """
    if points < 2:
        raise ValueError("points must be >= 2")
    with _run_claim:
        if _iv_active.is_set():
            raise RuntimeError("An I-V sweep is already running.")
        if _seebeck_running():
            raise RuntimeError(SEEBECK_BLOCKS_IV)
        _iv_abort.clear()
        _iv_active.set()

    def _aborted() -> bool:
        return _iv_abort.is_set() or bool(abort_check and abort_check())

    results: List[Dict] = []
    measurement_id: Optional[int] = None
    db = None
    measurement_obj = None
    db_warning: Optional[str] = None
    temperature_C: Optional[float] = None
    outcome = "error"
    end_reason: Optional[str] = None
    system = None
    started_audited = False
    from ..core import audit

    try:
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
            end_reason = "Failed to connect to instruments."
            raise RuntimeError(end_reason)

        # Settings snapshot (software, host, config, instrument *IDN?).
        from ..core.run_context import build_run_context
        identify = getattr(system, "identify", None)
        run_context = build_run_context(identify() if callable(identify) else {})

        rho_model = resistivity_model(geometry, length, width, thickness, spacing)

        # Optional: configure 2700 for temperature and read once at start
        try:
            if system.k2700.connected:
                system.k2700.configure_measurement()
            temperature_C = system.get_temperature_avg_c()
        except Exception:
            pass

        # Create DB record (lab may be None, e.g. super_admin)
        if _user_id is None:
            db_warning = "Not signed in: this sweep is NOT saved to History."
        else:
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
                        "temperature_C": temperature_C,
                        "resistivity_model": rho_model,
                        "run_context": run_context,
                    }, default=str),
                    started_at=datetime.utcnow(),
                )
                db.add(measurement_obj)
                db.commit()
                db.refresh(measurement_obj)
                measurement_id = measurement_obj.id
            except Exception as e:
                logger.error("IV: failed to create Measurement: %s", e)
                db_warning = f"Database error: this sweep is NOT saved to History ({e})."
                if db:
                    db.rollback()
                    db.close()
                db = None
                measurement_obj = None

        audit.record(
            "run_started", measurement_id=measurement_id, user_id=_user_id,
            username=operator,
            details={"type": "iv", "sample_id": sample_id, "source_mode": source_mode,
                     "start": start, "stop": stop, "points": points,
                     "current_limit": current_limit, "voltage_limit": voltage_limit,
                     "four_wire": four_wire, "geometry": geometry,
                     "saved": measurement_id is not None})
        started_audited = True

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
        # ρ = k·R for this sample (computed once; it depends only on the
        # geometry). Corrections that could not be applied are listed in it.
        t_start = time.monotonic()
        for idx, level in enumerate(sequence):
            if _aborted():
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
            _enrich_point(pt, length, width, thickness, geometry, spacing, model=rho_model)
            results.append(pt)
            # Persist every point immediately.
            if db is not None and measurement_obj is not None:
                try:
                    from ..models.db_models import MeasurementRow
                    db.add(MeasurementRow(
                        measurement_id=measurement_obj.id,
                        seq=len(results),
                        elapsed_s=int(time.monotonic() - t_start),
                        data_json=json.dumps(pt, default=str),
                    ))
                    db.commit()
                except Exception as e:
                    logger.error("IV: failed to insert MeasurementRow: %s", e)
                    db_warning = ("Database write failed: some points may be "
                                  f"missing from History ({e}).")
                    db.rollback()
            if progress_callback:
                progress_callback(idx, pt)
        system.k2401.output_off()
        if _aborted():
            outcome, end_reason = "stopped", "Aborted by operator"
        else:
            outcome = "finished"
    except Exception as exc:
        logger.error("IV sweep error: %s", exc)
        outcome = "error"
        end_reason = end_reason or f"Error: {exc}"
        raise
    finally:
        if system is not None:
            if system.k2401.connected:
                try:
                    system.k2401.output_off()
                except Exception:
                    logger.critical("IV: 2401 output-off failed during cleanup")
            try:
                system.disconnect_all()
            except Exception as exc:
                logger.error("IV: disconnect_all failed: %s", exc)
        if db is not None and measurement_obj is not None:
            try:
                from ..models.db_models import MeasurementIntegrity

                # Integrity hash
                if results:
                    canonical = json.dumps(
                        results, sort_keys=True, separators=(",", ":"), default=str
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
                measurement_obj.status = outcome
                measurement_obj.end_reason = end_reason
                measurement_obj.finished_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                logger.error("IV: failed to finalise DB: %s", e)
                db.rollback()
            finally:
                db.close()
        if started_audited:
            audit.record(
                "run_ended", measurement_id=measurement_id, user_id=_user_id,
                username=operator, reason=end_reason,
                details={"type": "iv", "outcome": outcome, "points": len(results),
                         "db_warning": db_warning})
        _iv_active.clear()

    # Fit and ohmic status
    fit_R, fit_R_squared = _linear_fit_resistance(results)
    n_valid = _valid_iv_count(results)
    ohmic = _ohmic_status(fit_R_squared, n_valid)

    return {
        "points": results,
        "fit_R": fit_R,
        "fit_R_squared": fit_R_squared,
        "ohmic_status": ohmic,
        "n_valid": n_valid,
        "resistivity_model": rho_model,
        "temperature_C": temperature_C,
        "measurement_id": measurement_id,
        "aborted": outcome == "stopped",
        "db_warning": db_warning,
    }


def fourpp_size_correction(s, length, width) -> tuple:
    """(factor, note). ``note`` is None when the finite-sheet correction was
    applied, else the reason it was not (factor is then 1.0)."""
    if not s or s <= 0:
        return 1.0, "probe spacing s is not set"
    if not (length and width) or length <= 0 or width <= 0:
        return 1.0, "sample length/width are not set"
    if length <= 3.0 * s:
        return 1.0, (f"the probe array (3·s = {3 * s:g} cm) does not fit in the sample "
                     f"length ({length:g} cm)")
    c = collinear_4pp_size_factor(s, length, width)
    if c == 1.0:
        return 1.0, "the image-sum correction could not be computed"
    return c, None


def resistivity_model(geometry: str, length: Optional[float], width: Optional[float],
                      thickness: Optional[float], spacing: Optional[float] = None,
                      size_factor: Optional[float] = None) -> Dict:
    """How resistivity follows from resistance for this sample: ρ = k · R.

    Returns {"geometry", "rho_per_ohm" (k in Ω·cm per Ω, None if ρ can't be
    computed), "size_factor", "thickness_factor", "notes"}. ``notes`` lists
    every correction that could NOT be applied and why, so a fallback value is
    never mistaken for a corrected one (CALC-1). Dimensions in cm. Pass a
    precomputed ``size_factor`` to skip the 4PP image sum.
    """
    import math
    geometry = geometry if geometry in ("bar", "vdp", "4pp") else "bar"
    out = {"geometry": geometry, "rho_per_ohm": None, "size_factor": None,
           "thickness_factor": None, "notes": []}
    notes = out["notes"]

    def pos(v):
        return v is not None and v > 0

    if geometry == "vdp":
        if not pos(thickness):
            notes.append("Resistivity not computed: van der Pauw needs the thickness.")
            return out
        out["rho_per_ohm"] = math.pi * thickness / math.log(2)
    elif geometry == "4pp":
        if not pos(thickness):
            notes.append("Resistivity not computed: the 4-point probe needs the thickness.")
            return out
        k = (math.pi / math.log(2)) * thickness                 # thin, infinite sheet
        f_t = None
        if pos(spacing):
            ts = thickness / spacing
            denom = math.log(math.sinh(ts) / math.sinh(ts / 2.0))
            if denom > 0:
                f_t = math.log(2) / denom                         # →1 thin, →bulk for large t/s
        if f_t is None:
            notes.append("Thickness correction F(t/s) NOT applied: "
                         + ("probe spacing s is not set." if not pos(spacing)
                            else "it could not be computed."))
        else:
            k *= f_t
        out["thickness_factor"] = f_t
        if size_factor is not None:
            c, why = size_factor, None
        else:
            c, why = fourpp_size_correction(spacing, length, width)
        if why:
            notes.append(f"Finite-size correction NOT applied ({why}): "
                         "ρ is the infinite-sheet value.")
        else:
            out["size_factor"] = c
            k *= c
        out["rho_per_ohm"] = k
    else:
        missing = [n for n, v in (("length", length), ("width", width),
                                  ("thickness", thickness)) if not pos(v)]
        if missing:
            notes.append("Resistivity not computed: the bar geometry needs "
                         + ", ".join(missing) + " > 0.")
            return out
        out["rho_per_ohm"] = width * thickness / length
    return out


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
    size_factor: Optional[float] = 1.0,
    model: Optional[Dict] = None,
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

    ``model`` (from resistivity_model) avoids recomputing the geometry per point.
    """
    if model is None:
        model = resistivity_model(geometry, length, width, thickness, spacing,
                                  size_factor=size_factor)
    r = pt.get("resistance")
    pt.setdefault("resistivity", None)
    pt.setdefault("conductivity", None)
    if r is None or r <= 0:
        return
    k = model.get("rho_per_ohm")
    rho = r * k if k else None
    pt["resistivity"] = rho
    pt["conductivity"] = (1.0 / rho) if rho else None

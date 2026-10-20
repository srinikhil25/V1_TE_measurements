import hashlib
import json
import logging
import threading
import time
import weakref
from datetime import datetime
from typing import Any, Dict, List, Optional

from .instrument import SeebeckSystem
from .safety import SafetyMonitor
from .seebeck_analysis import binned_seebeck_analysis, polarity_verdict, polarity_vote
from .visa_guard import failure_summary, reset_instrument_health
from ..core import audit
from ..core.config import get_config
from ..core.run_context import build_run_context
from ..core.database import get_session
from ..models.db_models import Measurement, MeasurementIntegrity, MeasurementRow

logger = logging.getLogger(__name__)

# Differential method: ΔT/T₀ should be small for linear S. Warn if above this.
LARGE_GRADIENT_RATIO = 0.1

# Run outcomes, stored in Measurement.status (and session_status for the UI).
STATUS_FINISHED = "finished"      # profile + cooling tail completed
STATUS_STOPPED = "stopped"        # operator pressed Stop / closed the app
STATUS_ABORTED = "aborted"        # software safety layer tripped
STATUS_ERROR = "error"            # instrument / connection failure

# Every manager ever created, so an application-level shutdown can stop any
# active run (see shutdown_all_sessions).
_managers: "weakref.WeakSet[MeasurementSessionManager]" = weakref.WeakSet()


class MeasurementSessionManager:
    def __init__(self):
        self.session_active = False
        self.session_thread = None
        self.session_data: List[Dict] = []
        self.session_status = "idle"
        self.session_params: Optional[Dict] = None
        self.session_start_time = None
        self.seebeck_system = SeebeckSystem()
        self.lock = threading.Lock()
        self.session_phase = None  # pre, ramp_up, hold, ramp_down, cooling_tail
        self.session_step = 0
        self.session_total_steps = 0
        self.session_metadata: Dict[str, Any] = {}  # sample_id, operator, notes, target_T0_K, probe_arrangement
        # DB linkage (set from params in start_session, used inside _run_session)
        self._db_user_id: Optional[int] = None
        self._db_lab_id: Optional[int] = None
        self._db_measurement_id: Optional[int] = None
        # Run outcome bookkeeping
        self._stop_requested = False
        self.end_reason: Optional[str] = None      # why the run ended (abort/error text)
        self.db_warning: Optional[str] = None      # set when the run is NOT being saved
        self.invalid_reads = 0                     # rows with an invalid thermocouple
        self._polarity_votes = [0, 0]              # [wrong sign, right sign]
        self.polarity_warning: Optional[str] = None  # hot/cold TCs look swapped
        self._run_context: Optional[Dict[str, Any]] = None
        _managers.add(self)

    def start_session(self, params: Dict):
        if self.session_active:
            return False  # Already running
        # A previous worker thread may still be unwinding its cleanup (its
        # finally block releases the instruments). Wait for it to finish
        # before reconnecting, or the two runs race on the same VISA sessions.
        if self.session_thread is not None and self.session_thread.is_alive():
            self.session_thread.join(timeout=25)
            if self.session_thread.is_alive():
                logger.error("Previous session thread did not exit; cannot start.")
                return False
        self.session_thread = None
        self.session_active = True
        self._stop_requested = False
        self.end_reason = None
        self.db_warning = None
        self.invalid_reads = 0
        self.polarity_warning = None
        self._polarity_votes = [0, 0]              # [wrong sign, right sign]
        self.session_data = []
        self.session_status = "running"
        self.session_params = params
        self.session_start_time = time.time()
        # Capture user/lab context for DB persistence (if provided)
        self._db_user_id = params.get("_user_id")
        self._db_lab_id = params.get("_lab_id")
        self._db_measurement_id = None
        self.session_metadata = {
            "sample_id": params.get("sample_id"),
            "operator": params.get("operator"),
            "notes": params.get("notes"),
            "target_T0_K": params.get("target_T0_K"),
            "probe_arrangement": params.get("probe_arrangement")
            or params.get("probe_mode"),
        }
        # Non-daemon on purpose: if the process tries to exit mid-run, the
        # worker keeps control of the heater until shutdown_all_sessions()
        # stops it cleanly, rather than being killed with the heater on.
        self.session_thread = threading.Thread(
            target=self._run_session, args=(params,), name="seebeck-session")
        self.session_thread.start()
        return True

    def stop_session(self, timeout_s: float = 25.0):
        """Signal the worker to stop and wait for it to release the instruments.

        The worker thread's ``finally`` block performs output_off +
        disconnect_all itself. stop_session must NOT disconnect here as well,
        or the two threads race on the same VISA sessions and leave them in a
        corrupted, half-closed state.
        """
        self._stop_requested = True
        self.session_active = False
        self.session_status = STATUS_STOPPED
        self.session_phase = None
        self.session_step = 0
        self.session_total_steps = 0
        if self.session_thread is not None:
            # Wait up to one VISA timeout so an in-flight instrument query can
            # return and the worker can clean up. Normally returns in well
            # under a second.
            self.session_thread.join(timeout=timeout_s)
            if self.session_thread.is_alive():
                logger.warning(
                    "Session thread still running after stop; instruments "
                    "may not be fully released."
                )
            else:
                self.session_thread = None

    def is_running(self) -> bool:
        """True while a run is active or its worker is still shutting down."""
        return bool(self.session_active or (
            self.session_thread is not None and self.session_thread.is_alive()))

    def cleanup(self):
        """Force the manager back to a clean, disconnected state.

        Used by the Seebeck page 'Reset' action. Safe to call when idle —
        output_off / disconnect_all are no-ops on already-disconnected
        instruments.
        """
        if self.session_active:
            self.stop_session()
        elif self.session_thread is not None and self.session_thread.is_alive():
            self.session_thread.join(timeout=25)
        self.session_thread = None
        # Belt-and-braces release in case the worker never ran its finally.
        try:
            self.seebeck_system.output_off()
        except Exception as exc:
            logger.error("cleanup output_off failed: %s", exc)
        try:
            self.seebeck_system.disconnect_all()
        except Exception as exc:
            logger.error("cleanup disconnect_all failed: %s", exc)
        self.session_status = "idle"
        self.session_phase = None
        self.session_step = 0
        self.session_total_steps = 0

    def get_data(self) -> List[Dict]:
        with self.lock:
            return list(self.session_data)

    def get_session_metadata(self) -> Dict[str, Any]:
        return dict(self.session_metadata)

    def get_binned_analysis(self) -> List[Dict]:
        """Binned S from linear fit ΔV vs ΔT per T₀ bin, with uncertainty."""
        with self.lock:
            data = list(self.session_data)
        return binned_seebeck_analysis(data, bin_width_k=10.0)

    def get_status(self) -> Dict:
        out = {
            "active": self.session_active,
            "status": self.session_status,
            "params": self.session_params,
            "start_time": self.session_start_time,
            "data_count": len(self.session_data),
            "end_reason": self.end_reason,
            "db_warning": self.db_warning,
            "invalid_reads": self.invalid_reads,
            "polarity_warning": self.polarity_warning,
            "instrument_errors": failure_summary() if self.session_thread else "",
            "measurement_id": self._db_measurement_id,
        }
        if self.session_total_steps and self.session_params:
            out["phase"] = self.session_phase
            out["step"] = self.session_step
            out["total_steps"] = self.session_total_steps
            interval = self.session_params.get("interval", 2)
            out["estimated_remaining_s"] = max(0, (self.session_total_steps - self.session_step) * interval)
            out["estimated_total_s"] = self.session_total_steps * interval
            out["hold_time_s"] = self.session_params.get("hold_time")
        out["metadata"] = self.session_metadata
        with self.lock:
            data = list(self.session_data)
        if data:
            out["warn_large_gradient"] = any(
                (r.get("delta_T_over_T0") or 0) > LARGE_GRADIENT_RATIO for r in data
            )
        return out

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    @staticmethod
    def _with_instrument_detail(reason: str) -> str:
        """Append which instrument is failing, and how, to an end reason."""
        detail = failure_summary()
        if detail and detail not in reason:
            return f"{reason} — {detail}"
        return reason

    def _heater_off_now(self, context: str) -> None:
        """Switch the heater off immediately; never raises."""
        try:
            if not self.seebeck_system.output_off():
                logger.critical("%s: heater output-off NOT confirmed", context)
        except Exception as exc:
            logger.critical("%s: heater output-off raised: %s", context, exc)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.monotonic() + max(0.0, seconds)
        while self.session_active and time.monotonic() < end:
            time.sleep(min(0.1, max(0.0, end - time.monotonic())))

    def _open_db_record(self, params: Dict):
        """Create the Measurement row. Returns (db, measurement) or (None, None)."""
        if self._db_user_id is None:
            self.db_warning = "Not signed in — this run is NOT being saved to History."
            logger.warning(self.db_warning)
            return None, None
        db = None
        try:
            db = get_session()
            measurement = Measurement(
                user_id=self._db_user_id,
                lab_id=self._db_lab_id,          # may be None (e.g. super_admin)
                type="seebeck",
                status="running",
                sample_id=self.session_metadata.get("sample_id"),
                operator=self.session_metadata.get("operator"),
                notes=self.session_metadata.get("notes"),
                params_json=json.dumps(
                    {**{k: v for k, v in params.items() if not k.startswith("_")},
                     "run_context": self._run_context}, default=str),
                started_at=datetime.utcnow(),
            )
            db.add(measurement)
            db.commit()
            db.refresh(measurement)
            self._db_measurement_id = measurement.id
            logger.info("Measurement %s started (user_id=%s)", measurement.id, self._db_user_id)
            return db, measurement
        except Exception as exc:
            logger.error("Failed to create Measurement in DB: %s", exc)
            self.db_warning = f"Database error — this run is NOT being saved to History ({exc})."
            if db is not None:
                try:
                    db.rollback()
                    db.close()
                except Exception:
                    pass
            self._db_measurement_id = None
            return None, None

    def _run_session(self, params: Dict):
        db = None
        measurement_obj: Optional[Measurement] = None
        outcome = STATUS_ERROR
        self._run_context = None
        started_audited = False
        try:
            cfg = get_config()
            reset_instrument_health()          # failures are reported per run
            # Connect to all instruments
            if not self.seebeck_system.connect_all():
                failed = getattr(self.seebeck_system, "connect_failures", None) or []
                self.end_reason = (("Could not connect to " + "; ".join(failed) + ".")
                                   if failed else
                                   "Failed to connect to one or more instruments.") + \
                    " Check the instrument is on and connected, then try again."
                self.session_status = f"error: {self.end_reason}"
                self.session_active = False
                logger.error("Failed to connect to instruments. Session aborted.")
                return

            # Settings snapshot: software, host, rig config, instrument *IDN?.
            # Taken before initialise so no query interleaves with heater control.
            # A Stop request cancels the retry of a timed-out command.
            set_abort = getattr(self.seebeck_system, "set_abort_check", None)
            if callable(set_abort):
                set_abort(lambda: self._stop_requested)
            identify = getattr(self.seebeck_system, "identify", None)
            instruments = identify() if callable(identify) else {}
            self._run_context = build_run_context(instruments, cfg)

            # Apply per-geometry heater limits (voltage compliance + current cap)
            # and route the relay BEFORE initialise, so compliance is set at
            # output-on. Channel selection for the TCs happens further below.
            _probe_mode_early = (params.get("probe_mode") or "in_plane").lower()
            self.seebeck_system.pk160_current_unit = params.get("pk160_current_unit") or "mA"
            self.seebeck_system.set_heater_mode(_probe_mode_early)

            # Initialize all instruments
            try:
                self.seebeck_system.initialize_all()
            except Exception as e:
                self.end_reason = self._with_instrument_detail(
                    f"Failed to initialize instruments: {e}")
                self.session_status = f"error: {self.end_reason}"
                self.session_active = False
                logger.error(self.end_reason)
                return  # instrument release handled by the finally block
            interval = params["interval"]
            pre_time = params["pre_time"]
            # start_volt/stop_volt: current setpoints I₀ and I (mA or A per pk160_current_unit), not voltage.
            start_volt = params["start_volt"]
            stop_volt = params["stop_volt"]
            inc_rate = params["inc_rate"]
            dec_rate = params["dec_rate"]
            hold_time = params["hold_time"]
            cooling_target_delta_t = float(params.get("cooling_target_delta_t") or 5.0)
            cooling_timeout_s = int(params.get("cooling_timeout_s") or 600)
            stabilization_delay_s = float(params.get("stabilization_delay_s") or 0.0)
            pk160_unit = params.get("pk160_current_unit") or "mA"
            self.seebeck_system.pk160_current_unit = pk160_unit

            # Seebeck geometry: select the 2700 thermocouple channels (rig config).
            probe_mode = (params.get("probe_mode") or "in_plane").lower()
            temp1_channel, temp2_channel = cfg.tc_channels(probe_mode)
            logger.info(
                "Seebeck geometry: %s (2700 channels T1=%s, T2=%s)",
                probe_mode, temp1_channel, temp2_channel,
            )

            safety = SafetyMonitor.from_config(cfg.safety)
            logger.info(
                "Safety limits: T_max=%.1f °C, rise ≤ %.1f °C/min over %.0f s, "
                "abort after %d invalid reads",
                safety.max_temperature_C, safety.max_rise_rate_C_per_min,
                safety.rate_window_s, safety.max_consecutive_invalid_reads,
            )

            # ── Create Measurement row in DB ─────────────────────────────
            db, measurement_obj = self._open_db_record(params)
            audit.record(
                "run_started", measurement_id=self._db_measurement_id,
                user_id=self._db_user_id, username=self.session_metadata.get("operator"),
                details={"type": "seebeck",
                         "sample_id": self.session_metadata.get("sample_id"),
                         "probe_mode": probe_mode,
                         "params": {k: v for k, v in params.items() if not k.startswith("_")},
                         "safety": cfg.to_dict()["safety"],
                         "saved": self._db_measurement_id is not None})
            started_audited = True

            # Segment step counts: pre, ramp-up, hold (plateau), ramp-down. Each step ~interval seconds.
            # hold_time is the plateau duration only (e.g. 200 s at peak I); total run = pre + ramp_up + hold + ramp_down.
            kaisuu1 = int(pre_time // interval) if pre_time % interval == 0 else int(pre_time // interval + 1)
            ramp_up_sec = (stop_volt - start_volt) / inc_rate if inc_rate > 0 else 0
            kaisuu2 = int(ramp_up_sec // interval) if ramp_up_sec % interval == 0 else int(ramp_up_sec // interval + 1)
            kaisuu3 = int(hold_time // interval) if hold_time % interval == 0 else int(hold_time // interval + 1)  # plateau steps
            ramp_down_sec = (stop_volt - start_volt) / dec_rate if dec_rate > 0 else 0
            kaisuu4 = int(ramp_down_sec // interval) if ramp_down_sec % interval == 0 else int(ramp_down_sec // interval + 1)
            # Ensure ramp-up does not overshoot stop_volt
            while kaisuu2 > 0 and start_volt + inc_rate * kaisuu2 * interval > stop_volt:
                kaisuu2 -= 1
            # Ensure ramp-down does not undershoot start_volt
            while kaisuu4 > 0 and stop_volt - dec_rate * kaisuu4 * interval < start_volt:
                kaisuu4 -= 1
            # When ramp is faster than interval, we can get kaisuu2=0 and kaisuu4=0 → no ramp-down and no cooling.
            # Force at least 10 ramp-up and 10 ramp-down steps so we get a visible cooling branch (many points).
            if start_volt < stop_volt:
                if kaisuu2 == 0:
                    kaisuu2 = 10
                if kaisuu4 == 0:
                    kaisuu4 = 10

            total_steps = kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4
            self.session_total_steps = total_steps
            volt = start_volt
            kaisuu = 1
            start_time = time.time()
            mono_start = time.monotonic()
            cooling_tail_start_time = None
            safety_tripped = False
            instrument_failed = False
            temf_fail_streak = 0

            while self.session_active:
                loop_start = time.time()
                elapsed_time = int(time.time() - start_time)
                # Current setpoint (start_volt/stop_volt are I₀/I in mA or A per pk160_current_unit; we pass current, not voltage).
                # After programmed steps, cooling tail: set current to 0 so power supply stops heating and sample cools.
                if kaisuu > total_steps:
                    phase = "cooling_tail"
                    volt = start_volt  # for display only; we send 0 to hardware below
                else:
                    self.session_step = kaisuu
                    if 1 <= kaisuu <= kaisuu1:
                        volt = start_volt
                        phase = "pre"
                    elif kaisuu1 + 1 <= kaisuu <= kaisuu1 + kaisuu2:
                        volt = min(volt + inc_rate * interval, stop_volt)
                        phase = "ramp_up"
                    elif kaisuu1 + kaisuu2 + 1 <= kaisuu <= kaisuu1 + kaisuu2 + kaisuu3:
                        volt = stop_volt
                        phase = "hold"
                    elif kaisuu1 + kaisuu2 + kaisuu3 + 1 <= kaisuu <= kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4:
                        # Ramp down linearly over kaisuu4 steps so current never jumps to zero in one step
                        step_index = kaisuu - (kaisuu1 + kaisuu2 + kaisuu3)  # 1-based step within ramp_down
                        volt = stop_volt - (stop_volt - start_volt) * (step_index / kaisuu4)
                        phase = "ramp_down"
                    else:
                        volt = start_volt
                        phase = "pre"
                self.session_phase = phase

                # During cooling tail, turn power supply output OFF so the sample can cool (set_current(0) alone may not disable the output).
                if phase == "cooling_tail":
                    self.seebeck_system.output_off()
                else:
                    current_setpoint = volt
                    self.seebeck_system.set_current(current_setpoint)
                if stabilization_delay_s > 0:
                    self._sleep_interruptible(stabilization_delay_s)
                result = self.seebeck_system.measure_all(
                    temp1_channel=temp1_channel,
                    temp2_channel=temp2_channel,
                )

                # ── Safety layer: validate readings, enforce limits ──────
                check = safety.check(time.monotonic() - mono_start,
                                     result.get("Temp1_C"), result.get("Temp2_C"))
                if check.abort:
                    # Heater off FIRST — before any bookkeeping.
                    self._heater_off_now("Safety abort")
                    safety_tripped = True
                    self.end_reason = self._with_instrument_detail(
                        f"Safety abort: {check.abort_reason}")
                    logger.critical(self.end_reason)
                if not check.valid:
                    self.invalid_reads += 1
                    logger.warning("Invalid thermocouple reading: %s", check.flag_text)

                t1, t2 = check.t1, check.t2
                temf_mv = result["TEMF_mV"]
                if check.valid:
                    delta_t = t2 - t1
                    t0_c = (t1 + t2) / 2.0
                    t0_k = t0_c + 273.15
                else:
                    # Never substitute a default temperature: an invalid read
                    # yields no ΔT, T₀ or S for this row.
                    delta_t = t0_c = t0_k = None
                # Seebeck S = ΔV/ΔT in µV/K; ΔV in mV, ΔT in °C (= K for difference). Guard small ΔT.
                # When S is not computed, the row says why (CALC-1).
                delta_t_threshold = 0.01
                s_uv_per_k = None
                if delta_t is None:
                    s_note = "invalid thermocouple reading"
                elif temf_mv is None:
                    s_note = "no TEMF reading"
                elif abs(delta_t) < delta_t_threshold:
                    s_note = f"|ΔT| below {delta_t_threshold:g} K"
                else:
                    s_uv_per_k = (temf_mv * 1000.0) / delta_t  # mV -> µV, °C = K
                    s_note = None
                # ΔT/T₀: differential method assumes small gradient; warn if large
                delta_t_over_t0 = (abs(delta_t) / t0_k) if (delta_t is not None and t0_k) else None
                branch = "cooling" if phase in ("ramp_down", "cooling_tail") else "heating"
                heater_v = result.get("HeaterV_V")
                heater_i = result.get("HeaterI_A")
                row = {
                    "Time [s]": elapsed_time,
                    "TEMF [mV]": temf_mv,
                    "Temp1 [oC]": t1,
                    "Temp2 [oC]": t2,
                    "Delta Temp [oC]": delta_t,
                    "T0 [oC]": t0_c,
                    "T0 [K]": t0_k,
                    "delta_T_over_T0": round(delta_t_over_t0, 6) if delta_t_over_t0 is not None else None,
                    "S [µV/K]": s_uv_per_k,
                    "S_note": s_note,
                    "Heater V [V]": round(heater_v, 4) if heater_v is not None else None,
                    "Heater I [A]": round(heater_i, 4) if heater_i is not None else None,
                    "branch": branch,
                    "valid": check.valid,
                    "flag": check.abort_reason or check.flag_text,
                }
                with self.lock:
                    self.session_data.append(row)
                    seq = len(self.session_data)
                vote = polarity_vote(row)
                if vote and self.polarity_warning is None:
                    self._polarity_votes[0 if vote > 0 else 1] += 1
                    self.polarity_warning = polarity_verdict(*self._polarity_votes)
                    if self.polarity_warning:
                        logger.warning("Polarity check: %s", self.polarity_warning)

                # Persist every point immediately — a crash loses at most the
                # point in flight (cheap at ~1 point per second).
                if db is not None and self._db_measurement_id is not None:
                    try:
                        db.add(MeasurementRow(
                            measurement_id=self._db_measurement_id,
                            seq=seq,
                            elapsed_s=elapsed_time,
                            data_json=json.dumps(row, default=str),
                        ))
                        db.commit()
                    except Exception as e:
                        logger.error("Failed to insert MeasurementRow: %s", e)
                        self.db_warning = f"Database write failed — some points may be missing from History ({e})."
                        try:
                            db.rollback()
                        except Exception:
                            pass

                if safety_tripped:
                    break

                temf_fail_streak = temf_fail_streak + 1 if temf_mv is None else 0
                if temf_fail_streak >= safety.max_consecutive_invalid_reads:
                    self._heater_off_now("Instrument failure")
                    instrument_failed = True
                    self.end_reason = self._with_instrument_detail(
                        f"Keithley 2182A gave no TEMF reading {temf_fail_streak} times "
                        "in a row — run stopped")
                    logger.error(self.end_reason)
                    break

                # Cooling tail: output already turned off above; keep measuring until |ΔT| < target or timeout
                if phase == "cooling_tail":
                    if cooling_tail_start_time is None:
                        cooling_tail_start_time = time.time()
                    if delta_t is not None and abs(delta_t) < cooling_target_delta_t:
                        logger.info(f"Cooling tail finished: |ΔT| = {abs(delta_t):.2f} °C < target {cooling_target_delta_t} °C")
                        break
                    if time.time() - cooling_tail_start_time > cooling_timeout_s:
                        logger.warning("Cooling tail timeout after %s s; |ΔT| = %s",
                                       cooling_timeout_s,
                                       f"{abs(delta_t):.2f} °C" if delta_t is not None else "unknown")
                        break
                    self._sleep_interruptible(interval - (time.time() - loop_start))
                    continue

                kaisuu += 1
                self._sleep_interruptible(interval - (time.time() - loop_start))

            self._heater_off_now("End of run")  # heater off immediately
            if safety_tripped:
                outcome = STATUS_ABORTED
                self.session_status = f"error: {self.end_reason}"
            elif instrument_failed:
                outcome = STATUS_ERROR
                self.session_status = f"error: {self.end_reason}"
            elif self._stop_requested:
                outcome = STATUS_STOPPED
                self.end_reason = self.end_reason or "Stopped by operator"
                self.session_status = STATUS_STOPPED
            else:
                outcome = STATUS_FINISHED
                self.session_status = STATUS_FINISHED
            self.session_active = False
            self.session_phase = None
            self.session_step = 0
            self.session_total_steps = 0
        except Exception as e:
            outcome = STATUS_ERROR
            self.end_reason = self._with_instrument_detail(f"Error: {e}")
            logger.exception("Seebeck session error")
            self.session_status = f"error: {str(e)}"
            self.session_active = False
            self.session_phase = None
            self.session_step = 0
            self.session_total_steps = 0
        finally:
            # Guaranteed cleanup on EVERY exit path — normal finish, Stop,
            # safety abort, error, and failed/partial connect. Without this the
            # heater can be left ON and the GPIB instruments locked to this
            # process, forcing an app + device restart.
            self._heater_off_now("Session cleanup")
            try:
                self.seebeck_system.disconnect_all()
            except Exception as exc:
                logger.error("Cleanup disconnect_all failed: %s", exc)
            self.session_active = False
            self.session_phase = None
            self.session_step = 0
            self.session_total_steps = 0
            if db is not None and measurement_obj is not None:
                self._finalise_db(db, measurement_obj, outcome)
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
            if started_audited:
                with self.lock:
                    n_points = len(self.session_data)
                audit.record(
                    "run_ended", measurement_id=self._db_measurement_id,
                    user_id=self._db_user_id, username=self.session_metadata.get("operator"),
                    reason=self.end_reason,
                    details={"type": "seebeck", "outcome": outcome, "points": n_points,
                             "invalid_reads": self.invalid_reads,
                             "polarity_warning": self.polarity_warning,
                             "db_warning": self.db_warning})

    def _finalise_db(self, db, measurement_obj: Measurement, outcome: str) -> None:
        """Record the outcome, end reason and integrity hash of the run."""
        try:
            with self.lock:
                data_copy = list(self.session_data)
            if data_copy:
                canonical = json.dumps(data_copy, sort_keys=True, separators=(",", ":"), default=str)
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                integ = (
                    db.query(MeasurementIntegrity)
                    .filter_by(measurement_id=measurement_obj.id)
                    .first()
                )
                if integ is None:
                    db.add(MeasurementIntegrity(measurement_id=measurement_obj.id, data_hash=digest))
                else:
                    integ.data_hash = digest
            measurement_obj.status = outcome
            measurement_obj.end_reason = self.end_reason
            measurement_obj.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            logger.error("Failed to finalise Measurement in DB: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass


def shutdown_all_sessions(timeout_s: float = 30.0) -> bool:
    """Stop every active Seebeck run (heater off) — call before the app exits.

    Returns True if every worker exited within the timeout.
    """
    ok = True
    for mgr in list(_managers):
        if mgr.is_running():
            logger.warning("Application shutdown: stopping active Seebeck run")
            mgr.stop_session(timeout_s=timeout_s)
            if mgr.is_running():
                ok = False
                logger.critical("Seebeck worker did not stop within %.0f s; forcing heater off", timeout_s)
                mgr._heater_off_now("Forced shutdown")
    return ok

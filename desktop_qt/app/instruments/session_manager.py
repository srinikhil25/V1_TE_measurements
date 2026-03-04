import threading
import time
import logging
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

from .instrument import SeebeckSystem
from .seebeck_analysis import binned_seebeck_analysis
from ..core.database import get_session
from ..models.db_models import Measurement, MeasurementRow

logger = logging.getLogger(__name__)

# Differential method: ΔT/T₀ should be small for linear S. Warn if above this.
LARGE_GRADIENT_RATIO = 0.1


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

    def start_session(self, params: Dict):
        if self.session_active:
            return False  # Already running
        self.session_active = True
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
            "probe_arrangement": params.get("probe_arrangement"),
        }
        self.session_thread = threading.Thread(target=self._run_session, args=(params,))
        self.session_thread.start()
        return True

    def stop_session(self):
        self.session_active = False
        self.session_status = "stopped"
        self.session_phase = None
        self.session_step = 0
        self.session_total_steps = 0
        if self.session_thread:
            self.session_thread.join(timeout=2)
        self.seebeck_system.output_off()
        self.seebeck_system.disconnect_all()

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

    def _run_session(self, params: Dict):
        db = None
        measurement_obj: Optional[Measurement] = None
        try:
            # Connect to all instruments
            if not self.seebeck_system.connect_all():
                self.session_status = "error: Failed to connect to one or more instruments. Please check instrument connections and try again."
                self.session_active = False
                logger.error("Failed to connect to instruments. Session aborted.")
                return
            
            # Initialize all instruments
            try:
                self.seebeck_system.initialize_all()
            except Exception as e:
                self.session_status = f"error: Failed to initialize instruments: {str(e)}"
                self.session_active = False
                logger.error(f"Failed to initialize instruments: {str(e)}")
                self.seebeck_system.disconnect_all()
                return
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

            # ── Create Measurement row in DB (if user/lab known) ─────────
            if self._db_user_id is not None and self._db_lab_id is not None:
                try:
                    db = get_session()
                    measurement_obj = Measurement(
                        user_id=self._db_user_id,
                        lab_id=self._db_lab_id,
                        type="seebeck",
                        status="running",
                        sample_id=self.session_metadata.get("sample_id"),
                        operator=self.session_metadata.get("operator"),
                        notes=self.session_metadata.get("notes"),
                        params_json=json.dumps(params, default=str),
                        started_at=datetime.utcnow(),
                    )
                    db.add(measurement_obj)
                    db.commit()
                    db.refresh(measurement_obj)
                    self._db_measurement_id = measurement_obj.id
                    logger.info("Measurement %s started (user_id=%s)", measurement_obj.id, self._db_user_id)
                except Exception as e:
                    logger.error("Failed to create Measurement in DB: %s", e)
                    if db is not None:
                        db.rollback()
                        db.close()
                        db = None
                    self._db_measurement_id = None

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
            cooling_tail_start_time = None

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
                    for _ in range(int(stabilization_delay_s * 10)):
                        if not self.session_active:
                            break
                        time.sleep(0.1)
                result = self.seebeck_system.measure_all()
                t1 = result["Temp1_C"] if result["Temp1_C"] is not None else 0.0
                t2 = result["Temp2_C"] if result["Temp2_C"] is not None else 0.0
                delta_t = t2 - t1
                t0_c = (t1 + t2) / 2.0
                t0_k = t0_c + 273.15
                temf_mv = result["TEMF_mV"]
                # Seebeck S = ΔV/ΔT in µV/K; ΔV in mV, ΔT in °C (= K for difference). Guard small ΔT.
                delta_t_threshold = 0.01
                if temf_mv is not None and abs(delta_t) >= delta_t_threshold:
                    s_uv_per_k = (temf_mv * 1000.0) / delta_t  # mV -> µV, °C = K
                else:
                    s_uv_per_k = None
                # ΔT/T₀: differential method assumes small gradient; warn if large
                delta_t_over_t0 = (abs(delta_t) / t0_k) if t0_k > 0 else None
                branch = "cooling" if phase in ("ramp_down", "cooling_tail") else "heating"
                row = {
                    "Time [s]": elapsed_time,
                    "TEMF [mV]": temf_mv,
                    "Temp1 [oC]": result["Temp1_C"],
                    "Temp2 [oC]": result["Temp2_C"],
                    "Delta Temp [oC]": delta_t,
                    "T0 [oC]": t0_c,
                    "T0 [K]": t0_k,
                    "delta_T_over_T0": round(delta_t_over_t0, 6) if delta_t_over_t0 is not None else None,
                    "S [µV/K]": s_uv_per_k,
                    "branch": branch,
                }
                with self.lock:
                    self.session_data.append(row)

                # Persist this data point to DB as a MeasurementRow (best-effort).
                if db is not None and self._db_measurement_id is not None:
                    try:
                        seq = len(self.session_data)
                        mr = MeasurementRow(
                            measurement_id=self._db_measurement_id,
                            seq=seq,
                            elapsed_s=elapsed_time,
                            data_json=json.dumps(row, default=str),
                        )
                        db.add(mr)
                        # Commit in small batches to avoid excessive I/O
                        if seq % 50 == 0:
                            db.commit()
                    except Exception as e:
                        logger.error("Failed to insert MeasurementRow: %s", e)
                        if db is not None:
                            db.rollback()

                # Cooling tail: output already turned off above; keep measuring until |ΔT| < target or timeout
                if phase == "cooling_tail":
                    if cooling_tail_start_time is None:
                        cooling_tail_start_time = time.time()
                    if abs(delta_t) < cooling_target_delta_t:
                        logger.info(f"Cooling tail finished: |ΔT| = {abs(delta_t):.2f} °C < target {cooling_target_delta_t} °C")
                        break
                    if time.time() - cooling_tail_start_time > cooling_timeout_s:
                        logger.warning(f"Cooling tail timeout after {cooling_timeout_s} s; |ΔT| = {abs(delta_t):.2f} °C")
                        break
                    elapsed = time.time() - loop_start
                    remaining = max(0, interval - elapsed)
                    for _ in range(int(remaining * 10)):
                        if not self.session_active:
                            break
                        time.sleep(0.1)
                    continue

                kaisuu += 1
                elapsed = time.time() - loop_start
                remaining = max(0, interval - elapsed)
                for _ in range(int(remaining * 10)):
                    if not self.session_active:
                        break
                    time.sleep(0.1)
            self.seebeck_system.output_off()
            self.seebeck_system.disconnect_all()
            self.session_status = "finished"
            self.session_active = False
            self.session_phase = None
            self.session_step = 0
            self.session_total_steps = 0

            # Final DB commit for any remaining rows + mark measurement finished.
            if db is not None and self._db_measurement_id is not None and measurement_obj is not None:
                try:
                    measurement_obj.status = "finished"
                    measurement_obj.finished_at = datetime.utcnow()
                    db.commit()
                except Exception as e:
                    logger.error("Failed to finalise Measurement in DB: %s", e)
                    db.rollback()
        except Exception as e:
            self.session_status = f"error: {str(e)}"
            self.session_active = False
            self.session_phase = None
            self.session_step = 0
            self.session_total_steps = 0

            # Mark measurement as errored in DB if it exists.
            if db is not None and self._db_measurement_id is not None and measurement_obj is not None:
                try:
                    measurement_obj.status = "error"
                    measurement_obj.finished_at = datetime.utcnow()
                    db.commit()
                except Exception as exc:
                    logger.error("Failed to mark Measurement as error in DB: %s", exc)
                    db.rollback()
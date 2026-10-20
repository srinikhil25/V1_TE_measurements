"""Seebeck run loop against a simulated rig (no instruments, no real DB)."""

import json
import time

import pytest

from app.core.config import AppConfig
from app.instruments import session_manager as sm


class FakeRig:
    """Stands in for SeebeckSystem. Hot side follows the heater setpoint."""

    def __init__(self, temps=None):
        self.current = 0.0
        self.output_on = False
        self.calls = []
        self.cycle = 0
        # temps(cycle, current, output_on) -> (t1, t2); default: ΔT = 10 K per unit
        self.temps = temps or (lambda n, i, on: (25.0, 25.0 + 10.0 * i if on else 25.5))
        self.pk160_current_unit = "mA"

    def connect_all(self):
        self.calls.append("connect")
        return True

    def set_heater_mode(self, mode):
        self.calls.append(("mode", mode))

    def initialize_all(self):
        self.calls.append("init")

    def set_current(self, i):
        self.current = i
        self.output_on = True

    def output_off(self):
        self.calls.append("off")
        self.output_on = False
        self.current = 0.0
        return True

    def measure_all(self, temp1_channel=None, temp2_channel=None):
        self.cycle += 1
        t1, t2 = self.temps(self.cycle, self.current, self.output_on)
        temf = None if (t1 is None or t2 is None) else -0.05 * (t2 - t1)   # S = -50 µV/K
        return {"TEMF_mV": temf, "Temp1_C": t1, "Temp2_C": t2,
                "HeaterV_V": None, "HeaterI_A": None}

    def disconnect_all(self):
        self.calls.append("disconnect")


PARAMS = dict(interval=0.01, pre_time=0.02, start_volt=0.0, stop_volt=1.0,
              inc_rate=50.0, dec_rate=50.0, hold_time=0.03,
              cooling_target_delta_t=5.0, cooling_timeout_s=2, probe_mode="in_plane")


@pytest.fixture
def cfg(monkeypatch):
    c = AppConfig()
    monkeypatch.setattr(sm, "get_config", lambda: c)
    return c


def run(mgr, params=None, timeout=10.0):
    assert mgr.start_session(dict(params or PARAMS))
    deadline = time.monotonic() + timeout
    while mgr.is_running() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not mgr.is_running(), "run did not end"
    return mgr.get_status()


def make(rig):
    mgr = sm.MeasurementSessionManager()
    mgr.seebeck_system = rig
    return mgr


def test_normal_run_finishes_and_turns_heater_off(cfg):
    rig = FakeRig()
    mgr = make(rig)
    st = run(mgr)
    assert st["status"] == sm.STATUS_FINISHED
    assert st["end_reason"] is None
    assert rig.calls[-2:] == ["off", "disconnect"]
    data = mgr.get_data()
    assert data and all(r["valid"] for r in data)
    hot = [r for r in data if r["Delta Temp [oC]"] and r["Delta Temp [oC]"] > 1]
    assert hot and all(r["S [µV/K]"] == pytest.approx(-50.0) for r in hot)
    assert data[-1]["branch"] == "cooling"
    # not signed in → explicit warning instead of silent loss
    assert "NOT being saved" in st["db_warning"]


def test_over_temperature_aborts_immediately(cfg):
    cfg.safety.max_temperature_C = 30.0      # hot side reaches 35 °C at full current
    rig = FakeRig()
    mgr = make(rig)
    st = run(mgr)
    assert st["status"].startswith("error: Safety abort")
    assert "over-temperature" in st["end_reason"]
    data = mgr.get_data()
    assert data[-1]["flag"] and "over-temperature" in data[-1]["flag"]
    # heater switched off straight after the offending reading
    assert rig.calls.count("off") >= 1 and not rig.output_on
    assert max(r["Temp2 [oC]"] for r in data) <= 35.0


def test_invalid_readings_are_recorded_not_zeroed_then_abort(cfg):
    cfg.safety.max_consecutive_invalid_reads = 3
    rig = FakeRig(temps=lambda n, i, on: (None if n >= 3 else 25.0, 26.0))
    mgr = make(rig)
    st = run(mgr)
    assert "consecutive invalid" in st["end_reason"]
    bad = [r for r in mgr.get_data() if not r["valid"]]
    assert len(bad) == 3
    for r in bad:
        assert r["Temp1 [oC]"] is None            # never substituted with 0 °C
        assert r["Delta Temp [oC]"] is None
        assert r["T0 [K]"] is None
        assert r["S [µV/K]"] is None
        assert "T1" in r["flag"]
    assert st["invalid_reads"] == 3


def test_open_thermocouple_overflow_is_invalid(cfg):
    rig = FakeRig(temps=lambda n, i, on: (25.0, 9.9e37))
    mgr = make(rig)
    st = run(mgr)
    assert "overflow" in st["end_reason"]
    assert all(r["Temp2 [oC]"] is None for r in mgr.get_data())


def test_operator_stop_is_recorded_as_stopped(cfg):
    rig = FakeRig()
    mgr = make(rig)
    params = dict(PARAMS, hold_time=60.0, interval=0.05)
    assert mgr.start_session(params)
    time.sleep(0.3)
    mgr.stop_session()
    assert not mgr.is_running()
    st = mgr.get_status()
    assert st["status"] == sm.STATUS_STOPPED
    assert st["end_reason"] == "Stopped by operator"
    assert rig.calls[-2:] == ["off", "disconnect"]


def test_shutdown_all_sessions_stops_active_run(cfg):
    rig = FakeRig()
    mgr = make(rig)
    assert mgr.start_session(dict(PARAMS, hold_time=60.0, interval=0.05))
    time.sleep(0.2)
    assert sm.shutdown_all_sessions(timeout_s=5)
    assert not mgr.is_running()
    assert not rig.output_on


def test_connect_failure_reports_error_and_releases(cfg):
    rig = FakeRig()
    rig.connect_all = lambda: False
    mgr = make(rig)
    st = run(mgr)
    assert st["status"].startswith("error:")
    assert "connect" in st["end_reason"].lower()
    assert "disconnect" in rig.calls


def test_run_is_saved_row_by_row_with_outcome(cfg, app_db, monkeypatch):
    from datetime import datetime

    from app.models.db_models import Measurement, MeasurementIntegrity, MeasurementRow, User

    _path, factory = app_db
    s = factory()
    u = User(username="admin", email="a@x", password_hash="h", role="super_admin",
             lab_id=None, active=True, created_at=datetime.utcnow())
    s.add(u)
    s.commit()
    uid = u.id
    s.close()
    monkeypatch.setattr(sm, "get_session", factory)

    cfg.safety.max_temperature_C = 30.0
    rig = FakeRig()
    mgr = make(rig)
    st = run(mgr, dict(PARAMS, _user_id=uid, _lab_id=None))   # super_admin: no lab
    assert st["db_warning"] is None

    s = factory()
    m = s.query(Measurement).one()
    assert m.lab_id is None
    assert m.status == sm.STATUS_ABORTED
    assert "over-temperature" in m.end_reason
    rows = s.query(MeasurementRow).filter_by(measurement_id=m.id).order_by(MeasurementRow.seq).all()
    assert len(rows) == len(mgr.get_data())
    assert json.loads(rows[-1].data_json)["valid"] is True
    assert s.query(MeasurementIntegrity).filter_by(measurement_id=m.id).one().data_hash
    params = json.loads(m.params_json)
    assert "_user_id" not in params
    ctx = params["run_context"]
    assert ctx["software"]["version"] and ctx["config"]["safety"]["max_temperature_C"] == 30.0
    s.close()

    from app.core import audit
    entries = list(reversed(audit.recent(measurement_id=m.id)))
    assert [e["action"] for e in entries] == ["run_started", "run_ended"]
    assert entries[1]["details"]["outcome"] == sm.STATUS_ABORTED
    assert "over-temperature" in entries[1]["reason"]
    assert audit.verify_chain()["ok"]

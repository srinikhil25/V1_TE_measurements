"""I-V analysis maths and the sweep's run control / persistence (simulated 2401)."""

import json
import math
import threading
import time

import pytest

from app.services import measurement_service as ms

# ── analysis ────────────────────────────────────────────────────────────────

def test_linear_fit_recovers_resistance_and_ignores_offset():
    pts = [{"current": i * 1e-3, "voltage": 2.5 * i * 1e-3 + 40e-6} for i in range(-5, 6)]
    R, R2 = ms._linear_fit_resistance(pts)
    assert pytest.approx(2.5, rel=1e-9) == R
    assert pytest.approx(1.0) == R2
    assert ms._ohmic_status(R2) == "ohmic"


def test_linear_fit_skips_missing_points():
    pts = [{"current": 1e-3, "voltage": 1e-3}, {"current": None, "voltage": 5.0},
           {"current": 2e-3, "voltage": 2e-3}]
    R, _ = ms._linear_fit_resistance(pts)
    assert pytest.approx(1.0) == R
    assert ms._linear_fit_resistance([{"current": 1e-3, "voltage": 1e-3}]) == (None, None)


@pytest.mark.parametrize("r2, status", [(None, "unknown"), (0.9995, "ohmic"),
                                        (0.995, "check_contacts"), (0.9, "non_ohmic")])
def test_ohmic_status_thresholds(r2, status):
    assert ms._ohmic_status(r2) == status


def test_bar_resistivity():
    pt = {"resistance": 10.0}
    ms._enrich_point(pt, length=1.0, width=0.5, thickness=0.01, geometry="bar")
    assert pt["resistivity"] == pytest.approx(10.0 * 0.5 * 0.01 / 1.0)
    assert pt["conductivity"] == pytest.approx(1.0 / pt["resistivity"])


def test_van_der_pauw_resistivity():
    pt = {"resistance": 2.0}
    ms._enrich_point(pt, None, None, thickness=0.002, geometry="vdp")
    assert pt["resistivity"] == pytest.approx(math.pi * 0.002 / math.log(2) * 2.0)


def test_4pp_thin_infinite_sheet_limit():
    pt = {"resistance": 1.0}
    ms._enrich_point(pt, None, None, thickness=1e-5, geometry="4pp", spacing=0.1,
                     size_factor=1.0)
    assert pt["resistivity"] == pytest.approx(math.pi / math.log(2) * 1e-5, rel=1e-6)


def test_missing_dimensions_give_no_resistivity():
    pt = {"resistance": 1.0}
    ms._enrich_point(pt, None, None, None, geometry="bar")
    assert pt["resistivity"] is None and pt["conductivity"] is None
    neg = {"resistance": -1.0}
    ms._enrich_point(neg, 1, 1, 1)
    assert neg["resistivity"] is None


def test_size_factor_large_sheet_tends_to_one_and_small_sheet_below_one():
    big = ms.collinear_4pp_size_factor(0.1, 50.0, 50.0)
    small = ms.collinear_4pp_size_factor(0.1, 0.5, 0.5)
    assert big == pytest.approx(1.0, abs=0.01)
    assert 0 < small < big
    assert ms.collinear_4pp_size_factor(0.1, 0.2, 1.0) == 1.0     # probe array doesn't fit
    assert ms.collinear_4pp_size_factor(None, 1, 1) == 1.0


# ── sweep run control (simulated 2401) ─────────────────────────────────────

class Fake2401:
    def __init__(self, R=5.0, delay=0.0):
        self.R, self.delay = R, delay
        self.connected = True
        self.level = 0.0
        self.on = False
        self.mode = "current"

    def configure(self, source_mode, compliance, nplc, four_wire):
        self.mode = source_mode

    def output_on(self):
        self.on = True

    def output_off(self):
        self.on = False

    def set_level(self, level):
        self.level = level

    def read_point(self):
        time.sleep(self.delay)
        if self.mode == "current":
            return {"current": self.level, "voltage": self.level * self.R}
        return {"voltage": self.level, "current": self.level / self.R}


class FakeK2700:
    connected = False


class FakeSystem:
    def __init__(self, k2401):
        self.k2401 = k2401
        self.k2700 = FakeK2700()
        self.disconnected = False

    def connect_all(self):
        return True

    def get_temperature_avg_c(self):
        return 24.0

    def disconnect_all(self):
        self.disconnected = True


@pytest.fixture
def fake_rig(monkeypatch):
    holder = {"k": Fake2401()}
    systems = []

    def factory():
        s = FakeSystem(holder["k"])
        systems.append(s)
        return s

    monkeypatch.setattr(ms, "_get_seebeck_system", lambda: factory)
    return holder, systems


def test_sweep_finishes_and_switches_output_off(fake_rig):
    holder, systems = fake_rig
    res = ms.run_iv_sweep(start=-1e-3, stop=1e-3, points=5, delay_ms=0)
    assert len(res["points"]) == 5
    assert res["fit_R"] == pytest.approx(5.0)
    assert not res["aborted"]
    assert "NOT saved" in res["db_warning"]
    assert not holder["k"].on and systems[0].disconnected
    assert not ms.iv_running()


def test_sweep_abort_from_other_thread_and_rows_persisted(fake_rig, temp_db, monkeypatch):
    from datetime import datetime

    from app.core import database
    from app.models.db_models import Measurement, MeasurementRow, User

    holder, _ = fake_rig
    holder["k"] = Fake2401(delay=0.02)
    _path, factory = temp_db
    monkeypatch.setattr(database, "get_session", factory)
    s = factory()
    u = User(username="r", email="r@x", password_hash="h", role="super_admin",
             active=True, created_at=datetime.utcnow())
    s.add(u)
    s.commit()
    uid = u.id
    s.close()

    out = {}
    t = threading.Thread(target=lambda: out.update(ms.run_iv_sweep(
        start=0, stop=1e-3, points=200, delay_ms=0, _user_id=uid, _lab_id=None)))
    t.start()
    deadline = time.monotonic() + 5
    while not ms.iv_running() and time.monotonic() < deadline:
        time.sleep(0.005)
    time.sleep(0.15)
    assert ms.any_measurement_running()
    assert ms.stop_all_measurements(timeout_s=5)
    t.join(5)
    assert out["aborted"]
    assert 0 < len(out["points"]) < 200
    assert not holder["k"].on

    s = factory()
    m = s.query(Measurement).one()
    assert (m.status, m.lab_id, m.end_reason) == ("stopped", None, "Aborted by operator")
    rows = s.query(MeasurementRow).filter_by(measurement_id=m.id).count()
    assert rows == len(out["points"])
    assert json.loads(m.params_json)["temperature_C"] == 24.0
    s.close()


def test_instrument_error_marks_run_error_and_releases(fake_rig, temp_db, monkeypatch):
    from datetime import datetime

    from app.core import database
    from app.models.db_models import Measurement, User

    holder, systems = fake_rig

    class Broken(Fake2401):
        def read_point(self):
            raise IOError("GPIB timeout")

    holder["k"] = Broken()
    _path, factory = temp_db
    monkeypatch.setattr(database, "get_session", factory)
    s = factory()
    s.add(User(username="r", email="r@x", password_hash="h", role="researcher",
               active=True, created_at=datetime.utcnow()))
    s.commit()
    uid = s.query(User).one().id
    s.close()

    with pytest.raises(IOError):
        ms.run_iv_sweep(points=3, delay_ms=0, _user_id=uid)
    assert not holder["k"].on and systems[0].disconnected
    assert not ms.iv_running()
    s = factory()
    m = s.query(Measurement).one()
    assert m.status == "error" and "GPIB timeout" in m.end_reason
    s.close()

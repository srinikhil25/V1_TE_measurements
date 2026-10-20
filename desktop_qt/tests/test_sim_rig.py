"""End-to-end against the simulated rig (pyvisa-sim, app/instruments/sim/te_rig.yaml).

Unlike the FakeRig tests, these run the real drivers, the VISA guard and the
real pyvisa message layer. Every command each simulated instrument receives is
recorded, and a command the profile does not know fails the test — so a typo
or format change in a driver command is caught without hardware.
"""

import json
import os
import time
from datetime import datetime

import pytest

if os.environ.get("CI"):
    import pyvisa_sim  # noqa: F401  — in CI a missing simulator must fail, not skip
else:
    pytest.importorskip("pyvisa_sim")

from pyvisa_sim.devices import Device  # noqa: E402

from app.instruments import visa_backend  # noqa: E402

UNKNOWN = b"SIM_UNKNOWN_COMMAND"
PK = "GPIB0::15::INSTR"


@pytest.fixture
def sim(monkeypatch):
    """Select the simulated backend and record all instrument traffic."""
    monkeypatch.setenv(visa_backend.ENV_VAR, "sim")
    traffic = []
    orig = Device._match

    def recording_match(self, query):
        out = orig(self, query)
        bad = out is None or (isinstance(out, (bytes, bytearray)) and UNKNOWN in out)
        traffic.append((self._resource_name, query.decode("utf-8", "replace"), not bad))
        return out

    monkeypatch.setattr(Device, "_match", recording_match)
    return traffic


def _rejected(traffic):
    return [(addr, cmd) for addr, cmd, ok in traffic if not ok]


def _cmds(traffic, addr):
    return [cmd for a, cmd, _ok in traffic if a == addr]


def _user(factory):
    from app.models.db_models import User
    s = factory()
    u = User(username="sim", email="s@x", password_hash="h", role="super_admin",
             active=True, created_at=datetime.utcnow())
    s.add(u)
    s.commit()
    uid = u.id
    s.close()
    return uid


# ── backend selection ─────────────────────────────────────────────────────
def test_backend_selection(monkeypatch):
    monkeypatch.delenv(visa_backend.ENV_VAR, raising=False)
    assert visa_backend.visa_backend() == "" and not visa_backend.is_simulated()
    monkeypatch.setenv(visa_backend.ENV_VAR, "SIM")
    assert visa_backend.visa_backend().endswith("te_rig.yaml@sim")
    assert visa_backend.is_simulated()
    monkeypatch.setenv(visa_backend.ENV_VAR, "custom.yaml@sim")
    assert visa_backend.visa_backend() == "custom.yaml@sim"


def test_sim_profile_lists_the_configured_addresses(sim):
    from app.core.config import get_config
    rm = visa_backend.resource_manager()
    try:
        found = set(rm.list_resources())
    finally:
        rm.close()
    addrs = get_config().instruments
    assert {addrs.k2182a, addrs.k2700, addrs.pk480m, addrs.k2401} <= found


# ── drivers ───────────────────────────────────────────────────────────────
def test_driver_protocol_round_trip(sim):
    from app.instruments.instrument import SeebeckSystem

    system = SeebeckSystem()
    assert system.connect_all()
    try:
        ids = system.identify()
        assert "MODEL 2182A" in ids["k2182a"]["idn"]
        assert "MODEL 2401" in ids["k2401"]["idn"]
        assert ids["pk480m"]["idn"] is None

        system.set_heater_mode("in_plane")
        system.initialize_all()
        pk = system.pk.instrument
        assert pk.query("#1 SW?").strip() == "1"            # output armed at VCN 0
        assert float(pk.query("#1 ICN?")) == pytest.approx(1.0 / 1.3 * 100, abs=1e-3)

        system.pk160_current_unit = "mA"
        system.set_current(500)                              # 0.5 A → 5 V → VCN 4.545 %
        assert float(pk.query("#1 VCN?")) == pytest.approx(4.545, abs=1e-3)

        m = system.measure_all(102, 104)
        assert m["TEMF_mV"] == pytest.approx(-0.125)
        assert m["Temp1_C"] == pytest.approx(25.0) and m["Temp2_C"] == pytest.approx(25.0)

        assert system.output_off()
        assert pk.query("#1 SW?").strip() == "0"
        assert float(pk.query("#1 VCN?")) == 0.0
    finally:
        system.disconnect_all()

    assert _rejected(sim) == []
    pk_cmds = _cmds(sim, PK)
    assert not any("IDN" in c or c.startswith(("*", ":")) for c in pk_cmds), pk_cmds
    assert pk_cmds[-1] == "#1 LCL"                         # front panel handed back
    # disconnect re-sends heater-off before returning to local
    assert pk_cmds[-4:-1] == ["#1 REN", "#1 VCN 0", "#1 SW0"]


def test_out_of_range_heater_command_is_rejected_by_the_sim(sim):
    """The P4K-80M profile enforces 0–100 % — guards the percent conversion."""
    rm = visa_backend.resource_manager()
    try:
        pk = rm.open_resource(PK, read_termination="\r", write_termination="\r\n")
        pk.write("#1 VCN 120")
    finally:
        rm.close()
    assert _rejected(sim) == [(PK, "#1 VCN 120")]


# ── full runs ─────────────────────────────────────────────────────────────
def test_seebeck_run_end_to_end(sim, app_db, monkeypatch):
    from app.core import audit
    from app.instruments import session_manager as sm
    from app.models.db_models import Measurement, MeasurementRow

    _path, factory = app_db
    monkeypatch.setattr(sm, "get_session", factory)
    uid = _user(factory)

    mgr = sm.MeasurementSessionManager()
    params = dict(interval=0.01, pre_time=0.02, start_volt=0.0, stop_volt=1.0,
                  inc_rate=50.0, dec_rate=50.0, hold_time=0.03,
                  cooling_target_delta_t=5.0, cooling_timeout_s=2,
                  probe_mode="in_plane", sample_id="SIM-1", _user_id=uid, _lab_id=None)
    assert mgr.start_session(params)
    deadline = time.monotonic() + 30
    while mgr.is_running() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not mgr.is_running(), "simulated run did not end"
    st = mgr.get_status()
    assert st["db_warning"] is None

    s = factory()
    m = s.query(Measurement).one()
    ctx = json.loads(m.params_json)["run_context"]
    assert ctx["visa_backend"].endswith("@sim")             # provenance marks it simulated
    assert "MODEL 2700" in ctx["instruments"]["k2700"]["idn"]
    assert s.query(MeasurementRow).filter_by(measurement_id=m.id).count() == len(mgr.get_data()) > 0
    s.close()
    assert audit.verify_chain()["ok"]

    assert _rejected(sim) == []
    pk_cmds = _cmds(sim, PK)
    assert pk_cmds[-1] == "#1 LCL" and "#1 SW0" in pk_cmds[-4:]
    drives = [c for c in pk_cmds if c.startswith("#1 VCN ") and c != "#1 VCN 0"]
    assert drives, "the heater was never driven"


def test_iv_sweep_end_to_end(sim, app_db):
    from app.models.db_models import Measurement
    from app.services import measurement_service as ms

    _path, factory = app_db
    uid = _user(factory)
    res = ms.run_iv_sweep(start=-1e-3, stop=1e-3, points=5, delay_ms=0,
                          _user_id=uid, _lab_id=None)
    assert len(res["points"]) == 5 and not res["aborted"]
    assert res["db_warning"] is None
    assert res["temperature_C"] == pytest.approx(25.0)

    s = factory()
    m = s.query(Measurement).one()
    assert json.loads(m.params_json)["run_context"]["visa_backend"].endswith("@sim")
    s.close()

    assert _rejected(sim) == []
    k2401 = _cmds(sim, "GPIB0::24::INSTR")
    levels = [c for c in k2401 if c.startswith(":SOUR:CURR ") and c != ":SOUR:CURR 0"]
    assert len(levels) == 5
    assert k2401.index(":OUTP ON") < k2401.index(levels[0])
    assert ":OUTP OFF" in k2401[k2401.index(levels[-1]):]

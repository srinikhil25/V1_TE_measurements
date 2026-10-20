"""Run checks and errors mid-run (UI-5…UI-8): which instrument failed and why,
runs that stop on a dead instrument, Stop that skips the retry, required
fields and live geometry checks."""

import time
from types import SimpleNamespace

import pytest
from pyvisa.errors import VisaIOError

from app.instruments import visa_guard as vg
from app.services import measurement_service as ms
from tests.test_visa_guard import FakeRes


@pytest.fixture(autouse=True)
def _fresh_guard(monkeypatch):
    monkeypatch.setattr(vg, "_locks", {})
    vg.reset_instrument_health()
    yield
    vg.reset_instrument_health()


def _tmo():
    return VisaIOError(vg.VI_ERROR_TMO)


# ── instrument health registry ────────────────────────────────────────────
def test_failure_names_instrument_command_and_cause():
    g = vg.guard(FakeRes(name="GPIB0::16::INSTR", fail=2), "Keithley 2700")
    with pytest.raises(VisaIOError):
        g.query(":READ?")
    h = vg.instrument_health()["GPIB0::16::INSTR"]
    assert h["consecutive_failures"] == 1 and h["failures"] == 1
    assert vg.failure_summary() == \
        "Keithley 2700 (GPIB0::16::INSTR): no answer (timeout) on query(':READ?')"


def test_success_clears_the_current_failure_but_keeps_history():
    raw = FakeRes(name="GPIB0::7::INSTR", fail=2)
    g = vg.guard(raw, "Keithley 2182A")
    with pytest.raises(VisaIOError):
        g.query(":READ?")
    g.query(":READ?")
    assert vg.failure_summary() == ""
    assert "timeout" in vg.failure_summary(only_current=False)
    vg.reset_instrument_health()
    assert vg.instrument_health() == {}


def test_stop_request_skips_the_retry():
    raw = FakeRes(name="GPIB0::24::INSTR", fail=5)
    g = vg.guard(raw, "Keithley 2401")
    vg.set_abort_check(g, lambda: True)
    t0 = time.monotonic()
    with pytest.raises(VisaIOError):
        g.query(":READ?")
    assert len(raw.log) == 1                  # one attempt, no retry
    assert time.monotonic() - t0 < 0.05
    vg.set_abort_check(g, None)
    raw.fail = 5
    with pytest.raises(VisaIOError):
        g.query(":READ?")
    assert len(raw.log) == 3                  # normal: attempt + one retry


def test_unparseable_reply_is_reported_by_the_driver():
    from app.instruments.instrument import Keithley2182A

    raw = FakeRes(name="GPIB0::7::INSTR")
    raw.query = lambda msg: "ERROR -113"
    k = Keithley2182A(raw.resource_name)
    k.instrument = vg.guard(raw, "Keithley 2182A")
    k.connected = True
    assert k.read_voltage() is None
    assert "ERROR -113" in vg.failure_summary()


# ── connection failures say which instrument ──────────────────────────────
def test_connect_failure_names_the_instrument(monkeypatch):
    pytest.importorskip("pyvisa_sim")
    from app.core.config import get_config
    from app.instruments import session_manager as sm
    from app.instruments import visa_backend
    from app.instruments.instrument import Keithley2700

    def not_present(self, rm=None):           # what NI-VISA says for a missing device
        self.last_error = ("VI_ERROR_RSRC_NFOUND (-1073807343): the requested device "
                           "or resource is not present in the system.")
        return False

    monkeypatch.setenv(visa_backend.ENV_VAR, "sim")
    monkeypatch.setattr(get_config().instruments, "k2700", "GPIB0::29::INSTR")
    monkeypatch.setattr(Keithley2700, "connect", not_present)
    mgr = sm.MeasurementSessionManager()
    assert mgr.start_session({"interval": 0.01, "pre_time": 0.01, "start_volt": 0.0,
                              "stop_volt": 1.0, "inc_rate": 50.0, "dec_rate": 50.0,
                              "hold_time": 0.01, "probe_mode": "in_plane"})
    deadline = time.monotonic() + 15
    while mgr.is_running() and time.monotonic() < deadline:
        time.sleep(0.02)
    st = mgr.get_status()
    assert "Could not connect to Keithley 2700 (GPIB0::29::INSTR)" in st["end_reason"]


# ── a dead instrument ends the run, with the reason ───────────────────────
def test_seebeck_run_stops_when_the_nanovoltmeter_stops_answering():
    from app.core.config import AppConfig
    from app.instruments import session_manager as sm
    from tests.test_session_manager import PARAMS, FakeRig, make, run

    class Dead2182A(FakeRig):
        def measure_all(self, temp1_channel=None, temp2_channel=None):
            out = super().measure_all(temp1_channel, temp2_channel)
            out["TEMF_mV"] = None
            return out

    orig = sm.get_config
    sm.get_config = lambda: AppConfig()
    try:
        rig = Dead2182A(lambda n, i, on: (25.0 + 10 * i if on else 25.0, 25.0))
        mgr = make(rig)
        st = run(mgr, dict(PARAMS, hold_time=30.0))
    finally:
        sm.get_config = orig
    assert st["status"].startswith("error")
    assert "Keithley 2182A gave no TEMF reading 3 times in a row" in st["end_reason"]
    assert len(mgr.get_data()) == 3
    assert rig.calls[-2:] == ["off", "disconnect"]


def test_iv_sweep_stops_after_three_failed_reads(monkeypatch):
    from tests.test_iv import Fake2401, FakeSystem

    class Dead2401(Fake2401):
        def read_point(self):
            return None

    k = Dead2401()
    monkeypatch.setattr(ms, "_get_seebeck_system", lambda: (lambda: FakeSystem(k)))
    with pytest.raises(RuntimeError, match="Keithley 2401 gave no reading 3 times in a row"):
        ms.run_iv_sweep(start=-1e-3, stop=1e-3, points=11, delay_ms=0)
    assert not k.on and not ms.iv_running()


# ── UI: required fields, live geometry check, failing instrument ──────────
pytest.importorskip("pytestqt")


def _user():
    return SimpleNamespace(id=1, username="t", role="researcher", lab_id=None)


def test_iv_sweep_needs_sample_and_operator(qtbot, monkeypatch):
    from app.ui.pages import iv_page
    page = iv_page.IVPage(_user())
    qtbot.addWidget(page)
    started = []
    monkeypatch.setattr(iv_page.IVWorker, "start", lambda self: started.append(1))
    page.le_operator.setText("")
    page._run()
    assert not started
    assert page.f_sample.error_lbl.text() and page.f_operator.error_lbl.text()
    page.le_sample_id.setText("Cu-01")
    page.le_operator.setText("t")
    page.cb_geometry.setCurrentIndex(0)
    page._run()
    assert started


def test_iv_geometry_problems_are_shown_live(qtbot):
    from app.ui.pages import iv_page
    page = iv_page.IVPage(_user())
    qtbot.addWidget(page)
    page.show()
    page.cb_geometry.setCurrentIndex(2)            # 4-point probe
    page.sb_length_cm.setValue(1.0)
    page.sb_spacing_cm.setValue(0.5)               # 3·s = 1.5 cm > 1 cm
    qtbot.waitUntil(lambda: page.geom_check.isVisible(), timeout=2000)
    assert "does not fit" in page.geom_check.text_lbl.text()
    page.sb_spacing_cm.setValue(0.1)
    qtbot.waitUntil(lambda: not page.geom_check.isVisible(), timeout=2000)


def test_iv_thickness_accepts_thin_films(qtbot):
    from app.ui.pages import iv_page
    page = iv_page.IVPage(_user())
    qtbot.addWidget(page)
    page.sb_thickness_cm.setValue(0.00025)         # 2.5 µm MXene film
    assert page.sb_thickness_cm.value() == pytest.approx(0.00025)


def test_iv_error_is_shown_inline(qtbot):
    from app.ui.pages import iv_page
    page = iv_page.IVPage(_user())
    qtbot.addWidget(page)
    page.show()
    page._on_error("Could not connect to Keithley 2401 (GPIB0::24::INSTR): no answer")
    assert page.err_box.isVisible()
    assert "GPIB0::24::INSTR" in page.err_box.text_lbl.text()


def test_seebeck_run_needs_a_sample_id(qtbot, monkeypatch):
    from app.services import measurement_service
    from app.ui.pages.seebeck_page import SeebeckPage
    page = SeebeckPage(_user())
    qtbot.addWidget(page)
    calls = []
    monkeypatch.setattr(measurement_service.SeebeckService, "start",
                        lambda self, p: calls.append(p) or False)
    page.inp_sample.setText("")
    page._start()
    assert not calls and page.f_sample.error_lbl.text()


def test_footer_marks_a_failing_instrument(qtbot):
    from app.ui.widgets.status_footer import StatusFooter
    footer = StatusFooter()
    qtbot.addWidget(footer)
    footer._on_scan({"GPIB0::16::INSTR", "GPIB0::7::INSTR"})
    addr = next(a for a in footer._dots if a.upper() == "GPIB0::16::INSTR")
    footer.set_run_state({"running": True, "instrument_health": {
        "GPIB0::16::INSTR": {"consecutive_failures": 2, "last_error": "no answer (timeout) "
                             "on query(':READ?')", "last_error_at": time.time() + 1}}})
    assert "NOT RESPONDING" in footer._dots[addr][1].toolTip()
    footer.set_run_state({"running": False, "instrument_health": {}})
    assert "answering" in footer._dots[addr][1].toolTip()

"""VISA guard: one retry on timeout, per-instrument lock, run exclusion (SAF-6)."""

import threading
import time

import pytest
from pyvisa.errors import VisaIOError

from app.instruments import visa_guard as vg
from app.instruments.instrument import PK480M, Keithley2700
from app.services import measurement_service as ms


def _tmo():
    return VisaIOError(vg.VI_ERROR_TMO)


class FakeRes:
    """Records calls; fails the first ``fail`` calls of each op with ``exc``."""

    def __init__(self, name="GPIB0::7::INSTR", fail=0, exc=None, delay=0.0, log=None):
        self.resource_name = name
        self.timeout = 2000
        self.fail = fail
        self.exc = exc or _tmo()
        self.delay = delay
        self.log = log if log is not None else []
        self.clears = 0
        self.closed = False

    def _op(self, op, msg=None):
        self.log.append((op, msg))
        if self.delay:
            time.sleep(self.delay)
        if self.fail > 0:
            self.fail -= 1
            raise self.exc
        return "1.0" if op == "query" else None

    def write(self, msg):
        return self._op("write", msg)

    def query(self, msg):
        return self._op("query", msg)

    def read(self):
        return self._op("read")

    def clear(self):
        self.clears += 1

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fresh_locks(monkeypatch):
    monkeypatch.setattr(vg, "_locks", {})


# ── retry ──────────────────────────────────────────────────────────────────
def test_query_timeout_once_clears_and_retries():
    raw = FakeRes(fail=1)
    g = vg.guard(raw, "2182A")
    assert g.query(":READ?") == "1.0"
    assert raw.clears == 1
    assert [c for c in raw.log if c[0] == "query"] == [("query", ":READ?")] * 2
    assert g.stats == {"timeouts": 1, "recovered": 1, "failed": 0}


def test_second_timeout_fails_hard():
    raw = FakeRes(fail=2)
    g = vg.guard(raw)
    with pytest.raises(VisaIOError):
        g.query(":READ?")
    assert len(raw.log) == 2                      # exactly one retry
    assert g.stats["failed"] == 1


def test_non_timeout_error_is_not_retried():
    raw = FakeRes(fail=1, exc=VisaIOError(-1073807343))   # VI_ERROR_RSRC_NFOUND
    g = vg.guard(raw)
    with pytest.raises(VisaIOError):
        g.write("*RST")
    assert len(raw.log) == 1


def test_write_retry_never_sends_device_clear():
    raw = FakeRes(fail=1)
    g = vg.guard(raw)
    g.write(":OUTP OFF")
    assert raw.clears == 0
    assert len(raw.log) == 2


def test_no_clear_for_matsusada_style_sessions():
    raw = FakeRes(name="GPIB0::15::INSTR", fail=1)
    g = vg.guard(raw, clear_on_timeout=False)
    g.query("#1 IMON")
    assert raw.clears == 0


def test_retry_false_and_write_once():
    raw = FakeRes(fail=1)
    g = vg.guard(raw)
    with pytest.raises(VisaIOError):
        vg.write_once(g, "#1 SW0")
    assert len(raw.log) == 1


def test_attribute_passthrough():
    raw = FakeRes()
    g = vg.guard(raw)
    g.timeout = 5000
    g.read_termination = "\r"
    assert raw.timeout == 5000 and raw.read_termination == "\r"
    assert g.resource_name == raw.resource_name
    assert vg.guard(g) is g                        # idempotent


def test_timeout_detected_from_message_too():
    assert vg.is_timeout(RuntimeError("VI_ERROR_TMO (-1073807339): Timeout expired"))
    assert not vg.is_timeout(RuntimeError("something else"))


# ── locking ────────────────────────────────────────────────────────────────
def test_two_sessions_to_same_address_share_one_lock():
    log = []
    a = vg.guard(FakeRes(name="GPIB0::16::INSTR", log=log))
    b = vg.guard(FakeRes(name="gpib0::16::instr", log=log))   # case-insensitive
    other = vg.guard(FakeRes(name="GPIB0::7::INSTR", log=log))
    entered = threading.Event()

    def hold():
        with a.transaction():
            a.write(":ROUT:CLOS (@102)")
            entered.set()
            time.sleep(0.15)
            a.query(":READ?")

    t = threading.Thread(target=hold)
    t.start()
    entered.wait(1)
    other.write("2182A")          # different instrument: not blocked
    b.write("INTERLOPER")         # same instrument: waits for the transaction
    t.join()
    ops = [m for _op, m in log]
    assert ops.index("2182A") < ops.index(":READ?")
    assert ops.index(":READ?") < ops.index("INTERLOPER")


def test_lock_wait_gives_up_with_busy_error():
    a = vg.guard(FakeRes())
    b = vg.guard(FakeRes(), lock_wait_s=0.05)
    entered, release = threading.Event(), threading.Event()

    def hold():
        with a.transaction():
            entered.set()
            release.wait(1)

    t = threading.Thread(target=hold)
    t.start()
    entered.wait(1)
    with pytest.raises(vg.InstrumentBusyError):
        b.query(":READ?")
    release.set()
    t.join()


def test_transaction_helper_is_noop_for_unguarded_objects():
    with vg.transaction(object()):
        pass
    with vg.transaction(None):
        pass


# ── drivers ────────────────────────────────────────────────────────────────
def _pk(raw):
    pk = PK480M(raw.resource_name)
    pk.instrument = vg.guard(raw, "PK4-80M", clear_on_timeout=False)
    pk.connected = True
    return pk


def test_heater_off_sequence_cannot_be_split_by_a_setpoint():
    log = []
    pk = _pk(FakeRes(name="GPIB0::15::INSTR", log=log, delay=0.03))
    t = threading.Thread(target=pk.output_off)
    t.start()
    time.sleep(0.01)                       # output_off is inside its sequence
    pk.set_voltage_volts(5.0)              # e.g. a late ramp step
    t.join()
    cmds = [m for _op, m in log]
    off = cmds[:3]
    assert off == ["#1 REN", "#1 VCN 0", "#1 SW0"]
    assert cmds[3:] == ["#1 REN", "#1 SW1", "#1 VCN 4.545"]


def test_heater_off_keeps_its_own_bounded_retry():
    raw = FakeRes(name="GPIB0::15::INSTR", fail=10)
    pk = _pk(raw)
    assert pk.output_off(retries=2) is False
    assert len(raw.log) == 6               # 3 steps × 2 attempts, no hidden extra retries


def test_heater_off_still_sent_when_lock_is_stuck(monkeypatch):
    raw = FakeRes(name="GPIB0::15::INSTR")
    pk = _pk(raw)
    object.__setattr__(pk.instrument, "_lock_wait_s", 0.05)
    holder = vg.guard(FakeRes(name="GPIB0::15::INSTR"))
    entered, release = threading.Event(), threading.Event()

    def hold():
        with holder.transaction():
            entered.set()
            release.wait(2)

    t = threading.Thread(target=hold)
    t.start()
    entered.wait(1)
    assert pk.output_off() is True
    assert [m for _op, m in raw.log][-1] == "#1 SW0"
    release.set()
    t.join()


def test_2700_reading_recovers_from_one_timeout():
    raw = FakeRes(name="GPIB0::16::INSTR")
    k = Keithley2700(raw.resource_name)
    k.instrument = vg.guard(raw, "Keithley 2700")
    k.connected = True
    raw.fail = 0
    orig_query = raw.query
    calls = {"n": 0}

    def flaky(msg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _tmo()
        return "+2.351E+01"

    raw.query = flaky
    assert k.take_measurement(102) == pytest.approx(23.51)
    assert raw.clears == 1
    raw.query = orig_query


# ── run exclusion ──────────────────────────────────────────────────────────
def test_seebeck_start_refused_while_iv_runs(monkeypatch):
    svc = ms.SeebeckService()
    ms._iv_active.set()
    try:
        assert svc.start({"sample_id": "x"}) is False
        assert svc.last_error == ms.IV_BLOCKS_SEEBECK
    finally:
        ms._iv_active.clear()


def test_iv_refused_while_seebeck_runs(monkeypatch):
    monkeypatch.setattr(ms, "_seebeck_running", lambda: True)
    with pytest.raises(RuntimeError, match="Seebeck run is in progress"):
        ms.run_iv_sweep(start=0, stop=1e-3, points=3)
    assert not ms._iv_active.is_set()


def test_tests_cannot_open_the_real_visa_library(monkeypatch):
    """conftest blocks NI-VISA: a stray scan must never reach the real GPIB bus."""
    import pyvisa

    from app.instruments import visa_backend
    monkeypatch.delenv(visa_backend.ENV_VAR, raising=False)
    with pytest.raises(RuntimeError, match="real VISA library"):
        pyvisa.ResourceManager()
    with pytest.raises(RuntimeError, match="real VISA library"):
        visa_backend.resource_manager()

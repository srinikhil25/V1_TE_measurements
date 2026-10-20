import math

import pytest

from app.instruments.safety import SafetyMonitor


def monitor(**kw):
    args = dict(max_temperature_C=100.0, max_rise_rate_C_per_min=30.0,
                rate_window_s=30.0, max_consecutive_invalid_reads=3)
    args.update(kw)
    return SafetyMonitor(**args)


@pytest.mark.parametrize("raw, reason", [
    (None, "no reading"),
    (float("nan"), "not a number"),
    (float("inf"), "not a number"),
    (9.9e37, "overflow"),
    (-9.9e37, "overflow"),
    (-200.0, "implausible"),
    (900.0, "implausible"),
    ("abc", "unreadable"),
])
def test_invalid_readings_are_rejected(raw, reason):
    value, why = monitor().sanitize(raw)
    assert value is None
    assert reason in why


def test_valid_reading_passes_unchanged():
    assert monitor().sanitize(25.5) == (25.5, None)
    assert monitor().sanitize("30") == (30.0, None)


def test_normal_cycle_is_valid_and_no_abort():
    r = monitor().check(0.0, 25.0, 30.0)
    assert r.valid and not r.abort
    assert (r.t1, r.t2) == (25.0, 30.0)
    assert r.flag_text is None


def test_invalid_reading_is_never_replaced_by_a_default():
    r = monitor().check(0.0, None, 30.0)
    assert not r.valid
    assert r.t1 is None          # not 0.0
    assert r.t2 == 30.0
    assert "T1" in r.flag_text


def test_invalid_streak_aborts_and_valid_read_resets_it():
    m = monitor(max_consecutive_invalid_reads=3)
    assert not m.check(0, None, 25).abort
    assert not m.check(1, None, 25).abort
    assert not m.check(2, 25, 25).abort          # streak reset
    assert not m.check(3, 9.9e37, 25).abort
    assert not m.check(4, 9.9e37, 25).abort
    r = m.check(5, 9.9e37, 25)
    assert r.abort
    assert "consecutive invalid" in r.abort_reason


def test_over_temperature_aborts_on_hottest_side():
    m = monitor(max_temperature_C=100.0)
    assert not m.check(0, 25, 99.9).abort
    r = m.check(1, 25, 100.1)
    assert r.abort and "over-temperature" in r.abort_reason


def test_over_temperature_still_checked_when_other_side_invalid():
    r = monitor(max_temperature_C=100.0).check(0, None, 150.0)
    assert r.abort and "over-temperature" in r.abort_reason


def test_rate_of_rise_aborts():
    m = monitor(max_rise_rate_C_per_min=30.0, rate_window_s=30.0)
    # 1 °C/s = 60 °C/min, sustained
    aborted = None
    for t in range(0, 31):
        r = m.check(float(t), 25.0, 25.0 + t)
        if r.abort:
            aborted = t
            break
    assert aborted is not None
    assert "rising too fast" in r.abort_reason
    # needs at least max(5, window/3) = 10 s of history before it can trip
    assert aborted >= 10


def test_slow_heating_does_not_trip_rate_limit():
    m = monitor(max_rise_rate_C_per_min=30.0)
    for t in range(0, 120):
        r = m.check(float(t), 25.0, 25.0 + 0.25 * t)   # 15 °C/min
        assert not r.abort


def test_single_noise_spike_does_not_trip_rate_limit():
    m = monitor(max_rise_rate_C_per_min=30.0, max_temperature_C=200)
    m.check(0.0, 25.0, 25.0)
    r = m.check(1.0, 25.0, 40.0)        # +15 °C in 1 s, but only 1 s of history
    assert not r.abort


def test_from_config_uses_safety_section():
    from app.core.config import SafetyLimits
    m = SafetyMonitor.from_config(SafetyLimits(max_temperature_C=80.0))
    assert m.max_temperature_C == 80.0
    assert not math.isnan(m.max_rise_rate_C_per_min)


def test_stuck_sensor_becomes_invalid_then_aborts():
    m = monitor(max_identical_reads=5, max_consecutive_invalid_reads=3)
    results = [m.check(float(t), 25.0, 30.0 + 0.01 * t) for t in range(10)]
    assert all(r.valid for r in results[:4])
    assert not results[4].valid and "stuck" in results[4].flag_text
    assert results[6].abort and "consecutive invalid" in results[6].abort_reason


def test_noisy_sensor_is_not_stuck():
    m = monitor(max_identical_reads=5)
    for t in range(50):
        assert m.check(float(t), 25.0 + (0.001 if t % 2 else 0.0), 30.0 + 0.002 * (t % 3)).valid


def test_stuck_check_can_be_disabled():
    m = monitor(max_identical_reads=0)
    for t in range(100):
        assert m.check(float(t), 25.0, 30.0).valid

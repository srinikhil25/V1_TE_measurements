"""
Interval reliability smoke test for the Seebeck measurement loop.

This script:
  - Uses a mock SeebeckSystem (no real hardware required).
  - Runs a short Seebeck session at 1 s interval.
  - Prints basic timing statistics (min/avg/max Δt between samples).

Usage (from desktop_qt venv):
  cd desktop_qt
  python -m tests_interval.run_interval_smoke_test
"""

from __future__ import annotations

import time
from statistics import mean

from app.instruments.session_manager import MeasurementSessionManager


class MockSeebeckSystem:
    """Minimal stand-in for SeebeckSystem used only for timing tests."""

    def __init__(self):
        self.pk160_current_unit = "mA"

    # Connection / init
    def connect_all(self) -> bool:
        return True

    def initialize_all(self) -> None:
        # Simulate small startup cost
        time.sleep(0.05)

    def disconnect_all(self) -> None:
        pass

    # Output control
    def output_off(self) -> None:
        pass

    def set_current(self, _current: float) -> None:
        # Simulate small instrument latency to set current
        time.sleep(0.03)

    # Measurement
    def measure_all(self) -> dict:
        """Return a synthetic measurement payload."""
        # Simulate the real instrument read taking e.g. ~50 ms
        time.sleep(0.05)
        t = time.time()
        # Simple fake data — only timing matters for this test.
        return {
            "Temp1_C": 300.0 + 0.1 * (t % 10),
            "Temp2_C": 305.0 + 0.1 * (t % 10),
            "TEMF_mV": 1.23,
        }


class TestSessionManager(MeasurementSessionManager):
    """MeasurementSessionManager wired to MockSeebeckSystem for tests."""

    def __init__(self):
        super().__init__()
        # Override the real hardware with the mock
        self.seebeck_system = MockSeebeckSystem()


def main() -> None:
    mgr = TestSessionManager()

    params = {
        "interval": 1,          # 1 s target interval
        "pre_time": 2,
        "start_volt": 0.0,
        "stop_volt": 1.0,
        "inc_rate": 0.5,
        "dec_rate": 0.5,
        "hold_time": 4,
        "cooling_target_delta_t": 1.0,
        "cooling_timeout_s": 10,
        "stabilization_delay_s": 0.0,
        "pk160_current_unit": "mA",
    }

    print("Starting 1-second-interval timing test (mock instruments)…", flush=True)
    started = mgr.start_session(params)
    if not started:
        print("ERROR: session did not start (already active).", flush=True)
        return

    # Wait for the background thread to finish.
    if mgr.session_thread is not None:
        mgr.session_thread.join(timeout=120)

    data = mgr.get_data()
    if len(data) < 2:
        print("Not enough points collected for timing analysis.", flush=True)
        return

    times = [row.get("Time [s]", 0) for row in data]
    deltas = [t1 - t0 for t0, t1 in zip(times, times[1:])]

    print(f"Collected {len(times)} points.")
    print("Δt statistics (s) between successive samples:")
    print(f"  min: {min(deltas):.3f}")
    print(f"  avg: {mean(deltas):.3f}")
    print(f"  max: {max(deltas):.3f}")
    print("Raw Δt sequence:", ", ".join(f"{d:.3f}" for d in deltas))


if __name__ == "__main__":
    main()


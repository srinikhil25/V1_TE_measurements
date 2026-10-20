"""Software safety layer for heater-driven runs (roadmap "layer 1").

``SafetyMonitor`` is fed the raw thermocouple readings once per measurement
cycle and decides whether the run may continue. It is pure logic — no
instrument I/O — so every rule is unit-testable.

Rules (limits come from ``[safety]`` in the rig config):

* **Plausibility** — a reading that is missing, NaN/inf, an instrument overflow
  (an open thermocouple on the 2700 reads ~9.9e37) or outside
  ``[plausible_min_C, plausible_max_C]`` is *invalid*. Invalid readings are
  never replaced by a default value; the row is recorded as invalid and no
  ΔT or Seebeck value is computed from it.
* **Invalid-read streak** — ``max_consecutive_invalid_reads`` cycles in a row
  with any invalid thermocouple aborts the run: with a sensor gone, the
  over-temperature check is blind on that side.
* **Stuck sensor** — ``max_identical_reads`` bit-identical readings in a row on
  one channel make that channel invalid (a live thermocouple always shows
  last-digit noise; a frozen value means the input is no longer updating).
* **Over-temperature** — any valid reading above ``max_temperature_C`` aborts.
* **Rate of rise** — heating faster than ``max_rise_rate_C_per_min``, measured
  over ``rate_window_s``, aborts (thermal runaway / bad coupling).

Limitations: this layer only works while the application is running and the
2700 is answering. It cannot protect against a PC or app crash, a hung GPIB
bus, or a thermocouple that reads plausibly but wrongly (e.g. detached from
the heater). An independent hardware cut-off is required for unattended runs.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

# Readings this large are instrument overflow / open-circuit markers, not temperatures.
_OVERFLOW = 1e30


@dataclass
class SafetyResult:
    t1: Optional[float]            # sanitised T1 (°C) — None if invalid
    t2: Optional[float]            # sanitised T2 (°C) — None if invalid
    valid: bool                    # both readings valid
    flags: List[str] = field(default_factory=list)   # why a reading was invalid
    abort_reason: Optional[str] = None               # set → stop heating now

    @property
    def abort(self) -> bool:
        return self.abort_reason is not None

    @property
    def flag_text(self) -> Optional[str]:
        return "; ".join(self.flags) if self.flags else None


class SafetyMonitor:
    """Stateful per-run safety checker. Create one per run."""

    def __init__(
        self,
        max_temperature_C: float,
        max_rise_rate_C_per_min: float,
        rate_window_s: float = 30.0,
        max_consecutive_invalid_reads: int = 3,
        plausible_min_C: float = -60.0,
        plausible_max_C: float = 600.0,
        max_identical_reads: int = 0,
    ):
        self.max_temperature_C = float(max_temperature_C)
        self.max_rise_rate_C_per_min = float(max_rise_rate_C_per_min)
        self.rate_window_s = float(rate_window_s)
        self.max_consecutive_invalid_reads = int(max_consecutive_invalid_reads)
        self.plausible_min_C = float(plausible_min_C)
        self.plausible_max_C = float(plausible_max_C)
        self.max_identical_reads = int(max_identical_reads)
        self._last_raw: List[Optional[float]] = [None, None]
        self._identical = [0, 0]
        self._invalid_streak = 0
        self._history: Deque[Tuple[float, float]] = deque()   # (time_s, hottest °C)

    @classmethod
    def from_config(cls, safety) -> "SafetyMonitor":
        """Build from an ``app.core.config.SafetyLimits`` instance."""
        return cls(
            max_temperature_C=safety.max_temperature_C,
            max_rise_rate_C_per_min=safety.max_rise_rate_C_per_min,
            rate_window_s=safety.rate_window_s,
            max_consecutive_invalid_reads=safety.max_consecutive_invalid_reads,
            plausible_min_C=safety.plausible_min_C,
            plausible_max_C=safety.plausible_max_C,
            max_identical_reads=getattr(safety, "max_identical_reads", 0),
        )

    # ------------------------------------------------------------------
    def sanitize(self, value) -> Tuple[Optional[float], Optional[str]]:
        """Return (temperature, None) if valid, else (None, reason)."""
        if value is None:
            return None, "no reading"
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None, f"unreadable value {value!r}"
        if math.isnan(v) or math.isinf(v):
            return None, "not a number"
        if abs(v) >= _OVERFLOW:
            return None, "overflow (open thermocouple?)"
        if v < self.plausible_min_C or v > self.plausible_max_C:
            return None, f"implausible {v:.1f} °C"
        return v, None

    def _stuck(self, ch: int, value: float) -> bool:
        if self.max_identical_reads <= 0:
            return False
        if value == self._last_raw[ch]:
            self._identical[ch] += 1
        else:
            self._last_raw[ch] = value
            self._identical[ch] = 1
        return self._identical[ch] >= self.max_identical_reads

    def check(self, now_s: float, t1_raw, t2_raw) -> SafetyResult:
        """Evaluate one measurement cycle. ``now_s`` is a monotonic time in seconds."""
        t1, why1 = self.sanitize(t1_raw)
        t2, why2 = self.sanitize(t2_raw)
        if t1 is not None and self._stuck(0, t1):
            t1, why1 = None, f"stuck ({self._identical[0]} identical readings)"
        if t2 is not None and self._stuck(1, t2):
            t2, why2 = None, f"stuck ({self._identical[1]} identical readings)"
        flags = []
        if why1:
            flags.append(f"T1 {why1}")
        if why2:
            flags.append(f"T2 {why2}")
        result = SafetyResult(t1=t1, t2=t2, valid=(t1 is not None and t2 is not None), flags=flags)

        # Invalid-read streak
        if result.valid:
            self._invalid_streak = 0
        else:
            self._invalid_streak += 1
            if self._invalid_streak >= self.max_consecutive_invalid_reads:
                result.abort_reason = (
                    f"{self._invalid_streak} consecutive invalid thermocouple readings "
                    f"({result.flag_text})"
                )
                return result

        valid_temps = [t for t in (t1, t2) if t is not None]
        if not valid_temps:
            return result
        hottest = max(valid_temps)

        # Over-temperature
        if hottest > self.max_temperature_C:
            result.abort_reason = (
                f"over-temperature: {hottest:.1f} °C exceeds the limit of "
                f"{self.max_temperature_C:.1f} °C"
            )
            return result

        # Rate of rise over the window. Needs at least a third of the window
        # (and ≥ 5 s) of history so single-point noise can't trip it.
        self._history.append((now_s, hottest))
        while self._history and now_s - self._history[0][0] > self.rate_window_s:
            self._history.popleft()
        t_old, temp_old = self._history[0]
        span = now_s - t_old
        if span >= max(5.0, self.rate_window_s / 3.0):
            rate = (hottest - temp_old) / span * 60.0
            if rate > self.max_rise_rate_C_per_min:
                result.abort_reason = (
                    f"temperature rising too fast: {rate:.1f} °C/min exceeds the limit of "
                    f"{self.max_rise_rate_C_per_min:.1f} °C/min"
                )
        return result

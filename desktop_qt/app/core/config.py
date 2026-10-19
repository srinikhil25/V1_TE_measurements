"""Persistent rig configuration — instrument addresses, channels, limits.

Replaces the constants that used to be hard-coded in ``instruments/instrument.py``
and the in-memory-only Settings page. The configuration lives in a TOML file:

    %APPDATA%\\TEMeasurement\\config.toml      (override with TE_CONFIG_PATH)

The file is created with defaults on first run and can be edited from the
Settings page or by hand. Every value is validated on load; a malformed file is
never silently half-applied — the app falls back to the built-in defaults and
reports what was wrong (see ``load_warnings()``).

Usage::

    from app.core.config import get_config, save_config
    cfg = get_config()
    cfg.instruments.k2700          # "GPIB0::16::INSTR"
    cfg.safety.max_temperature_C   # software over-temperature limit

``get_config()`` returns a cached instance; ``save_config()`` validates, writes
atomically and replaces the cache, so the next instrument connect picks up the
new values.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, List, Optional

from .paths import get_app_dir

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "config.toml"
SCHEMA_VERSION = 1

# P4K-80M-LDe ratings (device label): 110 V / 1.3 A / 80 W. Heater limits can
# never be configured above these.
PK_RATED_VOLTAGE_V = 110.0
PK_RATED_CURRENT_A = 1.3


class ConfigError(ValueError):
    """Raised when a configuration fails validation. ``problems`` lists each issue."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Schema (defaults = the values that were previously hard-coded)
# ---------------------------------------------------------------------------

@dataclass
class InstrumentAddresses:
    k2182a: str = "GPIB0::7::INSTR"    # nanovoltmeter — thermovoltage
    k2700: str = "GPIB0::16::INSTR"    # DMM + scanner — thermocouples
    pk480m: str = "GPIB0::15::INSTR"   # Matsusada P4K-80M — heater supply
    k2401: str = "GPIB0::24::INSTR"    # SourceMeter — I-V sweeps


@dataclass
class VisaTimeouts:
    """Per-instrument VISA timeout in milliseconds.

    Must exceed the longest legitimate operation (e.g. a 2182A/2700 reading at
    high NPLC with filtering can take several seconds). Shorter values make a
    hung bus fail faster; too short and normal readings time out.
    """
    k2182a: int = 20000
    k2700: int = 20000
    pk480m: int = 5000
    k2401: int = 20000


@dataclass
class Thermocouples:
    """Keithley 2700 scanner channels. T1 = hot side, T2 = cold side."""
    in_plane_t1: int = 102
    in_plane_t2: int = 104
    out_plane_t1: int = 103
    out_plane_t2: int = 105
    # Open-thermocouple detection on the 2700: an open/broken TC then reads as
    # overflow instead of a floating, plausible-looking temperature, so the
    # software safety checks can catch it.
    open_tc_detect: bool = True


@dataclass
class HeaterLimit:
    current_max_A: float = 1.0
    voltage_drive_max_V: float = 10.0


@dataclass
class HeaterLimits:
    in_plane: HeaterLimit = field(default_factory=lambda: HeaterLimit(1.0, 10.0))
    out_plane: HeaterLimit = field(default_factory=lambda: HeaterLimit(1.3, 40.0))


@dataclass
class SafetyLimits:
    """Software safety layer (layer 1). NOT a substitute for an independent
    hardware over-temperature cut-off — these checks only work while the app
    is running. Set the limits from this rig's own operating envelope: above
    the hottest temperature a normal run reaches, below the damage temperature
    of the sample, fixture, wiring and thermocouples.
    """
    max_temperature_C: float = 120.0         # abort if any thermocouple exceeds this
    max_rise_rate_C_per_min: float = 30.0    # abort on faster heating (runaway)
    rate_window_s: float = 30.0              # rate is measured over this window
    max_consecutive_invalid_reads: int = 3   # abort after this many bad TC reads in a row
    plausible_min_C: float = -60.0           # readings outside [min, max] are invalid
    plausible_max_C: float = 600.0


@dataclass
class IrCameraPaths:
    otc_sdk_dir: str = r"C:\Program Files\Optris\otcsdk"
    legacy_dll: str = r"C:\IrDirectSDK\sdk\x64\libirimager.dll"
    legacy_config: str = r"C:\IrDirectSDK\generic.xml"


@dataclass
class AppConfig:
    instruments: InstrumentAddresses = field(default_factory=InstrumentAddresses)
    visa_timeout_ms: VisaTimeouts = field(default_factory=VisaTimeouts)
    thermocouples: Thermocouples = field(default_factory=Thermocouples)
    heater: HeaterLimits = field(default_factory=HeaterLimits)
    safety: SafetyLimits = field(default_factory=SafetyLimits)
    ir_camera: IrCameraPaths = field(default_factory=IrCameraPaths)

    # -- helpers -----------------------------------------------------------
    def heater_limit(self, probe_mode: str) -> HeaterLimit:
        return self.heater.out_plane if str(probe_mode).lower() == "out_plane" else self.heater.in_plane

    def tc_channels(self, probe_mode: str) -> tuple:
        tc = self.thermocouples
        if str(probe_mode).lower() == "out_plane":
            return tc.out_plane_t1, tc.out_plane_t2
        return tc.in_plane_t1, tc.in_plane_t2

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "AppConfig":
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(cfg: AppConfig) -> List[str]:
    """Return a list of human-readable problems (empty = valid)."""
    p: List[str] = []

    for name in ("k2182a", "k2700", "pk480m", "k2401"):
        addr = getattr(cfg.instruments, name)
        if not isinstance(addr, str) or not addr.strip():
            p.append(f"instruments.{name}: address must not be empty")

    for name in ("k2182a", "k2700", "pk480m", "k2401"):
        t = getattr(cfg.visa_timeout_ms, name)
        if not isinstance(t, int) or isinstance(t, bool) or not (500 <= t <= 120_000):
            p.append(f"visa_timeout_ms.{name}: must be an integer 500–120000 ms (got {t!r})")

    tc = cfg.thermocouples
    chans = {}
    for name in ("in_plane_t1", "in_plane_t2", "out_plane_t1", "out_plane_t2"):
        ch = getattr(tc, name)
        if not isinstance(ch, int) or isinstance(ch, bool) or not (101 <= ch <= 240):
            p.append(f"thermocouples.{name}: must be a 2700 channel 101–240 (got {ch!r})")
        chans[name] = ch
    if chans.get("in_plane_t1") == chans.get("in_plane_t2"):
        p.append("thermocouples: in-plane T1 and T2 must be different channels")
    if chans.get("out_plane_t1") == chans.get("out_plane_t2"):
        p.append("thermocouples: out-of-plane T1 and T2 must be different channels")
    if not isinstance(tc.open_tc_detect, bool):
        p.append("thermocouples.open_tc_detect: must be true or false")

    for mode in ("in_plane", "out_plane"):
        lim = getattr(cfg.heater, mode)
        if not _finite(lim.current_max_A) or not (0 < lim.current_max_A <= PK_RATED_CURRENT_A):
            p.append(f"heater.{mode}.current_max_A: must be > 0 and ≤ {PK_RATED_CURRENT_A} A")
        if not _finite(lim.voltage_drive_max_V) or not (0 < lim.voltage_drive_max_V <= PK_RATED_VOLTAGE_V):
            p.append(f"heater.{mode}.voltage_drive_max_V: must be > 0 and ≤ {PK_RATED_VOLTAGE_V} V")

    s = cfg.safety
    if not _finite(s.max_temperature_C) or not (20 <= s.max_temperature_C <= 1000):
        p.append("safety.max_temperature_C: must be 20–1000 °C")
    if not _finite(s.max_rise_rate_C_per_min) or s.max_rise_rate_C_per_min <= 0:
        p.append("safety.max_rise_rate_C_per_min: must be > 0")
    if not _finite(s.rate_window_s) or not (5 <= s.rate_window_s <= 600):
        p.append("safety.rate_window_s: must be 5–600 s")
    if (not isinstance(s.max_consecutive_invalid_reads, int) or isinstance(s.max_consecutive_invalid_reads, bool)
            or not (1 <= s.max_consecutive_invalid_reads <= 20)):
        p.append("safety.max_consecutive_invalid_reads: must be an integer 1–20")
    if not (_finite(s.plausible_min_C) and _finite(s.plausible_max_C)) or s.plausible_min_C >= s.plausible_max_C:
        p.append("safety.plausible_min_C must be below plausible_max_C")
    elif _finite(s.max_temperature_C) and s.max_temperature_C >= s.plausible_max_C:
        p.append("safety.max_temperature_C must be below plausible_max_C")

    for name in ("otc_sdk_dir", "legacy_dll", "legacy_config"):
        if not isinstance(getattr(cfg.ir_camera, name), str):
            p.append(f"ir_camera.{name}: must be a path string")
    return p


# ---------------------------------------------------------------------------
# (De)serialisation
# ---------------------------------------------------------------------------

def _apply(obj: Any, data: dict, path: str, problems: List[str]) -> None:
    """Copy values from a parsed TOML table onto a dataclass instance."""
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        where = f"{path}{key}"
        if key not in known:
            logger.warning("config: ignoring unknown key %r", where)
            continue
        current = getattr(obj, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                problems.append(f"{where}: expected a table")
                continue
            _apply(current, value, where + ".", problems)
        elif isinstance(current, bool):
            if not isinstance(value, bool):
                problems.append(f"{where}: expected true/false (got {value!r})")
            else:
                setattr(obj, key, value)
        elif isinstance(current, float):
            # TOML writes 120 and 120.0 differently; accept ints for float fields.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"{where}: expected a number (got {value!r})")
            else:
                setattr(obj, key, float(value))
        elif isinstance(current, int):
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"{where}: expected an integer (got {value!r})")
            else:
                setattr(obj, key, value)
        elif isinstance(current, str):
            if not isinstance(value, str):
                problems.append(f"{where}: expected text (got {value!r})")
            else:
                setattr(obj, key, value)


def from_dict(data: dict) -> AppConfig:
    """Build and validate a config from a parsed dict. Raises ConfigError."""
    cfg = AppConfig()
    problems: List[str] = []
    data = dict(data)
    data.pop("schema_version", None)
    _apply(cfg, data, "", problems)
    problems += validate(cfg)
    if problems:
        raise ConfigError(problems)
    return cfg


def _toml_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        # JSON string escaping is a valid TOML basic string.
        return json.dumps(v)
    raise TypeError(f"unsupported config value type: {type(v).__name__}")


def _toml_lines(table: dict, prefix: tuple = ()) -> List[str]:
    lines: List[str] = []
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in table.items() if isinstance(v, dict)}
    if prefix and scalars:
        lines.append(f"[{'.'.join(prefix)}]")
    for k, v in scalars.items():
        lines.append(f"{k} = {_toml_scalar(v)}")
    for k, v in tables.items():
        sub = _toml_lines(v, prefix + (k,))
        if sub:
            lines.append("")
            lines.extend(sub)
    return lines


_HEADER = """\
# TE Measurement — rig configuration
# Edited from Settings, or by hand. Validated on every start; if anything is
# invalid the app uses built-in defaults and shows a warning.
#
# [safety] is the SOFTWARE safety layer only. It cannot protect the sample if
# the PC or the app crashes — an independent hardware over-temperature cut-off
# is still required for unattended runs. Set max_temperature_C above the
# hottest normal run temperature and below the damage temperature of the
# sample, fixture, wiring and thermocouples.
"""


def to_toml(cfg: AppConfig) -> str:
    body = _toml_lines(cfg.to_dict())
    return _HEADER + f"\nschema_version = {SCHEMA_VERSION}\n\n" + "\n".join(body).lstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# File I/O + cache
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_cached: Optional[AppConfig] = None
_warnings: List[str] = []


def config_path() -> Path:
    override = os.environ.get("TE_CONFIG_PATH")
    if override:
        return Path(override)
    return get_app_dir() / CONFIG_FILENAME


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_config() -> AppConfig:
    """Read the config file (creating it with defaults if missing).

    Never raises: on any problem the defaults are returned and the reasons are
    available from ``load_warnings()``. A malformed file is left untouched so the
    user can fix it.
    """
    global _warnings
    path = config_path()
    _warnings = []
    if not path.exists():
        cfg = AppConfig()
        try:
            _write_atomic(path, to_toml(cfg))
            logger.info("Created default config at %s", path)
        except OSError as exc:
            logger.error("Could not write default config %s: %s", path, exc)
        return cfg
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        cfg = from_dict(data)
        logger.info("Loaded config from %s", path)
        return cfg
    except ConfigError as exc:
        _warnings = [f"{path.name}: {p}" for p in exc.problems]
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _warnings = [f"{path.name}: {exc}"]
    for w in _warnings:
        logger.error("config: %s", w)
    logger.error("Using built-in default configuration.")
    return AppConfig()


def get_config() -> AppConfig:
    """Cached configuration (loaded on first use)."""
    global _cached
    with _lock:
        if _cached is None:
            _cached = load_config()
        return _cached


def reload_config() -> AppConfig:
    global _cached
    with _lock:
        _cached = load_config()
        return _cached


def save_config(cfg: AppConfig) -> None:
    """Validate, write atomically and make ``cfg`` the active configuration.

    Raises ConfigError (nothing is written) if the config is invalid.
    """
    global _cached, _warnings
    problems = validate(cfg)
    if problems:
        raise ConfigError(problems)
    _write_atomic(config_path(), to_toml(cfg))
    with _lock:
        _cached = cfg.copy()
        _warnings = []
    logger.info("Saved config to %s", config_path())


def load_warnings() -> List[str]:
    """Problems found in the config file at the last load (empty if none)."""
    return list(_warnings)

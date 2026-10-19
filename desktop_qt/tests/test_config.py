import tomllib

import pytest

from app.core import config as C


def test_defaults_are_valid():
    assert C.validate(C.AppConfig()) == []


def test_missing_file_is_created_with_defaults(isolated_config):
    cfg = C.get_config()
    assert isolated_config.exists()
    assert cfg == C.AppConfig()
    assert C.load_warnings() == []


def test_round_trip_through_toml(isolated_config):
    cfg = C.AppConfig()
    cfg.instruments.k2700 = "GPIB0::17::INSTR"
    cfg.thermocouples.in_plane_t1 = 110
    cfg.safety.max_temperature_C = 95.5
    cfg.heater.out_plane.current_max_A = 0.8
    cfg.ir_camera.legacy_dll = r"D:\SDK\x64\lib \"quoted\".dll"
    C.save_config(cfg)
    loaded = C.reload_config()
    assert loaded == cfg
    # the file is valid TOML with the schema version
    data = tomllib.loads(isolated_config.read_text(encoding="utf-8"))
    assert data["schema_version"] == C.SCHEMA_VERSION


def test_int_accepted_for_float_fields():
    cfg = C.from_dict({"safety": {"max_temperature_C": 90}})
    assert cfg.safety.max_temperature_C == 90.0
    assert isinstance(cfg.safety.max_temperature_C, float)


@pytest.mark.parametrize("data, needle", [
    ({"thermocouples": {"in_plane_t1": 104}}, "different channels"),
    ({"thermocouples": {"out_plane_t2": 99}}, "101–240"),
    ({"heater": {"in_plane": {"current_max_A": 5.0}}}, "current_max_A"),
    ({"heater": {"out_plane": {"voltage_drive_max_V": 500.0}}}, "voltage_drive_max_V"),
    ({"safety": {"max_temperature_C": 700.0}}, "plausible_max_C"),
    ({"safety": {"max_consecutive_invalid_reads": 0}}, "invalid_reads"),
    ({"visa_timeout_ms": {"k2700": 10}}, "500–120000"),
    ({"instruments": {"k2182a": "  "}}, "must not be empty"),
    ({"safety": {"max_temperature_C": "hot"}}, "expected a number"),
    ({"thermocouples": {"open_tc_detect": 1}}, "true/false"),
    ({"heater": 3}, "expected a table"),
])
def test_invalid_values_raise(data, needle):
    with pytest.raises(C.ConfigError) as exc:
        C.from_dict(data)
    assert any(needle in p for p in exc.value.problems), exc.value.problems


def test_unknown_keys_are_ignored():
    cfg = C.from_dict({"future_section": {"x": 1}, "safety": {"new_knob": 2}})
    assert cfg == C.AppConfig()


def test_bad_file_falls_back_to_defaults_with_warnings(isolated_config):
    isolated_config.write_text('[safety]\nmax_temperature_C = 5000\n', encoding="utf-8")
    cfg = C.get_config()
    assert cfg == C.AppConfig()
    assert C.load_warnings()
    # the user's file is left untouched for them to fix
    assert "5000" in isolated_config.read_text(encoding="utf-8")


def test_malformed_toml_falls_back(isolated_config):
    isolated_config.write_text("this is = = not toml", encoding="utf-8")
    assert C.get_config() == C.AppConfig()
    assert C.load_warnings()


def test_save_rejects_invalid_and_writes_nothing(isolated_config):
    C.get_config()
    before = isolated_config.read_text(encoding="utf-8")
    bad = C.AppConfig()
    bad.safety.max_temperature_C = -5.0
    with pytest.raises(C.ConfigError):
        C.save_config(bad)
    assert isolated_config.read_text(encoding="utf-8") == before


def test_helpers_select_by_probe_mode():
    cfg = C.AppConfig()
    assert cfg.tc_channels("in_plane") == (102, 104)
    assert cfg.tc_channels("OUT_PLANE") == (103, 105)
    assert cfg.heater_limit("out_plane").voltage_drive_max_V == 40.0
    assert cfg.heater_limit("anything").voltage_drive_max_V == 10.0


def test_copy_is_independent():
    a = C.AppConfig()
    b = a.copy()
    b.safety.max_temperature_C = 50.0
    assert a.safety.max_temperature_C == 120.0

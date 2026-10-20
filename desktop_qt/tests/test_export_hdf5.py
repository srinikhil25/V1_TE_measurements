import hashlib
import json
import math
from datetime import datetime

import pytest

h5py = pytest.importorskip("h5py")

from app.core.run_context import build_run_context  # noqa: E402
from app.models.db_models import (  # noqa: E402
    Measurement, MeasurementIntegrity, MeasurementRow)
from app.services.export_hdf5 import export_measurement  # noqa: E402


def _store(factory, uid, mtype, rows, params):
    s = factory()
    m = Measurement(user_id=uid, lab_id=None, type=mtype, status="aborted",
                    end_reason="Safety abort: over-temperature", sample_id="CAF-1",
                    operator="alice", notes="test", params_json=json.dumps(params),
                    started_at=datetime(2026, 10, 19, 5, 0, 0),
                    finished_at=datetime(2026, 10, 19, 5, 30, 0))
    s.add(m)
    s.flush()
    for i, r in enumerate(rows, start=1):
        s.add(MeasurementRow(measurement_id=m.id, seq=i, elapsed_s=i, data_json=json.dumps(r)))
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    s.add(MeasurementIntegrity(measurement_id=m.id,
                               data_hash=hashlib.sha256(canonical.encode()).hexdigest()))
    s.commit()
    mid = m.id
    s.close()
    return mid


def _seebeck_rows():
    rows = []
    for i in range(30):
        dt = 0.2 * i
        rows.append({"Time [s]": i, "TEMF [mV]": -0.05 * dt, "Temp1 [oC]": 25.0,
                     "Temp2 [oC]": 25.0 + dt, "Delta Temp [oC]": dt, "T0 [oC]": 25 + dt / 2,
                     "T0 [K]": 298.15 + dt / 2, "delta_T_over_T0": dt / 300,
                     "S [µV/K]": -50.0 if dt >= 0.01 else None,
                     "Heater V [V]": None, "Heater I [A]": None,
                     "branch": "heating", "valid": True, "flag": None})
    rows.append({**rows[-1], "Temp1 [oC]": None, "Delta Temp [oC]": None, "T0 [K]": None,
                 "S [µV/K]": None, "valid": False, "flag": "T1 overflow (open thermocouple?)"})
    return rows


def test_seebeck_export_structure(app_db, make_user, tmp_path):
    _p, factory = app_db
    uid = make_user("alice", "super_admin")
    ctx = build_run_context({"k2700": {"address": "GPIB0::16::INSTR", "idn": "KEITHLEY,MODEL 2700"}})
    mid = _store(factory, uid, "seebeck", _seebeck_rows(), {"interval": 2, "run_context": ctx})

    out = export_measurement(mid, str(tmp_path / "run.h5"))
    with h5py.File(out, "r") as f:
        assert f.attrs["default"] == "entry"
        e = f["entry"]
        assert e.attrs["NX_class"] == "NXentry"
        assert e["status"][()].decode() == "aborted"
        assert e["start_time"][()].decode().startswith("2026-10-19T05:00:00")
        assert e["sample/name"][()].decode() == "CAF-1"
        d = e["data"]
        assert d.attrs["signal"] == "seebeck_coefficient" and d.attrs["axes"] == "T0"
        assert d["seebeck_coefficient"].attrs["units"] == "uV/K"
        assert d["T1"].shape == (31,)
        assert math.isnan(d["T1"][30])                       # missing stays missing
        assert list(d["valid"][-2:]) == [1, 0]
        assert d["flag"][30].decode().startswith("T1 overflow")
        assert e["instrument/k2700/idn"][()].decode() == "KEITHLEY,MODEL 2700"
        assert e["parameters/interval"][()] == 2
        assert "run_context" not in e["parameters"]
        sw = e["provenance/software/version"][()].decode()
        assert sw
        assert json.loads(e["provenance/run_context_json"][()])["config"]["safety"]
        assert bool(e["integrity/match"][()]) is True
        assert "seebeck_coefficient" in e["analysis"]


def test_iv_export_and_audit(app_db, make_user, tmp_path):
    from app.core import audit
    _p, factory = app_db
    uid = make_user("bob")
    rows = [{"current": i * 1e-3, "voltage": 2.0 * i * 1e-3, "resistance": 2.0 if i else None,
             "resistivity": None, "conductivity": None} for i in range(-3, 4)]
    mid = _store(factory, uid, "iv", rows, {"geometry": "bar", "length": 1.0, "thickness": 0.01})

    out = export_measurement(mid, str(tmp_path / "iv.h5"))
    with h5py.File(out, "r") as f:
        e = f["entry"]
        assert e["data"].attrs["signal"] == "voltage"
        assert e["data/current"].attrs["units"] == "A"
        assert e["analysis/fit_resistance"][()] == pytest.approx(2.0)
        assert e["sample/length"].attrs["units"] == "cm"
        assert "note" in e["provenance"]          # run recorded before snapshots existed
    last = audit.recent()[0]
    assert last["action"] == "export" and last["measurement_id"] == mid
    assert last["details"]["format"] == "HDF5/NeXus"


def test_export_unknown_measurement(app_db, tmp_path):
    with pytest.raises(ValueError):
        export_measurement(9999, str(tmp_path / "x.h5"))

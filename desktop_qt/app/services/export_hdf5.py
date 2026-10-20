"""Export a stored measurement to HDF5 with NeXus base-class structure.

One self-describing file per run: data columns with units, the analysis, the
settings snapshot (software version, rig configuration, instrument *IDN?), the
run's audit-trail entries and an integrity check. Readable by any HDF5 tool
(h5py, HDFView, NeXpy, MATLAB, Origin).

Layout (NeXus base classes; no NeXus *application definition* is claimed,
because none exists for Seebeck / I-V measurements)::

    /entry                      NXentry      title, times, status, end_reason
      user                      NXuser       operator, lab
      sample                    NXsample     sample_id, notes
      instrument                NXinstrument one NXcollection per instrument
      parameters                NXparameters run parameters
      data                      NXdata       measured columns (default plot)
      analysis                  NXprocess    binned Seebeck fit / I-V fit
      provenance                NXcollection run_context (software, host, config)
      audit                     NXcollection audit entries for this run
      integrity                 NXcollection stored vs recomputed SHA-256
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..version import APP_VERSION

# key in stored row -> (dataset name, units)
SEEBECK_COLUMNS: Dict[str, Tuple[str, Optional[str]]] = {
    "Time [s]": ("time", "s"),
    "TEMF [mV]": ("thermoelectric_voltage", "mV"),
    "Temp1 [oC]": ("T1", "degC"),
    "Temp2 [oC]": ("T2", "degC"),
    "Delta Temp [oC]": ("delta_T", "K"),
    "T0 [oC]": ("T0_celsius", "degC"),
    "T0 [K]": ("T0", "K"),
    "delta_T_over_T0": ("delta_T_over_T0", ""),
    "S [µV/K]": ("seebeck_coefficient", "uV/K"),
    "Heater V [V]": ("heater_voltage", "V"),
    "Heater I [A]": ("heater_current", "A"),
    "branch": ("branch", None),
    "valid": ("valid", None),
    "flag": ("flag", None),
}
IV_COLUMNS: Dict[str, Tuple[str, Optional[str]]] = {
    "current": ("current", "A"),
    "voltage": ("voltage", "V"),
    "resistance": ("resistance", "Ohm"),
    "resistivity": ("resistivity", "Ohm*cm"),
    "conductivity": ("conductivity", "S/cm"),
}


def _safe_name(key: str) -> str:
    n = re.sub(r"[^0-9A-Za-z_]+", "_", key).strip("_")
    return n or "column"


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)      # stored timestamps are naive UTC
    return dt.isoformat()


def _str_ds(group, name: str, value: Any):
    import h5py
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return group.create_dataset(name, data=text, dtype=h5py.string_dtype("utf-8"))


def _scalar(group, name: str, value: Any, units: Optional[str] = None):
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        ds = group.create_dataset(name, data=value)
    elif isinstance(value, (dict, list)):
        ds = _str_ds(group, name, value)
    else:
        ds = _str_ds(group, name, str(value))
    if units:
        ds.attrs["units"] = units
    return ds


def _group(parent, name: str, nx_class: str):
    g = parent.create_group(name)
    g.attrs["NX_class"] = nx_class
    return g


def _write_columns(group, rows: List[Dict[str, Any]],
                   known: Dict[str, Tuple[str, Optional[str]]]) -> List[str]:
    """Write one dataset per column. Numbers → float64 with NaN for missing."""
    import h5py
    import numpy as np

    keys: List[str] = list(known)
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    written = []
    for key in keys:
        values = [r.get(key) for r in rows]
        if all(v is None for v in values) and key not in known:
            continue
        name, units = known.get(key, (_safe_name(key), None))
        present = [v for v in values if v is not None]
        if present and all(isinstance(v, bool) for v in present):
            data = np.array([-1 if v is None else int(v) for v in values], dtype="i1")
            ds = group.create_dataset(name, data=data)
            ds.attrs["long_name"] = f"{key} (1 = true, 0 = false, -1 = missing)"
        elif present and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                             for v in present):
            data = np.array([math.nan if v is None else float(v) for v in values], dtype="f8")
            ds = group.create_dataset(name, data=data, compression="gzip")
            ds.attrs["long_name"] = key
        else:
            data = ["" if v is None else str(v) for v in values]
            ds = group.create_dataset(name, data=data, dtype=h5py.string_dtype("utf-8"))
            ds.attrs["long_name"] = key
        if units:
            ds.attrs["units"] = units
        written.append(name)
    return written


def _load(measurement_id: int) -> Dict[str, Any]:
    from ..core import audit, database
    from ..models.db_models import Lab, Measurement, MeasurementIntegrity, MeasurementRow, User

    db = database.SessionLocal()
    try:
        m = db.query(Measurement).filter_by(id=measurement_id).first()
        if m is None:
            raise ValueError(f"Measurement {measurement_id} not found")
        rows = (db.query(MeasurementRow).filter_by(measurement_id=measurement_id)
                .order_by(MeasurementRow.seq).all())
        integ = db.query(MeasurementIntegrity).filter_by(measurement_id=measurement_id).first()
        user = db.query(User).filter_by(id=m.user_id).first()
        lab = db.query(Lab).filter_by(id=m.lab_id).first() if m.lab_id else None
        info = {
            "id": m.id, "type": m.type, "status": m.status, "end_reason": m.end_reason,
            "sample_id": m.sample_id, "operator": m.operator, "notes": m.notes,
            "params": json.loads(m.params_json) if m.params_json else {},
            "started_at": m.started_at, "finished_at": m.finished_at,
            "user": user.username if user else None, "lab": lab.name if lab else None,
            "stored_hash": integ.data_hash if integ else None,
            "data": [json.loads(r.data_json) for r in rows],
        }
    finally:
        db.close()
    info["audit"] = list(reversed(audit.recent(limit=1000, measurement_id=measurement_id)))
    return info


def export_measurement(measurement_id: int, path: str) -> str:
    """Write ``path`` (.h5) for the stored measurement. Returns the path."""
    import h5py

    from ..core import audit

    info = _load(measurement_id)
    data = info["data"]
    params = dict(info["params"])
    run_context = params.pop("run_context", None)
    is_seebeck = info["type"] == "seebeck"

    with h5py.File(path, "w") as f:
        f.attrs["default"] = "entry"
        f.attrs["file_name"] = path.replace("\\", "/").rsplit("/", 1)[-1]
        f.attrs["file_time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        f.attrs["creator"] = "TE Measurement"
        f.attrs["creator_version"] = APP_VERSION
        f.attrs["HDF5_Version"] = h5py.version.hdf5_version
        f.attrs["h5py_version"] = h5py.version.version

        entry = _group(f, "entry", "NXentry")
        entry.attrs["default"] = "data"
        kind = "Seebeck coefficient" if is_seebeck else "I-V sweep / resistivity"
        _scalar(entry, "title", f"{kind} — sample {info['sample_id'] or '?'} (run {info['id']})")
        _scalar(entry, "experiment_identifier", f"TE-{info['id']}")
        _scalar(entry, "measurement_type", info["type"])
        _scalar(entry, "start_time", _iso(info["started_at"]))
        _scalar(entry, "end_time", _iso(info["finished_at"]))
        _scalar(entry, "status", info["status"])
        _scalar(entry, "end_reason", info["end_reason"])
        prog = _scalar(entry, "program_name", "TE Measurement")
        prog.attrs["version"] = APP_VERSION

        user = _group(entry, "user", "NXuser")
        _scalar(user, "name", info["operator"] or info["user"])
        _scalar(user, "username", info["user"])
        _scalar(user, "affiliation", info["lab"])

        sample = _group(entry, "sample", "NXsample")
        _scalar(sample, "name", info["sample_id"])
        _scalar(sample, "description", info["notes"])
        if not is_seebeck:
            for key, units in (("length", "cm"), ("width", "cm"), ("thickness", "cm")):
                _scalar(sample, key, params.get(key), units)
            _scalar(sample, "geometry", params.get("geometry"))

        instrument = _group(entry, "instrument", "NXinstrument")
        _scalar(instrument, "name", "TE Measurement rig")
        for key, dev in ((run_context or {}).get("instruments") or {}).items():
            g = _group(instrument, key, "NXcollection")
            for k, v in dev.items():
                _scalar(g, k, v)

        pg = _group(entry, "parameters", "NXparameters")
        for k, v in params.items():
            _scalar(pg, _safe_name(k), v)
        _str_ds(pg, "all_parameters_json", params)

        dg = _group(entry, "data", "NXdata")
        cols = SEEBECK_COLUMNS if is_seebeck else IV_COLUMNS
        written = _write_columns(dg, data, cols)
        if is_seebeck and {"seebeck_coefficient", "T0"} <= set(written):
            dg.attrs["signal"], dg.attrs["axes"] = "seebeck_coefficient", "T0"
        elif not is_seebeck and {"voltage", "current"} <= set(written):
            dg.attrs["signal"], dg.attrs["axes"] = "voltage", "current"
        _scalar(dg, "n_points", len(data))

        an = _group(entry, "analysis", "NXprocess")
        _scalar(an, "program", "TE Measurement")
        _scalar(an, "version", APP_VERSION)
        if is_seebeck:
            from ..instruments.seebeck_analysis import binned_seebeck_analysis
            bins = binned_seebeck_analysis(data, bin_width_k=10.0)
            _scalar(an, "method", "Linear fit of thermoelectric voltage vs ΔT per 10 K bin of "
                                  "T0, rejection of rare (<= 5 %) spikes beyond 5 robust sigma (MAD)")
            if bins:
                _write_columns(an, bins, {
                    "T0_center_K": ("T0_center", "K"),
                    "S_uV_per_K": ("seebeck_coefficient", "uV/K"),
                    "S_uncertainty_uV_per_K": ("seebeck_uncertainty", "uV/K"),
                    "n_points": ("n_points_fitted", None),
                    "n_rejected": ("n_outliers_rejected", None),
                })
        else:
            from .measurement_service import _linear_fit_resistance, _ohmic_status, _valid_iv_count
            R, R2 = _linear_fit_resistance(data)
            _scalar(an, "method", "Least-squares fit V = R*I + V0 (offset absorbs thermal EMF)")
            _scalar(an, "fit_resistance", R, "Ohm")
            _scalar(an, "fit_R_squared", R2)
            _scalar(an, "ohmic_status", _ohmic_status(R2, _valid_iv_count(data)))

        prov = _group(entry, "provenance", "NXcollection")
        if run_context:
            _str_ds(prov, "run_context_json", run_context)
            for k in ("software", "host"):
                sub = _group(prov, k, "NXcollection")
                for kk, vv in (run_context.get(k) or {}).items():
                    _scalar(sub, kk, vv)
        else:
            _scalar(prov, "note", "Run recorded before settings snapshots were introduced.")

        au = _group(entry, "audit", "NXcollection")
        _str_ds(au, "entries_json", info["audit"])
        _scalar(au, "n_entries", len(info["audit"]))

        ig = _group(entry, "integrity", "NXcollection")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        _scalar(ig, "algorithm", "SHA-256 of canonical JSON of all data rows")
        _scalar(ig, "stored_hash", info["stored_hash"])
        _scalar(ig, "recomputed_hash", recomputed)
        _scalar(ig, "match", info["stored_hash"] == recomputed if info["stored_hash"] else None)

    audit.record("export", measurement_id=measurement_id,
                 details={"format": "HDF5/NeXus",
                          "file": path.replace("\\", "/").rsplit("/", 1)[-1],
                          "points": len(data)})
    return path

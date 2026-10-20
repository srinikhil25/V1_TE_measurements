"""Calculation correctness (CALC-1…4): no silent fallbacks, polarity check,
robust Seebeck fit, ohmic verdict needs enough points."""

import math
import random

import pytest

from app.instruments import seebeck_analysis as sa
from app.services import measurement_service as ms


# ── CALC-3: robust binned fit ─────────────────────────────────────────────
def _rows(n=40, s_uv=-40.0, t0=300.0, spike_at=(), noise=0.0005, seed=1):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        dt = -0.25 * (i + 1)                          # heating: ΔT negative
        temf = s_uv / 1000.0 * dt + rnd.gauss(0, noise)
        if i in spike_at:
            temf += 0.5                               # EMI spike: +0.5 mV
        rows.append({"T0 [K]": t0 + 0.1 * i, "Delta Temp [oC]": dt, "TEMF [mV]": temf,
                     "branch": "heating", "valid": True})
    return rows


def test_clean_data_robust_equals_plain_fit():
    rows = _rows()
    robust = sa.binned_seebeck_analysis(rows)
    plain = sa.binned_seebeck_analysis(rows, reject_outliers=False)
    assert len(robust) == 1 and robust[0]["n_rejected"] == 0
    assert robust[0]["S_uV_per_K"] == plain[0]["S_uV_per_K"]
    assert robust[0]["S_uV_per_K"] == pytest.approx(-40.0, abs=0.5)


def test_a_spike_is_rejected_and_does_not_bias_s():
    rows = _rows(spike_at=(20,))
    plain = sa.binned_seebeck_analysis(rows, reject_outliers=False)[0]
    robust = sa.binned_seebeck_analysis(rows)[0]
    assert robust["n_rejected"] == 1 and robust["n_points"] == 39
    assert abs(robust["S_uV_per_K"] + 40.0) < 0.5
    assert abs(plain["S_uV_per_K"] + 40.0) > abs(robust["S_uV_per_K"] + 40.0)


def test_robust_fit_never_clips_below_three_points():
    fit = sa.robust_linear_fit([1, 2, 3, 4], [1, 2, 3, 40])
    assert fit is not None and fit["n_used"] >= 3


def test_invalid_rows_are_ignored_by_the_bins():
    rows = _rows()
    rows[5]["valid"] = False
    rows[5]["TEMF [mV]"] = 99.0
    assert sa.binned_seebeck_analysis(rows)[0]["n_rejected"] == 0


# ── CALC-2: polarity check ────────────────────────────────────────────────
def test_polarity_ok_for_hot_t1():
    assert sa.polarity_check(_rows()) is None


def test_polarity_flags_swapped_thermocouples():
    rows = _rows()
    for r in rows:
        r["Delta Temp [oC]"] = -r["Delta Temp [oC]"]
    msg = sa.polarity_check(rows)
    assert msg and "swapped" in msg


def test_polarity_ignores_cooling_and_small_gradients():
    rows = [{"branch": "cooling", "Delta Temp [oC]": 5.0}] * 20 + \
           [{"branch": "heating", "Delta Temp [oC]": 0.1}] * 20
    assert sa.polarity_check(rows) is None


def _run_fake(temps):
    from app.core.config import AppConfig
    from app.instruments import session_manager as sm
    from tests.test_session_manager import PARAMS, FakeRig, make, run  # noqa: F401
    sm_get = sm.get_config
    sm.get_config = lambda: AppConfig()
    try:
        mgr = make(FakeRig(temps))
        st = run(mgr)
    finally:
        sm.get_config = sm_get
    return mgr, st


def test_session_reports_polarity_warning_live():
    # T2 heated = the hot/cold channels swapped relative to the convention.
    _mgr, st = _run_fake(lambda n, i, on: (25.0, 25.0 + 10.0 * i if on else 25.0))
    assert st["polarity_warning"] and "swapped" in st["polarity_warning"]


def test_session_no_polarity_warning_for_correct_wiring():
    mgr, st = _run_fake(lambda n, i, on: (25.0 + 10.0 * i if on else 25.0, 25.0))
    assert st["polarity_warning"] is None
    hot = [r for r in mgr.get_data() if (r["Delta Temp [oC]"] or 0) < -1]
    assert hot and all(r["S [µV/K]"] == pytest.approx(-50.0) for r in hot)


# ── CALC-1: S blank always has a reason ──────────────────────────────────
def test_blank_s_has_a_reason():
    mgr, _st = _run_fake(lambda n, i, on: (25.0 + 10.0 * i if on else 25.0, 25.0))
    for r in mgr.get_data():
        if r["S [µV/K]"] is None:
            assert r["S_note"], r
        else:
            assert r["S_note"] is None
    assert any(r["S_note"] == "|ΔT| below 0.01 K" for r in mgr.get_data())


# ── CALC-1: resistivity model ────────────────────────────────────────────
def test_bar_and_vdp_formulas_unchanged():
    m = ms.resistivity_model("bar", 1.0, 0.5, 0.01)
    assert m["rho_per_ohm"] == pytest.approx(0.5 * 0.01 / 1.0) and m["notes"] == []
    v = ms.resistivity_model("vdp", None, None, 0.002)
    assert v["rho_per_ohm"] == pytest.approx(math.pi * 0.002 / math.log(2))


def test_missing_dimensions_are_named():
    m = ms.resistivity_model("bar", 1.0, None, 0)
    assert m["rho_per_ohm"] is None
    assert "width, thickness" in m["notes"][0]
    assert "thickness" in ms.resistivity_model("vdp", None, None, None)["notes"][0]


def test_4pp_size_correction_applied_when_it_fits():
    m = ms.resistivity_model("4pp", 2.0, 2.0, 0.053, spacing=0.2)
    assert m["notes"] == []
    assert 0 < m["size_factor"] < 1 and m["thickness_factor"] is not None


def test_4pp_fallbacks_are_reported_not_silent():
    no_fit = ms.resistivity_model("4pp", 0.5, 2.0, 0.053, spacing=0.2)   # 3·s = 0.6 > 0.5
    assert no_fit["size_factor"] is None
    assert any("does not fit" in n and "NOT applied" in n for n in no_fit["notes"])
    no_dims = ms.resistivity_model("4pp", None, None, 0.053, spacing=0.2)
    assert any("length/width" in n for n in no_dims["notes"])
    no_s = ms.resistivity_model("4pp", 2.0, 2.0, 0.053)
    assert any("F(t/s)" in n for n in no_s["notes"])
    assert no_s["rho_per_ohm"] == pytest.approx(math.pi / math.log(2) * 0.053)


def test_enrich_point_matches_model():
    model = ms.resistivity_model("4pp", 2.0, 2.0, 0.053, spacing=0.2)
    pt = {"resistance": 2.67e-4}
    ms._enrich_point(pt, 2.0, 2.0, 0.053, "4pp", 0.2, model=model)
    assert pt["resistivity"] == pytest.approx(2.67e-4 * model["rho_per_ohm"])


# ── CALC-4: ohmic verdict ────────────────────────────────────────────────
def test_ohmic_needs_five_points():
    assert ms._ohmic_status(0.99999, n_points=3) == "too_few_points"
    assert ms._ohmic_status(0.99999, n_points=5) == "ohmic"
    assert ms._ohmic_status(0.99999) == "ohmic"                # n unknown: old behaviour


def test_sweep_with_three_points_gets_no_ohmic_verdict(monkeypatch):
    from tests.test_iv import Fake2401, FakeSystem
    monkeypatch.setattr(ms, "_get_seebeck_system", lambda: (lambda: FakeSystem(Fake2401())))
    res = ms.run_iv_sweep(start=-1e-3, stop=1e-3, points=3, delay_ms=0)
    assert res["ohmic_status"] == "too_few_points" and res["n_valid"] == 2   # I = 0 excluded
    assert res["resistivity_model"]["geometry"] == "bar"


def test_structured_residuals_are_flagged_not_clipped():
    # 75 % on the line, 25 % lagging by +0.05 mV (e.g. hysteresis): not spikes.
    rows = _rows(n=40)
    for i, r in enumerate(rows):
        if i % 4 == 0:
            r["TEMF [mV]"] += 0.05
    robust = sa.binned_seebeck_analysis(rows)[0]
    plain = sa.binned_seebeck_analysis(rows, reject_outliers=False)[0]
    assert robust["n_rejected"] == 0 and robust["n_points"] == 40
    assert robust["S_uV_per_K"] == plain["S_uV_per_K"]
    assert "hysteresis" in robust["fit_warning"]


# ── Run library summaries ────────────────────────────────────────────────
class _Run:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, _k):
        return None


def test_library_quality_for_seebeck_runs():
    from app.ui.pages.history_page import _summarise
    good = _summarise(_Run(type="seebeck", status="finished"), _rows())
    assert good["quality"][0] == "OK" and good["result"].startswith("S ≈")
    swapped = _rows()
    for r in swapped:
        r["Delta Temp [oC]"] = -r["Delta Temp [oC]"]
    assert _summarise(_Run(type="seebeck", status="finished"), swapped)["quality"][0] == \
        "Check polarity"
    assert _summarise(_Run(type="seebeck", status="finished"), _rows(n=2))["quality"][0] == \
        "No S fit"


def test_library_derives_rho_notes_for_old_runs():
    from app.ui.pages.history_page import _rho_notes
    old = {"geometry": "4pp", "length": 1.0, "width": 0.5, "thickness": 0.05, "spacing": 0.5}
    assert any("does not fit" in n for n in _rho_notes(old))
    assert _rho_notes({"resistivity_model": {"notes": []}, **old}) == []   # stored wins
    assert _rho_notes({}) == []

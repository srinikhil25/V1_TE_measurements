"""Live-chart data reduction (UI-2): buffers, thinning, Seebeck page charts."""

import math
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.ui.widgets.plot_data import ColumnBuffer, thin


def test_column_buffer_grows_and_maps_none_to_nan():
    b = ColumnBuffer(2, capacity=16)
    for i in range(1000):
        b.append((i, None if i % 7 == 0 else i * 2))
    assert len(b) == 1000
    assert b.col(0)[-1] == 999
    assert math.isnan(b.col(1)[0]) and b.col(1)[1] == 2
    assert b.last() == (999, 1998)
    b.clear()
    assert len(b) == 0 and b.last() is None


def test_thin_bounds_points_and_keeps_newest():
    x = np.arange(10_001, dtype=float)
    tx, ty = thin(x, x * 2, max_points=3000)
    assert len(tx) <= 3000
    assert tx[-1] == 10_000 and ty[-1] == 20_000
    assert np.all(np.diff(tx) > 0)
    sx, _ = thin(x[:50], x[:50])
    assert len(sx) == 50


# ── Seebeck page ───────────────────────────────────────────────────────────
pytest.importorskip("pytestqt")


def _rows(n, cool_from=None):
    rows = []
    for i in range(n):
        cooling = cool_from is not None and i >= cool_from
        dt = (n - i) * 0.01 if cooling else i * 0.01
        rows.append({
            "Time [s]": float(i), "Temp1 [oC]": 25 + dt, "Temp2 [oC]": 25.0,
            "TEMF [mV]": None if i % 97 == 0 else -0.04 * dt,
            "Delta Temp [oC]": dt, "T0 [K]": 298.15 + dt / 2,
            "S [µV/K]": -40.0 if i > 5 else None,
            "branch": "cooling" if cooling else "heating",
        })
    return rows


@pytest.fixture
def page(qtbot):
    from app.ui.pages.seebeck_page import SeebeckPage
    p = SeebeckPage(SimpleNamespace(id=1, username="t", role="researcher", lab_id=None))
    qtbot.addWidget(p)
    return p


def test_incremental_polls_match_a_full_recompute(page):
    rows = _rows(12_000, cool_from=8_000)
    # Simulate polls that each deliver a growing copy of the run's rows.
    for n in (1, 50, 3_000, 7_999, 8_000, 8_001, 12_000):
        page._data = list(rows[:n])
        page._refresh_charts()

    t = page.curve_t1.xData
    assert len(t) == 12_000                         # full data kept, not thinned
    assert np.array_equal(t, np.arange(12_000, dtype=float))
    temf = page.curve_temf.yData
    assert math.isnan(temf[0]) and temf[1] == pytest.approx(-0.04 * 0.01)

    heat = [(r["Delta Temp [oC]"], r["TEMF [mV]"]) for r in rows[:8_000]
            if r["TEMF [mV]"] is not None]
    assert len(page._buf_heat) == len(heat)
    cool_n = sum(1 for r in rows[8_000:] if r["TEMF [mV]"] is not None)
    assert len(page._buf_cool) == cool_n + 1         # seeded with the heating peak
    assert page._buf_cool.col(0)[0] == heat[-1][0]

    # What is drawn for parametric curves is thinned, and ends at the newest point.
    assert len(page.curve_heat.xData) <= 3000
    assert page.curve_cool.xData[-1] == page._buf_cool.col(0)[-1]
    assert page.curve_t1.opts["autoDownsample"] and page.curve_t1.opts["clipToView"]
    assert page.curve_temf.opts["autoDownsample"]


def test_new_run_resets_the_chart_buffers(page):
    page._data = _rows(500)
    page._refresh_charts()
    page._data = _rows(20)                # a shorter list = a different run
    page._refresh_charts()
    assert len(page.curve_t1.xData) == 20
    page._clear_results()
    assert page._rows_charted == 0 and len(page._buf_time) == 0


def test_long_run_poll_stays_cheap(page):
    rows = _rows(12_000, cool_from=8_000)
    page._data = list(rows[:11_999])
    page._refresh_charts()
    page._data = list(rows)
    t0 = time.perf_counter()
    page._refresh_charts()                # one poll on a ~3 h run
    assert time.perf_counter() - t0 < 0.5


def test_run_detail_window_draws_long_run_without_errors(qtbot):
    from app.ui.pages import history_page as hp

    class Run(SimpleNamespace):
        def __getattr__(self, _k):
            return None

    w = hp.RunDetailWindow(None, Run(id=1, type="seebeck", status="completed"),
                           _rows(5_000, cool_from=3_500), None)
    qtbot.addWidget(w)
    w.show()
    qtbot.wait(50)

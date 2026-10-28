"""Thermal camera: regions of interest, the simulated camera, the live view's
mouse handling, the camera panel and the Seebeck page around them."""

import time
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, Qt

from app.instruments import visa_backend
from app.services import ir_regions
from app.services.ir_camera_service import SIM_SHAPE, IrCameraService, sim_scene
from app.services.ir_regions import Region, RegionStore, camera_snapshot, region_key, stats


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh region store for this test (the app keeps one per process)."""
    s = RegionStore(tmp_path / "ir_regions.json")
    monkeypatch.setattr(ir_regions, "_store", s)
    return s


@pytest.fixture
def camera(monkeypatch, store):
    """The simulated camera, connected."""
    monkeypatch.setenv(visa_backend.ENV_VAR, "sim")
    svc = IrCameraService()
    assert svc.connect()
    yield svc
    svc.disconnect()


def _user():
    return SimpleNamespace(id=1, username="tester", role="researcher", lab_id=None)


# ── regions ──────────────────────────────────────────────────────────────────
def test_stats_and_clipping():
    frame = np.arange(20, dtype=np.float32).reshape(4, 5)
    st = stats(frame, Region("R1", "", 1, 1, 2, 2))
    assert st == {"min": 6.0, "mean": 9.0, "max": 12.0}
    # a region hanging off the frame is moved inside it, not cut to nothing
    assert Region("R1", "", 4, 3, 3, 3).clipped((4, 5)) == Region("R1", "", 2, 1, 3, 3)
    frame[:] = np.nan
    assert stats(frame, Region("R1", "", 0, 0, 2, 2)) is None


def test_store_keeps_regions_per_geometry_and_survives_a_restart(tmp_path):
    path = tmp_path / "r.json"
    s = RegionStore(path)
    assert [r.name for r in s.regions()] == ["R1"]          # default: frame centre
    s.set_regions([Region("R1", "hot side", 10, 20, 5, 5), Region("R2", "cold side", 50, 20, 5, 5),
                   Region("R3", "extra", 0, 0, 1, 1)])
    s.set_geometry("out_plane")
    assert len(s.regions()) == 1                             # other geometry: default
    again = RegionStore(path)
    assert [(r.name, r.x) for r in again.regions()] == [("R1", 10), ("R2", 50)]  # max 2


def test_a_broken_region_file_is_ignored(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    assert [r.name for r in RegionStore(path).regions()] == ["R1"]


def test_snapshot_needs_a_fresh_frame(store):
    store.set_regions([Region("R1", "", 0, 0, 2, 2), Region("R2", "", 2, 2, 2, 2)])
    frame = np.full((4, 4), 30.0, dtype=np.float32)
    frame[2:, 2:] = 25.0
    assert store.snapshot(frame, 0.1) == {region_key("R1"): 30.0, region_key("R2"): 25.0}
    assert store.snapshot(frame, ir_regions.MAX_FRAME_AGE_S + 1) == {}
    assert store.snapshot(None) == {}


def test_no_camera_means_no_camera_values(store):
    IrCameraService().disconnect()
    assert camera_snapshot(30.0, 25.0) == {}


# ── simulated camera ─────────────────────────────────────────────────────────
def test_sim_scene_has_a_hot_to_cold_sample():
    f = sim_scene(40.0, 30.0)
    h, w = SIM_SHAPE
    assert f.shape == SIM_SHAPE and f.dtype == np.float32
    row = f[h // 2]
    assert row[int(w * .21)] == pytest.approx(40.0, abs=0.3)
    assert row[w // 2] == pytest.approx(35.0, abs=0.3)
    assert row[int(w * .79)] == pytest.approx(30.0, abs=0.3)


def test_sim_camera_frames_and_recording(camera):
    assert camera.backend == "sim"
    frame, age = camera.latest()
    assert frame is not None and frame.shape == SIM_SHAPE and age < 1.0
    assert camera.get_frame() is not None
    assert camera.get_frame() is None              # nothing new yet: frames are seen once
    assert camera.latest()[0] is not None          # ...but latest() still has it

    camera_snapshot(40.0, 30.0)                    # the sample follows the thermocouples
    time.sleep(0.4)
    snap = camera_snapshot(40.0, 30.0)
    assert snap[region_key("R1")] == pytest.approx(35.0, abs=0.5)   # default R1: centre

    camera.disconnect()
    assert camera.latest()[0] is None and camera_snapshot() == {}


# ── live view ────────────────────────────────────────────────────────────────
def _view(qtbot, portrait=True):
    from app.ui.widgets.ir_panel import ThermalView
    v = ThermalView()
    qtbot.addWidget(v)
    v.resize(420, 520)
    v.set_portrait(portrait)
    v.set_frame(sim_scene(40.0, 30.0))
    v.regions = [Region("R1", "sample centre", 0, 0, 10, 10)]
    v.show()
    return v


def _at(v, sx, sy) -> QPoint:
    """Widget position of sensor pixel (sx, sy) — the inverse of the view mapping."""
    rows, _cols = v._sensor_shape()
    vx, vy = (rows - 1 - sy, sx) if v.portrait else (sx, sy)
    vr, vc = v._view_shape()
    ir = v.image_rect()
    return QPoint(int(ir.left() + (vx + .5) / vc * ir.width()),
                  int(ir.top() + (vy + .5) / vr * ir.height()))


@pytest.mark.parametrize("portrait", [True, False])
def test_drag_draws_a_box_in_sensor_pixels(qtbot, portrait):
    v = _view(qtbot, portrait)
    edited = []
    v.regions_edited.connect(lambda: edited.append(1))
    a, b = _at(v, 100, 50), _at(v, 149, 89)
    qtbot.mousePress(v, Qt.MouseButton.LeftButton, pos=a)
    qtbot.mouseMove(v, (a + b) / 2)
    qtbot.mouseMove(v, b)
    qtbot.mouseRelease(v, Qt.MouseButton.LeftButton, pos=b)
    r = v.regions[0]
    # one view pixel is ~1.2 sensor pixels here, so allow one pixel of rounding
    assert abs(r.x - 100) <= 1 and abs(r.y - 50) <= 1
    assert abs(r.w - 50) <= 2 and abs(r.h - 40) <= 2
    assert edited == [1]


def test_click_places_a_spot_and_hover_reads_the_pixel(qtbot):
    v = _view(qtbot)
    p = _at(v, 200, 140)
    qtbot.mouseClick(v, Qt.MouseButton.LeftButton, pos=p)
    r = v.regions[0]
    assert r.is_spot and abs(r.x + 1 - 200) <= 1 and abs(r.y + 1 - 140) <= 1
    qtbot.mouseMove(v, p)
    assert v._hover is not None and v._hover[1].endswith("°C")


def test_colour_bar_click_locks_the_range(qtbot):
    v = _view(qtbot)
    lo_hi = v.levels
    qtbot.mouseClick(v, Qt.MouseButton.LeftButton, pos=v._cbar_rect().center().toPoint())
    assert v.locked
    v.set_frame(sim_scene(80.0, 60.0))
    assert v.levels == lo_hi


# ── panel ────────────────────────────────────────────────────────────────────
def test_panel_second_region_and_geometry(qtbot, store):
    from app.ui.widgets.ir_panel import IrPanel
    p = IrPanel()
    qtbot.addWidget(p)
    notes = []
    p.regions_changed.connect(notes.append)
    p.toggle_second_region()
    assert [r.name for r in store.regions()] == ["R1", "R2"]
    assert p.btn_region.text() == "− Region" and len(p.cards) == 2 and notes
    p.set_geometry("out_plane")
    assert len(p.view.regions) == 1
    p.set_geometry("in_plane")
    assert len(p.view.regions) == 2
    p.toggle_second_region()
    assert [r.name for r in store.regions()] == ["R1"]


def test_panel_live_view_with_the_simulated_camera(qtbot, monkeypatch, store):
    from app.ui.widgets.ir_panel import IrPanel
    monkeypatch.setenv(visa_backend.ENV_VAR, "sim")
    p = IrPanel()
    qtbot.addWidget(p)
    try:
        p.toggle_second_region()
        p.toggle_connection()
        qtbot.waitUntil(lambda: p.view.frame is not None, timeout=5000)
        assert p.is_connected() and p.btn_connect.text() == "Disconnect"
        assert "°C" not in p.cards[0].vals["mean"].text() and "—" not in p.cards[0].vals["mean"].text()
        assert not p.lbl_camdt.isHidden() and "Camera ΔT" in p.lbl_camdt.text()
        p.toggle_connection()
        assert not p.is_connected() and p.view.frame is None
    finally:
        IrCameraService().disconnect()


# ── Seebeck page ─────────────────────────────────────────────────────────────
@pytest.fixture
def page(qtbot, store):
    from app.ui.pages.seebeck_page import SeebeckPage
    p = SeebeckPage(_user())
    qtbot.addWidget(p)
    yield p
    p._timer.stop()


def test_camera_columns_appear_only_with_camera_data(page):
    from app.ui.pages.seebeck_page import _TABLE_COLS, table_cols
    keys = [k for k, _h, _f in _TABLE_COLS]
    r1 = keys.index("IR R1 [oC]")
    row = {"Time [s]": 0.0, "Temp1 [oC]": 25.0, "Temp2 [oC]": 26.0, "TEMF [mV]": -0.05}
    page._data = [dict(row)]
    page._refresh_charts()
    assert page.tbl_data.isColumnHidden(r1)
    assert "IR R1 [oC]" not in [c[0] for c in table_cols(page._data)]
    page._data = [dict(row), {**row, "Time [s]": 2.0, "IR R1 [oC]": 25.4}]
    page._refresh_charts()
    assert not page.tbl_data.isColumnHidden(r1)
    assert page.tbl_data.isColumnHidden(r1 + 1)                     # no R2 recorded
    assert page.curve_ir.yData[-1] == pytest.approx(25.4)
    assert "IR R1 [oC]" in [c[0] for c in table_cols(page._data)]


def test_start_warns_but_runs_without_the_camera(page, monkeypatch):
    from app.services import measurement_service
    IrCameraService().disconnect()
    calls = []
    monkeypatch.setattr(measurement_service.SeebeckService, "start",
                        lambda self, p: calls.append(p) or True)
    page.inp_sample.setText("Ti3C2-04")
    page._start()
    page._timer.stop()
    assert calls and calls[0]["sample_id"] == "Ti3C2-04"
    log = [page.lst_log.item(i).text() for i in range(page.lst_log.count())]
    assert any("Thermal camera not connected" in t for t in log)
    assert page.tabs_data.button(2).text().endswith("●")           # unread warning
    assert not page.editor.isEnabled()


def test_start_needs_a_rising_heater_profile(page, monkeypatch):
    from app.services import measurement_service
    calls = []
    monkeypatch.setattr(measurement_service.SeebeckService, "start",
                        lambda self, p: calls.append(p) or True)
    page.inp_sample.setText("Ti3C2-04")
    page.editor.sb_i0.setValue(page.editor.sb_ipeak.value())
    page._start()
    assert not calls and not page.lbl_profile_err.isHidden()
    page.editor.sb_i0.setValue(0.0)                                 # editing clears it
    assert page.lbl_profile_err.isHidden()


def test_geometry_caps_the_profile_and_switches_regions(page, store):
    page.editor.cb_unit.setCurrentText("A")
    page.editor.sb_ipeak.setValue(1.2)
    page.seg_geometry.setCurrentIndex(0)                            # in-plane: 1.0 A
    page._on_geometry_changed(0)
    assert page._profile_params["stop_volt"] <= page.current_cap_a["in_plane"]
    page.seg_geometry.setCurrentIndex(1)
    assert store.geometry == "out_plane"


def test_enlarging_the_camera_moves_the_other_columns_aside(page):
    page.show()
    page._toggle_enlarge(page.side)
    assert page.params_col.isHidden() and page.middle.isHidden() and not page.side.isHidden()
    page._toggle_enlarge(page.side)
    assert not page.params_col.isHidden() and not page.middle.isHidden()
    page._toggle_enlarge(page._tiles["g1"])
    assert page.side.isHidden() and page._tiles["g2"].isHidden()
    page._toggle_enlarge(page._tiles["g1"])
    assert not page._tiles["g2"].isHidden()


def test_phase_bar_follows_the_run(page):
    page._apply_phase("hold", 0.5)
    assert page.toolbar.chip.text() == "RUNNING"
    assert page.toolbar.title_lbl.text().startswith("Hold")
    assert page.segments._current == 2 and 0 < page.segments._progress < 1
    page._apply_phase("finished")
    assert page.toolbar.chip.text() == "FINISHED" and page.segments._all_done

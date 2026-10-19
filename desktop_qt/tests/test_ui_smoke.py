"""Headless UI checks (pytest-qt, offscreen platform)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")


@pytest.fixture
def admin():
    return SimpleNamespace(id=1, username="superadmin", role="super_admin", lab_id=None)


@pytest.fixture(autouse=True)
def no_visa_scan(monkeypatch):
    from app.services import instrument_scan
    monkeypatch.setattr(instrument_scan, "start_resource_scan", lambda cb: False)


def test_settings_page_round_trips_config(qtbot, admin):
    from app.core import config as C
    from app.ui.pages.settings_page import SettingsPage

    page = SettingsPage(admin)
    qtbot.addWidget(page)
    assert page._addr["k2401"].text() == "GPIB0::24::INSTR"
    assert page.sb_tmax.value() == 120.0

    page._addr["k2700"].setText("GPIB0::17::INSTR")
    page.sb_tmax.setValue(95.0)
    page._tc["out_plane_t1"].setValue(110)
    page._save_config()
    assert "Saved" in page.lbl_cfg_msg.text()

    cfg = C.reload_config()
    assert cfg.instruments.k2700 == "GPIB0::17::INSTR"
    assert cfg.safety.max_temperature_C == 95.0
    assert cfg.thermocouples.out_plane_t1 == 110


def test_settings_page_rejects_invalid_config(qtbot, admin):
    from app.core import config as C
    from app.ui.pages.settings_page import SettingsPage

    page = SettingsPage(admin)
    qtbot.addWidget(page)
    page._tc["in_plane_t2"].setValue(page._tc["in_plane_t1"].value())   # same channel
    page._save_config()
    assert "Not saved" in page.lbl_cfg_msg.text()
    assert C.reload_config().thermocouples.in_plane_t2 == 104


def test_researcher_does_not_see_rig_configuration(qtbot):
    from app.ui.pages.settings_page import SettingsPage

    page = SettingsPage(SimpleNamespace(id=2, username="r", role="researcher", lab_id=1))
    qtbot.addWidget(page)
    assert not hasattr(page, "_addr")


def test_close_is_blocked_while_running_unless_confirmed(qtbot, admin, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from app.services import measurement_service as ms
    from app.ui.main_window import MainWindow

    win = MainWindow(admin)
    qtbot.addWidget(win)
    stopped = []
    monkeypatch.setattr(ms, "any_measurement_running", lambda: True)
    monkeypatch.setattr(ms, "stop_all_measurements", lambda **kw: stopped.append(1) or True)

    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    assert win._stop_running_measurements("Closing") is False
    assert stopped == []

    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    assert win._stop_running_measurements("Closing") is True
    assert stopped == [1]


def test_close_proceeds_when_idle(qtbot, admin, monkeypatch):
    from app.services import measurement_service as ms
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(ms, "any_measurement_running", lambda: False)
    win = MainWindow(admin)
    qtbot.addWidget(win)
    win.show()
    assert win.close()

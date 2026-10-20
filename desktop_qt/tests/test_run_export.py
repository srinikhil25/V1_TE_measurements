"""Shared run export (UI-9): file names, CSV / Excel contents, and the
'Save data / Save graph(s)' buttons on the live pages and in the run library."""

import csv
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services import run_export as rx

openpyxl = pytest.importorskip("openpyxl")


# ── file names ───────────────────────────────────────────────────────────────
def test_default_filename_uses_run_id_and_a_safe_sample_name():
    assert rx.default_filename("seebeck", run_id=142, sample="Ti3C2 / #04") == \
        "seebeck_142_Ti3C2-04_data.xlsx"
    assert rx.default_filename("iv", run_id=7, what="graph", ext="png") == "iv_7_graph.png"


def test_default_filename_before_the_run_is_saved_has_a_timestamp():
    name = rx.default_filename("iv", sample="Cu", when=datetime(2026, 10, 20, 14, 8))
    assert name == "iv_Cu_20261020-1408_data.xlsx"


@pytest.mark.parametrize("path, filt, expected", [
    ("a", "Excel workbook (*.xlsx)", ("a.xlsx", "xlsx")),
    ("a", "CSV file (*.csv)", ("a.csv", "csv")),
    ("a.csv", "Excel workbook (*.xlsx)", ("a.csv", "csv")),      # typed extension wins
    ("a.xlsx", "CSV file (*.csv)", ("a.xlsx", "xlsx")),
    ("a.XLSX", "", ("a.XLSX", "xlsx")),
])
def test_with_extension(path, filt, expected):
    assert rx.with_extension(path, filt) == expected


# ── table builders ──────────────────────────────────────────────────────────
BINS = [{"T0_center_K": 305.0, "T0_min_K": 300.0, "T0_max_K": 310.0, "S_uV_per_K": -40.0,
         "S_uncertainty_uV_per_K": 0.5, "n_points": 30, "n_rejected": 1, "fit_warning": None},
        {"T0_center_K": 315.0, "T0_min_K": 310.0, "T0_max_K": 320.0, "S_uV_per_K": -42.0,
         "S_uncertainty_uV_per_K": 0.6, "n_points": 28, "n_rejected": 0, "fit_warning": None}]
COLS = [("Time [s]", "Time [s]"), ("TEMF [mV]", "TEMF [mV]")]


def test_seebeck_table_adds_bins_and_mean_s():
    t = rx.seebeck_table([{"Time [s]": 0.0, "TEMF [mV]": None}], COLS, BINS)
    assert t.headers == ["Time [s]", "TEMF [mV]"]
    assert t.rows == [[0.0, None]]
    assert t.extra[0].name == "Seebeck by T0 bin" and len(t.extra[0].rows) == 2
    assert t.summary == [("S, mean of bins [µV/K]", -41.0)]


def test_iv_table_computes_power_and_lists_rho_notes():
    t = rx.iv_table([{"current": 1e-3, "voltage": 2e-3, "resistance": 2.0},
                     {"current": 2e-3, "voltage": None}],
                    fit_R=2.0, fit_R2=0.999, ohmic="ohmic", cf=0.9,
                    rho_notes=["Finite-size correction NOT applied"])
    assert t.rows[0][3] == pytest.approx(2e-3)            # mW
    assert t.rows[1][3] is None
    assert ("4PP correction factor CF", 0.9) in t.summary
    assert ("ρ note", "Finite-size correction NOT applied") in t.summary


def test_iv_info_describes_the_sweep():
    lines = dict(rx.iv_info({"geometry": "4pp", "thickness": 0.00025, "spacing": 0.1,
                             "source_mode": "current", "start": -0.01, "stop": 0.01,
                             "points": 21, "bidirectional": True, "four_wire": True}))
    assert lines["Geometry"] == "4-point probe"
    assert lines["Thickness (cm)"] == 0.00025
    assert lines["Sweep"] == "source current -0.01 → 0.01 A, 21 points, forward + reverse"
    assert lines["Wiring"].startswith("4-wire")


# ── writers ──────────────────────────────────────────────────────────────────
def _table():
    t = rx.seebeck_table([{"Time [s]": 0.0, "TEMF [mV]": 0.1},
                          {"Time [s]": 2.0, "TEMF [mV]": None}], COLS, BINS,
                         rx.info_lines(kind="Seebeck", run_id=3, sample="S1", operator="op"))
    return t


def test_csv_is_readings_only(tmp_path):
    p = tmp_path / "x.csv"
    rx.write_csv(str(p), _table())
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows == [["Time [s]", "TEMF [mV]"], ["0.0", "0.1"], ["2.0", ""]]


def _png():
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    raw = b"\x00\xff\x00\x00"                                    # one red pixel
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_xlsx_has_data_bins_run_sheet_and_chart(tmp_path):
    pytest.importorskip("PIL")
    p = tmp_path / "x.xlsx"
    assert rx.write_xlsx(str(p), _table(), [("Chart", _png())]) is True
    wb = openpyxl.load_workbook(p)
    assert wb.sheetnames == ["Data", "Seebeck by T0 bin", "Run"]
    data = wb["Data"]
    assert [c.value for c in data[1]] == ["Time [s]", "TEMF [mV]"]
    assert data.cell(3, 2).value is None
    values = [r[0] for r in data.iter_rows(values_only=True)]
    assert "S, mean of bins [µV/K]" in values and "Chart" in values
    assert len(data._images) == 1
    run = dict(wb["Run"].iter_rows(values_only=True))
    assert run["Run"] == "#3" and run["Sample"] == "S1" and run["Operator"] == "op"
    assert run["Software"].startswith("TE Measurement")


def test_xlsx_without_pillow_still_saves_the_data(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "openpyxl.drawing.image", None)   # import fails
    p = tmp_path / "x.xlsx"
    assert rx.write_xlsx(str(p), _table(), [("Chart", _png())]) is False
    assert openpyxl.load_workbook(p)["Data"].cell(2, 2).value == 0.1


# ── dialogs ──────────────────────────────────────────────────────────────────
pytest.importorskip("pytestqt")


@pytest.fixture
def dialogs(monkeypatch):
    """Answer the save dialog with `answer` and record message boxes."""
    from app.ui.widgets import export_ui

    state = SimpleNamespace(answer=("", ""), asked=[], messages=[])

    def ask(parent, title, suggestion, filt):
        state.asked.append(suggestion)
        return state.answer

    monkeypatch.setattr(export_ui.QFileDialog, "getSaveFileName", staticmethod(ask))
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(export_ui.QMessageBox, kind, staticmethod(
            lambda parent, title, text, k=kind: state.messages.append((k, text))))
    monkeypatch.setattr(export_ui, "_last_dir", "")
    return state


def _chart(qtbot):
    import pyqtgraph as pg
    w = pg.PlotWidget()
    w.plot([0, 1, 2], [0, 1, 4])
    w.resize(300, 200)
    qtbot.addWidget(w)
    w.show()
    return w


def test_save_data_without_data_says_so(qtbot, dialogs):
    from app.ui.widgets.export_ui import save_data
    assert save_data(None, rx.RunTable(["a"], []), kind="iv") is None
    assert dialogs.asked == [] and "no data" in dialogs.messages[0][1]


def test_save_data_cancelled_writes_nothing(qtbot, dialogs, tmp_path):
    from app.ui.widgets.export_ui import save_data
    assert save_data(None, _table(), kind="seebeck", run_id=3) is None
    assert dialogs.asked == ["seebeck_3_data.xlsx"] and dialogs.messages == []


def test_save_data_xlsx_then_next_dialog_opens_in_the_same_folder(qtbot, dialogs, tmp_path):
    from app.ui.widgets.export_ui import save_data
    chart = _chart(qtbot)
    dialogs.answer = (str(tmp_path / "out"), "Excel workbook (*.xlsx)")
    path = save_data(None, _table(), kind="seebeck", run_id=3, charts=[("Chart", chart)])
    assert path == str(tmp_path / "out.xlsx")
    assert len(openpyxl.load_workbook(path)["Data"]._images) == 1
    dialogs.answer = (str(tmp_path / "out.csv"), "Excel workbook (*.xlsx)")
    save_data(None, _table(), kind="seebeck", run_id=3)
    assert dialogs.asked[1].startswith(str(tmp_path))
    assert "readings only" in dialogs.messages[-1][1]


def test_save_data_reports_a_write_error(qtbot, dialogs, tmp_path):
    from app.ui.widgets.export_ui import save_data
    dialogs.answer = (str(tmp_path / "missing" / "x.csv"), "")
    assert save_data(None, _table(), kind="seebeck") is None
    assert dialogs.messages[-1][0] == "critical"


def test_save_graphs_one_and_several(qtbot, dialogs, tmp_path):
    from app.ui.widgets.export_ui import save_graphs
    a, b = _chart(qtbot), _chart(qtbot)
    dialogs.answer = (str(tmp_path / "g"), "")
    assert save_graphs(None, [(a, "graph")], kind="iv", run_id=9) == [str(tmp_path / "g.png")]
    assert dialogs.asked[0] == "iv_9_graph.png"
    dialogs.answer = (str(tmp_path / "set.png"), "")
    saved = save_graphs(None, [(a, "live"), (b, "temf_vs_dt")], kind="seebeck", run_id=9)
    assert saved == [str(tmp_path / "set_live.png"), str(tmp_path / "set_temf_vs_dt.png")]
    assert all((tmp_path / n).stat().st_size > 100 for n in ("set_live.png", "set_temf_vs_dt.png"))
    assert save_graphs(None, [(a, "x")], kind="iv", has_data=False) == []


# ── the pages use it ─────────────────────────────────────────────────────────
def _user():
    return SimpleNamespace(id=1, username="tester", role="researcher", lab_id=None)


def test_seebeck_page_export(qtbot, dialogs, tmp_path):
    from app.ui.pages.seebeck_page import SeebeckPage
    page = SeebeckPage(_user())
    qtbot.addWidget(page)
    page.inp_sample.setText("Ti3C2-04")
    page._run_id = 12
    page._data = [{"Time [s]": 0.0, "TEMF [mV]": -0.4, "T0 [K]": 305.0}]
    page._analysis = list(BINS)
    dialogs.answer = (str(tmp_path / "s.xlsx"), "")
    page._export_data()
    assert dialogs.asked[0] == "seebeck_12_Ti3C2-04_data.xlsx"
    wb = openpyxl.load_workbook(tmp_path / "s.xlsx")
    run = dict(wb["Run"].iter_rows(values_only=True))
    assert run["Sample"] == "Ti3C2-04" and run["Operator"] == "tester"
    assert run["Geometry"] == "In-plane"
    assert wb["Seebeck by T0 bin"].max_row == 3
    dialogs.answer = (str(tmp_path / "c"), "")
    page._export_single_chart(page.chart_live, "live")
    assert (tmp_path / "c.png").exists()


def test_iv_page_export(qtbot, dialogs, tmp_path):
    from app.ui.pages.iv_page import IVPage
    page = IVPage(_user())
    qtbot.addWidget(page)
    page._run_id = 5
    page._sweep_params = {"sample_id": "Cu-01", "operator": "tester", "geometry": "bar",
                          "length": 1.0, "source_mode": "current", "start": -0.01,
                          "stop": 0.01, "points": 3, "four_wire": False}
    page._results = [{"current": -0.01, "voltage": -0.02, "resistance": 2.0},
                     {"current": 0.01, "voltage": 0.02, "resistance": 2.0}]
    page._result_summary = {"fit_R": 2.0, "fit_R_squared": 1.0, "ohmic_status": "ohmic"}
    page.le_sample_id.setText("Cu-01")
    dialogs.answer = (str(tmp_path / "iv"), "")
    page._export_data()
    wb = openpyxl.load_workbook(tmp_path / "iv.xlsx")
    data = [r for r in wb["Data"].iter_rows(values_only=True)]
    assert data[0][0] == "Current (A)" and ("Fit R (Ω)", 2.0) in [r[:2] for r in data]
    run = dict(wb["Run"].iter_rows(values_only=True))
    assert run["Run"] == "#5" and run["Wiring"] == "2-wire"


def test_run_library_export(qtbot, dialogs, tmp_path):
    from app.ui.pages import history_page as hp

    class Run(SimpleNamespace):
        def __getattr__(self, _k):
            return None

    m = Run(id=21, type="iv", status="finished", sample_id="Bi2Te3", operator="op",
            started_at=datetime(2026, 10, 1, 9, 0), finished_at=datetime(2026, 10, 1, 9, 5),
            end_reason="Stopped by user",
            params_json='{"geometry": "vdp", "thickness": 0.01, "points": 2}')
    w = hp.RunDetailWindow(None, m, [{"current": 1e-3, "voltage": 1e-3, "resistance": 1.0},
                                     {"current": 2e-3, "voltage": 2e-3, "resistance": 1.0}], None)
    qtbot.addWidget(w)
    w.show()
    dialogs.answer = (str(tmp_path / "lib.xlsx"), "")
    w.btn_data.click()
    assert dialogs.asked[0] == "iv_21_Bi2Te3_data.xlsx"
    run = dict(openpyxl.load_workbook(tmp_path / "lib.xlsx")["Run"].iter_rows(values_only=True))
    assert run["Geometry"] == "van der Pauw" and run["End reason"] == "Stopped by user"
    assert run["Started"] == "2026-10-01 09:00:00"
    dialogs.answer = (str(tmp_path / "lib_graph"), "")
    w.btn_graphs.click()
    assert (tmp_path / "lib_graph.png").exists()

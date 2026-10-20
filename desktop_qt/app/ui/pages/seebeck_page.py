"""
Seebeck measurement — live run console.

Toolbar   : title / run summary · phase stepper · Reset · Start / Stop
Left      : run setup (sample, geometry) · heater profile · safety · event log
Centre    : live readouts · T/TEMF vs time · TEMF vs ΔT · S vs T₀ · data table
Right     : Seebeck by T₀ bin · thermal camera   (toggle from the toolbar)

Every chart / table tile can be enlarged to fill the centre area.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Dict, List, Optional

import pyqtgraph as pg
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from .. import theme as T
from ..widgets.ir_camera_widget import IrCameraWidget
from ..widgets.measurement_setup_dialog import MeasurementSetupDialog
from ..widgets.plot_data import ColumnBuffer, fast_time_curve, thin
from ..widgets.profile_preview import ProfilePreview, fmt_duration, profile_duration_s
from ..widgets.tile import Tile, icon_button
from ..widgets.ui_kit import (
    bin_n_text,
    Chip, KeyValueList, LegendStrip, Panel, Readout, ReadoutGrid, Segmented, Stepper,
    button, cell, field, label, make_table, page_scaffold, pen, set_props, style_plot,
)

# Phase vocabulary: key → (display name, chip kind)
PHASES = {
    "idle":         ("Ready", "neutral"),
    "pre":          ("Pre-heat", "info"),
    "ramp_up":      ("Power up", "info"),
    "hold":         ("Hold", "info"),
    "ramp_down":    ("Power down", "info"),
    "cooling_tail": ("Cooling", "info"),
    "finished":     ("Finished", "success"),
    "error":        ("Stopped on error", "danger"),
}
# Kept for older imports.
PHASE_STYLE = {k: ("", "", v[0].upper()) for k, v in PHASES.items()}

# Segmented progress: (phase key, display label). Order matters.
_SEGMENTS = [
    ("pre",          "Pre-heat"),
    ("ramp_up",      "Power up"),
    ("hold",         "Hold"),
    ("ramp_down",    "Power down"),
    ("cooling_tail", "Cooling"),
]

# Data-table column definitions  (data-dict key, display header, format string)
_TABLE_COLS: List[tuple] = [
    ("Time [s]",        "Time [s]",  "{:.1f}"),
    ("TEMF [mV]",       "TEMF [mV]", "{:.4f}"),
    ("Temp1 [oC]",      "T₁ [°C]",   "{:.2f}"),
    ("Temp2 [oC]",      "T₂ [°C]",   "{:.2f}"),
    ("Delta Temp [oC]", "ΔT [°C]",   "{:.2f}"),
    ("delta_T_over_T0", "ΔT/T₀",     "{:.4f}"),
    ("T0 [oC]",         "T₀ [°C]",   "{:.2f}"),
    ("T0 [K]",          "T₀ [K]",    "{:.2f}"),
    ("S [µV/K]",        "S [µV/K]",  "{:.2f}"),
    ("Heater V [V]",    "Heater [V]", "{:.2f}"),
    ("Heater I [A]",    "Heater [A]", "{:.3f}"),
]

_GEOMETRY = (("in_plane", "In-plane"), ("out_plane", "Out-of-plane"))


class SeebeckPage(QWidget):

    # Default heater profile (used until the operator edits it).
    _DEFAULT_PROFILE = {
        "interval": 2, "pre_time": 5, "hold_time": 600,
        "start_volt": 0.0, "stop_volt": 1.0,
        "inc_rate": 1.0, "dec_rate": 1.0, "pk160_current_unit": "mA",
    }

    # Per-geometry current cap (amperes): In-Plane 1.0 A · Out-Plane 1.3 A
    CURRENT_CAP_A = {"in_plane": 1.0, "out_plane": 1.3}

    # Secondary columns shown only when the data tile is enlarged
    # (ΔT/T₀ · T₀[°C] · T₀[K]).
    _SECONDARY_COLS = (5, 6, 7)

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._data: List[Dict] = []
        self._analysis: List[Dict] = []
        self._table_row_count: int = 0
        # Chart series, filled incrementally from self._data (UI-2). The rows
        # in self._data stay complete; only what is drawn is reduced.
        self._buf_time = ColumnBuffer(4)    # t, T1, T2, TEMF
        self._buf_heat = ColumnBuffer(2)    # ΔT, TEMF (heating branch)
        self._buf_cool = ColumnBuffer(2)    # ΔT, TEMF (cooling branch)
        self._buf_s = ColumnBuffer(2)       # T0, S
        self._rows_charted = 0
        self._profile_params: Dict = dict(self._DEFAULT_PROFILE)
        self._cooling_target: float = 5.0
        self._tiles: Dict[str, Tile] = {}
        self._grid_positions: Dict[str, tuple] = {}
        self._enlarged: Optional[Tile] = None
        self._last_phase: Optional[str] = None
        self._last_invalid = 0
        self._last_db_warning = None
        self._polarity_logged = False
        self._run_id = None
        self._auto_hid_side = False

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)

        try:
            from ...core.config import get_config
            h = get_config().heater
            self.CURRENT_CAP_A = {"in_plane": h.in_plane.current_max_A,
                                  "out_plane": h.out_plane.current_max_A}
        except Exception:
            pass

        pg.setConfigOptions(antialias=True)
        self._build_ui()
        self._refresh_profile_panel()
        self._log("Ready. Set the sample ID and heater profile, then press Start.")

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        tb, body = page_scaffold(self, "Seebeck measurement",
                                 "Ready · no run in progress", margins=12, spacing=12)
        self.toolbar = tb
        self.stepper = Stepper([s for _k, s in _SEGMENTS])
        self.stepper.setMinimumWidth(460)
        self.stepper.setMaximumWidth(620)
        tb.add_middle(18)
        tb.add_middle(self.stepper)

        self.btn_side = button("", "ghost", icon="panel-right", checkable=True,
                               tooltip="Show / hide the results and thermal camera column")
        self.btn_side.setChecked(True)
        self.btn_side.toggled.connect(self._set_side_visible)
        self.btn_reset = button("Reset", icon="rotate",
                                tooltip="Clear the screen and release all instruments")
        self.btn_reset.clicked.connect(self._reset)
        self.btn_start = button("Start run", "primary", icon="play")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = button("Stop run", "danger", icon="stop",
                               tooltip="Stop the run and switch the heater output off. "
                                       "Data measured so far is kept.")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setVisible(False)
        tb.add_action(self.btn_side)
        tb.add_action(self.btn_reset)
        tb.add_action(self.btn_start)
        tb.add_action(self.btn_stop)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._build_left(), 0)
        row.addWidget(self._build_centre(), 1)
        self.side = self._build_right()
        row.addWidget(self.side, 0)
        body.addLayout(row, 1)

    # ── Left column ───────────────────────────────────────────────────
    def _build_left(self) -> QWidget:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setFixedWidth(292)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(12)

        # Run setup
        setup = Panel("Run setup")
        self.inp_sample = QLineEdit()
        self.inp_sample.setPlaceholderText("e.g. Bi2Te3-001")
        self.inp_sample.textEdited.connect(lambda _t: set_props(self.inp_sample, invalid=False))
        setup.body.addWidget(field("Sample ID", self.inp_sample))
        self.seg_geometry = Segmented([g[1] for g in _GEOMETRY])
        self.seg_geometry.currentIndexChanged.connect(self._on_geometry_changed)
        self.lbl_geom_hint = label("", "caption", wrap=True)
        setup.body.addWidget(field("Geometry", self.seg_geometry))
        setup.body.addWidget(self.lbl_geom_hint)
        op = label(f"Operator: {getattr(self._user, 'username', '—')}", "caption")
        setup.body.addWidget(op)
        v.addWidget(setup)

        # Heater profile
        prof = Panel("Heater profile")
        self.btn_edit_profile = button("Edit…", size="sm", icon="edit")
        self.btn_edit_profile.clicked.connect(self._new_measurement)
        prof.add_action(self.btn_edit_profile)
        self.profile_preview = ProfilePreview()
        prof.body.addWidget(self.profile_preview)
        self.kv_profile = KeyValueList(mono_values=True, key_width=96)
        prof.body.addWidget(self.kv_profile)
        self.lbl_profile_lock = label("Locked while the run is in progress.", "caption")
        self.lbl_profile_lock.setVisible(False)
        prof.body.addWidget(self.lbl_profile_lock)
        v.addWidget(prof)

        # Safety
        safe = Panel("Safety")
        self.kv_safety = KeyValueList(mono_values=True, key_width=120)
        safe.body.addWidget(self.kv_safety)
        safe.body.addWidget(label("Software limits: the heater is switched off when one is "
                                  "exceeded. Change them in Settings.", "caption", wrap=True))
        v.addWidget(safe)
        self._refresh_safety_panel()

        # Event log
        logp = Panel("Event log", flush=True)
        self.lst_log = QListWidget()
        self.lst_log.setProperty("flat", True)
        self.lst_log.setWordWrap(True)
        self.lst_log.setMinimumHeight(150)
        self.lst_log.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        logp.body.addWidget(self.lst_log)
        v.addWidget(logp, 1)

        sa.setWidget(host)
        self._on_geometry_changed(0)
        return sa

    # ── Centre column ─────────────────────────────────────────────────
    def _build_centre(self) -> QWidget:
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        self.ro = {
            "t1":   Readout("T₁ hot side", "°C"),
            "t2":   Readout("T₂ cold side", "°C"),
            "dt":   Readout("ΔT", "K",
                            tooltip="ΔT = T₂ − T₁ (cold − hot): negative while heating. "
                                    "S = TEMF / ΔT."),
            "t0":   Readout("T₀ mean", "K"),
            "temf": Readout("TEMF", "mV"),
            "s":    Readout("S (point)", "µV/K", tone="accent",
                            tooltip="Point-wise S of the latest reading. The fitted S "
                                    "per T₀ bin is in the results column."),
            "heat": Readout("Heater", "V"),
            "grad": Readout("ΔT / T₀", "%",
                            tooltip="Large gradients (> 10 %) make S less accurate."),
        }
        self.readouts = ReadoutGrid(list(self.ro.values()), 4)
        v.addWidget(self.readouts)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._build_tiles()
        self._layout_grid_normal()
        v.addWidget(self._grid_host, 1)
        return host

    # ── Right column ──────────────────────────────────────────────────
    def _build_right(self) -> QWidget:
        host = QWidget()
        host.setFixedWidth(330)
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        res = Panel("Seebeck by T₀ bin", flush=True)
        self.chip_fit = Chip("No data", "neutral")
        res.add_action(self.chip_fit)
        self.tbl_bins = make_table(["T₀ [K]", "S [µV/K]", "± [µV/K]", "n"], row_height=28)
        self.tbl_bins.setProperty("mono", True)
        for i, w in enumerate((76, 86, 76)):
            self.tbl_bins.setColumnWidth(i, w)
        self.tbl_bins.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_bins.setMinimumHeight(150)
        res.body.addWidget(self.tbl_bins)
        res.show_footer(label("Linear fit of TEMF vs ΔT within each 10 K bin of T₀.", "caption", wrap=True))
        v.addWidget(res, 2)

        self._tiles["ir"] = self._make_ir_tile()
        self._tiles["ir"].enlarge_btn.setVisible(False)
        v.addWidget(self._tiles["ir"], 3)
        return host

    def _set_side_visible(self, on: bool):
        self.side.setVisible(on)
        self._auto_hid_side = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_side_column()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_side_column()

    def _fit_side_column(self):
        # Narrow window: fold the right column away so the charts keep their width.
        narrow = self.width() < 1180
        if narrow and not self.side.isHidden() and self.btn_side.isChecked():
            self.btn_side.blockSignals(True)
            self.btn_side.setChecked(False)
            self.btn_side.blockSignals(False)
            self.side.setVisible(False)
            self._auto_hid_side = True
        elif not narrow and self._auto_hid_side:
            self.btn_side.setChecked(True)

    # ------------------------------------------------------------------
    # Tiles
    # ------------------------------------------------------------------

    def _build_tiles(self):
        self._tiles["g1"] = self._make_live_chart_tile()
        self._tiles["g2"] = self._make_temf_dt_tile()
        self._tiles["g3"] = self._make_s_t0_tile()
        self._tiles["data"] = self._make_data_tile()
        for key in ("g1", "g2", "g3", "data"):
            self._tiles[key].enlarge_clicked.connect(self._toggle_enlarge)
        # (row, col, rowspan, colspan) in the 2-column centre grid
        self._grid_positions = {
            "g1":   (0, 0, 1, 2),
            "g2":   (1, 0, 1, 1),
            "g3":   (1, 1, 1, 1),
            "data": (2, 0, 1, 2),
        }

    def _make_live_chart_tile(self) -> Tile:
        tile = Tile("g1", "Temperatures and TEMF vs time")
        tile.add_action(icon_button("image", "Save this chart as PNG",
                                    lambda: self._export_single_chart(self.chart_live, "live")))
        tile.body_layout.setContentsMargins(8, 6, 8, 6)
        tile.body_layout.addWidget(self._build_live_chart())
        return tile

    def _make_temf_dt_tile(self) -> Tile:
        tile = Tile("g2", "TEMF vs ΔT")
        tile.add_action(icon_button("image", "Save this chart as PNG",
                                    lambda: self._export_single_chart(self.chart_temf_dt, "temf_vs_dt")))
        self.chart_temf_dt = pg.PlotWidget()
        style_plot(self.chart_temf_dt, "TEMF (mV)", "ΔT (K)")
        self.curve_heat = self.chart_temf_dt.plot(pen=pen(T.SERIES_HEAT))
        self.curve_cool = self.chart_temf_dt.plot(pen=pen(T.SERIES_COOL))
        tile.body_layout.setContentsMargins(8, 6, 8, 6)
        tile.body_layout.addWidget(LegendStrip([(T.SERIES_HEAT, "Heating"), (T.SERIES_COOL, "Cooling")]))
        tile.body_layout.addWidget(self.chart_temf_dt, 1)
        return tile

    def _make_s_t0_tile(self) -> Tile:
        tile = Tile("g3", "S vs T₀")
        tile.add_action(icon_button("image", "Save this chart as PNG",
                                    lambda: self._export_single_chart(self.chart_s_t0, "seebeck_vs_t0")))
        self.chart_s_t0 = pg.PlotWidget()
        style_plot(self.chart_s_t0, "S (µV/K)", "T₀ (K)")
        self.curve_s = self.chart_s_t0.plot(
            pen=pen("#C4B5FD", 1.2), symbol="o", symbolSize=4,
            symbolBrush="#A78BFA", symbolPen=None)
        self.scatter_bins = pg.ScatterPlotItem(size=9, pen=pg.mkPen(T.SURFACE, width=1.5),
                                               brush=pg.mkBrush(T.SERIES_S))
        self.err_bins = pg.ErrorBarItem(pen=pen(T.SERIES_S, 1.2), beam=4)
        self.chart_s_t0.addItem(self.err_bins)
        self.chart_s_t0.addItem(self.scatter_bins)
        tile.body_layout.setContentsMargins(8, 6, 8, 6)
        tile.body_layout.addWidget(LegendStrip([("#A78BFA", "Point-wise"), (T.SERIES_S, "Binned fit ± 1σ")],
                                               kinds=["dot", "dot"]))
        tile.body_layout.addWidget(self.chart_s_t0, 1)
        return tile

    def _make_data_tile(self) -> Tile:
        tile = Tile("data", "Readings")
        btn_graphs = button("Save graphs…", size="sm", icon="image")
        btn_graphs.clicked.connect(self._export_graphs)
        btn_data = button("Save data…", size="sm", icon="download")
        btn_data.clicked.connect(self._export_data)
        tile.add_action(btn_graphs)
        tile.add_action(btn_data)

        headers = [c[1] for c in _TABLE_COLS]
        self.tbl_data = make_table(headers, row_height=24, mono=True)
        self.tbl_data.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        from PyQt6.QtWidgets import QHeaderView
        hh = self.tbl_data.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(64)
        self.tbl_data.setSelectionMode(self.tbl_data.SelectionMode.ExtendedSelection)
        tile.body_layout.addWidget(self.tbl_data)
        self._set_table_full(False)
        return tile

    def _set_table_full(self, full: bool):
        for col in self._SECONDARY_COLS:
            self.tbl_data.setColumnHidden(col, not full)

    def _make_ir_tile(self) -> Tile:
        tile = Tile("ir", "Thermal camera")
        self.ir_camera = IrCameraWidget()
        tile.body_layout.setContentsMargins(0, 0, 0, 0)
        tile.body_layout.addWidget(self.ir_camera)
        return tile

    # ------------------------------------------------------------------
    # Chart builders
    # ------------------------------------------------------------------

    def _build_live_chart(self) -> QWidget:
        chart = pg.PlotWidget()
        style_plot(chart, "Temperature (°C)", "Time (s)", right="TEMF (mV)")
        pi = chart.getPlotItem()

        # Secondary view box carries TEMF against the right axis.
        self._vb_temf = pg.ViewBox()
        pi.scene().addItem(self._vb_temf)
        pi.getAxis("right").linkToView(self._vb_temf)
        self._vb_temf.setXLink(pi)

        self.curve_t1 = fast_time_curve(pi.plot(pen=pen(T.SERIES_T1)))
        self.curve_t2 = fast_time_curve(pi.plot(pen=pen(T.SERIES_T2)))
        self.curve_temf = pg.PlotDataItem(pen=pen(T.SERIES_TEMF, 1.6, dashed=True))
        self._vb_temf.addItem(self.curve_temf)
        fast_time_curve(self.curve_temf)  # only once it is inside its ViewBox

        def _sync_views():
            self._vb_temf.setGeometry(pi.vb.sceneBoundingRect())
            self._vb_temf.linkedViewChanged(pi.vb, self._vb_temf.XAxis)

        pi.vb.sigResized.connect(_sync_views)
        _sync_views()

        chart.setXRange(0, 60, padding=0)
        chart.setYRange(0, 100, padding=0.05)
        self._vb_temf.setYRange(-5, 5, padding=0.05)
        self.chart_live = chart

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(LegendStrip([(T.SERIES_T1, "T₁ [°C]"), (T.SERIES_T2, "T₂ [°C]"),
                                 (T.SERIES_TEMF, "TEMF [mV] · right axis")],
                                kinds=["line", "line", "dash"]))
        v.addWidget(chart, 1)
        return box

    @staticmethod
    def _legend_strip(items) -> QWidget:
        """Legend above a chart. items: (color, text). Kept for older callers."""
        return LegendStrip(items)

    # ==================================================================
    # Enlarge / restore
    # ==================================================================

    def _layout_grid_normal(self):
        for name in ("g1", "g2", "g3", "data"):
            tile = self._tiles[name]
            self._grid.removeWidget(tile)
            tile.setVisible(True)
            r, c, rs, cs = self._grid_positions[name]
            self._grid.addWidget(tile, r, c, rs, cs)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._grid.setRowStretch(0, 26)
        self._grid.setRowStretch(1, 22)
        self._grid.setRowStretch(2, 16)

    def _toggle_enlarge(self, tile: Tile):
        if self._enlarged is tile:
            self._restore()
        else:
            if self._enlarged is not None:
                self._restore()
            self._enlarge(tile)

    def _enlarge(self, tile: Tile):
        for name in ("g1", "g2", "g3", "data"):
            t = self._tiles[name]
            self._grid.removeWidget(t)
            t.setVisible(t is tile)
        for c in range(2):
            self._grid.setColumnStretch(c, 1 if c == 0 else 0)
        for r in range(3):
            self._grid.setRowStretch(r, 1 if r == 0 else 0)
        self._grid.addWidget(tile, 0, 0, 1, 1)
        tile.set_enlarged(True)
        self._enlarged = tile
        if tile is self._tiles.get("data"):
            self._set_table_full(True)

    def _restore(self):
        if self._enlarged is not None:
            self._enlarged.set_enlarged(False)
            self._enlarged = None
        self._set_table_full(False)
        self._layout_grid_normal()

    # ==================================================================
    # Setup panels
    # ==================================================================

    def _current_mode(self) -> str:
        return _GEOMETRY[max(self.seg_geometry.currentIndex(), 0)][0]

    def _on_geometry_changed(self, _idx: int):
        mode = self._current_mode()
        cap = self.CURRENT_CAP_A.get(mode)
        if cap is not None:
            self.lbl_geom_hint.setText(f"Heater current is limited to {cap:g} A in this geometry.")
            unit = self._profile_params.get("pk160_current_unit", "mA")
            cap_u = cap * (1000.0 if unit == "mA" else 1.0)
            for k in ("start_volt", "stop_volt"):
                if float(self._profile_params.get(k, 0)) > cap_u:
                    self._profile_params[k] = cap_u
            self._refresh_profile_panel()

    def _set_mode_enabled(self, enabled: bool):
        self.seg_geometry.setEnabled(enabled)
        self.inp_sample.setReadOnly(not enabled)
        self.btn_edit_profile.setEnabled(enabled)
        self.lbl_profile_lock.setVisible(not enabled)

    def _refresh_profile_panel(self):
        p = self._profile_params
        u = p.get("pk160_current_unit", "mA")
        self.profile_preview.set_params(p)
        kv = self.kv_profile
        kv.set("Current", f"{float(p['start_volt']):g} → {float(p['stop_volt']):g} {u}")
        kv.set("Ramp up", f"{float(p['inc_rate']):g} {u}/s")
        kv.set("Hold", fmt_duration(float(p["hold_time"])))
        kv.set("Ramp down", f"{float(p['dec_rate']):g} {u}/s")
        kv.set("Pre-heat", fmt_duration(float(p["pre_time"])))
        kv.set("Sampling", f"every {int(p['interval'])} s")
        kv.set("Cooling until", f"|ΔT| < {self._cooling_target:g} K")
        kv.set("Duration", f"≈ {fmt_duration(profile_duration_s(p))} + cooling")

    def _refresh_safety_panel(self):
        try:
            from ...core.config import get_config
            cfg = get_config()
            s = cfg.safety
            self.kv_safety.set("Max temperature", f"{s.max_temperature_C:g} °C")
            self.kv_safety.set("Max heating rate", f"{s.max_rise_rate_C_per_min:g} °C/min")
            self.kv_safety.set("Invalid readings", f"abort after {int(s.max_consecutive_invalid_reads)}")
            self.kv_safety.set("Open-TC detect", "on" if cfg.thermocouples.open_tc_detect else "off",
                               tone=None if cfg.thermocouples.open_tc_detect else "warning")
        except Exception:
            self.kv_safety.set("Limits", "unavailable", tone="danger")

    def on_shown(self):
        if not self._timer.isActive():
            self._refresh_safety_panel()

    # ==================================================================
    # Event log
    # ==================================================================

    def _log(self, text: str, kind: str = "info"):
        stamp = time.strftime("%H:%M:%S")
        it = QListWidgetItem(f"{stamp}   {text}")
        color = {"warning": T.WARNING, "danger": T.DANGER, "success": T.SUCCESS}.get(kind)
        if color:
            from PyQt6.QtGui import QBrush, QColor
            it.setForeground(QBrush(QColor(color)))
        self.lst_log.insertItem(0, it)
        while self.lst_log.count() > 200:
            self.lst_log.takeItem(self.lst_log.count() - 1)

    # ==================================================================
    # Button-bar state
    # ==================================================================

    def _show_running_buttons(self):
        self.btn_reset.setVisible(False)
        self.btn_start.setVisible(False)
        self.btn_stop.setVisible(True)

    def _show_idle_buttons(self):
        self.btn_stop.setVisible(False)
        self.btn_reset.setVisible(True)
        self.btn_start.setVisible(True)

    # ==================================================================
    # Profile / Start / Stop / Reset
    # ==================================================================

    def _new_measurement(self):
        """Open the heater-profile editor (disabled while a run is active)."""
        import logging
        import traceback
        log = logging.getLogger("seebeck.new")
        try:
            from ...services.measurement_service import SeebeckService
            if SeebeckService().is_active():
                QMessageBox.warning(self, "Measurement running",
                                    "The heater profile cannot be changed during a run.")
                return
            win = self.window()
            dlg = MeasurementSetupDialog(
                self._profile_params, self._cooling_target,
                self.CURRENT_CAP_A[self._current_mode()], win,
            )
            geo = dlg.frameGeometry()
            geo.moveCenter(win.frameGeometry().center())
            dlg.move(geo.topLeft())
            if dlg.exec():
                self._profile_params = dlg.get_profile_params()
                self._cooling_target = dlg.get_cooling_target()
                self._refresh_profile_panel()
                self._log("Heater profile updated.")
        except Exception as e:
            log.critical("Profile editor failed: %s\n%s", e, traceback.format_exc())
            QMessageBox.critical(self, "Heater profile", f"Could not open the editor:\n{e}")

    _edit_profile = _new_measurement

    def _clear_results(self):
        """Wipe the on-screen data, charts and table for a fresh run."""
        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0
        self._reset_chart_buffers()
        for curve in (self.curve_temf, self.curve_t1, self.curve_t2,
                      self.curve_heat, self.curve_cool, self.curve_s):
            curve.setData([], [])
        self.scatter_bins.setData([], [])
        self.err_bins.setData(x=[], y=[], height=[])
        self.tbl_data.setRowCount(0)
        self.tbl_bins.setRowCount(0)
        self.chip_fit.set("No data", "neutral")
        for r in self.ro.values():
            r.set_value("—")
            r.set_note("")
            r.set_tone("accent" if r is self.ro["s"] else None)
        self._apply_phase("idle")

    def _start(self):
        from ...services.measurement_service import SeebeckService

        wp = self._profile_params
        if wp["start_volt"] >= wp["stop_volt"]:
            QMessageBox.warning(
                self, "Heater profile",
                "The start current I₀ must be lower than the peak current.\n"
                "Use Edit… in the Heater profile panel to fix it.")
            return
        sample = self.inp_sample.text().strip()
        if not sample:
            set_props(self.inp_sample, invalid=True)
            reply = QMessageBox.question(
                self, "No sample ID",
                "No sample ID is entered. The run will be hard to find in the run library.\n\n"
                "Start anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                self.inp_sample.setFocus()
                return

        params = {
            **wp,
            "sample_id": sample or None,
            "operator":  getattr(self._user, "username", None),
            "probe_mode": self._current_mode(),
            "cooling_target_delta_t": self._cooling_target,
        }

        svc = SeebeckService()
        if not svc.start(params):
            QMessageBox.critical(self, "Start run", getattr(svc, "last_error", None)
                                 or "The measurement could not be started.")
            return

        self._clear_results()
        self.chart_live.enableAutoRange()
        self._vb_temf.enableAutoRange()
        self.chart_temf_dt.enableAutoRange()
        self.chart_s_t0.enableAutoRange()

        self._last_phase = None
        self._last_invalid = 0
        self._last_db_warning = None
        self._polarity_logged = False
        self._run_id = None
        self._show_running_buttons()
        self._set_mode_enabled(False)
        self._log(f"Run started · {sample or 'no sample ID'} · "
                  f"{dict(_GEOMETRY)[self._current_mode()]}", "success")
        self.toolbar.set_subtitle("Starting — connecting to the instruments…")
        self._timer.start()

    def _stop(self):
        from ...services.measurement_service import SeebeckService
        SeebeckService().stop()
        self._timer.stop()
        self._show_idle_buttons()
        self._set_mode_enabled(True)
        self._apply_phase("idle")
        self._log("Run stopped by the operator — heater output off.", "warning")
        self.toolbar.set_subtitle(
            f"Stopped · run #{self._run_id} kept in the run library" if self._run_id
            else "Stopped")

    def _reset(self):
        from ...services.measurement_service import SeebeckService
        self._timer.stop()
        SeebeckService().reset()
        self._clear_results()
        self._show_idle_buttons()
        self._set_mode_enabled(True)
        self.toolbar.set_subtitle("Ready · no run in progress")
        self._log("Screen cleared and instruments released.")

    # ==================================================================
    # Polling
    # ==================================================================

    def _poll(self):
        from ...services.measurement_service import SeebeckService
        svc = SeebeckService()
        status = svc.get_status()

        phase = status.get("phase") or "idle"
        run_ended = not svc.is_active()
        if run_ended:
            phase = "error" if "error" in (status.get("status") or "") else "finished"
            self._timer.stop()
            self._show_idle_buttons()
            self._set_mode_enabled(True)

        if status.get("measurement_id"):
            self._run_id = status["measurement_id"]
        self._apply_phase(phase)

        if phase != self._last_phase and phase not in ("finished", "error"):
            self._log(f"Phase: {PHASES.get(phase, (phase,))[0]}")
        self._last_phase = phase

        invalid = status.get("invalid_reads") or 0
        if invalid > self._last_invalid:
            self._log(f"{invalid} invalid thermocouple reading(s) so far — not used as data.",
                      "warning")
            self._last_invalid = invalid
        if status.get("polarity_warning") and not self._polarity_logged:
            self._polarity_logged = True
            self._log(status["polarity_warning"], "danger")
        if status.get("db_warning") and status["db_warning"] != self._last_db_warning:
            self._last_db_warning = status["db_warning"]
            self._log("NOT SAVED: " + str(status["db_warning"]), "danger")

        step = status.get("step", 0)
        total = status.get("total_steps", 0)
        remaining = status.get("estimated_remaining_s")
        parts = []
        if self._run_id:
            parts.append(f"Run #{self._run_id}")
        parts.append(PHASES.get(phase, (phase.replace("_", " ").title(),))[0])
        if total and not run_ended:
            parts.append(f"step {step} / {total}")
        if remaining is not None and not run_ended:
            parts.append(f"{int(remaining) // 60:02d}:{int(remaining) % 60:02d} remaining")
        if invalid:
            parts.append(f"{invalid} invalid reading(s)")
        if status.get("db_warning"):
            parts.append("NOT SAVED")
        self.toolbar.set_subtitle("  ·  ".join(parts))

        new_data = svc.get_data()
        if len(new_data) > len(self._data):
            self._data = new_data
            self._refresh_charts()
            self._refresh_readouts(status)

        new_analysis = svc.get_analysis()
        if new_analysis and len(new_analysis) != len(self._analysis):
            self._analysis = new_analysis
            self._refresh_bins()

        if run_ended:
            if phase == "finished":
                self._log("Run finished — heater output off. Saved to the run library.", "success")
            self._report_run_end(status)

    def _report_run_end(self, status: dict):
        """Tell the operator why a run ended early, and if it was not saved."""
        reason = status.get("end_reason")
        db_warning = status.get("db_warning")
        if "error" in (status.get("status") or ""):
            title = ("Safety abort — heater switched off"
                     if reason and reason.startswith("Safety abort") else "Measurement error")
            msg = reason or status.get("status")
            self._log(f"{title}: {msg}", "danger")
            if db_warning:
                msg += "\n\n" + db_warning
            QMessageBox.critical(self, title, msg)
        elif db_warning:
            QMessageBox.warning(self, "Measurement not saved", db_warning)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_readouts(self, status: dict):
        if not self._data:
            return
        r = self._data[-1]

        def put(key, val, fmt, note: str = ""):
            ro = self.ro[key]
            if val is None:
                ro.set_value("—")
                ro.set_tone("muted")
            else:
                ro.set_value(fmt.format(val))
                ro.set_tone("accent" if key == "s" else None)
            ro.set_note(note)

        put("t1", r.get("Temp1 [oC]"), "{:.2f}")
        put("t2", r.get("Temp2 [oC]"), "{:.2f}")
        put("dt", r.get("Delta Temp [oC]"), "{:.2f}")
        put("t0", r.get("T0 [K]"), "{:.1f}")
        put("temf", r.get("TEMF [mV]"), "{:.4f}")
        put("s", r.get("S [µV/K]"), "{:.1f}")
        hv, hi = r.get("Heater V [V]"), r.get("Heater I [A]")
        put("heat", hv, "{:.2f}", f"{hi:.3f} A" if hi is not None else "")
        g = r.get("delta_T_over_T0")
        put("grad", g * 100 if g is not None else None, "{:.2f}")
        try:
            from ...instruments.session_manager import LARGE_GRADIENT_RATIO
        except Exception:
            LARGE_GRADIENT_RATIO = 0.1
        if g is not None and g > LARGE_GRADIENT_RATIO:
            self.ro["grad"].set_tone("warning")
            self.ro["grad"].set_note("large gradient")

    def _refresh_bins(self):
        rows = self._analysis
        t = self.tbl_bins
        t.setRowCount(len(rows))
        xs, ys, es = [], [], []
        for i, b in enumerate(rows):
            unc = b.get("S_uncertainty_uV_per_K")
            t.setItem(i, 0, cell(f"{b.get('T0_center_K', 0):.1f}", align="right", mono=True,
                                 tooltip=f"{b.get('T0_min_K')}–{b.get('T0_max_K')} K"))
            t.setItem(i, 1, cell(f"{b.get('S_uV_per_K', 0):.2f}", align="right", mono=True, bold=True))
            t.setItem(i, 2, cell("—" if unc is None else f"{unc:.2f}", align="right", mono=True,
                                 color=T.TEXT_SECONDARY))
            n_text, n_tip = bin_n_text(b)
            t.setItem(i, 3, cell(n_text, align="right", mono=True, tooltip=n_tip,
                                 color=T.WARNING if b.get("n_rejected") else T.TEXT_SECONDARY))
            if b.get("S_uV_per_K") is not None:
                xs.append(b["T0_center_K"])
                ys.append(b["S_uV_per_K"])
                es.append(2 * (unc or 0.0))
        self.scatter_bins.setData(xs, ys)
        if xs:
            import numpy as np
            self.err_bins.setData(x=np.array(xs), y=np.array(ys), height=np.array(es))
        self.chip_fit.set(f"{len(rows)} bin(s)" if rows else "No data",
                          "info" if rows else "neutral")

    def _reset_chart_buffers(self):
        for b in (self._buf_time, self._buf_heat, self._buf_cool, self._buf_s):
            b.clear()
        self._rows_charted = 0

    def _consume_new_rows(self):
        """Move rows that arrived since the last poll into the chart buffers."""
        if len(self._data) < self._rows_charted:      # a different run's data
            self._reset_chart_buffers()
        for r in self._data[self._rows_charted:]:
            self._buf_time.append((r.get("Time [s]", 0), r.get("Temp1 [oC]"),
                                   r.get("Temp2 [oC]"), r.get("TEMF [mV]")))
            dt, tf = r.get("Delta Temp [oC]"), r.get("TEMF [mV]")
            if r.get("branch") == "cooling":
                # Cooling continues from the heating peak (max ΔT) and traces back down.
                if len(self._buf_cool) == 0 and len(self._buf_heat):
                    self._buf_cool.append(self._buf_heat.last())
                if dt is not None and tf is not None:
                    self._buf_cool.append((dt, tf))
            elif dt is not None and tf is not None:
                self._buf_heat.append((dt, tf))
            t0, sv = r.get("T0 [K]"), r.get("S [µV/K]")
            if t0 is not None and sv is not None:
                self._buf_s.append((t0, sv))
        self._rows_charted = len(self._data)

    def _refresh_charts(self):
        if not self._data:
            return
        self._consume_new_rows()

        bt = self._buf_time
        t = bt.col(0)
        self.curve_temf.setData(t, bt.col(3))
        self.curve_t1.setData(t, bt.col(1))
        self.curve_t2.setData(t, bt.col(2))

        for curve, buf in ((self.curve_heat, self._buf_heat),
                           (self.curve_cool, self._buf_cool),
                           (self.curve_s, self._buf_s)):
            if len(buf):
                curve.setData(*thin(buf.col(0), buf.col(1)))

        # Data table — append only new rows
        new_count = len(self._data)
        if new_count > self._table_row_count:
            self.tbl_data.setRowCount(new_count)
            for i in range(self._table_row_count, new_count):
                row = self._data[i]
                invalid = row.get("valid") is False
                for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                    val = row.get(key)
                    text = "—" if val is None else fmt.format(val)
                    tip = (row.get("flag") or "invalid reading") if invalid else ""
                    if key == "S [µV/K]" and val is None and row.get("S_note"):
                        tip = f"S not computed: {row['S_note']}"
                    it = cell(text, align="right",
                              color=T.WARNING if invalid else None, tooltip=tip)
                    self.tbl_data.setItem(i, j, it)
            self._table_row_count = new_count
            self.tbl_data.scrollToBottom()
        self._tiles["data"].set_subtitle(f"{new_count} rows")

    # ------------------------------------------------------------------
    # Phase indicator
    # ------------------------------------------------------------------

    def _apply_phase(self, phase: str):
        keys = [k for k, _ in _SEGMENTS]
        if phase in keys:
            self.stepper.set_state(keys.index(phase))
        elif phase == "finished":
            self.stepper.set_state(-1, all_done=True)
        elif phase == "error":
            pass  # keep showing where it stopped
        else:
            self.stepper.set_state(-1)
        self.profile_preview.set_active(phase if phase in keys else None)

    def _update_segments(self, phase: str):
        self._apply_phase(phase)

    # ==================================================================
    # Export
    # ==================================================================

    def _export_single_chart(self, widget: pg.PlotWidget, suffix: str):
        if not self._data:
            QMessageBox.information(self, "Save chart", "There is no data to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart", f"seebeck_{suffix}.png", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pix = widget.grab()
        if not pix.isNull():
            pix.save(path, "PNG")
            QMessageBox.information(self, "Save chart", f"Chart saved to:\n{path}")

    def _export_graphs(self):
        if not self._data:
            QMessageBox.information(self, "Save graphs", "There is no data to save yet.")
            return
        base, _ = QFileDialog.getSaveFileName(
            self, "Save graphs (base filename)", "seebeck_graphs", "PNG images (*.png)")
        if not base:
            return
        root, _ext = os.path.splitext(base)
        targets = [
            (self.chart_live, f"{root}_live.png"),
            (self.chart_temf_dt, f"{root}_temf_vs_dt.png"),
            (self.chart_s_t0, f"{root}_seebeck_vs_t0.png"),
        ]
        for widget, path in targets:
            pix = widget.grab()
            if not pix.isNull():
                pix.save(path, "PNG")
        QMessageBox.information(
            self, "Save graphs",
            "Graphs saved as:\n" + "\n".join(os.path.basename(p) for _, p in targets))

    def _export_data(self):
        if not self._data:
            QMessageBox.information(self, "Save data", "There is no data to save yet.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save data", "seebeck_data.xlsx",
            "Excel workbook (*.xlsx);;CSV file (*.csv)")
        if not path:
            return
        if selected_filter.startswith("CSV") or path.lower().endswith(".csv"):
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self._export_csv(path)
        else:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self._export_excel_with_graphs(path)

    def _export_csv(self, path: str):
        import csv
        headers = [c[1] for c in _TABLE_COLS]
        keys = [c[0] for c in _TABLE_COLS]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in self._data:
                writer.writerow([row.get(k, "") if row.get(k) is not None else "" for k in keys])
        QMessageBox.information(self, "Save data", f"CSV saved to:\n{path}")

    def _export_excel_with_graphs(self, path: str):
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        headers = [c[1] for c in _TABLE_COLS]
        keys = [c[0] for c in _TABLE_COLS]
        ws.append(headers)
        for row in self._data:
            ws.append([row.get(k, "") if row.get(k) is not None else "" for k in keys])

        try:
            import PIL  # type: ignore  # noqa: F401
            img_start_row = len(self._data) + 3
            tmpdir = tempfile.mkdtemp(prefix="seebeck_graphs_")
            files = []

            def _save_chart(widget, name, row_offset):
                pix = widget.grab()
                if pix.isNull():
                    return
                fp = os.path.join(tmpdir, name)
                pix.save(fp, "PNG")
                ws.add_image(XLImage(fp), f"A{img_start_row + row_offset}")
                files.append(fp)

            _save_chart(self.chart_live, "chart_live.png", 0)
            _save_chart(self.chart_temf_dt, "chart_temf_dt.png", 20)
            _save_chart(self.chart_s_t0, "chart_s_t0.png", 40)
            wb.save(path)
            for fp in files:
                try:
                    os.remove(fp)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
            QMessageBox.information(self, "Save data", f"Excel workbook saved to:\n{path}")
        except ImportError:
            wb.save(path)
            QMessageBox.warning(
                self, "Save data",
                "Excel file saved without embedded graphs.\n\n"
                "To include graphs, install Pillow:\n  pip install pillow")

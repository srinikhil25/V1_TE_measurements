"""
I-V sweep and resistivity.

Left  : sample · geometry and dimensions · sweep settings · display units
Right : result readouts (R, ρ, σ, R², ohmic check …) · I-V chart · points table
"""

from __future__ import annotations

import math
import os
import tempfile
from typing import Dict, List, Optional

import pyqtgraph as pg
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLineEdit, QMessageBox, QProgressBar, QScrollArea, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)

from .. import theme as T
from ..widgets.tile import icon_button
from ..widgets.ui_kit import (
    LegendStrip, Panel, Readout, ReadoutGrid, Segmented, button, cell, field, fmt_sci,
    label, make_table, page_scaffold, pen, set_props, style_plot,
)

# Display-unit scaling for the display settings. Data is stored in SI
# (amps, volts); displayed value = SI * scale.
_V_UNITS = [("V", 1.0), ("mV", 1e3), ("µV", 1e6)]
_I_UNITS = [("A", 1.0), ("mA", 1e3), ("µA", 1e6), ("nA", 1e9)]

_GEOMETRIES = [("bar", "Bar"), ("vdp", "van der Pauw"), ("4pp", "4-point probe")]


# ---------------------------------------------------------------------------
# Worker thread for blocking IV sweep
# ---------------------------------------------------------------------------

class IVWorker(QThread):
    finished = pyqtSignal(dict)   # full result dict
    error = pyqtSignal(str)
    progress = pyqtSignal(int, dict)  # index, point

    def __init__(self, params: dict, abort_flag: Optional[object] = None):
        super().__init__()
        self._params = params
        self._abort_flag = abort_flag  # object with .abort_requested bool

    def run(self):
        try:
            from ...services.measurement_service import run_iv_sweep
            abort_check = None
            if self._abort_flag is not None:
                abort_check = lambda: getattr(self._abort_flag, "abort_requested", False)
            progress_cb = lambda i, pt: self.progress.emit(i, pt)
            result = run_iv_sweep(
                progress_callback=progress_cb,
                abort_check=abort_check,
                **self._params,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spinbox(lo, hi, val, decimals=2, suffix="") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setDecimals(decimals)          # before setValue, or the value is rounded to 2 dp
    sb.setRange(lo, hi)
    sb.setValue(val)
    if suffix:
        sb.setSuffix(f"  {suffix}")
    sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    sb.setProperty("buttons", "none")
    sb.setProperty("mono", True)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return sb


def _ispinbox(lo, hi, val) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    sb.setProperty("buttons", "none")
    sb.setProperty("mono", True)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return sb


def _pair(a: QWidget, b: QWidget) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(10)
    g.addWidget(a, 0, 0)
    g.addWidget(b, 0, 1)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    return w


# ---------------------------------------------------------------------------
# IV Page
# ---------------------------------------------------------------------------

class IVPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._worker: Optional[IVWorker] = None
        self._abort_flag = type("AbortFlag", (), {"abort_requested": False})()
        self._results: List[Dict] = []
        self._result_summary: Dict = {}  # fit_R, fit_R_squared, ohmic_status, temperature_C
        self._v_unit, self._v_scale = "V", 1.0
        self._i_unit, self._i_scale = "A", 1.0
        self._show_fit = True
        self._iv_cf = None
        pg.setConfigOptions(antialias=True)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        try:
            from ...core.config import get_config
            addr = get_config().instruments.k2401
        except Exception:
            addr = ""
        tb, body = page_scaffold(self, "I-V sweep and resistivity",
                                 f"Keithley 2401 SourceMeter · {addr}" if addr else "Keithley 2401 SourceMeter")
        self.toolbar = tb
        self.btn_abort = button("Abort", "danger-outline", icon="stop",
                                tooltip="Stop after the current point and switch the output off")
        self.btn_abort.clicked.connect(self._abort)
        self.btn_abort.setEnabled(False)
        self.btn_abort.setVisible(False)
        self.btn_run = button("Run sweep", "primary", icon="play")
        self.btn_run.clicked.connect(self._run)
        tb.add_action(self.btn_abort)
        tb.add_action(self.btn_run)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._build_left(), 0)
        row.addWidget(self._build_right(), 1)
        body.addLayout(row, 1)

    def _build_left(self) -> QWidget:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setFixedWidth(336)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(12)

        # ── Sample ─────────────────────────────────────────────────────
        sp = Panel("Sample")
        self.le_sample_id = QLineEdit()
        self.le_sample_id.setPlaceholderText("e.g. constantan-02")
        self.le_sample_id.textEdited.connect(lambda _t: set_props(self.le_sample_id, invalid=False))
        self.le_operator = QLineEdit()
        self.le_operator.setPlaceholderText("Operator")
        if self._user:
            self.le_operator.setText(getattr(self._user, "username", "") or "")
        self.le_notes = QLineEdit()
        self.le_notes.setPlaceholderText("Optional")
        sp.body.addWidget(field("Sample ID", self.le_sample_id))
        sp.body.addWidget(_pair(field("Operator", self.le_operator), field("Notes", self.le_notes)))
        v.addWidget(sp)

        # ── Geometry ──────────────────────────────────────────────────
        gp = Panel("Geometry", "Used to convert R into resistivity")
        self.cb_geometry = Segmented([g[1] for g in _GEOMETRIES], current=0)
        self.cb_geometry.currentIndexChanged.connect(self._on_geometry_changed)
        gp.body.addWidget(self.cb_geometry)
        self.sb_length_cm = _spinbox(0.0001, 100, 1.0, 4, "cm")
        self.sb_width_cm = _spinbox(0.0001, 100, 0.5, 4, "cm")
        self.sb_spacing_cm = _spinbox(0.0001, 10, 0.1, 4, "cm")
        self.sb_thickness_cm = _spinbox(0.0001, 10, 0.0525, 4, "cm")
        gp.body.addWidget(_pair(field("Length", self.sb_length_cm), field("Width", self.sb_width_cm)))
        gp.body.addWidget(_pair(field("Thickness", self.sb_thickness_cm),
                                field("Probe spacing", self.sb_spacing_cm)))
        self.lbl_geom_hint = label("", "caption", wrap=True)
        gp.body.addWidget(self.lbl_geom_hint)
        v.addWidget(gp)

        # ── Sweep ─────────────────────────────────────────────────────
        wp = Panel("Sweep")
        self.cb_source_mode = Segmented(["Source I · measure V", "Source V · measure I"])
        self.cb_source_mode.currentIndexChanged.connect(self._on_source_mode_changed)
        wp.body.addWidget(self.cb_source_mode)
        self.sb_start = _spinbox(-1.0, 1.0, -0.01, 4, "A")
        self.sb_stop = _spinbox(-1.0, 1.0, 0.01, 4, "A")
        wp.body.addWidget(_pair(field("Start", self.sb_start), field("Stop", self.sb_stop)))
        self.sb_points = _ispinbox(2, 500, 21)
        self.sb_delay = _spinbox(1, 5000, 50.0, 1, "ms")
        wp.body.addWidget(_pair(field("Points", self.sb_points), field("Step delay", self.sb_delay)))
        self.sb_nplc = _spinbox(0.01, 10, 5.0, 2, "NPLC")
        self.sb_ilimit = _spinbox(1e-6, 1.0, 0.1, 4, "A")
        self.sb_vlimit = _spinbox(0.1, 21, 21.0, 1, "V")
        wp.body.addWidget(_pair(field("Integration", self.sb_nplc),
                                field("Current limit", self.sb_ilimit)))
        wp.body.addWidget(_pair(field("Voltage limit", self.sb_vlimit), QWidget()))
        self.cb_bidirectional = QCheckBox("Forward and reverse")
        self.cb_bidirectional.setToolTip("Sweep back down as well — shows hysteresis and self-heating.")
        self.cb_four_wire = QCheckBox("4-wire remote sense")
        self.cb_four_wire.setToolTip("Needs the sense leads connected.")
        wp.body.addWidget(self.cb_bidirectional)
        wp.body.addWidget(self.cb_four_wire)
        v.addWidget(wp)

        # ── Display ───────────────────────────────────────────────────
        dp = Panel("Display")
        self.grp_vunit = Segmented([u for u, _ in _V_UNITS])
        self.grp_iunit = Segmented([u for u, _ in _I_UNITS])
        self.cb_show_fit = QCheckBox("Show linear fit")
        self.cb_show_fit.setChecked(True)
        dp.body.addWidget(field("Voltage unit", self.grp_vunit))
        dp.body.addWidget(field("Current unit", self.grp_iunit))
        dp.body.addWidget(self.cb_show_fit)
        self.grp_vunit.currentIndexChanged.connect(lambda _i: self._apply_units())
        self.grp_iunit.currentIndexChanged.connect(lambda _i: self._apply_units())
        self.cb_show_fit.toggled.connect(lambda _c: self._apply_units())
        v.addWidget(dp)
        v.addStretch()

        sa.setWidget(host)
        self._on_geometry_changed()
        return sa

    def _build_right(self) -> QWidget:
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        self.ro_R = Readout("Resistance R (fit)", "Ω")
        self.ro_rho = Readout("Resistivity ρ", "Ω·cm", tone="accent")
        self.ro_sigma = Readout("Conductivity σ", "S/cm")
        self.ro_R2 = Readout("Linearity R²", "")
        self.ro_ohmic = Readout("Ohmic check", "", size="sm")
        self.ro_cf = Readout("4PP correction CF", "",
                             tooltip="Smits 4-point-probe geometric correction factor.\n"
                                     "CF = (π/ln2)·C_size → 4.532 for an infinite sheet, "
                                     "less for a finite one.")
        self.ro_T = Readout("Sample temperature", "°C")
        self.ro_n = Readout("Points", "")
        self.readouts = ReadoutGrid([self.ro_R, self.ro_rho, self.ro_sigma, self.ro_R2,
                                     self.ro_ohmic, self.ro_cf, self.ro_T, self.ro_n], 4)
        v.addWidget(self.readouts)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        split.setStyleSheet("QSplitter::handle { background: transparent; }")

        # Chart panel
        cp = Panel("I-V characteristic", flush=True)
        self.chart_panel = cp
        cp.add_action(icon_button("image", "Save the chart as PNG", self._save_graph))
        self.chart = pg.PlotWidget()
        style_plot(self.chart, "Current (A)", "Voltage (V)")
        self.chart.setMinimumHeight(240)
        self.scatter_fwd = pg.ScatterPlotItem(size=7, pen=pg.mkPen(None),
                                              brush=pg.mkBrush(T.SERIES_T1))
        self.scatter_rev = pg.ScatterPlotItem(size=8, pen=pg.mkPen(T.SERIES_T2, width=1.5),
                                              brush=pg.mkBrush(None))
        self.fit_line = pg.PlotDataItem(pen=pen(T.SERIES_FIT, 1.6))
        self.chart.addItem(self.fit_line)
        self.chart.addItem(self.scatter_fwd)
        self.chart.addItem(self.scatter_rev)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(10, 8, 10, 8)
        il.setSpacing(4)
        il.addWidget(LegendStrip([(T.SERIES_T1, "Forward"), (T.SERIES_T2, "Reverse"),
                                  (T.SERIES_FIT, "Fit  V = R·I + V₀")],
                                 kinds=["dot", "ring", "line"]))
        il.addWidget(self.chart, 1)
        cp.body.addWidget(inner)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.lbl_status = label("Set the sweep and press Run sweep.", "caption", wrap=True)
        cp.show_footer()
        cp.footer_layout.addWidget(self.lbl_status, 1)
        cp.footer_layout.addWidget(self.progress)
        self.progress.setFixedWidth(180)
        split.addWidget(cp)

        # Points table
        tp = Panel("Points", flush=True)
        self.points_panel = tp
        self.btn_save_graph = button("Save graph…", size="sm", icon="image")
        self.btn_save_graph.clicked.connect(self._save_graph)
        self.btn_export_csv = button("Save data…", size="sm", icon="download")
        self.btn_export_csv.clicked.connect(self._export_data)
        tp.add_action(self.btn_save_graph)
        tp.add_action(self.btn_export_csv)
        self.table = make_table(["#", "Current (A)", "Voltage (V)", "V/I (Ω)", "Power (mW)",
                                 "ρ (Ω·cm)", "σ (S/cm)"], row_height=26, mono=True)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setColumnWidth(0, 48)
        for c in range(1, 6):
            self.table.setColumnWidth(c, 120)
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        tp.body.addWidget(self.table)
        tp.show_footer(label("Point-wise V/I includes the thermal-EMF offset V₀; the fitted "
                             "slope R does not — ρ and σ use R.", "caption", wrap=True))
        split.addWidget(tp)
        split.setSizes([520, 300])
        v.addWidget(split, 1)
        self._update_metric_cards()
        return host

    # ------------------------------------------------------------------
    # Settings behaviour
    # ------------------------------------------------------------------

    def _on_source_mode_changed(self, *_):
        is_current = self.cb_source_mode.currentIndex() == 0
        if is_current:
            self.sb_start.setRange(-1.0, 1.0)
            self.sb_stop.setRange(-1.0, 1.0)
            self.sb_start.setSuffix("  A")
            self.sb_stop.setSuffix("  A")
            self.sb_start.setValue(-0.01)
            self.sb_stop.setValue(0.01)
        else:
            self.sb_start.setRange(-21, 21)
            self.sb_stop.setRange(-21, 21)
            self.sb_start.setSuffix("  V")
            self.sb_stop.setSuffix("  V")
            self.sb_start.setValue(-1.0)
            self.sb_stop.setValue(1.0)

    def _on_geometry_changed(self, *_):
        idx = self.cb_geometry.currentIndex()   # 0 bar, 1 vdp, 2 4pp
        is_bar = idx == 0
        is_4pp = idx == 2
        # 4pp uses length/width too, for the finite-sheet geometric correction.
        self.sb_length_cm.setEnabled(is_bar or is_4pp)
        self.sb_width_cm.setEnabled(is_bar or is_4pp)
        self.sb_spacing_cm.setEnabled(is_4pp)
        if idx == 1:
            self.lbl_geom_hint.setText(
                "Arbitrary flat shape of uniform thickness, 4 contacts on the edge. "
                "ρ = (π·t / ln2)·R — needs the thickness only.")
        elif is_4pp:
            self.lbl_geom_hint.setText(
                "In-line probe: outer pins force current, inner pins sense voltage. "
                "ρ = (π/ln2)·t·R, corrected for finite thickness and sample size.")
        else:
            self.lbl_geom_hint.setText(
                "Uniform bar, current along its length. ρ = R·(W·t)/L.")
        if self._result_summary:
            self._update_metric_cards()

    def _apply_units(self):
        """Apply the display settings: rescale axes, chart and table."""
        vi = self.grp_vunit.currentIndex()
        ii = self.grp_iunit.currentIndex()
        self._v_unit, self._v_scale = _V_UNITS[vi] if 0 <= vi < len(_V_UNITS) else ("V", 1.0)
        self._i_unit, self._i_scale = _I_UNITS[ii] if 0 <= ii < len(_I_UNITS) else ("A", 1.0)
        self._show_fit = self.cb_show_fit.isChecked()
        style_plot(self.chart, f"Current ({self._i_unit})", f"Voltage ({self._v_unit})")
        self._replot()
        if self._results:
            self._fill_table()

    def _replot(self):
        """Redraw scatter + fit line from self._results using current units."""
        vs, is_ = self._v_scale, self._i_scale
        pts = [p for p in self._results
               if p.get("voltage") is not None and p.get("current") is not None]
        npts = self.sb_points.value()
        if self.cb_bidirectional.isChecked() and len(pts) > npts:
            fwd, rev = pts[:npts], pts[npts:]
        else:
            fwd, rev = pts, []
        self.scatter_fwd.setData([p["voltage"] * vs for p in fwd],
                                 [p["current"] * is_ for p in fwd])
        self.scatter_rev.setData([p["voltage"] * vs for p in rev],
                                 [p["current"] * is_ for p in rev])
        R = self._result_summary.get("fit_R")
        if self._show_fit and R is not None and abs(R) > 1e-12 and pts:
            ys = [p["current"] for p in pts]
            i_lo, i_hi = min(ys), max(ys)
            v0 = fit_offset(pts, R)
            self.fit_line.setData([(R * i_lo + v0) * vs, (R * i_hi + v0) * vs],
                                  [i_lo * is_, i_hi * is_])
        else:
            self.fit_line.setData([], [])

    # ------------------------------------------------------------------
    # Run / Abort / Progress
    # ------------------------------------------------------------------

    def _set_running(self, running: bool):
        self.btn_run.setEnabled(not running)
        self.btn_abort.setEnabled(running)
        self.btn_abort.setVisible(running)
        self.progress.setVisible(running)
        for w in (self.cb_source_mode, self.sb_start, self.sb_stop, self.sb_points,
                  self.sb_delay, self.sb_nplc, self.sb_ilimit, self.sb_vlimit,
                  self.cb_bidirectional, self.cb_four_wire, self.le_sample_id):
            w.setEnabled(not running)

    def _run(self):
        sample = self.le_sample_id.text().strip()
        if not sample:
            set_props(self.le_sample_id, invalid=True)
            reply = QMessageBox.question(
                self, "No sample ID",
                "No sample ID is entered. The sweep will be hard to find in the run library.\n\n"
                "Run anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                self.le_sample_id.setFocus()
                return

        self._abort_flag.abort_requested = False
        self._set_running(True)
        self.lbl_status.setText("Connecting to the SourceMeter…")
        self.scatter_fwd.setData([], [])
        self.scatter_rev.setData([], [])
        self.fit_line.setData([], [])
        self.table.setRowCount(0)
        self._results.clear()
        self._result_summary.clear()
        self._update_metric_cards()
        total = self.sb_points.value() * (2 if self.cb_bidirectional.isChecked() else 1)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.toolbar.set_subtitle(f"Sweeping · {sample or 'no sample ID'}")

        is_current_mode = self.cb_source_mode.currentIndex() == 0
        start = self.sb_start.value()
        stop = self.sb_stop.value()
        length_cm = self.sb_length_cm.value() if self.sb_length_cm.value() > 1e-9 else None
        width_cm = self.sb_width_cm.value() if self.sb_width_cm.value() > 1e-9 else None
        thickness_cm = self.sb_thickness_cm.value() if self.sb_thickness_cm.value() > 1e-9 else None
        spacing_cm = self.sb_spacing_cm.value() if self.sb_spacing_cm.value() > 1e-9 else None
        geometry = {0: "bar", 1: "vdp", 2: "4pp"}.get(self.cb_geometry.currentIndex(), "bar")

        try:
            user = self._user
            user_id = getattr(user, "id", None) if user else None
            lab_id = getattr(user, "lab_id", None) if user else None
        except Exception:
            user_id = lab_id = None

        params = dict(
            source_mode="current" if is_current_mode else "voltage",
            start=start,
            stop=stop,
            points=self.sb_points.value(),
            bidirectional=self.cb_bidirectional.isChecked(),
            delay_ms=self.sb_delay.value(),
            current_limit=self.sb_ilimit.value(),
            voltage_limit=self.sb_vlimit.value(),
            nplc=self.sb_nplc.value(),
            four_wire=self.cb_four_wire.isChecked(),
            length=length_cm,
            width=width_cm,
            thickness=thickness_cm,
            geometry=geometry,
            spacing=spacing_cm,
            sample_id=sample or None,
            operator=self.le_operator.text().strip() or None,
            notes=self.le_notes.text().strip() or None,
            _user_id=user_id,
            _lab_id=lab_id,
        )

        self._worker = IVWorker(params, self._abort_flag)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _abort(self):
        self._abort_flag.abort_requested = True
        self.lbl_status.setText("Aborting after the current point…")

    def _on_progress(self, index: int, point: Dict):
        self._results.append(point)
        self._replot()
        self.progress.setValue(index + 1)
        self.ro_n.set_value(str(len(self._results)))
        self.lbl_status.setText(f"Point {index + 1} of {self.progress.maximum()}…")

    def _on_done(self, result: Dict):
        self._set_running(False)
        self._results = result.get("points", [])
        self._result_summary = {
            "fit_R": result.get("fit_R"),
            "fit_R_squared": result.get("fit_R_squared"),
            "ohmic_status": result.get("ohmic_status", "unknown"),
            "temperature_C": result.get("temperature_C"),
        }

        self._replot()
        self._update_metric_cards()
        self._fill_table()

        n = len(self._results)
        mid = result.get("measurement_id")
        msg = f"Done — {n} points."
        if mid is not None:
            msg += f" Saved to the run library as #{mid}."
        if result.get("aborted"):
            msg = "Aborted — " + msg
        if result.get("db_warning"):
            msg += "  ⚠ " + result["db_warning"]
        self.lbl_status.setText(msg)
        sample = self.le_sample_id.text().strip() or "no sample ID"
        self.toolbar.set_subtitle(
            f"Last sweep: {'run #' + str(mid) + ', ' if mid else ''}{sample}"
            + (" · aborted" if result.get("aborted") else ""))
        self.chart_panel.set_title(f"I-V characteristic · run #{mid}" if mid else "I-V characteristic")

    def _update_metric_cards(self):
        R = self._result_summary.get("fit_R")
        R2 = self._result_summary.get("fit_R_squared")
        status = self._result_summary.get("ohmic_status", "unknown")
        Tc = self._result_summary.get("temperature_C")

        rho = None
        sigma = None
        cf = None                                              # 4-point-probe correction factor
        if self._results and R is not None:
            idx = self.cb_geometry.currentIndex()
            t_cm = self.sb_thickness_cm.value() if self.sb_thickness_cm.value() > 1e-9 else None
            if idx == 1:                                       # van der Pauw
                if t_cm:
                    rho = (math.pi * t_cm / math.log(2)) * R
            elif idx == 2:                                     # in-line 4-point probe
                s_cm = self.sb_spacing_cm.value() if self.sb_spacing_cm.value() > 1e-9 else None
                l_cm = self.sb_length_cm.value() if self.sb_length_cm.value() > 1e-9 else None
                w_cm = self.sb_width_cm.value() if self.sb_width_cm.value() > 1e-9 else None
                if t_cm:
                    from ...services.measurement_service import collinear_4pp_size_factor
                    c_size = collinear_4pp_size_factor(s_cm, l_cm, w_cm)
                    cf = (math.pi / math.log(2)) * c_size      # Smits CF (chart value)
                    rho = (math.pi / math.log(2)) * t_cm * R   # thin, infinite sheet
                    if s_cm:                                   # smooth thickness factor
                        ts = t_cm / s_cm
                        denom = math.log(math.sinh(ts) / math.sinh(ts / 2.0))
                        if denom > 0:
                            rho *= math.log(2) / denom
                    rho *= c_size                              # finite-sheet correction
            else:                                              # rectangular bar
                l_cm = self.sb_length_cm.value() if self.sb_length_cm.value() > 1e-9 else None
                w_cm = self.sb_width_cm.value() if self.sb_width_cm.value() > 1e-9 else None
                if l_cm and w_cm and t_cm and l_cm > 0:
                    rho = R * (w_cm * t_cm) / l_cm
            sigma = (1.0 / rho) if rho else None
        self._iv_cf = cf

        self.ro_R.set_value(*_si(R, "Ω"))
        self.ro_rho.set_value(fmt_sci(rho, 3) if rho is not None else "—")
        self.ro_sigma.set_value(fmt_sci(sigma, 3) if sigma is not None else "—")
        self.ro_cf.set_value(f"{cf:.3f}" if cf is not None else "—")
        self.ro_R2.set_value(f"{R2:.4f}" if R2 is not None else "—")
        self.ro_T.set_value(f"{Tc:.1f}" if Tc is not None else "—")
        self.ro_n.set_value(str(len(self._results)) if self._results else "—")

        text, tone = {
            "ohmic":          ("Ohmic", "success"),
            "check_contacts": ("Check contacts", "warning"),
            "non_ohmic":      ("Non-ohmic", "danger"),
        }.get(status, ("—", None))
        self.ro_ohmic.set_value(text)
        self.ro_ohmic.set_tone(tone)
        self.ro_R2.set_tone(tone if tone in ("warning", "danger") else None)

    def _fill_table(self):
        self.table.setHorizontalHeaderLabels([
            "#", f"Current ({self._i_unit})", f"Voltage ({self._v_unit})",
            "V/I (Ω)", "Power (mW)", "ρ (Ω·cm)", "σ (S/cm)",
        ])
        self.table.setRowCount(len(self._results))
        npts = self.sb_points.value()
        bidir = self.cb_bidirectional.isChecked()
        for row, pt in enumerate(self._results):
            i = pt.get("current")
            v = pt.get("voltage")
            r = pt.get("resistance")
            p_mw = (v * i * 1000) if (v is not None and i is not None) else None
            i_disp = i * self._i_scale if i is not None else None
            v_disp = v * self._v_scale if v is not None else None
            rev = bidir and row >= npts
            self.table.setItem(row, 0, cell(str(row + 1), align="right",
                                            color=T.SERIES_T2 if rev else T.TEXT_SECONDARY,
                                            tooltip="reverse" if rev else "forward"))
            for col, val in enumerate([i_disp, v_disp, r, p_mw,
                                       pt.get("resistivity"), pt.get("conductivity")], start=1):
                self.table.setItem(row, col, cell("—" if val is None else f"{val:.6g}",
                                                  align="right"))
        self.points_panel.set_subtitle(f"{len(self._results)} points"
                                       + (" · forward then reverse" if bidir else ""))

    def _on_error(self, msg: str):
        self._set_running(False)
        self.lbl_status.setText("The sweep failed — see the message.")
        self.toolbar.set_subtitle("Last sweep failed")
        QMessageBox.critical(
            self, "I-V sweep error",
            f"The sweep failed:\n\n{msg}\n\n"
            "Check that the SourceMeter is connected and switched on, then try again.")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _table_rows(self):
        """(headers, rows) shared by the CSV and Excel exporters."""
        headers = ["Current (A)", "Voltage (V)", "Resistance (Ohm)", "Power (mW)",
                   "Resistivity (Ohm.cm)", "Conductivity (S/cm)"]
        rows = []
        for pt in self._results:
            i = pt.get("current")
            v = pt.get("voltage")
            r = pt.get("resistance")
            p = (v * i * 1000) if (v is not None and i is not None) else None
            rows.append([i, v, r, p, pt.get("resistivity"), pt.get("conductivity")])
        return headers, rows

    def _export_data(self):
        """Save the sweep. Excel (.xlsx) embeds the I-V graph; CSV is data-only."""
        if not self._results:
            QMessageBox.information(self, "Save data", "There is no data to save. Run a sweep first.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save I-V data", "iv_data.xlsx",
            "Excel workbook (*.xlsx);;CSV file (*.csv)")
        if not path:
            return
        try:
            if selected_filter.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                self._write_csv(path)
                QMessageBox.information(self, "Save data", f"CSV saved to:\n{path}")
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                self._export_excel_with_graph(path)
        except Exception as e:
            QMessageBox.critical(self, "Save data", str(e))

    def _write_csv(self, path: str):
        import csv
        headers, rows = self._table_rows()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(["" if v is None else v for v in row])

    def _export_excel_with_graph(self, path: str):
        """Write the data sheet + a fit summary and embed the I-V chart PNG."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        headers, rows = self._table_rows()
        ws.append(headers)
        for row in rows:
            ws.append(["" if v is None else v for v in row])

        s = self._result_summary
        ws.append([])
        ws.append(["Fit R (Ohm)", s.get("fit_R")])
        ws.append(["R^2", s.get("fit_R_squared")])
        ws.append(["Ohmic status", s.get("ohmic_status")])
        ws.append(["Temperature (C)", s.get("temperature_C")])
        ws.append(["4PP correction factor CF", getattr(self, "_iv_cf", None)])

        try:
            import PIL  # type: ignore  # noqa: F401
            tmpdir = tempfile.mkdtemp(prefix="iv_graph_")
            fp = None
            pix = self.chart.grab()
            if not pix.isNull():
                fp = os.path.join(tmpdir, "iv_chart.png")
                pix.save(fp, "PNG")
                ws.add_image(XLImage(fp), f"A{len(rows) + 9}")
            wb.save(path)
            if fp:
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
                "Excel file saved without the embedded graph.\n\n"
                "To include the graph, install Pillow:\n  pip install pillow")

    def _save_graph(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save graph", "iv_chart.png", "PNG (*.png)")
        if not path:
            return
        try:
            pix = self.chart.grab()
            if pix.isNull():
                QMessageBox.warning(self, "Save graph", "The chart image is empty.")
                return
            pix.save(path, "PNG")
            QMessageBox.information(self, "Save graph", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save graph", str(e))


def fit_offset(points, R) -> float:
    """Intercept V₀ of the least-squares line V = R·I + V₀ (thermal-EMF offset)."""
    pts = [(p["current"], p["voltage"]) for p in points
           if p.get("current") is not None and p.get("voltage") is not None]
    if not pts or R is None:
        return 0.0
    mi = sum(i for i, _ in pts) / len(pts)
    mv = sum(v for _, v in pts) / len(pts)
    return mv - R * mi


def _si(value, unit: str):
    """(text, unit) with an SI prefix so R reads like '267.0' 'µΩ'."""
    if value is None:
        return "—", unit
    a = abs(value)
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"),
                           (1e-6, "µ"), (1e-9, "n")):
        if a >= factor:
            return f"{value / factor:.4g}", prefix + unit
    return f"{value:.3g}", unit

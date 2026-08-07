"""
I-V measurement page.

Left: sample info, sweep parameters (source mode, start/stop, points, bidirectional),
      compliance, dimensions, Run/Abort.
Right: live I-V chart (forward/reverse + fit), metric cards, results table, export.
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QDoubleSpinBox, QSpinBox, QSplitter, QAbstractSpinBox,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLineEdit, QComboBox, QCheckBox, QGridLayout,
    QFileDialog, QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Display-unit scaling for the "Data handling" radios. Data is stored in SI
# (amps, volts); displayed value = SI * scale.
_V_UNITS = [("V", 1.0), ("mV", 1e3), ("µV", 1e6)]
_I_UNITS = [("A", 1.0), ("mA", 1e3), ("µA", 1e6), ("nA", 1e9)]

import os
import tempfile

import pyqtgraph as pg
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ERROR, ERROR_BG, SUCCESS, SUCCESS_BG, WARNING, WARNING_BG,
)


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

def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; }}"
    )
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px; border: none;"
    )
    return lbl


def _flabel(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; "
        f"letter-spacing: 0.3px; border: none;"
    )
    return lbl


def _field(label: str, widget: QWidget, layout: QVBoxLayout):
    layout.addWidget(_flabel(label))
    layout.addSpacing(4)
    layout.addWidget(widget)
    layout.addSpacing(12)


def _row2(label1, w1, label2, w2, layout: QVBoxLayout):
    """Two fields side by side — for natural pairs (Start/Stop, limits)."""
    row = QHBoxLayout()
    row.setSpacing(12)
    for lbl, w in ((label1, w1), (label2, w2)):
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_flabel(lbl))
        col.addWidget(w)
        row.addLayout(col)
    layout.addLayout(row)
    layout.addSpacing(12)


def _spinbox(lo, hi, val, decimals=2, suffix="") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setDecimals(decimals)
    if suffix:
        sb.setSuffix(f"  {suffix}")
    sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)  # no broken stepper box
    sb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    sb.setFixedHeight(40)
    return sb


def _ispinbox(lo, hi, val) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    sb.setFixedHeight(40)
    return sb


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
        # Display units / graph format (set by the Data handling radios).
        self._v_unit, self._v_scale = "V", 1.0
        self._i_unit, self._i_scale = "A", 1.0
        self._show_fit = True
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #E2DED4; }")

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([320, 900])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    def _build_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setFixedWidth(320)

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(16)

        # Sample info
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(0)
        cl.addWidget(_section_label("SAMPLE INFO"))
        cl.addSpacing(10)
        self.le_sample_id = QLineEdit()
        self.le_sample_id.setPlaceholderText("Sample ID")
        self.le_sample_id.setFixedHeight(36)
        cl.addWidget(self.le_sample_id)
        cl.addSpacing(8)
        self.le_operator = QLineEdit()
        self.le_operator.setPlaceholderText("Operator")
        self.le_operator.setFixedHeight(36)
        if self._user:
            self.le_operator.setText(getattr(self._user, "username", "") or "")
        cl.addWidget(self.le_operator)
        cl.addSpacing(8)
        self.le_notes = QLineEdit()
        self.le_notes.setPlaceholderText("Notes")
        self.le_notes.setFixedHeight(36)
        cl.addWidget(self.le_notes)
        v.addWidget(card)

        # ── Measurement (sweep setup + compliance + run) ──────────────────
        card2 = _card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(16, 14, 16, 14)
        c2.setSpacing(0)
        c2.addWidget(_section_label("MEASUREMENT"))
        c2.addSpacing(10)

        self.cb_source_mode = QComboBox()
        self.cb_source_mode.addItems(["Source Current (measure V)", "Source Voltage (measure I)"])
        self.cb_source_mode.setFixedHeight(40)
        self.cb_source_mode.currentIndexChanged.connect(self._on_source_mode_changed)
        _field("Source mode", self.cb_source_mode, c2)

        self.cb_four_wire = QCheckBox("4-wire sense (remote) — needs sense leads")
        self.cb_four_wire.setChecked(False)
        c2.addWidget(self.cb_four_wire)
        c2.addSpacing(12)

        self.sb_start = _spinbox(-1.0, 1.0, -0.01, 4, "A")
        self.sb_stop = _spinbox(-1.0, 1.0, 0.01, 4, "A")
        _row2("Start", self.sb_start, "Stop", self.sb_stop, c2)

        self.sb_points = _ispinbox(2, 500, 21)
        _field("Number of points", self.sb_points, c2)

        self.cb_bidirectional = QCheckBox("Bidirectional (forward + reverse)")
        self.cb_bidirectional.setChecked(False)
        c2.addWidget(self.cb_bidirectional)
        c2.addSpacing(12)

        self.sb_delay = _spinbox(1, 5000, 50.0, 1, "ms")
        self.sb_nplc = _spinbox(0.01, 10, 5.0, 2, "NPLC")
        _row2("Step delay", self.sb_delay, "Integration", self.sb_nplc, c2)

        self.sb_ilimit = _spinbox(1e-6, 1.0, 0.1, 4, "A")
        self.sb_vlimit = _spinbox(0.1, 21, 21.0, 1, "V")
        _row2("Current limit", self.sb_ilimit, "Voltage limit", self.sb_vlimit, c2)

        self.btn_run = QPushButton("▶  Run sweep")
        self.btn_run.setFixedHeight(42)
        self.btn_run.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 7px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #26606A; }}"
            f"QPushButton:disabled {{ background: #8FB6BA; }}"
        )
        self.btn_run.clicked.connect(self._run)
        c2.addWidget(self.btn_run)
        v.addWidget(card2)

        # ── Data handling (display units + graph format) ──────────────────
        card_dh = _card()
        cdh = QVBoxLayout(card_dh)
        cdh.setContentsMargins(16, 14, 16, 14)
        cdh.setSpacing(0)
        cdh.addWidget(_section_label("DATA HANDLING"))
        cdh.addSpacing(10)

        cdh.addWidget(_flabel("Voltage unit"))
        cdh.addSpacing(4)
        self.grp_vunit = QButtonGroup(self)
        cdh.addLayout(self._radio_row(self.grp_vunit, [u for u, _ in _V_UNITS], checked=0))
        cdh.addSpacing(12)

        cdh.addWidget(_flabel("Current unit"))
        cdh.addSpacing(4)
        self.grp_iunit = QButtonGroup(self)
        cdh.addLayout(self._radio_row(self.grp_iunit, [u for u, _ in _I_UNITS], checked=0))
        cdh.addSpacing(12)

        cdh.addWidget(_flabel("Graph format"))
        cdh.addSpacing(4)
        self.grp_fmt = QButtonGroup(self)
        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(5)
        for i, txt in enumerate(["Scatter plot", "Scatter plot + linear fit"]):
            rb = QRadioButton(txt)
            if i == 1:
                rb.setChecked(True)
            self.grp_fmt.addButton(rb, i)
            fmt_col.addWidget(rb)
        cdh.addLayout(fmt_col)
        for grp in (self.grp_vunit, self.grp_iunit, self.grp_fmt):
            grp.buttonClicked.connect(self._apply_units)
        v.addWidget(card_dh)

        # ── Sample geometry + dimensions (cm) — for resistivity ───────────
        card4 = _card()
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(16, 14, 16, 14)
        c4.setSpacing(0)
        c4.addWidget(_section_label("SAMPLE GEOMETRY  (for resistivity)"))
        c4.addSpacing(10)
        self.cb_geometry = QComboBox()
        self.cb_geometry.addItems(["Rectangular bar  (ρ = R·A/L)",
                                   "Van der Pauw  (arbitrary shape)",
                                   "4-point probe (in-line)"])
        self.cb_geometry.setFixedHeight(40)
        self.cb_geometry.currentIndexChanged.connect(self._on_geometry_changed)
        _field("Shape", self.cb_geometry, c4)
        self.sb_length_cm = _spinbox(0.0001, 100, 1.0, 4, "cm")
        self.sb_width_cm = _spinbox(0.0001, 100, 0.5, 4, "cm")
        self.sb_spacing_cm = _spinbox(0.0001, 10, 0.1, 4, "cm")
        self.sb_thickness_cm = _spinbox(0.0001, 10, 0.0525, 4, "cm")
        _row2("Length", self.sb_length_cm, "Width", self.sb_width_cm, c4)
        _row2("Probe spacing", self.sb_spacing_cm, "Thickness", self.sb_thickness_cm, c4)
        self.lbl_geom_hint = QLabel("")
        self.lbl_geom_hint.setWordWrap(True)
        self.lbl_geom_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border: none;"
        )
        c4.addWidget(self.lbl_geom_hint)
        v.addWidget(card4)
        self._on_geometry_changed()

        self.btn_abort = QPushButton("⏹  Abort")
        self.btn_abort.setFixedHeight(42)
        self.btn_abort.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; border: none; "
            f"border-radius: 7px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #883333; }}"
            f"QPushButton:disabled {{ background: #D8B4B4; }}"
        )
        self.btn_abort.clicked.connect(self._abort)
        self.btn_abort.setEnabled(False)
        v.addWidget(self.btn_abort)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; border: none;"
        )
        v.addWidget(self.lbl_status)
        v.addStretch()

        scroll.setWidget(panel)
        return scroll

    def _on_source_mode_changed(self):
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

    def _on_geometry_changed(self):
        idx = self.cb_geometry.currentIndex()   # 0 bar, 1 vdp, 2 4pp
        is_bar = idx == 0
        is_4pp = idx == 2
        # Enable the dimensions each method uses. 4pp now uses length/width too,
        # for the finite-sheet geometric correction.
        self.sb_length_cm.setEnabled(is_bar or is_4pp)
        self.sb_width_cm.setEnabled(is_bar or is_4pp)
        self.sb_spacing_cm.setEnabled(is_4pp)
        if idx == 1:
            self.lbl_geom_hint.setText(
                "Van der Pauw — for arbitrary flat shapes of uniform thickness "
                "(4 contacts on the edge). ρ = (π·t / ln2)·R. Needs thickness only."
            )
        elif is_4pp:
            self.lbl_geom_hint.setText(
                "In-line 4-point probe — outer pins force current, inner pins sense "
                "voltage. ρ = (π/ln2)·t·R, auto-corrected for finite thickness and "
                "sample size. Enter probe spacing, thickness, and sample length × width."
            )
        else:
            self.lbl_geom_hint.setText(
                "Rectangular bar — uniform, unidirectional current. "
                "ρ = R·(W·t)/L. Needs length, width and thickness."
            )

    def _radio_row(self, group: QButtonGroup, labels, checked=0) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        for i, txt in enumerate(labels):
            rb = QRadioButton(txt)
            if i == checked:
                rb.setChecked(True)
            group.addButton(rb, i)
            row.addWidget(rb)
        row.addStretch()
        return row

    def _apply_units(self):
        """Apply the Data-handling radios: rescale axes, chart and table."""
        vi = self.grp_vunit.checkedId()
        ii = self.grp_iunit.checkedId()
        self._v_unit, self._v_scale = _V_UNITS[vi] if 0 <= vi < len(_V_UNITS) else ("V", 1.0)
        self._i_unit, self._i_scale = _I_UNITS[ii] if 0 <= ii < len(_I_UNITS) else ("A", 1.0)
        self._show_fit = (self.grp_fmt.checkedId() == 1)
        self.chart.getAxis("left").enableAutoSIPrefix(False)
        self.chart.getAxis("bottom").enableAutoSIPrefix(False)
        self.chart.setLabel("left", f"Current ({self._i_unit})")
        self.chart.setLabel("bottom", f"Voltage ({self._v_unit})")
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
                                 [p["current"] * is_ for p in fwd],
                                 brush=pg.mkBrush(PRIMARY + "CC"))
        self.scatter_rev.setData([p["voltage"] * vs for p in rev],
                                 [p["current"] * is_ for p in rev],
                                 brush=pg.mkBrush(WARNING + "CC"))
        R = self._result_summary.get("fit_R")
        if self._show_fit and R is not None and abs(R) > 1e-12 and pts:
            ys = [p["current"] for p in pts]
            i_lo, i_hi = min(ys), max(ys)
            self.fit_line.setData([R * i_lo * vs, R * i_hi * vs],
                                  [i_lo * is_, i_hi * is_])
        else:
            self.fit_line.setData([], [])

    def _build_right(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        pg.setConfigOptions(antialias=True)

        self.chart = pg.PlotWidget()
        self.chart.setBackground("white")
        self.chart.getAxis("left").enableAutoSIPrefix(False)
        self.chart.getAxis("bottom").enableAutoSIPrefix(False)
        self.chart.setLabel("left", "Current (A)")
        self.chart.setLabel("bottom", "Voltage (V)")
        self.chart.setTitle("I-V Characteristic")
        self.chart.showGrid(x=True, y=True, alpha=0.3)
        self.chart.setMinimumHeight(320)
        self.scatter_fwd = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None),
            brush=pg.mkBrush(PRIMARY + "CC"),
        )
        self.scatter_rev = pg.ScatterPlotItem(
            size=6, pen=pg.mkPen(None),
            brush=pg.mkBrush(WARNING + "CC"),
        )
        self.fit_line = pg.PlotDataItem(pen=pg.mkPen(SUCCESS, width=2))
        self.chart.addItem(self.scatter_fwd)
        self.chart.addItem(self.scatter_rev)
        self.chart.addItem(self.fit_line)
        v.addWidget(self.chart, stretch=2)

        # Metric cards
        cards_row = QHBoxLayout()
        self.lbl_R = QLabel("R: —")
        self.lbl_rho = QLabel("ρ: —")
        self.lbl_sigma = QLabel("σ: —")
        self.lbl_cf = QLabel("CF: —")
        self.lbl_cf.setToolTip(
            "Smits 4-point-probe geometric correction factor.\n"
            "CF = (π/ln2)·C_size  →  4.532 for an infinite sheet, less for a finite one."
        )
        self.lbl_R2 = QLabel("R²: —")
        self.lbl_ohmic = QLabel("—")
        self.lbl_T = QLabel("T: —")
        for w in (self.lbl_R, self.lbl_rho, self.lbl_sigma, self.lbl_cf,
                  self.lbl_R2, self.lbl_ohmic, self.lbl_T):
            w.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
                f"padding: 6px 10px; background: {CARD_BG}; border-radius: 6px; "
                f"border: 1px solid {BORDER};"
            )
        cards_row.addWidget(self.lbl_R)
        cards_row.addWidget(self.lbl_rho)
        cards_row.addWidget(self.lbl_sigma)
        cards_row.addWidget(self.lbl_cf)
        cards_row.addWidget(self.lbl_R2)
        cards_row.addWidget(self.lbl_ohmic)
        cards_row.addWidget(self.lbl_T)
        cards_row.addStretch()
        v.addLayout(cards_row)

        # Table
        v.addWidget(_section_label("RESULTS"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Current (A)", "Voltage (V)", "Resistance (Ω)", "Power (mW)",
             "Resistivity (Ω·cm)", "Conductivity (S/cm)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; font-size: 12px; }}"
            f"QTableWidget::item:alternate {{ background: #FBFAF5; }}"
        )
        v.addWidget(self.table, stretch=1)

        # Export
        export_row = QHBoxLayout()
        self.btn_export_csv = QPushButton("Save Data…")
        self.btn_export_csv.setStyleSheet(
            f"QPushButton {{ background: {CARD_BG}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 14px; }}"
        )
        self.btn_export_csv.clicked.connect(self._export_data)
        self.btn_save_graph = QPushButton("Save graph…")
        self.btn_save_graph.setStyleSheet(
            f"QPushButton {{ background: {CARD_BG}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 14px; }}"
        )
        self.btn_save_graph.clicked.connect(self._save_graph)
        export_row.addWidget(self.btn_export_csv)
        export_row.addWidget(self.btn_save_graph)
        export_row.addStretch()
        v.addLayout(export_row)

        return panel

    # ------------------------------------------------------------------
    # Run / Abort / Progress
    # ------------------------------------------------------------------

    def _run(self):
        self._abort_flag.abort_requested = False
        self.btn_run.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.lbl_status.setText("Connecting and running sweep…")
        self.scatter_fwd.setData([], [])
        self.scatter_rev.setData([], [])
        self.fit_line.setData([], [])
        self.table.setRowCount(0)
        self._results.clear()
        self._result_summary.clear()
        self._update_metric_cards()

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
            sample_id=self.le_sample_id.text().strip() or None,
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
        self.lbl_status.setText("Aborting…")

    def _on_progress(self, index: int, point: Dict):
        self._results.append(point)
        self._replot()
        self.lbl_status.setText(f"Point {index + 1}…")

    def _on_done(self, result: Dict):
        self.btn_run.setEnabled(True)
        self.btn_abort.setEnabled(False)
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
            msg += f" Saved to history (id={mid})."
        if result.get("aborted"):
            msg = "Aborted — " + msg
        self.lbl_status.setText(msg)

    def _update_metric_cards(self):
        R = self._result_summary.get("fit_R")
        R2 = self._result_summary.get("fit_R_squared")
        status = self._result_summary.get("ohmic_status", "unknown")
        T = self._result_summary.get("temperature_C")

        self.lbl_R.setText(f"R: {R:.6g} Ω" if R is not None else "R: —")
        rho = None
        sigma = None
        cf = None                                              # 4-point-probe correction factor
        if self._results and R is not None:
            import math
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
        self.lbl_rho.setText(f"ρ: {rho:.4e} Ω·cm" if rho is not None else "ρ: —")
        self.lbl_sigma.setText(f"σ: {sigma:.4e} S/cm" if sigma is not None else "σ: —")
        self.lbl_cf.setText(f"CF: {cf:.3f}" if cf is not None else "CF: —")
        self.lbl_R2.setText(f"R²: {R2:.4f}" if R2 is not None else "R²: —")

        if status == "ohmic":
            self.lbl_ohmic.setText("OHMIC")
            self.lbl_ohmic.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px; font-weight: 700; "
                f"padding: 6px 10px; background: {SUCCESS_BG}; border-radius: 6px; border: 1px solid {SUCCESS};"
            )
        elif status == "check_contacts":
            self.lbl_ohmic.setText("CHECK CONTACTS")
            self.lbl_ohmic.setStyleSheet(
                f"color: {WARNING}; font-size: 12px; font-weight: 700; "
                f"padding: 6px 10px; background: {WARNING_BG}; border-radius: 6px; border: 1px solid {WARNING};"
            )
        elif status == "non_ohmic":
            self.lbl_ohmic.setText("NON-OHMIC")
            self.lbl_ohmic.setStyleSheet(
                f"color: {ERROR}; font-size: 12px; font-weight: 700; "
                f"padding: 6px 10px; background: {ERROR_BG}; border-radius: 6px; border: 1px solid {ERROR};"
            )
        else:
            self.lbl_ohmic.setText("—")
            self.lbl_ohmic.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
                f"padding: 6px 10px; background: {CARD_BG}; border-radius: 6px; border: 1px solid {BORDER};"
            )

        self.lbl_T.setText(f"T: {T:.1f} °C" if T is not None else "T: —")

    def _fill_table(self):
        # Headers carry the chosen display units for current and voltage.
        self.table.setHorizontalHeaderLabels([
            f"Current ({self._i_unit})", f"Voltage ({self._v_unit})",
            "Resistance (Ω)", "Power (mW)",
            "Resistivity (Ω·cm)", "Conductivity (S/cm)",
        ])
        self.table.setRowCount(len(self._results))
        for row, pt in enumerate(self._results):
            def fmt(v):
                if v is None:
                    return "—"
                return f"{v:.6g}"

            i = pt.get("current")
            v = pt.get("voltage")
            r = pt.get("resistance")
            p_mw = (v * i * 1000) if (v is not None and i is not None) else None
            i_disp = i * self._i_scale if i is not None else None
            v_disp = v * self._v_scale if v is not None else None

            for col, val in enumerate([i_disp, v_disp, r, p_mw,
                                       pt.get("resistivity"), pt.get("conductivity")]):
                item = QTableWidgetItem(fmt(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

    def _on_error(self, msg: str):
        self.btn_run.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.lbl_status.setText("")
        QMessageBox.critical(
            self, "IV Sweep Error",
            f"The sweep failed:\n\n{msg}\n\n"
            "Check that all instruments are connected and try again."
        )

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
            QMessageBox.information(self, "Export", "No data to export. Run a sweep first.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save IV data", "iv_data.xlsx",
            "Excel workbook (*.xlsx);;CSV file (*.csv)",
        )
        if not path:
            return
        try:
            if selected_filter.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                self._write_csv(path)
                QMessageBox.information(self, "Export data", f"CSV saved to:\n{path}")
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                self._export_excel_with_graph(path)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

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

        # Fit summary block below the data
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
            QMessageBox.information(self, "Export data", f"Excel workbook saved to:\n{path}")
        except ImportError:
            wb.save(path)
            QMessageBox.warning(
                self, "Export data",
                "Excel file saved without the embedded graph.\n\n"
                "To include the graph, install Pillow:\n  pip install pillow",
            )

    def _save_graph(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save graph", "", "PNG (*.png)"
        )
        if not path:
            return
        try:
            pix = self.chart.grab()
            if pix.isNull():
                QMessageBox.warning(self, "Save graph", "Chart image is empty.")
                return
            pix.save(path, "PNG")
            QMessageBox.information(self, "Save graph", f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save graph", str(e))

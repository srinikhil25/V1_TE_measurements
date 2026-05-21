"""
I-V measurement page.

Left: sample info, sweep parameters (source mode, start/stop, points, bidirectional),
      compliance, dimensions, Run/Abort.
Right: live I-V chart (forward/reverse + fit), metric cards, results table, export.
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QDoubleSpinBox, QSpinBox, QSplitter,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLineEdit, QComboBox, QCheckBox, QGridLayout,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import pyqtgraph as pg

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


def _field(label: str, widget: QWidget, layout: QVBoxLayout):
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; border: none;")
    layout.addWidget(lbl)
    layout.addWidget(widget)
    layout.addSpacing(8)


def _spinbox(lo, hi, val, decimals=2, suffix="") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setDecimals(decimals)
    if suffix:
        sb.setSuffix(f"  {suffix}")
    sb.setFixedHeight(36)
    return sb


def _ispinbox(lo, hi, val) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setFixedHeight(36)
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
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #E5E7EB; }")

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

        # Sweep parameters
        card2 = _card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(16, 14, 16, 14)
        c2.setSpacing(0)
        c2.addWidget(_section_label("SWEEP PARAMETERS"))
        c2.addSpacing(10)

        self.cb_source_mode = QComboBox()
        self.cb_source_mode.addItems(["Current (4-probe)", "Voltage (2-probe)"])
        self.cb_source_mode.setFixedHeight(36)
        self.cb_source_mode.currentIndexChanged.connect(self._on_source_mode_changed)
        _field("Source mode", self.cb_source_mode, c2)

        self.sb_start = _spinbox(-1.0, 1.0, -0.01, 4, "A")
        self.sb_stop = _spinbox(-1.0, 1.0, 0.01, 4, "A")
        _field("Start (A or V)", self.sb_start, c2)
        _field("Stop (A or V)", self.sb_stop, c2)

        self.sb_points = _ispinbox(2, 500, 21)
        _field("Points", self.sb_points, c2)

        self.cb_bidirectional = QCheckBox("Bidirectional (forward + reverse)")
        self.cb_bidirectional.setChecked(False)
        self.cb_bidirectional.setStyleSheet(f"color: {TEXT_SECONDARY};")
        c2.addWidget(self.cb_bidirectional)
        c2.addSpacing(8)

        self.sb_delay = _spinbox(1, 5000, 50.0, 1, "ms")
        _field("Step delay", self.sb_delay, c2)

        self.sb_nplc = _spinbox(0.01, 10, 5.0, 2, "NPLC")
        _field("Integration (NPLC)", self.sb_nplc, c2)

        v.addWidget(card2)

        # Compliance
        card3 = _card()
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(16, 14, 16, 14)
        c3.setSpacing(0)
        c3.addWidget(_section_label("COMPLIANCE"))
        c3.addSpacing(10)
        self.sb_ilimit = _spinbox(1e-6, 1.0, 0.1, 4, "A")
        self.sb_vlimit = _spinbox(0.1, 21, 21.0, 1, "V")
        _field("Current limit", self.sb_ilimit, c3)
        _field("Voltage limit", self.sb_vlimit, c3)
        v.addWidget(card3)

        # Sample dimensions (mm)
        card4 = _card()
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(16, 14, 16, 14)
        c4.setSpacing(0)
        c4.addWidget(_section_label("SAMPLE DIMENSIONS  (optional)"))
        c4.addSpacing(10)
        self.sb_length_mm = _spinbox(0.001, 1000, 10.0, 3, "mm")
        self.sb_width_mm = _spinbox(0.001, 1000, 5.0, 3, "mm")
        self.sb_thickness_mm = _spinbox(0.001, 100, 1.0, 3, "mm")
        _field("Length", self.sb_length_mm, c4)
        _field("Width", self.sb_width_mm, c4)
        _field("Thickness", self.sb_thickness_mm, c4)
        v.addWidget(card4)

        # Run / Abort
        self.btn_run = QPushButton("▶  Run IV Sweep")
        self.btn_run.setFixedHeight(42)
        self.btn_run.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 7px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1D4ED8; }}"
            f"QPushButton:disabled {{ background: #93C5FD; }}"
        )
        self.btn_run.clicked.connect(self._run)
        v.addWidget(self.btn_run)

        self.btn_abort = QPushButton("⏹  Abort")
        self.btn_abort.setFixedHeight(42)
        self.btn_abort.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; border: none; "
            f"border-radius: 7px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #B91C1C; }}"
            f"QPushButton:disabled {{ background: #FCA5A5; }}"
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

    def _build_right(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        pg.setConfigOptions(antialias=True)

        self.chart = pg.PlotWidget()
        self.chart.setBackground("white")
        self.chart.setLabel("left", "Current", units="A")
        self.chart.setLabel("bottom", "Voltage", units="V")
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
        self.lbl_R2 = QLabel("R²: —")
        self.lbl_ohmic = QLabel("—")
        self.lbl_T = QLabel("T: —")
        for w in (self.lbl_R, self.lbl_rho, self.lbl_sigma, self.lbl_R2, self.lbl_ohmic, self.lbl_T):
            w.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
                f"padding: 6px 10px; background: {CARD_BG}; border-radius: 6px; "
                f"border: 1px solid {BORDER};"
            )
        cards_row.addWidget(self.lbl_R)
        cards_row.addWidget(self.lbl_rho)
        cards_row.addWidget(self.lbl_sigma)
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
             "Resistivity (Ω·m)", "Conductivity (S/m)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; font-size: 12px; }}"
            f"QTableWidget::item:alternate {{ background: #F9FAFB; }}"
        )
        v.addWidget(self.table, stretch=1)

        # Export
        export_row = QHBoxLayout()
        self.btn_export_csv = QPushButton("Save CSV…")
        self.btn_export_csv.setStyleSheet(
            f"QPushButton {{ background: {CARD_BG}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 14px; }}"
        )
        self.btn_export_csv.clicked.connect(self._export_csv)
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
        length_m = self.sb_length_mm.value() / 1000.0 if self.sb_length_mm.value() > 1e-6 else None
        width_m = self.sb_width_mm.value() / 1000.0 if self.sb_width_mm.value() > 1e-6 else None
        thickness_m = self.sb_thickness_mm.value() / 1000.0 if self.sb_thickness_mm.value() > 1e-6 else None

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
            length=length_m,
            width=width_m,
            thickness=thickness_m,
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
        n_fwd = self.sb_points.value()
        fwd_pts = [p for p in self._results[:n_fwd] if p.get("voltage") is not None and p.get("current") is not None]
        rev_pts = [p for p in self._results[n_fwd:] if p.get("voltage") is not None and p.get("current") is not None]
        if fwd_pts:
            self.scatter_fwd.setData(
                [p["voltage"] for p in fwd_pts],
                [p["current"] for p in fwd_pts],
                brush=pg.mkBrush(PRIMARY + "CC"),
            )
        if rev_pts:
            self.scatter_rev.setData(
                [p["voltage"] for p in rev_pts],
                [p["current"] for p in rev_pts],
                brush=pg.mkBrush(WARNING + "CC"),
            )
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

        xs = [p["voltage"] for p in self._results if p.get("voltage") is not None]
        ys = [p["current"] for p in self._results if p.get("current") is not None]
        if xs and ys:
            n_fwd = self.sb_points.value()
            if self.cb_bidirectional.isChecked():
                n_fwd = (self.sb_points.value() - 1) * 2 + 1
                fwd_x = xs[:self.sb_points.value()]
                fwd_y = ys[:self.sb_points.value()]
                rev_x = xs[self.sb_points.value():]
                rev_y = ys[self.sb_points.value():]
                self.scatter_fwd.setData(fwd_x, fwd_y, brush=pg.mkBrush(PRIMARY + "CC"))
                self.scatter_rev.setData(rev_x, rev_y, brush=pg.mkBrush(WARNING + "CC"))
            else:
                self.scatter_fwd.setData(xs, ys, brush=pg.mkBrush(PRIMARY + "CC"))
                self.scatter_rev.setData([], [])

            # Fit line V = R*I
            R = result.get("fit_R")
            if R is not None and abs(R) > 1e-12:
                I_min, I_max = min(ys), max(ys)
                I_fit = [I_min, I_max]
                V_fit = [R * i for i in I_fit]
                self.fit_line.setData(V_fit, I_fit)
            else:
                self.fit_line.setData([], [])
        else:
            self.fit_line.setData([], [])

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
        if self._results and R is not None:
            length_m = self.sb_length_mm.value() / 1000.0 if self.sb_length_mm.value() > 1e-6 else None
            width_m = self.sb_width_mm.value() / 1000.0 if self.sb_width_mm.value() > 1e-6 else None
            thickness_m = self.sb_thickness_mm.value() / 1000.0 if self.sb_thickness_mm.value() > 1e-6 else None
            if length_m and width_m and thickness_m:
                area = width_m * thickness_m
                if area > 0:
                    rho = R * area / length_m
                    sigma = 1.0 / rho if rho else None
        self.lbl_rho.setText(f"ρ: {rho:.4e} Ω·m" if rho is not None else "ρ: —")
        self.lbl_sigma.setText(f"σ: {sigma:.4e} S/m" if sigma is not None else "σ: —")
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
            rho = pt.get("resistivity")
            sigma = pt.get("conductivity")

            for col, val in enumerate([i, v, r, p_mw, rho, sigma]):
                item = QTableWidgetItem(fmt(val) if val is not None else "—")
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

    def _export_csv(self):
        if not self._results:
            QMessageBox.information(self, "Export", "No data to export. Run a sweep first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save IV data as CSV", "", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Current_A", "Voltage_V", "Resistance_Ohm", "Power_mW",
                            "Resistivity_Ohm_m", "Conductivity_S_m"])
                for pt in self._results:
                    i = pt.get("current")
                    v = pt.get("voltage")
                    r = pt.get("resistance")
                    p = (v * i * 1000) if (v is not None and i is not None) else None
                    w.writerow([
                        i if i is not None else "",
                        v if v is not None else "",
                        r if r is not None else "",
                        p if p is not None else "",
                        pt.get("resistivity") or "",
                        pt.get("conductivity") or "",
                    ])
            QMessageBox.information(self, "Export", f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

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

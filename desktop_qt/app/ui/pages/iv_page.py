"""
I-V Sweep page.

Left panel  — sweep parameters.
Right panel — I-V scatter chart + results table.
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QDoubleSpinBox, QSpinBox, QSplitter,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import pyqtgraph as pg

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ERROR, SUCCESS,
)


# ---------------------------------------------------------------------------
# Worker thread for the blocking IV sweep
# ---------------------------------------------------------------------------

class IVWorker(QThread):
    finished  = pyqtSignal(list)   # list of point dicts
    error     = pyqtSignal(str)

    def __init__(self, params: dict):
        super().__init__()
        self._params = params

    def run(self):
        try:
            from ...services.measurement_service import run_iv_sweep
            results = run_iv_sweep(**self._params)
            self.finished.emit(results)
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


def _field(label: str, widget: QWidget, layout: QVBoxLayout):
    lbl = QLabel(label)
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 12px; border: none;"
    )
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
# IV page
# ---------------------------------------------------------------------------

class IVPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._worker: Optional[IVWorker] = None
        self._results: List[Dict] = []
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
        splitter.setSizes([300, 860])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    # ── Left: parameters ────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setFixedWidth(300)

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(16)

        # Sweep parameters card
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(0)

        sec = QLabel("SWEEP PARAMETERS")
        sec.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; border: none;"
        )
        cl.addWidget(sec)
        cl.addSpacing(10)

        self.sb_start_v  = _spinbox(-21, 21, -1.0,  3, "V")
        self.sb_stop_v   = _spinbox(-21, 21,  1.0,  3, "V")
        self.sb_points   = _ispinbox(2, 500, 51)
        self.sb_delay    = _spinbox(1, 5000, 50.0,  1, "ms")
        self.sb_ilimit   = _spinbox(1e-6, 1.0, 0.1, 4, "A")
        self.sb_vlimit   = _spinbox(0.1, 21, 21.0,  1, "V")

        _field("Start voltage",    self.sb_start_v,  cl)
        _field("Stop voltage",     self.sb_stop_v,   cl)
        _field("Points",           self.sb_points,   cl)
        _field("Step delay",       self.sb_delay,    cl)
        _field("Current limit",    self.sb_ilimit,   cl)
        _field("Voltage limit",    self.sb_vlimit,   cl)

        v.addWidget(card)

        # Optional sample dimensions card
        dims_card = _card()
        dl = QVBoxLayout(dims_card)
        dl.setContentsMargins(16, 14, 16, 14)
        dl.setSpacing(0)

        dims_sec = QLabel("SAMPLE DIMENSIONS  (optional)")
        dims_sec.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; border: none;"
        )
        dl.addWidget(dims_sec)
        dl.addSpacing(10)

        self.sb_length    = _spinbox(1e-6, 1.0, 0.01,  4, "m")
        self.sb_width     = _spinbox(1e-6, 1.0, 0.005, 4, "m")
        self.sb_thickness = _spinbox(1e-6, 1.0, 0.001, 4, "m")

        _field("Length",    self.sb_length,    dl)
        _field("Width",     self.sb_width,     dl)
        _field("Thickness", self.sb_thickness, dl)

        v.addWidget(dims_card)

        # Run button
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

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; border: none;"
        )
        v.addWidget(self.lbl_status)
        v.addStretch()

        scroll.setWidget(panel)
        return scroll

    # ── Right: chart + table ─────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        pg.setConfigOptions(antialias=True)

        self.chart = pg.PlotWidget()
        self.chart.setBackground("white")
        self.chart.setLabel("left",   "Current", units="A")
        self.chart.setLabel("bottom", "Voltage", units="V")
        self.chart.setTitle("I-V Characteristic")
        self.chart.showGrid(x=True, y=True, alpha=0.3)
        self.chart.setMinimumHeight(300)
        self.scatter = pg.ScatterPlotItem(
            size=7, pen=pg.mkPen(None),
            brush=pg.mkBrush(PRIMARY + "CC"),
        )
        self.chart.addItem(self.scatter)
        v.addWidget(self.chart, stretch=2)

        # Results table
        table_label = QLabel("RESULTS")
        table_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; border: none;"
        )
        v.addWidget(table_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Voltage (V)", "Current (A)", "Resistance (Ω)",
             "Resistivity (Ω·m)", "Conductivity (S/m)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; font-size: 12px; }}"
            f"QTableWidget::item:alternate {{ background: #F9FAFB; }}"
        )
        v.addWidget(self.table, stretch=1)

        return panel

    # ------------------------------------------------------------------
    # Run / result handling
    # ------------------------------------------------------------------

    def _run(self):
        self.btn_run.setEnabled(False)
        self.lbl_status.setText("Running sweep…")
        self.scatter.clear()
        self.table.setRowCount(0)
        self._results.clear()

        params = dict(
            start_voltage = self.sb_start_v.value(),
            stop_voltage  = self.sb_stop_v.value(),
            points        = self.sb_points.value(),
            delay_ms      = self.sb_delay.value(),
            current_limit = self.sb_ilimit.value(),
            voltage_limit = self.sb_vlimit.value(),
            length        = self.sb_length.value()    if self.sb_length.value()    > 1e-10 else None,
            width         = self.sb_width.value()     if self.sb_width.value()     > 1e-10 else None,
            thickness     = self.sb_thickness.value() if self.sb_thickness.value() > 1e-10 else None,
        )

        self._worker = IVWorker(params)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, results: List[Dict]):
        self._results = results
        self.btn_run.setEnabled(True)
        self.lbl_status.setText(f"Done — {len(results)} points.")

        xs = [p["voltage"] for p in results if p.get("voltage") is not None]
        ys = [p["current"] for p in results if p.get("current") is not None]
        if xs and ys:
            self.scatter.setData(
                x=xs, y=ys,
                brush=pg.mkBrush(PRIMARY + "CC"),
            )

        self.table.setRowCount(len(results))
        for row, pt in enumerate(results):
            def fmt(v):
                if v is None:
                    return "—"
                return f"{v:.6g}"
            for col, key in enumerate(
                ["voltage", "current", "resistance", "resistivity", "conductivity"]
            ):
                item = QTableWidgetItem(fmt(pt.get(key)))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

    def _on_error(self, msg: str):
        self.btn_run.setEnabled(True)
        self.lbl_status.setText("")
        QMessageBox.critical(
            self, "IV Sweep Error",
            f"The sweep failed:\n\n{msg}\n\n"
            "Check that all instruments are connected and try again."
        )

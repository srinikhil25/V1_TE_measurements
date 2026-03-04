"""
Seebeck Measurement page.

Layout
──────
Left (min 440 px)    Sample info · Waveform diagram · IR camera · Start/Stop bar
Right (flex)         Phase badge
                     Chart 1 — TEMF (left axis) + T₁/T₂ (right axis) vs Time
                     Chart 2 — TEMF vs ΔT  (heating orange / cooling blue)
                     Chart 3 — S [µV/K] vs T₀ [K]
                     Metric cards
                     Data table  (scrollable, updates live)
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QScrollArea, QSplitter, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QTimer

import os
import tempfile

import pyqtgraph as pg
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY, PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_BG,
    ERROR, ERROR_BG,
)
from ..widgets.waveform_widget import SeebeckWaveformWidget
from ..widgets.ir_camera_widget import IrCameraWidget

# ---------------------------------------------------------------------------
# Phase badge colours  (bg, border/text colour, display label)
# ---------------------------------------------------------------------------
PHASE_STYLE = {
    "pre":          ("#FFF7ED", "#EA580C", "PRE-HEAT"),
    "ramp_up":      ("#EEF2FF", "#4F46E5", "RAMP UP"),
    "hold":         (SUCCESS_BG, SUCCESS,   "HOLD"),
    "ramp_down":    ("#FFF7ED", "#EA580C",  "RAMP DOWN"),
    "cooling_tail": ("#F0F9FF", "#0284C7",  "COOLING"),
    "idle":         ("#F8FAFC", TEXT_MUTED, "IDLE"),
    "finished":     (SUCCESS_BG, SUCCESS,   "FINISHED"),
    "error":        (ERROR_BG,  ERROR,      "ERROR"),
}

# Data-table column definitions  (data-dict key, display header, format string)
_TABLE_COLS: List[tuple] = [
    ("Time [s]",        "Time [s]",   "{:.1f}"),
    ("TEMF [mV]",       "TEMF [mV]",  "{:.3f}"),
    ("Temp1 [oC]",      "T₁ [°C]",   "{:.2f}"),
    ("Temp2 [oC]",      "T₂ [°C]",   "{:.2f}"),
    ("Delta Temp [oC]", "ΔT [°C]",   "{:.2f}"),
    ("delta_T_over_T0", "ΔT/T₀",     "{:.4f}"),
    ("T0 [oC]",         "T₀ [°C]",   "{:.2f}"),
    ("T0 [K]",          "T₀ [K]",    "{:.2f}"),
    ("S [µV/K]",        "S [µV/K]",  "{:.2f}"),
]

# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _section(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1.2px;"
    )
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
    return lbl


def _card(padding=(16, 14, 16, 16)) -> tuple:
    """Return (QFrame, inner QVBoxLayout)."""
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; }}"
    )
    v = QVBoxLayout(f)
    v.setContentsMargins(*padding)
    v.setSpacing(10)
    return f, v


def _row(label: str, widget: QWidget) -> QHBoxLayout:
    """Label (fixed width) + widget side by side."""
    h = QHBoxLayout()
    h.setSpacing(8)
    lbl = _field_label(label)
    lbl.setFixedWidth(130)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    h.addWidget(lbl)
    h.addWidget(widget)
    return h


# ---------------------------------------------------------------------------
# Metric card
# ---------------------------------------------------------------------------

class _MetricCard(QFrame):
    def __init__(self, title: str, unit: str):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px;"
        )

        self._val = QLabel("—")
        self._val.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 24px; font-weight: 700;"
        )

        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        v.addWidget(title_lbl)
        v.addWidget(self._val)
        v.addWidget(unit_lbl)

    def update(self, val: Optional[float], fmt: str = "{:.2f}"):
        self._val.setText("—" if val is None else fmt.format(val))


# ---------------------------------------------------------------------------
# Seebeck page
# ---------------------------------------------------------------------------

class SeebeckPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._data: List[Dict] = []
        self._analysis: List[Dict] = []
        self._table_row_count: int = 0
        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([480, 740])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

    # ── Left panel ──────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        container = QWidget()
        container.setMinimumWidth(440)
        container.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(18)

        # ── Sample info card ─────────────────────────────────────────────
        card, cl = _card()
        cl.addWidget(_section("Sample Info"))

        self.inp_sample = QLineEdit()
        self.inp_sample.setPlaceholderText("e.g. Bi2Te3-001")
        self.inp_sample.setFixedHeight(34)

        self.inp_operator = QLineEdit()
        self.inp_operator.setPlaceholderText("Your name")
        self.inp_operator.setFixedHeight(34)

        cl.addLayout(_row("Sample ID", self.inp_sample))
        cl.addLayout(_row("Operator",  self.inp_operator))
        v.addWidget(card)

        # ── Waveform diagram card ─────────────────────────────────────────
        wf_card, wf_cl = _card(padding=(10, 10, 10, 10))
        wf_cl.addWidget(_section("Measurement Parameters"))

        self.waveform = SeebeckWaveformWidget()
        self.waveform.setMinimumHeight(300)
        wf_cl.addWidget(self.waveform)
        v.addWidget(wf_card)

        # ── IR Camera card ────────────────────────────────────────────────
        self.ir_camera = IrCameraWidget()
        v.addWidget(self.ir_camera)

        v.addStretch()
        scroll.setWidget(panel)
        outer.addWidget(scroll, stretch=1)

        # ── Pinned Start / Stop bar ───────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setFixedHeight(60)
        btn_bar.setStyleSheet(
            f"background: white; border-top: 1px solid #E2E8F0;"
        )
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(14, 10, 14, 10)
        btn_layout.setSpacing(10)

        self.btn_start = QPushButton("Start")
        self.btn_start.setFixedHeight(38)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
            f"QPushButton:disabled {{ background: #BFDBFE; color: #93C5FD; }}"
        )
        self.btn_start.clicked.connect(self._start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #B91C1C; }}"
            f"QPushButton:disabled {{ background: #FCA5A5; color: #FECACA; }}"
        )
        self.btn_stop.clicked.connect(self._stop)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        outer.addWidget(btn_bar)

        return container

    # ── Right panel ─────────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        # Outer scroll area — lets the chart stack + table breathe freely
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        panel = QWidget()
        panel.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(18)

        # ── Phase badge + step label ─────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.phase_badge = QLabel("IDLE")
        self.phase_badge.setFixedHeight(28)
        self.phase_badge.setMinimumWidth(90)
        self.phase_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_phase("idle")

        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")

        top_row.addWidget(self.phase_badge)
        top_row.addWidget(self.lbl_step)
        top_row.addStretch()
        v.addLayout(top_row)

        # ── Export bar: graphs + data download ───────────────────────────
        export_row = QHBoxLayout()
        export_row.setSpacing(10)

        lbl_export = QLabel("Export:")
        lbl_export.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        self.btn_export_graphs = QPushButton("Download Graphs")
        self.btn_export_graphs.setFixedHeight(26)
        self.btn_export_graphs.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #F8FAFC; }"
            "QPushButton:disabled { color: #CBD5E1; border-color: #E2E8F0; }"
        )
        self.btn_export_graphs.clicked.connect(self._export_graphs)

        self.btn_export_data = QPushButton("Download Data")
        self.btn_export_data.setFixedHeight(26)
        self.btn_export_data.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #F8FAFC; }"
            "QPushButton:disabled { color: #CBD5E1; border-color: #E2E8F0; }"
        )
        self.btn_export_data.clicked.connect(self._export_data)

        export_row.addWidget(lbl_export)
        export_row.addWidget(self.btn_export_graphs)
        export_row.addWidget(self.btn_export_data)
        export_row.addStretch()
        v.addLayout(export_row)

        pg.setConfigOptions(antialias=True)

        # ── Chart 1: TEMF (left) + T₁/T₂ (right) vs Time  [dual Y-axis] ─
        v.addWidget(self._build_live_chart())

        # ── Chart 2: TEMF vs ΔT  (heating / cooling split) ───────────────
        self.chart_temf_dt = pg.PlotWidget()
        self._style_chart(self.chart_temf_dt, "TEMF (mV)", "ΔT (°C)")
        self.chart_temf_dt.setMenuEnabled(False)
        legend2 = self.chart_temf_dt.addLegend(offset=(10, 10))
        self.curve_heat = self.chart_temf_dt.plot(
            pen=pg.mkPen("#ED6C02", width=2), name="Heating"
        )
        self.curve_cool = self.chart_temf_dt.plot(
            pen=pg.mkPen("#2563EB", width=2), name="Cooling"
        )
        self.chart_temf_dt.setXRange(0, 10, padding=0)
        self.chart_temf_dt.setYRange(-5, 5, padding=0.05)
        v.addWidget(self.chart_temf_dt)

        # ── Chart 3: S [µV/K] vs T₀ [K] ────────────────────────────────
        self.chart_s_t0 = pg.PlotWidget()
        self._style_chart(self.chart_s_t0, "S (µV/K)", "T₀ (K)")
        self.chart_s_t0.setMenuEnabled(False)
        self.curve_s = self.chart_s_t0.plot(
            pen=pg.mkPen("#9C27B0", width=2),
            symbol="o", symbolSize=5,
            symbolBrush="#9C27B0", symbolPen=None,
        )
        self.chart_s_t0.setXRange(200, 600, padding=0)
        self.chart_s_t0.setYRange(-200, 200, padding=0.05)
        v.addWidget(self.chart_s_t0)

        # ── Metric cards ─────────────────────────────────────────────────
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.m_dt   = _MetricCard("ΔT",   "°C")
        self.m_t0   = _MetricCard("T₀",   "K")
        self.m_temf = _MetricCard("TEMF", "mV")
        self.m_s    = _MetricCard("S",    "µV/K")
        for m in (self.m_dt, self.m_t0, self.m_temf, self.m_s):
            metrics.addWidget(m)
        v.addLayout(metrics)

        # ── Data table ───────────────────────────────────────────────────
        v.addWidget(self._build_data_table())

        v.addStretch()
        scroll.setWidget(panel)
        return scroll

    # ── Chart builders ───────────────────────────────────────────────────

    def _build_live_chart(self) -> pg.PlotWidget:
        """Chart 1: TEMF [mV] on the left axis, T₁/T₂ [°C] on the right axis,
        both plotted against Time [s].  Uses a second ViewBox for the right axis."""
        chart = pg.PlotWidget()
        self._style_chart(chart, "TEMF (mV)", "Time (s)")
        chart.setMenuEnabled(False)

        pi = chart.getPlotItem()
        pi.showAxis("right")
        pi.setLabel("right", "Temperature (°C)")
        pi.getAxis("right").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))

        # Second ViewBox linked to the right axis
        self._vb_temp = pg.ViewBox()
        pi.scene().addItem(self._vb_temp)
        pi.getAxis("right").linkToView(self._vb_temp)
        self._vb_temp.setXLink(pi)

        # TEMF on the main (left) axis
        self.curve_temf = pi.plot(pen=pg.mkPen("#7C3AED", width=2))

        # T₁ / T₂ on the right ViewBox
        self.curve_t1 = pg.PlotCurveItem(pen=pg.mkPen("#2563EB", width=2))
        self.curve_t2 = pg.PlotCurveItem(pen=pg.mkPen("#DC2626", width=2))
        self._vb_temp.addItem(self.curve_t1)
        self._vb_temp.addItem(self.curve_t2)

        # Manual legend (ViewBox items aren't auto-registered)
        legend = pg.LegendItem(offset=(10, 10))
        legend.setParentItem(pi.graphicsItem())
        legend.addItem(self.curve_temf, "TEMF [mV]")
        legend.addItem(self.curve_t1,   "T₁ [°C]")
        legend.addItem(self.curve_t2,   "T₂ [°C]")

        # Keep right ViewBox geometry in sync with the main ViewBox
        def _sync_views():
            self._vb_temp.setGeometry(pi.vb.sceneBoundingRect())
            self._vb_temp.linkedViewChanged(pi.vb, self._vb_temp.XAxis)

        pi.vb.sigResized.connect(_sync_views)
        _sync_views()

        # Idle defaults
        chart.setXRange(0, 60, padding=0)
        chart.setYRange(-5, 5, padding=0.05)
        self._vb_temp.setYRange(0, 100, padding=0.05)

        self.chart_live = chart
        return chart

    def _build_data_table(self) -> QFrame:
        """Compact scrollable data table card."""
        card, cl = _card(padding=(10, 8, 10, 8))
        cl.setSpacing(6)
        cl.addWidget(_section("Data Table"))

        headers = [col[1] for col in _TABLE_COLS]
        self.tbl_data = QTableWidget(0, len(headers))
        self.tbl_data.setHorizontalHeaderLabels(headers)
        self.tbl_data.setMinimumHeight(300)
        self.tbl_data.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tbl_data.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_data.setAlternatingRowColors(True)
        self.tbl_data.verticalHeader().setVisible(False)
        self.tbl_data.verticalHeader().setDefaultSectionSize(22)
        self.tbl_data.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_data.horizontalHeader().setStretchLastSection(True)
        self.tbl_data.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.tbl_data.setStyleSheet(
            "QTableWidget { border: none; font-size: 11px; background: white; }"
            "QTableWidget::item { padding: 1px 4px; }"
        )
        cl.addWidget(self.tbl_data)
        return card

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _style_chart(chart: pg.PlotWidget, ylabel: str, xlabel: str):
        chart.setBackground("white")
        chart.showGrid(x=True, y=True, alpha=0.25)
        chart.setLabel("left",   ylabel)
        chart.setLabel("bottom", xlabel)
        chart.getAxis("left").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
        chart.getAxis("bottom").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
        chart.setFixedHeight(320)

    # ------------------------------------------------------------------ controls

    def _export_graphs(self):
        """Save the three charts as individual PNG files."""
        if not self._data:
            QMessageBox.information(self, "Export graphs", "No data available yet.")
            return

        base, _ = QFileDialog.getSaveFileName(
            self,
            "Save graphs (base filename)",
            "seebeck_graphs",
            "PNG images (*.png)",
        )
        if not base:
            return

        root, _ext = os.path.splitext(base)

        targets = [
            (self.chart_live,   f"{root}_live.png"),
            (self.chart_temf_dt, f"{root}_temf_vs_dt.png"),
            (self.chart_s_t0,   f"{root}_seebeck_vs_t0.png"),
        ]
        for widget, path in targets:
            pix = widget.grab()
            if not pix.isNull():
                pix.save(path, "PNG")

        QMessageBox.information(
            self,
            "Export graphs",
            "Graphs saved as:\n"
            + "\n".join(os.path.basename(p) for _, p in targets),
        )

    def _export_data(self):
        """Save data table as CSV or Excel (with embedded graphs)."""
        if not self._data:
            QMessageBox.information(self, "Export data", "No data available yet.")
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save data",
            "seebeck_data.xlsx",
            "Excel workbook (*.xlsx);;CSV file (*.csv)",
        )
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

    # ------------------------------------------------------------------ export helpers

    def _export_csv(self, path: str):
        """Write current data table to a CSV file."""
        import csv

        headers = [col[1] for col in _TABLE_COLS]
        keys    = [col[0] for col in _TABLE_COLS]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in self._data:
                writer.writerow(
                    [row.get(k, "") if row.get(k) is not None else "" for k in keys]
                )

        QMessageBox.information(self, "Export data", f"CSV saved to:\n{path}")

    def _export_excel_with_graphs(self, path: str):
        """Write data + three chart images into an Excel workbook."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"

        # Metadata / header block could be added here if needed.

        # Table header
        headers = [col[1] for col in _TABLE_COLS]
        keys    = [col[0] for col in _TABLE_COLS]
        ws.append(headers)
        for row in self._data:
            ws.append(
                [row.get(k, "") if row.get(k) is not None else "" for k in keys]
            )

        # Leave one empty row, then start placing images
        img_start_row = len(self._data) + 3

        tmpdir = tempfile.mkdtemp(prefix="seebeck_graphs_")
        files: list[tuple[str, int]] = []

        def _save_chart(widget: pg.PlotWidget, name: str, row_offset: int):
            pix = widget.grab()
            if pix.isNull():
                return
            file_path = os.path.join(tmpdir, name)
            pix.save(file_path, "PNG")
            img = XLImage(file_path)
            cell = f"A{img_start_row + row_offset}"
            ws.add_image(img, cell)
            files.append((file_path, img_start_row + row_offset))

        _save_chart(self.chart_live,    "chart_live.png", 0)
        _save_chart(self.chart_temf_dt, "chart_temf_dt.png", 20)
        _save_chart(self.chart_s_t0,    "chart_s_t0.png", 40)

        wb.save(path)

        # Best-effort cleanup of temp files
        for fp, _ in files:
            try:
                os.remove(fp)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

        QMessageBox.information(self, "Export data", f"Excel workbook saved to:\n{path}")
    def _start(self):
        from ...services.measurement_service import SeebeckService

        wp = self.waveform.get_params()
        if wp["start_volt"] >= wp["stop_volt"]:
            QMessageBox.warning(
                self, "Invalid Parameters",
                "I₀ (start current) must be less than I peak current."
            )
            return

        params = {
            **wp,
            "sample_id": self.inp_sample.text().strip() or None,
            "operator":  self.inp_operator.text().strip() or None,
        }

        if not SeebeckService().start(params):
            QMessageBox.critical(self, "Error", "Failed to start measurement.")
            return

        # Reset all charts and table
        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0

        self.curve_temf.setData([], [])
        self.curve_t1.setData([], [])
        self.curve_t2.setData([], [])
        self.curve_heat.setData([], [])
        self.curve_cool.setData([], [])
        self.curve_s.setData([], [])
        self.tbl_data.setRowCount(0)

        self.chart_live.enableAutoRange()
        self._vb_temp.enableAutoRange()
        self.chart_temf_dt.enableAutoRange()
        self.chart_s_t0.enableAutoRange()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._timer.start()

    def _stop(self):
        from ...services.measurement_service import SeebeckService
        SeebeckService().stop()
        self._timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._apply_phase("idle")
        self.lbl_step.setText("")

    # ------------------------------------------------------------------ polling

    def _poll(self):
        from ...services.measurement_service import SeebeckService
        svc = SeebeckService()
        status = svc.get_status()

        phase = status.get("phase") or "idle"
        if not svc.is_active():
            phase = "error" if "error" in status.get("status", "") else "finished"
            self._timer.stop()
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

        self._apply_phase(phase)

        step  = status.get("step", 0)
        total = status.get("total_steps", 0)
        self.lbl_step.setText(f"Step {step} / {total}" if total else "")

        new_data = svc.get_data()
        if len(new_data) > len(self._data):
            self._data = new_data
            self._refresh_charts()

        new_analysis = svc.get_analysis()
        if new_analysis and len(new_analysis) != len(self._analysis):
            self._analysis = new_analysis

    # ------------------------------------------------------------------ refresh

    def _refresh_charts(self):
        if not self._data:
            return

        nan = float("nan")

        def _v(lst):
            return [x if x is not None else nan for x in lst]

        times = [r.get("Time [s]", 0) for r in self._data]
        t1    = [r.get("Temp1 [oC]") for r in self._data]
        t2    = [r.get("Temp2 [oC]") for r in self._data]
        temf  = [r.get("TEMF [mV]")  for r in self._data]

        # ── Chart 1: live dual-axis ──────────────────────────────────────
        self.curve_temf.setData(times, _v(temf))
        self.curve_t1.setData(  times, _v(t1))
        self.curve_t2.setData(  times, _v(t2))

        # ── Chart 2: TEMF vs ΔT (heating / cooling split) ────────────────
        def _xy(rows, key_x, key_y):
            xs, ys = [], []
            for r in rows:
                x, y = r.get(key_x), r.get(key_y)
                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)
            return xs, ys

        heating = [r for r in self._data if r.get("branch") != "cooling"]
        cooling = [r for r in self._data if r.get("branch") == "cooling"]
        dt_h, tf_h = _xy(heating, "Delta Temp [oC]", "TEMF [mV]")
        dt_c, tf_c = _xy(cooling, "Delta Temp [oC]", "TEMF [mV]")
        self.curve_heat.setData(dt_h, tf_h)
        self.curve_cool.setData(dt_c, tf_c)

        # ── Chart 3: S vs T₀ ────────────────────────────────────────────
        s_pairs = [
            (r["T0 [K]"], r["S [µV/K]"])
            for r in self._data
            if r.get("T0 [K]") is not None and r.get("S [µV/K]") is not None
        ]
        if s_pairs:
            t0v, sv = zip(*s_pairs)
            self.curve_s.setData(list(t0v), list(sv))

        # ── Metric cards ─────────────────────────────────────────────────
        last = self._data[-1]
        self.m_dt.update(  last.get("Delta Temp [oC]"))
        self.m_t0.update(  last.get("T0 [K]"),      "{:.1f}")
        self.m_temf.update(last.get("TEMF [mV]"),   "{:.3f}")
        self.m_s.update(   last.get("S [µV/K]"),    "{:.1f}")

        # ── Data table — append only new rows ────────────────────────────
        new_count = len(self._data)
        if new_count > self._table_row_count:
            self.tbl_data.setRowCount(new_count)
            for i in range(self._table_row_count, new_count):
                row = self._data[i]
                for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                    val  = row.get(key)
                    text = "—" if val is None else fmt.format(val)
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.tbl_data.setItem(i, j, item)
            self._table_row_count = new_count
            self.tbl_data.scrollToBottom()

    def _apply_phase(self, phase: str):
        bg, color, label = PHASE_STYLE.get(
            phase, ("#F8FAFC", TEXT_MUTED, phase.upper())
        )
        self.phase_badge.setText(label)
        self.phase_badge.setStyleSheet(
            f"background: {bg}; color: {color}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 1px; "
            f"border: 1.5px solid {color}; border-radius: 12px; "
            f"padding: 0 12px;"
        )

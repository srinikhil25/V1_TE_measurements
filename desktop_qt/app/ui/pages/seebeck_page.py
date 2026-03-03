"""
Seebeck Measurement page.

Layout
──────
Left (min 440 px)    Sample info card · Waveform diagram · Start / Stop bar
Right (flex)         Phase badge · Temperature chart · TEMF chart · metric row
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QScrollArea, QSplitter, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer

import pyqtgraph as pg

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY, PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_BG, WARNING, WARNING_BG,
    ERROR, ERROR_BG, SIDEBAR_BG,
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
        """
        Returns a container with:
          - a scrollable form area (sample info + waveform diagram)
          - Start / Stop buttons pinned at the bottom, always visible
        """
        container = QWidget()
        container.setMinimumWidth(440)
        container.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Scrollable form ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 10)
        v.setSpacing(14)

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

        # ── Pinned Start / Stop bar (always visible) ─────────────────────
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
        panel = QWidget()
        panel.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        # Phase badge + step label
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

        # ── Charts ──────────────────────────────────────────────────────
        pg.setConfigOptions(antialias=True)

        # Temperature chart
        self.chart_temp = pg.PlotWidget()
        self._style_chart(self.chart_temp, "Temperature (°C)", "Time (s)")
        self.chart_temp.setMenuEnabled(False)
        legend = self.chart_temp.addLegend(offset=(10, 10))
        self.curve_t1 = self.chart_temp.plot(
            pen=pg.mkPen("#2563EB", width=2), name="T₁"
        )
        self.curve_t2 = self.chart_temp.plot(
            pen=pg.mkPen("#DC2626", width=2), name="T₂"
        )
        # Disable auto-range — set sensible idle defaults
        self.chart_temp.setXRange(0, 60, padding=0)
        self.chart_temp.setYRange(0, 100, padding=0.05)
        v.addWidget(self.chart_temp, stretch=3)

        # TEMF chart
        self.chart_temf = pg.PlotWidget()
        self._style_chart(self.chart_temf, "TEMF (mV)", "Time (s)")
        self.chart_temf.setMenuEnabled(False)
        self.curve_temf = self.chart_temf.plot(
            pen=pg.mkPen("#7C3AED", width=2)
        )
        self.chart_temf.setXRange(0, 60, padding=0)
        self.chart_temf.setYRange(-5, 5, padding=0.05)
        v.addWidget(self.chart_temf, stretch=2)

        # ── Metric cards ────────────────────────────────────────────────
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.m_dt   = _MetricCard("ΔT",   "°C")
        self.m_t0   = _MetricCard("T₀",   "K")
        self.m_temf = _MetricCard("TEMF", "mV")
        self.m_s    = _MetricCard("S",    "µV/K")
        for m in (self.m_dt, self.m_t0, self.m_temf, self.m_s):
            metrics.addWidget(m)
        v.addLayout(metrics)

        return panel

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _style_chart(chart: pg.PlotWidget, ylabel: str, xlabel: str):
        chart.setBackground("white")
        chart.showGrid(x=True, y=True, alpha=0.25)
        chart.setLabel("left",   ylabel)
        chart.setLabel("bottom", xlabel)
        chart.getAxis("left").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
        chart.getAxis("bottom").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
        chart.setMinimumHeight(180)

    # ------------------------------------------------------------------ controls

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

        # Reset charts to auto-range once real data arrives
        self._data.clear()
        self.curve_t1.setData([], [])
        self.curve_t2.setData([], [])
        self.curve_temf.setData([], [])
        self.chart_temp.enableAutoRange()
        self.chart_temf.enableAutoRange()

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

    def _refresh_charts(self):
        if not self._data:
            return
        times = [r.get("Time [s]", 0)   for r in self._data]
        t1    = [r.get("Temp1 [oC]")    for r in self._data]
        t2    = [r.get("Temp2 [oC]")    for r in self._data]
        temf  = [r.get("TEMF [mV]")     for r in self._data]

        nan = float("nan")
        self.curve_t1.setData(  times, [v if v is not None else nan for v in t1])
        self.curve_t2.setData(  times, [v if v is not None else nan for v in t2])
        self.curve_temf.setData(times, [v if v is not None else nan for v in temf])

        last = self._data[-1]
        self.m_dt.update(  last.get("Delta Temp [oC]"))
        self.m_t0.update(  last.get("T0 [K]"),  "{:.1f}")
        self.m_temf.update(last.get("TEMF [mV]"), "{:.3f}")
        self.m_s.update(   last.get("S [µV/K]"), "{:.1f}")

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

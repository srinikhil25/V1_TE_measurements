"""
Seebeck Measurement page — cockpit layout.

Top: phase bar (geometry chooser · Start/Stop/Reset · segmented progress).
Below: a 4-column grid of tiles —
    Params (on-graph waveform + sample/cooling)  |  G1 live chart  |  IR camera
                                                 |  G2 · G3        |
                                                 |  Data table     |
Every tile has an enlarge button that expands it to fill the whole grid.
"""

from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QGridLayout, QMessageBox, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QDoubleSpinBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, QSize

import os
import tempfile

import pyqtgraph as pg
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY, PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_BG, ERROR, ERROR_BG,
)
from ..icons import icon as _icon
from ..widgets.measurement_setup_dialog import MeasurementSetupDialog
from ..widgets.ir_camera_widget import IrCameraWidget
from ..widgets.tile import Tile

# ---------------------------------------------------------------------------
# Phase badge colours  (bg, border/text colour, display label)
# ---------------------------------------------------------------------------
PHASE_STYLE = {
    "pre":          ("#FFF7ED", "#EA580C", "PRE-HEAT"),
    "ramp_up":      ("#EEF2FF", "#4F46E5", "POWER UP"),
    "hold":         (SUCCESS_BG, SUCCESS,   "HOLD"),
    "ramp_down":    ("#FFF7ED", "#EA580C",  "POWER DOWN"),
    "cooling_tail": ("#F0F9FF", "#0284C7",  "COOLING"),
    "idle":         ("#FBFAF5", TEXT_MUTED, "IDLE"),
    "finished":     (SUCCESS_BG, SUCCESS,   "FINISHED"),
    "error":        (ERROR_BG,  ERROR,      "ERROR"),
}

# Segmented progress: (phase key, display label). Order matters.
_SEGMENTS = [
    ("pre",          "PRE"),
    ("ramp_up",      "INC RATE"),
    ("hold",         "HOLD"),
    ("ramp_down",    "DEC RATE"),
    ("cooling_tail", "COOLING"),
]

# Data-table column definitions  (data-dict key, display header, format string)
_TABLE_COLS: List[tuple] = [
    ("Time [s]",        "Time [s]",  "{:.1f}"),
    ("TEMF [mV]",       "TEMF [mV]", "{:.3f}"),
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


# ---------------------------------------------------------------------------
# Seebeck page
# ---------------------------------------------------------------------------

class SeebeckPage(QWidget):

    # Default heater profile (used until the operator configures one via the
    # New Measurement dialog).
    _DEFAULT_PROFILE = {
        "interval": 2, "pre_time": 5, "hold_time": 600,
        "start_volt": 0.0, "stop_volt": 1.0,
        "inc_rate": 1.0, "dec_rate": 1.0, "pk160_current_unit": "mA",
    }

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._data: List[Dict] = []
        self._analysis: List[Dict] = []
        self._table_row_count: int = 0

        # Heater profile is now configured in a fixed-size dialog (New
        # Measurement), not an always-on tile. The page holds the last config.
        self._profile_params: Dict = dict(self._DEFAULT_PROFILE)
        self._cooling_target: float = 5.0

        self._tiles: Dict[str, Tile] = {}
        self._grid_positions: Dict[str, tuple] = {}
        self._enlarged: Optional[Tile] = None

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)

        self._build_ui()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        root.addWidget(self._build_phase_bar())

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(14)
        self._build_tiles()
        self._layout_grid_normal()
        root.addWidget(self._grid_host, 1)

    # ------------------------------------------------------------------
    # Phase bar
    # ------------------------------------------------------------------

    def _build_phase_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("card")
        bar.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 10px; }}"
        )
        v = QVBoxLayout(bar)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(12)

        # ── Top row: badge + step info  ·····  geometry + buttons ────────
        top = QHBoxLayout()
        top.setSpacing(12)

        self.phase_badge = QLabel("IDLE")
        self.phase_badge.setFixedHeight(26)
        self.phase_badge.setMinimumWidth(96)
        self.phase_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_phase("idle")
        top.addWidget(self.phase_badge)

        info_box = QWidget()
        info = QVBoxLayout(info_box)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        info.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_phase_name = QLabel("Ready")
        self.lbl_phase_name.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600;"
        )
        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11.5px;")
        self.lbl_step.setVisible(False)   # only shown when there's step text
        info.addWidget(self.lbl_phase_name)
        info.addWidget(self.lbl_step)
        top.addWidget(info_box, 0, Qt.AlignmentFlag.AlignVCenter)

        # New Measurement — the primary action. Solid, prominent.
        self.btn_new = QPushButton("＋  New Measurement")
        self.btn_new.setFixedHeight(38)
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 8px; padding: 0 22px; font-size: 13.5px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
        )
        self.btn_new.setIcon(_icon("plus", "#FFFFFF", 16, width=2.4))
        self.btn_new.setIconSize(QSize(16, 16))
        self.btn_new.setText("New Measurement")
        self.btn_new.clicked.connect(self._new_measurement)   # ← was missing
        top.addSpacing(10)
        top.addWidget(self.btn_new)
        top.addStretch()

        # Sample ID (operator is taken automatically from the logged-in user)
        sample_box = QVBoxLayout()
        sample_box.setSpacing(3)
        sample_lbl = QLabel("Sample ID")
        sample_lbl.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT_MUTED}; "
            f"font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
        )
        self.inp_sample = QLineEdit()
        self.inp_sample.setPlaceholderText("e.g. Bi2Te3-001")
        self.inp_sample.setFixedHeight(34)
        self.inp_sample.setFixedWidth(190)
        sample_box.addWidget(sample_lbl)
        sample_box.addWidget(self.inp_sample)
        top.addLayout(sample_box)
        top.addSpacing(6)

        # Geometry chooser
        self.btn_inplane = QPushButton("In-Plane")
        self.btn_outplane = QPushButton("Out-Plane")
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for b in (self.btn_inplane, self.btn_outplane):
            b.setCheckable(True)
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self._mode_group.addButton(b)
            b.toggled.connect(self._update_mode_styles)
        self.btn_inplane.setChecked(True)
        geo_box = QFrame()
        geo_box.setStyleSheet(
            f"background: #EFECE4; border: 1px solid {BORDER}; border-radius: 8px;"
        )
        geo_l = QHBoxLayout(geo_box)
        geo_l.setContentsMargins(3, 3, 3, 3)
        geo_l.setSpacing(3)
        geo_l.addWidget(self.btn_inplane)
        geo_l.addWidget(self.btn_outplane)
        top.addWidget(geo_box)
        self._update_mode_styles()

        # Start / Stop / Reset
        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 16px; }}"
            f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
            f"QPushButton:disabled {{ background: #BBD3D6; color: #8FB6BA; }}"
        )
        self.btn_start.clicked.connect(self._start)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; border: none; "
            f"border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 16px; }}"
            f"QPushButton:hover {{ background: #883333; }}"
        )
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setVisible(False)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedHeight(36)
        self.btn_reset.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT_SECONDARY}; "
            f"border: 1.5px solid {BORDER}; border-radius: 8px; "
            f"font-size: 13px; font-weight: 600; padding: 0 16px; }}"
            f"QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
        )
        self.btn_reset.clicked.connect(self._reset)

        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_reset)
        v.addLayout(top)

        # ── Segments row ─────────────────────────────────────────────────
        seg_row = QHBoxLayout()
        seg_row.setSpacing(6)
        self._seg_labels: Dict[str, QLabel] = {}
        stretches = {"pre": 1, "ramp_up": 2, "hold": 3, "ramp_down": 2, "cooling_tail": 1}
        for key, label in _SEGMENTS:
            seg = QLabel(label)
            seg.setFixedHeight(28)
            seg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._seg_labels[key] = seg
            seg_row.addWidget(seg, stretches[key])
        v.addLayout(seg_row)
        self._update_segments("idle")

        return bar

    # ------------------------------------------------------------------
    # Tiles
    # ------------------------------------------------------------------

    def _build_tiles(self):
        self._tiles["g1"] = self._make_live_chart_tile()
        self._tiles["g2"] = self._make_temf_dt_tile()
        self._tiles["g3"] = self._make_s_t0_tile()
        self._tiles["data"] = self._make_data_tile()
        self._tiles["ir"] = self._make_ir_tile()

        for t in self._tiles.values():
            t.enlarge_clicked.connect(self._toggle_enlarge)

        # (row, col, rowspan, colspan) in the 3-col grid.
        #   G1 live chart (wide top) | IR (full height right)
        #   G2 · G3                  |
        #   Data (wide bottom)       |
        self._grid_positions = {
            "g1":   (0, 0, 1, 2),
            "g2":   (1, 0, 1, 1),
            "g3":   (1, 1, 1, 1),
            "data": (2, 0, 1, 2),
            "ir":   (0, 2, 3, 1),
        }

    def _make_live_chart_tile(self) -> Tile:
        tile = Tile("g1", "TEMF · T₁ / T₂  vs  Time", badge="G1")
        btn = self._chart_export_btn(lambda: self._export_single_chart(self.chart_live, "live"))
        tile.add_action(btn)
        pg.setConfigOptions(antialias=True)
        tile.body_layout.setContentsMargins(8, 8, 10, 8)
        tile.body_layout.addWidget(self._build_live_chart())
        return tile

    def _make_temf_dt_tile(self) -> Tile:
        tile = Tile("g2", "TEMF  vs  ΔT", badge="G2")
        btn = self._chart_export_btn(lambda: self._export_single_chart(self.chart_temf_dt, "temf_vs_dt"))
        tile.add_action(btn)

        self.chart_temf_dt = pg.PlotWidget()
        self._style_chart(self.chart_temf_dt, "TEMF (mV)", "ΔT (°C)")
        self.chart_temf_dt.setMenuEnabled(False)
        self.curve_heat = self.chart_temf_dt.plot(pen=pg.mkPen("#ED6C02", width=2))
        self.curve_cool = self.chart_temf_dt.plot(pen=pg.mkPen("#2563EB", width=2))
        legend = self._legend_strip([
            ("#ED6C02", "Heating"),
            ("#2563EB", "Cooling"),
        ])
        tile.body_layout.setContentsMargins(8, 8, 10, 8)
        tile.body_layout.addWidget(self._wrap_with_legend(legend, self.chart_temf_dt))
        return tile

    def _make_s_t0_tile(self) -> Tile:
        tile = Tile("g3", "S  vs  T₀", badge="G3")
        btn = self._chart_export_btn(lambda: self._export_single_chart(self.chart_s_t0, "seebeck_vs_t0"))
        tile.add_action(btn)

        self.chart_s_t0 = pg.PlotWidget()
        self._style_chart(self.chart_s_t0, "S (µV/K)", "T₀ (K)")
        self.chart_s_t0.setMenuEnabled(False)
        self.curve_s = self.chart_s_t0.plot(
            pen=pg.mkPen("#9C27B0", width=2),
            symbol="o", symbolSize=5, symbolBrush="#9C27B0", symbolPen=None,
        )
        tile.body_layout.setContentsMargins(8, 8, 10, 8)
        tile.body_layout.addWidget(self.chart_s_t0)
        return tile

    def _make_data_tile(self) -> Tile:
        tile = Tile("data", "Live Data Table", badge="Data")

        btn_graphs = self._mini_btn("Save Graphs…")
        btn_graphs.clicked.connect(self._export_graphs)
        btn_data = self._mini_btn("Save Data…", primary=True)
        btn_data.clicked.connect(self._export_data)
        tile.add_action(btn_graphs)
        tile.add_action(btn_data)

        headers = [c[1] for c in _TABLE_COLS]
        self.tbl_data = QTableWidget(0, len(headers))
        self.tbl_data.setHorizontalHeaderLabels(headers)
        self.tbl_data.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_data.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_data.setAlternatingRowColors(True)
        self.tbl_data.verticalHeader().setVisible(False)
        self.tbl_data.verticalHeader().setDefaultSectionSize(22)
        self.tbl_data.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tbl_data.horizontalHeader().setMinimumSectionSize(40)
        self.tbl_data.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_data.setStyleSheet(
            "QTableWidget { border: none; font-size: 11px; background: white; }"
            "QTableWidget::item { padding: 1px 4px; }"
        )
        tile.body_layout.addWidget(self.tbl_data)
        self._set_table_full(False)   # compact: hide secondary columns
        return tile

    # Secondary columns shown only when the Data tile is enlarged
    # (ΔT/T₀ · T₀[°C] · T₀[K]). Compact view keeps the 7 most-watched columns.
    _SECONDARY_COLS = (5, 6, 7)

    def _set_table_full(self, full: bool):
        for col in self._SECONDARY_COLS:
            self.tbl_data.setColumnHidden(col, not full)

    def _make_ir_tile(self) -> Tile:
        tile = Tile("ir", "Thermal Camera", badge="IR")
        self.ir_camera = IrCameraWidget()
        # The widget already draws its own card border; strip the duplicate.
        self.ir_camera.setStyleSheet("QFrame#card { background: transparent; border: none; }")
        tile.body_layout.setContentsMargins(6, 6, 6, 6)
        tile.body_layout.addWidget(self.ir_camera)
        return tile

    # ------------------------------------------------------------------
    # Small widget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(4)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11.5px; font-weight: 500;")
        box.addWidget(lbl)
        box.addWidget(widget)
        return box

    @staticmethod
    def _mini_btn(text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(26)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            b.setStyleSheet(
                f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
                f"border-radius: 5px; padding: 2px 10px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
            )
        else:
            b.setStyleSheet(
                f"QPushButton {{ background: white; color: {TEXT_SECONDARY}; "
                f"border: 1px solid {BORDER}; border-radius: 5px; padding: 2px 10px; "
                f"font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ color: {PRIMARY}; border-color: {PRIMARY}; }}"
            )
        return b

    def _chart_export_btn(self, slot) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(26, 26)
        b.setToolTip("Export PNG")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(_icon("download", TEXT_MUTED, 15))
        b.setIconSize(QSize(15, 15))
        b.setStyleSheet(
            f"QPushButton {{ background: white; "
            f"border: 1px solid {BORDER}; border-radius: 5px; }}"
            f"QPushButton:hover {{ border-color: {PRIMARY}; }}"
        )
        b.clicked.connect(slot)
        return b

    # ------------------------------------------------------------------
    # Chart builders
    # ------------------------------------------------------------------

    def _build_live_chart(self) -> pg.PlotWidget:
        chart = pg.PlotWidget()
        # Swapped per request: Temperature on the LEFT axis, TEMF on the RIGHT.
        self._style_chart(chart, "Temperature (°C)", "Time (s)")
        chart.setMenuEnabled(False)

        pi = chart.getPlotItem()
        pi.setContentsMargins(10, 10, 10, 10)          # breathing room around the plot
        pi.showAxis("right")
        pi.setLabel("right", "TEMF (mV)")
        pi.getAxis("right").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9), tickTextOffset=6)
        pi.getAxis("left").setStyle(tickTextOffset=6)

        # Secondary view box carries TEMF against the right axis.
        self._vb_temf = pg.ViewBox()
        pi.scene().addItem(self._vb_temf)
        pi.getAxis("right").linkToView(self._vb_temf)
        self._vb_temf.setXLink(pi)

        # Colours: TEMF green, T₁ red, T₂ blue.
        self.curve_t1 = pi.plot(pen=pg.mkPen("#DC2626", width=2))    # T₁ red (left axis)
        self.curve_t2 = pi.plot(pen=pg.mkPen("#2563EB", width=2))    # T₂ blue (left axis)
        self.curve_temf = pg.PlotCurveItem(pen=pg.mkPen("#2CA02C", width=2))  # TEMF green (right)
        self._vb_temf.addItem(self.curve_temf)

        def _sync_views():
            self._vb_temf.setGeometry(pi.vb.sceneBoundingRect())
            self._vb_temf.linkedViewChanged(pi.vb, self._vb_temf.XAxis)

        pi.vb.sigResized.connect(_sync_views)
        _sync_views()

        chart.setXRange(0, 60, padding=0)
        chart.setYRange(0, 100, padding=0.05)          # left = Temperature
        self._vb_temf.setYRange(-5, 5, padding=0.05)   # right = TEMF

        self.chart_live = chart

        # Legend as a strip ABOVE the plot, off the data area (no overlap).
        legend_row = self._legend_strip([
            ("#2CA02C", "TEMF [mV]"),
            ("#DC2626", "T₁ [°C]"),
            ("#2563EB", "T₂ [°C]"),
        ])
        return self._wrap_with_legend(legend_row, chart)

    @staticmethod
    def _style_chart(chart: pg.PlotWidget, ylabel: str, xlabel: str):
        chart.setBackground("white")
        chart.showGrid(x=True, y=True, alpha=0.25)
        chart.setLabel("left", ylabel)
        chart.setLabel("bottom", xlabel)
        chart.getAxis("left").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
        chart.getAxis("bottom").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))

    @staticmethod
    def _legend_strip(items) -> QWidget:
        """Horizontal legend ABOVE a chart, off the plot area. items: (color, text)."""
        row = QWidget()
        lr = QHBoxLayout(row)
        lr.setContentsMargins(10, 2, 10, 4)
        lr.setSpacing(22)
        for color, text in items:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            sw = QFrame()
            sw.setFixedSize(18, 4)
            sw.setStyleSheet(f"background:{color}; border:none; border-radius:2px;")
            lb = QLabel(text)
            lb.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px; border:none;")
            h.addWidget(sw)
            h.addWidget(lb)
            lr.addWidget(w)
        lr.addStretch()
        return row

    @staticmethod
    def _wrap_with_legend(legend: QWidget, chart: QWidget) -> QWidget:
        container = QWidget()
        cv = QVBoxLayout(container)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(2)
        cv.addWidget(legend)
        cv.addWidget(chart, stretch=1)
        return container

    # ==================================================================
    # Enlarge / restore
    # ==================================================================

    def _layout_grid_normal(self):
        for name, tile in self._tiles.items():
            self._grid.removeWidget(tile)
            tile.setVisible(True)
            r, c, rs, cs = self._grid_positions[name]
            self._grid.addWidget(tile, r, c, rs, cs)

        # 3 columns: two flexible (charts/data), one fixed-ish for the IR view.
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnStretch(2, 0)
        self._grid.setColumnMinimumWidth(0, 0)
        self._grid.setColumnMinimumWidth(1, 0)
        self._grid.setColumnMinimumWidth(2, 380)
        self._grid.setRowStretch(0, 23)
        self._grid.setRowStretch(1, 20)
        self._grid.setRowStretch(2, 20)

    def _toggle_enlarge(self, tile: Tile):
        if self._enlarged is tile:
            self._restore()
        else:
            if self._enlarged is not None:
                self._restore()
            self._enlarge(tile)

    def _enlarge(self, tile: Tile):
        for name, t in self._tiles.items():
            self._grid.removeWidget(t)
            t.setVisible(t is tile)
        for c in range(3):
            self._grid.setColumnStretch(c, 1 if c == 0 else 0)
            self._grid.setColumnMinimumWidth(c, 0)
        for r in range(3):
            self._grid.setRowStretch(r, 1 if r == 0 else 0)
        self._grid.addWidget(tile, 0, 0, 1, 1)
        tile.set_enlarged(True)
        self._enlarged = tile
        # Data tile: reveal the full column set when enlarged.
        if tile is self._tiles.get("data"):
            self._set_table_full(True)

    def _restore(self):
        if self._enlarged is not None:
            self._enlarged.set_enlarged(False)
            self._enlarged = None
        self._set_table_full(False)
        self._layout_grid_normal()

    # ==================================================================
    # Geometry chooser
    # ==================================================================

    _MODE_CHECKED = (
        f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
        f"border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 14px; }}"
        f"QPushButton:disabled {{ background: #BBD3D6; color: #DCE9FB; }}"
    )
    _MODE_UNCHECKED = (
        f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
        f"border: none; border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 14px; }}"
        f"QPushButton:hover {{ color: {PRIMARY}; }}"
        f"QPushButton:disabled {{ color: #C7C0B0; }}"
    )

    # Per-geometry current cap (amperes): In-Plane 1.0 A · Out-Plane 1.3 A
    CURRENT_CAP_A = {"in_plane": 1.0, "out_plane": 1.3}

    def _current_mode(self) -> str:
        return "in_plane" if self.btn_inplane.isChecked() else "out_plane"

    def _update_mode_styles(self):
        for b in (self.btn_inplane, self.btn_outplane):
            b.setStyleSheet(self._MODE_CHECKED if b.isChecked() else self._MODE_UNCHECKED)

    def _set_mode_enabled(self, enabled: bool):
        self.btn_inplane.setEnabled(enabled)
        self.btn_outplane.setEnabled(enabled)

    # ==================================================================
    # Button-bar state
    # ==================================================================

    def _show_running_buttons(self):
        self.btn_reset.setVisible(False)
        self.btn_stop.setVisible(True)

    def _show_idle_buttons(self):
        self.btn_stop.setVisible(False)
        self.btn_reset.setVisible(True)

    # ==================================================================
    # Start / Stop / Reset
    # ==================================================================

    def _new_measurement(self):
        """Guard unsaved results, then open the fixed-size profile setup dialog."""
        import logging, traceback
        log = logging.getLogger("seebeck.new")
        log.info(">>> New Measurement clicked")
        try:
            from ...services.measurement_service import SeebeckService
            log.info("checking active run…")
            if SeebeckService().is_active():
                log.info("run active — blocking")
                QMessageBox.warning(
                    self, "Measurement running",
                    "A measurement is in progress. Stop it before starting a new one."
                )
                return

            # If there are results on screen, offer to export before discarding.
            log.info("data rows on screen: %d", len(self._data))
            if self._data:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Question)
                box.setWindowTitle("Start new measurement")
                box.setText("You have measurement results on screen.")
                box.setInformativeText("Save the data before starting a new run?")
                save_btn = box.addButton("Save…", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Discard & New", QMessageBox.ButtonRole.DestructiveRole)
                cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                clicked = box.clickedButton()
                if clicked is cancel_btn:
                    return
                if clicked is save_btn:
                    self._export_data()

            log.info("constructing MeasurementSetupDialog…")
            win = self.window()
            dlg = MeasurementSetupDialog(
                self._profile_params, self._cooling_target,
                self.CURRENT_CAP_A[self._current_mode()], win,
            )
            log.info("dialog constructed; centering + showing")
            geo = dlg.frameGeometry()
            geo.moveCenter(win.frameGeometry().center())
            dlg.move(geo.topLeft())
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            log.info("calling dialog.exec()")
            result = dlg.exec()
            log.info("dialog.exec() returned: %s", result)

            if result:
                self._profile_params = dlg.get_profile_params()
                self._cooling_target = dlg.get_cooling_target()
                self._clear_results()
                log.info("profile applied: %s", self._profile_params)
        except Exception as e:
            log.critical("New Measurement FAILED: %s\n%s", e, traceback.format_exc())
            try:
                QMessageBox.critical(self, "New Measurement",
                                     f"Setup failed:\n{e}")
            except Exception:
                pass

    def _clear_results(self):
        """Wipe the on-screen data, charts and table for a fresh run."""
        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0
        for curve in (
            self.curve_temf, self.curve_t1, self.curve_t2,
            self.curve_heat, self.curve_cool, self.curve_s,
        ):
            curve.setData([], [])
        self.tbl_data.setRowCount(0)
        self._apply_phase("idle")
        self.lbl_phase_name.setText("Ready")
        self.lbl_step.setText("")
        self.lbl_step.setVisible(False)
        self._update_segments("idle")

    def _start(self):
        from ...services.measurement_service import SeebeckService

        wp = self._profile_params
        if wp["start_volt"] >= wp["stop_volt"]:
            QMessageBox.warning(
                self, "Invalid Parameters",
                "I₀ (start current) must be less than I peak current.\n"
                "Click 'New Measurement' to fix the heater profile."
            )
            return

        params = {
            **wp,
            "sample_id": self.inp_sample.text().strip() or None,
            "operator":  getattr(self._user, "username", None),
            "probe_mode": self._current_mode(),
            "cooling_target_delta_t": self._cooling_target,
        }

        if not SeebeckService().start(params):
            QMessageBox.critical(self, "Error", "Failed to start measurement.")
            return

        # Reset charts and table
        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0
        for curve in (
            self.curve_temf, self.curve_t1, self.curve_t2,
            self.curve_heat, self.curve_cool, self.curve_s,
        ):
            curve.setData([], [])
        self.tbl_data.setRowCount(0)
        self.chart_live.enableAutoRange()
        self._vb_temf.enableAutoRange()
        self.chart_temf_dt.enableAutoRange()
        self.chart_s_t0.enableAutoRange()

        self.btn_start.setEnabled(False)
        self._show_running_buttons()
        self._set_mode_enabled(False)
        self._timer.start()

    def _stop(self):
        from ...services.measurement_service import SeebeckService
        SeebeckService().stop()
        self._timer.stop()
        self.btn_start.setEnabled(True)
        self._show_idle_buttons()
        self._set_mode_enabled(True)
        self._apply_phase("idle")
        self.lbl_phase_name.setText("Ready")
        self.lbl_step.setText("")
        self.lbl_step.setVisible(False)
        self._update_segments("idle")

    def _reset(self):
        from ...services.measurement_service import SeebeckService
        self._timer.stop()
        SeebeckService().reset()

        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0
        for curve in (
            self.curve_temf, self.curve_t1, self.curve_t2,
            self.curve_heat, self.curve_cool, self.curve_s,
        ):
            curve.setData([], [])
        self.tbl_data.setRowCount(0)

        self._apply_phase("idle")
        self.lbl_phase_name.setText("Ready")
        self.lbl_step.setText("")
        self.lbl_step.setVisible(False)
        self._update_segments("idle")
        self.btn_start.setEnabled(True)
        self._show_idle_buttons()
        self._set_mode_enabled(True)

    # ==================================================================
    # Polling
    # ==================================================================

    def _poll(self):
        from ...services.measurement_service import SeebeckService
        svc = SeebeckService()
        status = svc.get_status()

        phase = status.get("phase") or "idle"
        if not svc.is_active():
            phase = "error" if "error" in status.get("status", "") else "finished"
            self._timer.stop()
            self.btn_start.setEnabled(True)
            self._show_idle_buttons()
            self._set_mode_enabled(True)

        self._apply_phase(phase)
        self._update_segments(phase)

        bg, color, label = PHASE_STYLE.get(phase, ("#FBFAF5", TEXT_MUTED, phase.upper()))
        self.lbl_phase_name.setText(label.title())

        step = status.get("step", 0)
        total = status.get("total_steps", 0)
        remaining = status.get("estimated_remaining_s")
        parts = []
        if total:
            parts.append(f"step {step} / {total}")
        if remaining is not None:
            parts.append(f"remaining {int(remaining)//60:02d}:{int(remaining)%60:02d}")
        text = "  ·  ".join(parts)
        self.lbl_step.setText(text)
        self.lbl_step.setVisible(bool(text))

        new_data = svc.get_data()
        if len(new_data) > len(self._data):
            self._data = new_data
            self._refresh_charts()

        new_analysis = svc.get_analysis()
        if new_analysis and len(new_analysis) != len(self._analysis):
            self._analysis = new_analysis

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_charts(self):
        if not self._data:
            return
        nan = float("nan")

        def _v(lst):
            return [x if x is not None else nan for x in lst]

        times = [r.get("Time [s]", 0) for r in self._data]
        t1 = [r.get("Temp1 [oC]") for r in self._data]
        t2 = [r.get("Temp2 [oC]") for r in self._data]
        temf = [r.get("TEMF [mV]") for r in self._data]

        self.curve_temf.setData(times, _v(temf))
        self.curve_t1.setData(times, _v(t1))
        self.curve_t2.setData(times, _v(t2))

        def _xy(rows, kx, ky):
            xs, ys = [], []
            for r in rows:
                x, y = r.get(kx), r.get(ky)
                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)
            return xs, ys

        heating = [r for r in self._data if r.get("branch") != "cooling"]
        cooling = [r for r in self._data if r.get("branch") == "cooling"]
        # Make cooling continue from the heating peak: prepend the last heating
        # point so the cooling line starts where heating ended (at max ΔT) and
        # traces back down, instead of detaching and starting from the left.
        if heating and cooling:
            cooling = [heating[-1]] + cooling
        dt_h, tf_h = _xy(heating, "Delta Temp [oC]", "TEMF [mV]")
        dt_c, tf_c = _xy(cooling, "Delta Temp [oC]", "TEMF [mV]")
        self.curve_heat.setData(dt_h, tf_h)
        self.curve_cool.setData(dt_c, tf_c)

        s_pairs = [
            (r["T0 [K]"], r["S [µV/K]"])
            for r in self._data
            if r.get("T0 [K]") is not None and r.get("S [µV/K]") is not None
        ]
        if s_pairs:
            t0v, sv = zip(*s_pairs)
            self.curve_s.setData(list(t0v), list(sv))

        # Data table — append only new rows
        new_count = len(self._data)
        if new_count > self._table_row_count:
            self.tbl_data.setRowCount(new_count)
            for i in range(self._table_row_count, new_count):
                row = self._data[i]
                for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                    val = row.get(key)
                    text = "—" if val is None else fmt.format(val)
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.tbl_data.setItem(i, j, item)
            self._table_row_count = new_count
            self.tbl_data.scrollToBottom()

    # ------------------------------------------------------------------
    # Phase badge + segments
    # ------------------------------------------------------------------

    def _apply_phase(self, phase: str):
        bg, color, label = PHASE_STYLE.get(phase, ("#FBFAF5", TEXT_MUTED, phase.upper()))
        self.phase_badge.setText(label)
        self.phase_badge.setStyleSheet(
            f"background: {bg}; color: {color}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; border: 1.5px solid {color}; border-radius: 13px; "
            f"padding: 0 12px;"
        )

    def _update_segments(self, phase: str):
        keys = [k for k, _ in _SEGMENTS]
        cur_idx = keys.index(phase) if phase in keys else -1
        for i, key in enumerate(keys):
            seg = self._seg_labels[key]
            if cur_idx == -1:
                # idle / finished / error → neutral
                seg.setStyleSheet(self._seg_style("idle"))
            elif i < cur_idx:
                seg.setStyleSheet(self._seg_style("done"))
            elif i == cur_idx:
                seg.setStyleSheet(self._seg_style("current"))
            else:
                seg.setStyleSheet(self._seg_style("idle"))

    @staticmethod
    def _seg_style(state: str) -> str:
        base = ("font-size: 10px; font-weight: 700; letter-spacing: 1px; "
                "border-radius: 6px; padding: 0 6px;")
        if state == "current":
            return (f"{base} background: white; color: {PRIMARY}; "
                    f"border: 1.5px solid {PRIMARY};")
        if state == "done":
            return f"{base} background: #E6EEEC; color: {PRIMARY}; border: 1px solid #C9DEE0;"
        return f"{base} background: #EFECE4; color: {TEXT_MUTED}; border: 1px solid {BORDER};"

    # ==================================================================
    # Export
    # ==================================================================

    def _export_single_chart(self, widget: pg.PlotWidget, suffix: str):
        if not self._data:
            QMessageBox.information(self, "Export", "No data available yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart", f"seebeck_{suffix}.png", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pix = widget.grab()
        if not pix.isNull():
            pix.save(path, "PNG")
            QMessageBox.information(self, "Export", f"Chart saved to:\n{path}")

    def _export_graphs(self):
        if not self._data:
            QMessageBox.information(self, "Export graphs", "No data available yet.")
            return
        base, _ = QFileDialog.getSaveFileName(
            self, "Save graphs (base filename)", "seebeck_graphs", "PNG images (*.png)"
        )
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
            self, "Export graphs",
            "Graphs saved as:\n" + "\n".join(os.path.basename(p) for _, p in targets),
        )

    def _export_data(self):
        if not self._data:
            QMessageBox.information(self, "Export data", "No data available yet.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save data", "seebeck_data.xlsx",
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

    def _export_csv(self, path: str):
        import csv
        headers = [c[1] for c in _TABLE_COLS]
        keys = [c[0] for c in _TABLE_COLS]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in self._data:
                writer.writerow(
                    [row.get(k, "") if row.get(k) is not None else "" for k in keys]
                )
        QMessageBox.information(self, "Export data", f"CSV saved to:\n{path}")

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
            QMessageBox.information(self, "Export data", f"Excel workbook saved to:\n{path}")
        except ImportError:
            wb.save(path)
            QMessageBox.warning(
                self, "Export data",
                "Excel file saved without embedded graphs.\n\n"
                "To include graphs, install Pillow:\n  pip install pillow",
            )

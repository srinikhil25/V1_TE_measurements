"""
Seebeck measurement — live run cockpit.

Phase bar : run state · phase · progress line · sample · geometry · Start / Stop
            and one box per phase, as wide as its share of the run
Readouts  : T₁ · T₂ · ΔT · T₀ · TEMF · S · heater · ΔT/T₀
Left      : heater profile, edited on the diagram · cooling target · safety
Middle    : T/TEMF vs time · TEMF vs ΔT · S vs T₀ · data (readings / bins / log)
Right     : thermal camera with regions — R1 (and R2) are recorded with
            every reading (toggle from the phase bar)

Every tile can be enlarged to fill the page body.
"""

from __future__ import annotations

import time
from typing import ClassVar, Dict, List, Optional, Sequence

import pyqtgraph as pg
from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...services.run_export import RunTable, info_lines, seebeck_table
from .. import theme as T
from ..widgets.export_ui import save_data, save_graphs
from ..widgets.ir_panel import IrPanel
from ..widgets.plot_data import ColumnBuffer, fast_time_curve, thin
from ..widgets.tile import Tile, icon_button
from ..widgets.ui_kit import (
    Callout,
    Chip,
    KeyValueList,
    LegendStrip,
    Panel,
    Readout,
    ReadoutGrid,
    Segmented,
    bin_n_text,
    button,
    cell,
    field,
    label,
    make_table,
    pen,
    set_field_error,
    style_plot,
)
from ..widgets.waveform_widget import SeebeckWaveformWidget, fmt_duration, profile_duration_s

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
    ("IR R1 [oC]",      "IR R1 [°C]", "{:.2f}"),
    ("IR R2 [oC]",      "IR R2 [°C]", "{:.2f}"),
]
# Camera columns exist only in runs recorded with the camera on.
_CAMERA_KEYS = ("IR R1 [oC]", "IR R2 [oC]")


def table_cols(rows: Sequence[dict]) -> List[tuple]:
    """_TABLE_COLS without the camera columns that no row has."""
    return [c for c in _TABLE_COLS
            if c[0] not in _CAMERA_KEYS or any(c[0] in r for r in rows)]


_GEOMETRY = (("in_plane", "In-plane"), ("out_plane", "Out-of-plane"))

_IR_TRACE = T.SUCCESS                   # camera R1 on the time chart


# ─────────────────────────────────────────────────────────────────────────────
# Phase bar
# ─────────────────────────────────────────────────────────────────────────────
class PhaseSegments(QWidget):
    """One box per run phase, as wide as its share of the run. Done phases are
    tinted, the current one is outlined and fills as it progresses."""

    def __init__(self, names: Sequence[str]):
        super().__init__()
        self._names = list(names)
        self._weights = [1.0] * len(self._names)
        self._current = -1
        self._progress = 0.0
        self._all_done = False
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_weights(self, weights: Sequence[float]) -> None:
        total = sum(weights) or 1.0
        # Every box keeps room for its name.
        self._weights = [max(w / total, 0.1) for w in weights]
        self.update()

    def set_state(self, current: int, progress: float = 0.0, all_done: bool = False) -> None:
        self._current, self._all_done = current, all_done
        self._progress = min(max(progress, 0.0), 1.0)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(T.ui_family())
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        p.setFont(f)
        gap = 6
        free = self.width() - gap * (len(self._names) - 1)
        total = sum(self._weights)
        x = 0.0
        for i, name in enumerate(self._names):
            w = free * self._weights[i] / total
            r = QRectF(x + 0.5, 0.5, w - 1, self.height() - 1)
            done = self._all_done or (self._current >= 0 and i < self._current)
            cur = i == self._current and not self._all_done
            if done:
                p.setPen(QPen(QColor(T.ACCENT_SOFT), 1))
                p.setBrush(QBrush(QColor(T.ACCENT_SOFT)))
                p.drawRoundedRect(r, 5, 5)
                color = T.ACCENT_TEXT
            elif cur:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(T.SURFACE)))
                p.drawRoundedRect(r, 5, 5)
                if self._progress > 0:
                    p.setBrush(QBrush(QColor(T.ACCENT_SOFT)))
                    p.drawRoundedRect(QRectF(r.left(), r.top(), r.width() * self._progress,
                                             r.height()), 5, 5)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(T.ACCENT), 1.6))
                p.drawRoundedRect(r, 5, 5)
                color = T.ACCENT_TEXT
            else:
                p.setPen(QPen(QColor(T.BORDER_SUBTLE), 1))
                p.setBrush(QBrush(QColor(T.SURFACE_ALT)))
                p.drawRoundedRect(r, 5, 5)
                color = T.TEXT_MUTED
            p.setPen(QColor(color))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, name.upper())
            x += w + gap


class PhaseBar(QFrame):
    """Top of the page: run state, phase, progress and the run controls."""

    def __init__(self):
        super().__init__()
        self.setProperty("panel", True)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.chip = Chip("READY", "neutral")
        top.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_lbl = label("Ready", "h1")
        self.subtitle_lbl = label("", "secondary")
        for lbl in (self.title_lbl, self.subtitle_lbl):     # long text is cut, never widens the page
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.subtitle_lbl.setProperty("mono", True)
        col.addWidget(self.title_lbl)
        col.addWidget(self.subtitle_lbl)
        top.addLayout(col, 1)
        self.fields = QHBoxLayout()
        self.fields.setSpacing(12)
        top.addLayout(self.fields)
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(8)
        top.addLayout(self.actions_row)
        v.addLayout(top)
        self.segments = PhaseSegments([s for _k, s in _SEGMENTS])
        v.addWidget(self.segments)

    def add_field(self, w: QWidget) -> None:
        self.fields.addWidget(w, 0, Qt.AlignmentFlag.AlignBottom)

    def add_action(self, w: QWidget) -> None:
        self.actions_row.addWidget(w, 0, Qt.AlignmentFlag.AlignBottom)

    def set_title(self, text: str) -> None:
        self.title_lbl.setText(text)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_lbl.setText(text)


class CameraTile(Tile):
    """The camera column: _SIDE_W wide when there is room, but never the reason
    the page cannot get narrower (it folds away below _FOLD_WIDTH instead)."""

    def sizeHint(self):
        return QSize(SeebeckPage._SIDE_W, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────
class SeebeckPage(QWidget):

    # Default heater profile (used until the operator edits it).
    _DEFAULT_PROFILE: ClassVar[dict] = {
        "interval": 2, "pre_time": 5, "hold_time": 600,
        "start_volt": 0.0, "stop_volt": 1.0,
        "inc_rate": 1.0, "dec_rate": 1.0, "pk160_current_unit": "mA",
    }

    # Per-geometry current cap (amperes): In-Plane 1.0 A · Out-Plane 1.3 A
    DEFAULT_CURRENT_CAP_A: ClassVar[dict] = {"in_plane": 1.0, "out_plane": 1.3}

    # Secondary columns shown only when the data tile is enlarged
    # (ΔT/T₀ · T₀[°C] · T₀[K]).
    _SECONDARY_COLS = (5, 6, 7)

    # Below this page width the camera column folds away.
    _FOLD_WIDTH = 1180
    _PARAMS_W = 364                     # the profile editor needs 340 px
    _SIDE_W = 352

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._data: List[Dict] = []
        self._analysis: List[Dict] = []
        self._table_row_count: int = 0
        # Chart series, filled incrementally from self._data (UI-2). The rows
        # in self._data stay complete; only what is drawn is reduced.
        self._buf_time = ColumnBuffer(5)    # t, T1, T2, TEMF, camera R1
        self._buf_heat = ColumnBuffer(2)    # ΔT, TEMF (heating branch)
        self._buf_cool = ColumnBuffer(2)    # ΔT, TEMF (cooling branch)
        self._buf_s = ColumnBuffer(2)       # T0, S
        self._rows_charted = 0
        self._camera_cols: set = set()      # camera columns shown in the table
        self._profile_params: Dict = dict(self._DEFAULT_PROFILE)
        self._cooling_target: float = 5.0
        self._tiles: Dict[str, Tile] = {}
        self._grid_positions: Dict[str, tuple] = {}
        self._enlarged: Optional[Tile] = None
        self._last_phase: Optional[str] = None
        self._last_invalid = 0
        self._last_db_warning = None
        self._last_instr_err = ""
        self._polarity_logged = False
        self._run_id = None
        self._auto_hid_side = False

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)

        self.current_cap_a = dict(self.DEFAULT_CURRENT_CAP_A)
        try:
            from ...core.config import get_config
            h = get_config().heater
            self.current_cap_a = {"in_plane": h.in_plane.current_max_A,
                                  "out_plane": h.out_plane.current_max_A}
        except Exception:
            pass

        pg.setConfigOptions(antialias=True)
        self._build_ui()
        self._on_geometry_changed(0)
        self._apply_phase("idle")
        self._log("Ready. Set the sample ID and heater profile, then press Start.")

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        self.setObjectName("Page")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QWidget()
        body.setObjectName("PageBody")
        root.addWidget(body, 1)
        v = QVBoxLayout(body)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)

        v.addWidget(self._build_phase_bar())
        # Why the last run ended early — stays until the next run (UI-6).
        self.end_box = Callout("", "danger")
        self.end_box.setVisible(False)
        v.addWidget(self.end_box)
        v.addWidget(self._build_readouts())

        row = QHBoxLayout()
        row.setSpacing(12)
        self.params_col = self._build_params()
        row.addWidget(self.params_col, 0)
        self.middle = self._build_middle()
        row.addWidget(self.middle, 1)
        self.side = self._build_camera()
        row.addWidget(self.side, 0)
        v.addLayout(row, 1)

    # ── Phase bar ─────────────────────────────────────────────────────
    def _build_phase_bar(self) -> QWidget:
        tb = PhaseBar()
        self.toolbar = tb
        self.segments = tb.segments

        self.inp_sample = QLineEdit()
        self.inp_sample.setPlaceholderText("e.g. Bi2Te3-001")
        self.inp_sample.setMinimumWidth(170)
        self.f_sample = field("Sample ID", self.inp_sample, required=True)
        self.inp_sample.textChanged.connect(lambda _t: set_field_error(self.f_sample))
        tb.add_field(self.f_sample)
        self.seg_geometry = Segmented([g[1] for g in _GEOMETRY])
        self.seg_geometry.currentIndexChanged.connect(self._on_geometry_changed)
        tb.add_field(field("Geometry", self.seg_geometry))

        self.btn_side = button("", "ghost", icon="camera", checkable=True,
                               tooltip="Show / hide the thermal camera column")
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
        for b in (self.btn_side, self.btn_reset, self.btn_start, self.btn_stop):
            tb.add_action(b)
        return tb

    # ── Readouts ──────────────────────────────────────────────────────
    def _build_readouts(self) -> QWidget:
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
                                    "per T₀ bin is in the Data tile."),
            "heat": Readout("Heater", "V"),
            "grad": Readout("ΔT / T₀", "%",
                            tooltip="Large gradients (> 10 %) make S less accurate."),
        }
        self.readouts = ReadoutGrid(list(self.ro.values()), len(self.ro))
        return self.readouts

    # ── Left: heater profile ──────────────────────────────────────────
    def _build_params(self) -> QWidget:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setFixedWidth(self._PARAMS_W)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(12)

        prof = Panel("Heater profile")
        self.panel_profile = prof
        self.editor = SeebeckWaveformWidget()
        self.editor.setMinimumSize(340, 300)
        self.editor.set_params(self._profile_params)
        self._profile_params = self.editor.get_params()
        self.editor.params_changed.connect(self._on_profile_edited)
        prof.body.setContentsMargins(8, 8, 8, 12)
        prof.body.addWidget(self.editor)
        self.lbl_profile_err = label("", "caption", wrap=True, tone="danger")
        self.lbl_profile_err.setVisible(False)
        prof.body.addWidget(self.lbl_profile_err)
        self.lbl_profile_lock = label("Locked while the run is in progress.", "caption")
        self.lbl_profile_lock.setVisible(False)
        prof.body.addWidget(self.lbl_profile_lock)

        self.sb_cooling = QDoubleSpinBox()
        self.sb_cooling.setRange(0.1, 100.0)
        self.sb_cooling.setDecimals(1)
        self.sb_cooling.setValue(self._cooling_target)
        self.sb_cooling.setSuffix("  K")
        self.sb_cooling.setProperty("mono", True)
        self.sb_cooling.valueChanged.connect(self._on_cooling_changed)
        prof.body.addWidget(field(
            "Cooling target |ΔT|", self.sb_cooling,
            "The cooling tail ends when |ΔT| falls below this, or at the timeout."))
        self.lbl_geom_hint = label("", "caption", wrap=True)
        prof.body.addWidget(self.lbl_geom_hint)
        v.addWidget(prof)

        safe = Panel("Safety limits")
        self.kv_safety = KeyValueList(mono_values=True, key_width=120)
        safe.body.addWidget(self.kv_safety)
        safe.body.addWidget(label("The heater is switched off when one is exceeded. "
                                  "Change them in Settings.", "caption", wrap=True))
        v.addWidget(safe)
        v.addStretch(1)
        self._refresh_safety_panel()

        sa.setWidget(host)
        return sa

    # ── Middle: charts and data ───────────────────────────────────────
    def _build_middle(self) -> QWidget:
        host = QWidget()
        self._grid = QGridLayout(host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        self._tiles["g1"] = self._make_live_chart_tile()
        self._tiles["g2"] = self._make_temf_dt_tile()
        self._tiles["g3"] = self._make_s_t0_tile()
        self._tiles["data"] = self._make_data_tile()
        for key in ("g1", "g2", "g3", "data"):
            self._tiles[key].enlarge_clicked.connect(self._toggle_enlarge)
        # (row, col, rowspan, colspan) in the 2-column middle grid
        self._grid_positions = {
            "g1":   (0, 0, 1, 2),
            "g2":   (1, 0, 1, 1),
            "g3":   (1, 1, 1, 1),
            "data": (2, 0, 1, 2),
        }
        self._layout_grid_normal()
        return host

    # ── Right: thermal camera ─────────────────────────────────────────
    def _build_camera(self) -> QWidget:
        tile = CameraTile("ir", "Thermal camera")
        self.ir_panel = IrPanel()
        self.ir_panel.regions_changed.connect(self._log)
        tile.body_layout.addWidget(self.ir_panel)
        tile.enlarge_clicked.connect(self._toggle_enlarge)
        tile.setMaximumWidth(self._SIDE_W)
        self._tiles["ir"] = tile
        return tile

    def _set_side_visible(self, on: bool):
        self.side.setVisible(on and (self._enlarged is None or self._enlarged is self.side))
        self._auto_hid_side = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_side_column()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_side_column()

    def _fit_side_column(self):
        # Narrow window: fold the camera column away so the charts keep their width.
        narrow = self.width() < self._FOLD_WIDTH
        if narrow and not self.side.isHidden() and self.btn_side.isChecked() \
                and self._enlarged is None:
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

    _DATA_TABS = ("Readings", "S by T₀", "Log")

    def _make_data_tile(self) -> Tile:
        tile = Tile("data", "Data")
        self.tabs_data = Segmented(list(self._DATA_TABS))
        self.tabs_data.currentIndexChanged.connect(self._on_data_tab)
        tile.add_action(self.tabs_data)
        self.tabs_data.button(1).setToolTip(
            "Seebeck coefficient by T₀ bin: linear fit of TEMF vs ΔT within each 10 K bin of T₀.")
        self._log_unread = False
        tile.add_action(icon_button("image", "Save the three graphs as PNG…", self._export_graphs))
        tile.add_action(icon_button("download", "Save data (Excel / CSV)…", self._export_data))

        self.data_stack = QStackedWidget()
        headers = [c[1] for c in _TABLE_COLS]
        self.tbl_data = make_table(headers, row_height=24, mono=True)
        self.tbl_data.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hh = self.tbl_data.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(64)
        self.tbl_data.setSelectionMode(self.tbl_data.SelectionMode.ExtendedSelection)
        self.data_stack.addWidget(self.tbl_data)

        self.tbl_bins = make_table(["T₀ [K]", "S [µV/K]", "± [µV/K]", "n"], row_height=26)
        self.tbl_bins.setProperty("mono", True)
        self.tbl_bins.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.data_stack.addWidget(self.tbl_bins)

        self.lst_log = QListWidget()
        self.lst_log.setProperty("flat", True)
        self.lst_log.setWordWrap(True)
        self.lst_log.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.data_stack.addWidget(self.lst_log)

        tile.body_layout.addWidget(self.data_stack)
        self._set_table_full(False)
        self._update_camera_columns()
        return tile

    def _on_data_tab(self, i: int):
        self.data_stack.setCurrentIndex(i)
        if i == 2:
            self._log_unread = False
            self._set_tab_labels()

    def _set_tab_labels(self):
        """Bin count on the Data tabs; a dot on Log while a warning is unread.
        (The number of readings is in the phase bar.)"""
        n_bins = len(self._analysis)
        names = (self._DATA_TABS[0],
                 f"{self._DATA_TABS[1]} · {n_bins}" if n_bins else self._DATA_TABS[1],
                 f"{self._DATA_TABS[2]} ●" if self._log_unread else self._DATA_TABS[2])
        for i, name in enumerate(names):
            self.tabs_data.button(i).setText(name)

    def _set_table_full(self, full: bool):
        for col in self._SECONDARY_COLS:
            self.tbl_data.setColumnHidden(col, not full)

    def _update_camera_columns(self):
        keys = [k for k, _h, _f in _TABLE_COLS]
        for k in _CAMERA_KEYS:
            self.tbl_data.setColumnHidden(keys.index(k), k not in self._camera_cols)

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
        self.curve_ir = fast_time_curve(pi.plot(pen=pen(_IR_TRACE, 1.4)))
        self.curve_temf = pg.PlotDataItem(pen=pen(T.SERIES_TEMF, 1.6, dashed=True))
        self._vb_temf.addItem(self.curve_temf)
        fast_time_curve(self.curve_temf)  # only once it is inside its ViewBox

        def _sync_views():
            self._vb_temf.setGeometry(pi.vb.sceneBoundingRect())
            self._vb_temf.linkedViewChanged(pi.vb, self._vb_temf.XAxis)

        pi.vb.sigResized.connect(_sync_views)
        _sync_views()

        pi.getViewBox().setXRange(0, 60, padding=0)
        pi.getViewBox().setYRange(0, 100, padding=0.05)
        self._vb_temf.setYRange(-5, 5, padding=0.05)
        self.chart_live = chart

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(LegendStrip([(T.SERIES_T1, "T₁ [°C]"), (T.SERIES_T2, "T₂ [°C]"),
                                 (_IR_TRACE, "Camera R1 [°C]"),
                                 (T.SERIES_TEMF, "TEMF [mV] · right axis")],
                                kinds=["line", "line", "line", "dash"]))
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
        self._grid.setRowStretch(2, 20)

    def _toggle_enlarge(self, tile: Tile):
        if self._enlarged is tile:
            self._restore()
        else:
            if self._enlarged is not None:
                self._restore()
            self._enlarge(tile)

    def _enlarge(self, tile: Tile):
        """The tile takes the whole body: the other columns step aside."""
        self.params_col.setVisible(False)
        if tile is self.side:
            self.middle.setVisible(False)
            self.side.setMaximumWidth(16_777_215)
            self.side.setVisible(True)
        else:
            self.side.setVisible(False)
            for name in ("g1", "g2", "g3", "data"):
                t = self._tiles[name]
                self._grid.removeWidget(t)
                t.setVisible(t is tile)
            for c in range(2):
                self._grid.setColumnStretch(c, 1 if c == 0 else 0)
            for r in range(3):
                self._grid.setRowStretch(r, 1 if r == 0 else 0)
            self._grid.addWidget(tile, 0, 0, 1, 1)
            if tile is self._tiles.get("data"):
                self._set_table_full(True)
        tile.set_enlarged(True)
        self._enlarged = tile

    def _restore(self):
        if self._enlarged is not None:
            self._enlarged.set_enlarged(False)
            self._enlarged = None
        self._set_table_full(False)
        self._layout_grid_normal()
        self.side.setMaximumWidth(self._SIDE_W)
        self.params_col.setVisible(True)
        self.middle.setVisible(True)
        self.side.setVisible(self.btn_side.isChecked())

    # ==================================================================
    # Setup
    # ==================================================================

    def _current_mode(self) -> str:
        return _GEOMETRY[max(self.seg_geometry.currentIndex(), 0)][0]

    def _on_geometry_changed(self, _idx: int):
        mode = self._current_mode()
        cap = self.current_cap_a.get(mode)
        self.editor.set_max_current_A(cap)      # clamps I₀ / I peak to the cap
        self.lbl_geom_hint.setText(
            f"Heater current is limited to {cap:g} A in this geometry." if cap is not None else "")
        self.ir_panel.set_geometry(mode)        # camera regions are kept per geometry
        self._on_profile_edited()

    def _on_profile_edited(self):
        self._profile_params = self.editor.get_params()
        self.lbl_profile_err.setVisible(False)
        self._refresh_profile_summary()

    def _on_cooling_changed(self, value: float):
        self._cooling_target = float(value)
        self._refresh_profile_summary()

    def _profile_durations(self) -> List[float]:
        """Seconds per phase (pre · up · hold · down), and a share for cooling."""
        p = self._profile_params
        di = max(float(p["stop_volt"]) - float(p["start_volt"]), 0.0)
        heat = [float(p["pre_time"]), di / max(float(p["inc_rate"]), 1e-9),
                float(p["hold_time"]), di / max(float(p["dec_rate"]), 1e-9)]
        return heat + [0.25 * sum(heat)]

    def _refresh_profile_summary(self):
        p = self._profile_params
        self.panel_profile.set_subtitle(
            f"≈ {fmt_duration(profile_duration_s(p))} + cooling · "
            f"a reading every {int(p['interval'])} s")
        self.segments.set_weights(self._profile_durations())
        if not self._timer.isActive() and self._last_phase in (None, "idle"):
            self._apply_phase("idle")

    def _set_mode_enabled(self, enabled: bool):
        self.seg_geometry.setEnabled(enabled)
        self.inp_sample.setReadOnly(not enabled)
        self.editor.setEnabled(enabled)
        self.sb_cooling.setEnabled(enabled)
        self.lbl_profile_lock.setVisible(not enabled)

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
            it.setForeground(QBrush(QColor(color)))
        self.lst_log.insertItem(0, it)
        while self.lst_log.count() > 200:
            self.lst_log.takeItem(self.lst_log.count() - 1)
        if kind in ("warning", "danger") and self.tabs_data.currentIndex() != 2:
            self._log_unread = True
            self._set_tab_labels()

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
    # Start / Stop / Reset
    # ==================================================================

    def _clear_results(self):
        """Wipe the on-screen data, charts and table for a fresh run."""
        self._data.clear()
        self._analysis.clear()
        self._table_row_count = 0
        self._reset_chart_buffers()
        for curve in (self.curve_temf, self.curve_t1, self.curve_t2, self.curve_ir,
                      self.curve_heat, self.curve_cool, self.curve_s):
            curve.setData([], [])
        self.scatter_bins.setData([], [])
        self.err_bins.setData(x=[], y=[], height=[])
        self.tbl_data.setRowCount(0)
        self.tbl_bins.setRowCount(0)
        self._camera_cols.clear()
        self._update_camera_columns()
        self._set_tab_labels()
        for r in self.ro.values():
            r.set_value("—")
            r.set_note("")
            r.set_tone("accent" if r is self.ro["s"] else None)
        self._apply_phase("idle")

    def _start(self):
        from ...services.measurement_service import SeebeckService

        self._profile_params = wp = self.editor.get_params()
        sample = self.inp_sample.text().strip()
        ok = True
        if not sample:
            set_field_error(self.f_sample, "Enter a sample ID — the run is filed under it "
                                           "in the run library.")
            self.inp_sample.setFocus()
            self._log("Enter a sample ID to start the run.", "warning")
            ok = False
        if wp["start_volt"] >= wp["stop_volt"]:
            self.lbl_profile_err.setText("The start current I₀ must be lower than the peak "
                                         "current I peak.")
            self.lbl_profile_err.setVisible(True)
            self._log("Heater profile: I₀ must be lower than I peak.", "warning")
            ok = False
        if not ok:
            return

        params = {
            **wp,
            "sample_id": sample,
            "operator":  getattr(self._user, "username", None),
            "probe_mode": self._current_mode(),
            "cooling_target_delta_t": self._cooling_target,
        }

        self.end_box.setVisible(False)
        self._last_instr_err = ""
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
        self._log(f"Run started · {sample} · {dict(_GEOMETRY)[self._current_mode()]}", "success")
        if not self.ir_panel.is_connected():
            # Not a reason to stop: the camera is a second opinion, not the measurement.
            self._log("Thermal camera not connected — readings are recorded without "
                      "camera temperatures.", "warning")
        self.toolbar.set_title("Starting…")
        self.toolbar.set_subtitle("connecting to the instruments")
        self._timer.start()

    def _stop(self):
        from ...services.measurement_service import SeebeckService
        SeebeckService().stop()
        self._timer.stop()
        self._show_idle_buttons()
        self._set_mode_enabled(True)
        self._apply_phase("idle")
        self.toolbar.chip.set("STOPPED", "warning")
        self.toolbar.set_title("Stopped by the operator")
        self._log("Run stopped by the operator — heater output off.", "warning")
        self.toolbar.set_subtitle(
            f"run #{self._run_id} kept in the run library" if self._run_id else "heater output off")

    def _reset(self):
        from ...services.measurement_service import SeebeckService
        self._timer.stop()
        SeebeckService().reset()
        self.end_box.setVisible(False)
        self._clear_results()
        self._show_idle_buttons()
        self._set_mode_enabled(True)
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
        step = status.get("step", 0) or 0
        total = status.get("total_steps", 0) or 0
        self._apply_phase(phase, step / total if total else None)

        if phase != self._last_phase and phase not in ("finished", "error"):
            self._log(f"Phase: {PHASES.get(phase, (phase,))[0]}")
        self._last_phase = phase

        invalid = status.get("invalid_reads") or 0
        if invalid > self._last_invalid:
            self._log(f"{invalid} invalid thermocouple reading(s) so far — not used as data.",
                      "warning")
            self._last_invalid = invalid
        instr = status.get("instrument_errors") or ""
        if instr and instr != self._last_instr_err:
            self._last_instr_err = instr
            self._log(f"Instrument not responding: {instr}", "danger")
        if status.get("polarity_warning") and not self._polarity_logged:
            self._polarity_logged = True
            self._log(status["polarity_warning"], "danger")
        if status.get("db_warning") and status["db_warning"] != self._last_db_warning:
            self._last_db_warning = status["db_warning"]
            self._log("NOT SAVED: " + str(status["db_warning"]), "danger")

        remaining = status.get("estimated_remaining_s")
        parts = []
        if self._run_id:
            parts.append(f"run #{self._run_id}")
        if total and not run_ended:
            parts.append(f"step {step} / {total}")
        if remaining is not None and not run_ended:
            parts.append(f"remaining {int(remaining) // 60:02d}:{int(remaining) % 60:02d}")
        if self._data:
            parts.append(f"{len(self._data)} readings")
        if invalid:
            parts.append(f"{invalid} invalid")
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
            safety = bool(reason and reason.startswith("Safety abort"))
            title = "Safety abort — heater switched off" if safety else "Run stopped by an error"
            msg = reason or status.get("status") or "unknown error"
            self._log(f"{title}: {msg}", "danger")
            if db_warning:
                msg += "\n\n" + db_warning
            self.end_box.set_title(title)
            self.end_box.set(msg, "danger")
            self.end_box.setVisible(True)
            if safety:          # the operator must see this even if not watching the page
                QMessageBox.critical(self, title, msg)
        elif db_warning:
            self.end_box.set_title("Measurement not saved")
            self.end_box.set(db_warning, "warning")
            self.end_box.setVisible(True)

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
        self.ir_panel.set_thermocouple_delta(r.get("Delta Temp [oC]"))

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
        self._set_tab_labels()

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
                                   r.get("Temp2 [oC]"), r.get("TEMF [mV]"),
                                   r.get(_CAMERA_KEYS[0])))
            dt, tf = r.get("Delta Temp [oC]"), r.get("TEMF [mV]")
            if r.get("branch") == "cooling":
                # Cooling continues from the heating peak (max ΔT) and traces back down.
                peak = self._buf_heat.last()
                if len(self._buf_cool) == 0 and peak is not None:
                    self._buf_cool.append(peak)
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
        self.curve_ir.setData(t, bt.col(4))

        for curve, buf in ((self.curve_heat, self._buf_heat),
                           (self.curve_cool, self._buf_cool),
                           (self.curve_s, self._buf_s)):
            if len(buf):
                curve.setData(*thin(buf.col(0), buf.col(1)))

        # Data table — append only new rows
        new_count = len(self._data)
        if new_count > self._table_row_count:
            self.tbl_data.setRowCount(new_count)
            seen = set(self._camera_cols)
            for i in range(self._table_row_count, new_count):
                row = self._data[i]
                invalid = row.get("valid") is False
                seen.update(k for k in _CAMERA_KEYS if k in row)
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
            if seen != self._camera_cols:
                self._camera_cols = seen
                self._update_camera_columns()
            self.tbl_data.scrollToBottom()
        self._set_tab_labels()

    # ------------------------------------------------------------------
    # Phase indicator
    # ------------------------------------------------------------------

    def _phase_title(self, phase: str) -> str:
        p = self._profile_params
        u = p.get("pk160_current_unit", "mA")
        i0, ip = float(p["start_volt"]), float(p["stop_volt"])
        return {
            "idle":         "Ready",
            "pre":          f"Pre-heat — heater at I₀ = {i0:g} {u}",
            "ramp_up":      f"Power up — ramping to {ip:g} {u} at {float(p['inc_rate']):g} {u}/s",
            "hold":         f"Hold — plateau at {ip:g} {u}",
            "ramp_down":    f"Power down — back to {i0:g} {u} at {float(p['dec_rate']):g} {u}/s",
            "cooling_tail": f"Cooling — heater off until |ΔT| < {self._cooling_target:g} K",
            "finished":     "Finished — saved to the run library",
            "error":        "Stopped on error",
        }.get(phase, phase.replace("_", " ").title())

    def _apply_phase(self, phase: str, run_fraction: Optional[float] = None):
        keys = [k for k, _ in _SEGMENTS]
        if phase in keys:
            i = keys.index(phase)
            progress = 0.0
            if run_fraction is not None and phase != "cooling_tail":
                # step / total covers pre-heat to power-down; place it in this phase.
                d = self._profile_durations()[:4]
                pos = run_fraction * sum(d)
                progress = (pos - sum(d[:i])) / d[i] if d[i] else 1.0
            self.segments.set_state(i, progress)
        elif phase == "finished":
            self.segments.set_state(-1, all_done=True)
        elif phase != "error":                 # error: keep showing where it stopped
            self.segments.set_state(-1)

        if phase == "idle":
            chip = ("READY", "neutral")
        elif phase == "finished":
            chip = ("FINISHED", "success")
        elif phase == "error":
            chip = ("ERROR", "danger")
        else:
            chip = ("RUNNING", "info")
        self.toolbar.chip.set(*chip)
        self.toolbar.set_title(self._phase_title(phase))
        if phase == "idle":
            p = self._profile_params
            self.toolbar.set_subtitle(
                f"no run in progress  ·  next run ≈ {fmt_duration(profile_duration_s(p))} "
                f"+ cooling  ·  operator {getattr(self._user, 'username', '—')}")

    def _update_segments(self, phase: str):
        self._apply_phase(phase)

    # ==================================================================
    # Export
    # ==================================================================

    def _export_args(self) -> dict:
        return {"kind": "seebeck", "run_id": self._run_id,
                "sample": self.inp_sample.text().strip() or None}

    def _run_table(self) -> RunTable:
        info = info_lines(
            kind="Seebeck", run_id=self._run_id,
            sample=self.inp_sample.text().strip(),
            operator=getattr(self._user, "username", None),
            extra=[("Geometry", dict(_GEOMETRY).get(self._current_mode(), self._current_mode())),
                   ("Readings", len(self._data))])
        return seebeck_table(self._data, [(k, h) for k, h, _ in table_cols(self._data)],
                             self._analysis, info)

    def _export_single_chart(self, widget: pg.PlotWidget, suffix: str):
        save_graphs(self, [(widget, suffix)], has_data=bool(self._data), **self._export_args())

    def _export_graphs(self):
        save_graphs(self, [(self.chart_live, "live"), (self.chart_temf_dt, "temf_vs_dt"),
                           (self.chart_s_t0, "seebeck_vs_t0")],
                    has_data=bool(self._data), **self._export_args())

    def _export_data(self):
        save_data(self, self._run_table(),
                  charts=[("Temperatures and TEMF vs time", self.chart_live),
                          ("TEMF vs ΔT", self.chart_temf_dt),
                          ("S vs T₀", self.chart_s_t0)],
                  **self._export_args())

"""Run library — every stored run, with filters, quality flags and a preview.

Double-click a run (or "Open") for the full view with charts, data table and
exports (PNG / Excel / CSV / HDF5-NeXus).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import theme as T
from ..icons import icon as _icon
from ..widgets.plot_data import fast_time_curve
from ..widgets.ui_kit import (
    Chip, EmptyState, KeyValueList, LegendStrip, Panel, STATUS_CHIP, Segmented, button,
    cell, chip_cell, fmt_sci, label, make_table, page_scaffold, pen, set_props, style_plot,
)

_TYPE_LABEL = {"seebeck": "Seebeck", "iv": "I-V"}
_PERIODS = [("All time", None), ("Last 7 days", 7), ("Last 30 days", 30), ("Last 90 days", 90)]
_STATUS_FILTERS = [
    ("Any status", None),
    ("Finished", {"finished", "completed"}),
    ("Stopped", {"stopped"}),
    ("Aborted / error", {"aborted", "error"}),
    ("Interrupted", {"interrupted"}),
]


def _hdf5_button(win: QWidget, measurement_id: int, prefix: str) -> QPushButton:
    """'Save HDF5…' — full self-describing export (data, analysis, settings, audit)."""
    btn = button("HDF5 / NeXus…", size="sm", icon="database")
    btn.setToolTip("One file with the data, analysis, settings snapshot, instrument "
                   "identities, audit entries and integrity check of this run.")

    def _save():
        path, _ = QFileDialog.getSaveFileName(
            win, "Save HDF5 / NeXus", f"{prefix}_{measurement_id}.h5",
            "HDF5 / NeXus (*.h5 *.nxs)")
        if not path:
            return
        if not path.lower().endswith((".h5", ".nxs", ".hdf5")):
            path += ".h5"
        try:
            from ...services.export_hdf5 import export_measurement
            export_measurement(measurement_id, path)
        except Exception as exc:
            QMessageBox.critical(win, "Save HDF5", f"Export failed:\n{exc}")
            return
        QMessageBox.information(win, "Save HDF5", f"Saved to:\n{path}")

    btn.clicked.connect(_save)
    return btn


def _fmt_duration(start, end) -> str:
    if not start or not end:
        return "—"
    s = int((end - start).total_seconds())
    if s < 0:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _si(value, unit: str) -> str:
    if value is None:
        return "—"
    a = abs(value)
    for factor, prefix in ((1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n")):
        if a >= factor:
            return f"{value / factor:.4g} {prefix}{unit}"
    return f"{value:.3g} {unit}"


def _summarise(m, data: List[Dict]) -> Dict:
    """Points, key result and quality flag for one run."""
    out = {"points": len(data), "result": "—", "quality": ("—", "neutral", "")}
    invalid = sum(1 for r in data if r.get("valid") is False)
    status = (m.status or "").lower()
    if not data:
        out["quality"] = ("No data", "warning", "No readings were stored for this run.")
        return out
    if m.type == "iv":
        from ...services.measurement_service import _linear_fit_resistance, _ohmic_status
        R, R2 = _linear_fit_resistance(data)
        out.update(R=R, R2=R2, ohmic=_ohmic_status(R2))
        out["result"] = f"R = {_si(R, 'Ω')}" if R is not None else "—"
        q = {"ohmic": ("Ohmic", "success", ""),
             "check_contacts": ("Check contacts", "warning", "0.99 ≤ R² < 0.999"),
             "non_ohmic": ("Non-ohmic", "danger", "R² < 0.99")}.get(
            out["ohmic"], ("No fit", "neutral", "Not enough valid points for a fit."))
        if R2 is not None:
            q = (q[0], q[1], f"R² = {R2:.4f}" + (f" · {q[2]}" if q[2] else ""))
        out["quality"] = q
    elif m.type == "seebeck":
        from ...instruments.seebeck_analysis import binned_seebeck_analysis
        bins = binned_seebeck_analysis(data, bin_width_k=10.0)
        out["bins"] = bins
        dts = [abs(r["Delta Temp [oC]"]) for r in data if r.get("Delta Temp [oC]") is not None]
        out["max_dt"] = max(dts) if dts else None
        if bins:
            n = sum(b["n_points"] for b in bins)
            s_mean = sum(b["S_uV_per_K"] * b["n_points"] for b in bins) / max(n, 1)
            out["S_mean"] = s_mean
            out["result"] = f"S ≈ {s_mean:.1f} µV/K"
            out["quality"] = ("OK", "success", f"{len(bins)} T₀ bin(s) fitted")
        else:
            out["quality"] = ("No S fit", "warning",
                              "Too few valid points per T₀ bin for a linear fit.")
    if invalid:
        out["quality"] = (f"{invalid} invalid", "warning",
                          f"{invalid} reading(s) flagged invalid (not used as data).")
    if status in ("aborted", "error"):
        out["quality"] = ("Aborted", "danger", m.end_reason or "")
    elif status == "interrupted":
        out["quality"] = ("Interrupted", "warning", m.end_reason or "")
    return out


class HistoryPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._runs: List[Dict] = []
        self._data: Dict[int, List[Dict]] = {}
        self._detail_windows: list = []
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        tb, body = page_scaffold(self, "Run library", "", margins=12, spacing=10)
        self.toolbar = tb
        b_refresh = button("Refresh", icon="refresh")
        b_refresh.clicked.connect(self._load)
        tb.add_action(b_refresh)

        # Filter bar
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Search sample, operator, run #, notes…")
        self.inp_search.addAction(_icon("search", T.TEXT_MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.inp_search.setClearButtonEnabled(True)
        self.inp_search.setMinimumWidth(280)
        self.inp_search.textChanged.connect(self._apply_filter)
        bar.addWidget(self.inp_search, 2)
        self.seg_type = Segmented(["All", "Seebeck", "I-V"])
        self.seg_type.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.seg_type)
        self.cb_status = QComboBox()
        for text, _v in _STATUS_FILTERS:
            self.cb_status.addItem(text)
        self.cb_status.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.cb_status)
        self.cb_period = QComboBox()
        for text, _v in _PERIODS:
            self.cb_period.addItem(text)
        self.cb_period.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.cb_period)
        self.chk_issues = QCheckBox("Only runs with issues")
        self.chk_issues.toggled.connect(lambda _c: self._apply_filter())
        bar.addWidget(self.chk_issues)
        bar.addStretch(1)
        body.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        split.setStyleSheet("QSplitter::handle { background: transparent; }")

        # Table
        tp = Panel(flush=True)
        self.table = make_table(["Run", "Type", "Sample", "Operator", "Started",
                                 "Points", "Result", "Status", "Quality"])
        widths = (62, 64, 110, 88, 150, 52, 116, 100)
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(self._open_detail)
        self.empty = EmptyState("history", "No runs match", "Change the filters or the search text.")
        self.empty.setVisible(False)
        tp.body.addWidget(self.table)
        tp.body.addWidget(self.empty)
        self.lbl_count = label("", "caption")
        tp.show_footer(self.lbl_count, None,
                       label("Double-click a run to open the full view.", "caption"))
        split.addWidget(tp)

        # Preview
        self.preview = self._build_preview()
        split.addWidget(self.preview)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([960, 310])
        body.addWidget(split, 1)

    def _build_preview(self) -> QWidget:
        p = Panel("Preview")
        p.setMinimumWidth(310)
        p.setMaximumWidth(440)
        self.pv_chip = Chip("", "neutral")
        self.pv_chip.setVisible(False)
        p.add_action(self.pv_chip)
        self.pv_stack = QStackedWidget()
        self.pv_stack.addWidget(EmptyState("history", "No run selected",
                                           "Select a run to see its details here."))
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.pv_chart = pg.PlotWidget()
        style_plot(self.pv_chart)
        self.pv_chart.setFixedHeight(190)
        self.pv_chart.setMouseEnabled(x=False, y=False)
        v.addWidget(self.pv_chart)
        self.pv_legend_host = QVBoxLayout()
        v.addLayout(self.pv_legend_host)
        v.addWidget(label("RESULT", "overline"))
        self.pv_result = KeyValueList(mono_values=True, key_width=104)
        v.addWidget(self.pv_result)
        v.addWidget(label("RUN", "overline"))
        self.pv_meta = KeyValueList(key_width=104)
        v.addWidget(self.pv_meta)
        v.addStretch()
        row = QHBoxLayout()
        row.setSpacing(6)
        self.pv_open = button("Open full view", "primary", size="sm", icon="external")
        self.pv_open.clicked.connect(lambda: self._open_detail(self.table.currentRow(), 0))
        row.addWidget(self.pv_open)
        self.pv_h5_host = QHBoxLayout()
        row.addLayout(self.pv_h5_host)
        row.addStretch()
        v.addLayout(row)
        self.pv_stack.addWidget(content)
        p.body.addWidget(self.pv_stack)
        self._pv_panel = p
        return p

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load(self):
        from ...core.database import SessionLocal
        from ...models.db_models import Measurement, MeasurementRow

        db = SessionLocal()
        try:
            role = self._user.role
            q = db.query(Measurement)
            if role == "researcher":
                q = q.filter_by(user_id=self._user.id)
            elif role == "lab_admin":
                q = q.filter_by(lab_id=self._user.lab_id)
            ms = q.order_by(Measurement.started_at.desc()).limit(500).all()
            ids = [m.id for m in ms]
            data: Dict[int, List[Dict]] = {i: [] for i in ids}
            if ids:
                for mid, js in (db.query(MeasurementRow.measurement_id, MeasurementRow.data_json)
                                .filter(MeasurementRow.measurement_id.in_(ids))
                                .order_by(MeasurementRow.measurement_id, MeasurementRow.seq)):
                    try:
                        data[mid].append(json.loads(js))
                    except (TypeError, ValueError):
                        pass
            runs = []
            for m in ms:
                summ = _summarise(m, data.get(m.id, []))
                runs.append({
                    "id": m.id, "type": m.type, "sample": m.sample_id or "",
                    "operator": m.operator or "", "status": m.status or "",
                    "end_reason": m.end_reason or "", "notes": m.notes or "",
                    "started": m.started_at, "finished": m.finished_at,
                    "params_json": m.params_json, **summ,
                })
        finally:
            db.close()
        self._runs = runs
        self._data = data
        self._fill_table()

    def _fill_table(self):
        t = self.table
        t.setSortingEnabled(False)
        t.clearContents()
        t.setRowCount(len(self._runs))
        for r, run in enumerate(self._runs):
            t.setItem(r, 0, _NumItem(f"#{run['id']}", run["id"]))
            t.setItem(r, 1, cell(_TYPE_LABEL.get(run["type"], run["type"])))
            t.setItem(r, 2, cell(run["sample"] or "—", tooltip=run["notes"]))
            t.setItem(r, 3, cell(run["operator"] or "—"))
            started = run["started"]
            t.setItem(r, 4, cell(started.strftime("%Y-%m-%d %H:%M") if started else "—", mono=True))
            t.setItem(r, 5, _NumItem(str(run["points"]), run["points"], align="right"))
            t.setItem(r, 6, cell(run["result"], mono=True))
            text, kind = STATUS_CHIP.get(run["status"].lower(), (run["status"].title() or "—", "neutral"))
            t.setItem(r, 7, cell(text))
            chip_cell(t, r, 7, text, kind, tooltip=run["end_reason"])
            qt, qk, qtip = run["quality"]
            t.setItem(r, 8, cell(qt))
            chip_cell(t, r, 8, qt, qk, tooltip=qtip)
            t.item(r, 0).setData(Qt.ItemDataRole.UserRole, run["id"])
            for c in range(1, 9):
                it = t.item(r, c)
                if it is not None:
                    it.setData(Qt.ItemDataRole.UserRole, run["id"])
        t.setSortingEnabled(True)
        self._apply_filter()

    def _run_by_id(self, mid: int) -> Optional[Dict]:
        for run in self._runs:
            if run["id"] == mid:
                return run
        return None

    def _apply_filter(self, *_):
        text = self.inp_search.text().strip().lower()
        typ = {0: None, 1: "seebeck", 2: "iv"}[max(self.seg_type.currentIndex(), 0)]
        statuses = _STATUS_FILTERS[self.cb_status.currentIndex()][1]
        days = _PERIODS[self.cb_period.currentIndex()][1]
        since = datetime.now() - timedelta(days=days) if days else None
        issues_only = self.chk_issues.isChecked()
        shown = 0
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            run = self._run_by_id(it.data(Qt.ItemDataRole.UserRole)) if it else None
            ok = run is not None
            if ok and typ and run["type"] != typ:
                ok = False
            if ok and statuses and run["status"].lower() not in statuses:
                ok = False
            if ok and since and (run["started"] is None or run["started"] < since):
                ok = False
            if ok and issues_only and run["quality"][1] in ("success", "neutral"):
                ok = False
            if ok and text:
                hay = " ".join([f"#{run['id']}", str(run["id"]), run["sample"], run["operator"],
                                run["notes"], run["end_reason"], run["result"]]).lower()
                ok = text in hay
            self.table.setRowHidden(r, not ok)
            shown += ok
        total = len(self._runs)
        self.toolbar.set_subtitle(f"{total} run(s) stored" + ("" if self._user.role == "super_admin"
                                                              else " that you can see"))
        self.lbl_count.setText(f"Showing {shown} of {total}")
        self.table.setVisible(shown > 0)
        self.empty.setVisible(shown == 0)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_select(self):
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        run = self._run_by_id(it.data(Qt.ItemDataRole.UserRole)) if it else None
        if run is None or self.table.isRowHidden(r):
            self.pv_stack.setCurrentIndex(0)
            self.pv_chip.setVisible(False)
            self._pv_panel.set_title("Preview")
            self._pv_panel.set_subtitle("")
            return
        self._show_preview(run)

    def _show_preview(self, run: Dict):
        data = self._data.get(run["id"], [])
        self._pv_panel.set_title(f"Run #{run['id']}")
        self._pv_panel.set_subtitle(f"{_TYPE_LABEL.get(run['type'], run['type'])} · "
                                    f"{run['sample'] or 'no sample ID'}")
        text, kind = STATUS_CHIP.get(run["status"].lower(), (run["status"].title(), "neutral"))
        self.pv_chip.set(text, kind)
        self.pv_chip.setVisible(True)

        # chart
        ch = self.pv_chart
        ch.clear()
        while self.pv_legend_host.count():
            w = self.pv_legend_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        if run["type"] == "iv":
            style_plot(ch, "I (A)", "V (V)")
            pts = [(d["voltage"], d["current"]) for d in data
                   if d.get("voltage") is not None and d.get("current") is not None]
            if pts:
                ch.addItem(pg.ScatterPlotItem([p[0] for p in pts], [p[1] for p in pts], size=5,
                                              pen=pg.mkPen(None), brush=pg.mkBrush(T.SERIES_T1)))
                R = run.get("R")
                if R:
                    from .iv_page import fit_offset
                    v0 = fit_offset(data, R)
                    ys = [p[1] for p in pts]
                    ch.plot([R * min(ys) + v0, R * max(ys) + v0], [min(ys), max(ys)],
                            pen=pen(T.SERIES_FIT, 1.4))
        else:
            style_plot(ch, "TEMF (mV)", "ΔT (K)")
            heat = [(d["Delta Temp [oC]"], d["TEMF [mV]"]) for d in data
                    if d.get("branch") != "cooling" and d.get("Delta Temp [oC]") is not None
                    and d.get("TEMF [mV]") is not None]
            cool = [(d["Delta Temp [oC]"], d["TEMF [mV]"]) for d in data
                    if d.get("branch") == "cooling" and d.get("Delta Temp [oC]") is not None
                    and d.get("TEMF [mV]") is not None]
            if heat:
                ch.plot([p[0] for p in heat], [p[1] for p in heat], pen=pen(T.SERIES_HEAT, 1.4))
            if cool:
                ch.plot([p[0] for p in cool], [p[1] for p in cool], pen=pen(T.SERIES_COOL, 1.4))
            self.pv_legend_host.addWidget(LegendStrip([(T.SERIES_HEAT, "Heating"),
                                                       (T.SERIES_COOL, "Cooling")]))
        ch.enableAutoRange()

        # result
        kv = self.pv_result
        kv.clear()
        try:
            params = json.loads(run["params_json"]) if run.get("params_json") else {}
        except (TypeError, ValueError):
            params = {}
        if run["type"] == "iv":
            kv.set("Resistance R", _si(run.get("R"), "Ω"))
            r2 = run.get("R2")
            kv.set("Linearity R²", f"{r2:.4f}" if r2 is not None else "—",
                   tone={"ohmic": "success", "check_contacts": "warning",
                         "non_ohmic": "danger"}.get(run.get("ohmic")))
            geo = params.get("geometry")
            if geo:
                dims = [f"{params[k]:g}" for k in ("length", "width", "thickness") if params.get(k)]
                kv.set("Geometry", {"bar": "Bar", "vdp": "van der Pauw", "4pp": "4-point probe"}
                       .get(geo, geo) + (f" · {' × '.join(dims)} cm" if dims else ""))
            if params.get("source_mode"):
                kv.set("Sweep", f"{params.get('source_mode')} {params.get('start')} → "
                       f"{params.get('stop')} · {params.get('points')} pts"
                       + (" · fwd+rev" if params.get("bidirectional") else ""))
        else:
            bins = run.get("bins") or []
            if bins:
                kv.set("S (mean of bins)", f"{run['S_mean']:.2f} µV/K")
                s_vals = [b["S_uV_per_K"] for b in bins]
                kv.set("S range", f"{min(s_vals):.1f} … {max(s_vals):.1f} µV/K")
                kv.set("T₀ range", f"{bins[0]['T0_min_K']:.0f} – {bins[-1]['T0_max_K']:.0f} K")
            else:
                kv.set("S", "no fit", tone="warning")
            if run.get("max_dt") is not None:
                kv.set("Max |ΔT|", f"{run['max_dt']:.2f} K")
            if params.get("probe_mode"):
                kv.set("Geometry", {"in_plane": "In-plane", "out_plane": "Out-of-plane"}
                       .get(params["probe_mode"], params["probe_mode"]))

        meta = self.pv_meta
        meta.clear()
        meta.set("Operator", run["operator"] or "—")
        meta.set("Started", run["started"].strftime("%Y-%m-%d %H:%M:%S") if run["started"] else "—")
        meta.set("Duration", _fmt_duration(run["started"], run["finished"]))
        meta.set("Points", str(run["points"]))
        qt, qk, qtip = run["quality"]
        meta.set("Quality", qt + (f" — {qtip}" if qtip else ""),
                 tone={"success": "success", "warning": "warning", "danger": "danger"}.get(qk))
        meta.set("End reason", run["end_reason"] or "—")
        meta.set("Notes", run["notes"] or "—")

        while self.pv_h5_host.count():
            w = self.pv_h5_host.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.pv_h5_host.addWidget(_hdf5_button(self, run["id"], run["type"]))
        self.pv_open.setEnabled(bool(data))
        self.pv_stack.setCurrentIndex(1)

    def on_shown(self):
        pass

    # ------------------------------------------------------------------
    # Full view
    # ------------------------------------------------------------------

    def _open_detail(self, row: int, _column: int = 0):
        """Open the full view for the measurement in ``row``."""
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        measurement_id = item.data(Qt.ItemDataRole.UserRole)
        if measurement_id is None:
            try:
                measurement_id = int(item.text().lstrip("#"))
            except ValueError:
                return

        from ...core.database import SessionLocal
        from ...models.db_models import Measurement, MeasurementIntegrity, MeasurementRow

        db = SessionLocal()
        try:
            m = db.query(Measurement).filter_by(id=measurement_id).first()
            if not m:
                QMessageBox.warning(self, "Run library", "This run is no longer in the database.")
                return
            if m.type not in ("seebeck", "iv"):
                QMessageBox.information(self, "Run library",
                                        f"There is no full view for '{m.type}' runs yet.")
                return
            rows = (db.query(MeasurementRow).filter_by(measurement_id=measurement_id)
                    .order_by(MeasurementRow.seq.asc()).all())
            data = [json.loads(r.data_json) for r in rows]
            integ = db.query(MeasurementIntegrity).filter_by(measurement_id=measurement_id).first()
            db.expunge(m)
        finally:
            db.close()

        if not data:
            QMessageBox.information(self, "Run library", "This run has no stored readings.")
            return

        integrity = None
        if integ is not None:
            canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
            integrity = hashlib.sha256(canonical.encode("utf-8")).hexdigest() == integ.data_hash

        win = RunDetailWindow(self, m, data, integrity)
        self._detail_windows.append(win)
        win.show()

    # Kept for older callers.
    def _show_iv_detail(self, m, measurement_id, data, integ):
        integrity = None
        if integ is not None:
            canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
            integrity = hashlib.sha256(canonical.encode("utf-8")).hexdigest() == integ.data_hash
        win = RunDetailWindow(self, m, data, integrity)
        self._detail_windows.append(win)
        win.show()


class _NumItem:
    """Factory: QTableWidgetItem that sorts numerically."""

    def __new__(cls, text: str, value, align: str = "left"):
        from PyQt6.QtWidgets import QTableWidgetItem

        class _It(QTableWidgetItem):
            def __lt__(self, other):
                a = self.data(Qt.ItemDataRole.UserRole + 1)
                b = other.data(Qt.ItemDataRole.UserRole + 1)
                if a is not None and b is not None:
                    return a < b
                return super().__lt__(other)

        it = _It(text)
        it.setData(Qt.ItemDataRole.UserRole + 1, value)
        a = Qt.AlignmentFlag.AlignRight if align == "right" else Qt.AlignmentFlag.AlignLeft
        it.setTextAlignment(a | Qt.AlignmentFlag.AlignVCenter)
        from PyQt6.QtGui import QFont
        f = QFont(T.mono_family())
        f.setPixelSize(12)
        it.setFont(f)
        return it


# ===========================================================================
# Full run view
# ===========================================================================

class RunDetailWindow(QWidget):
    """Charts + data table + exports for one stored run."""

    def __init__(self, parent: QWidget, m, data: List[Dict], integrity: Optional[bool]):
        super().__init__(parent, Qt.WindowType.Window)
        self._m = m
        self._data = data
        self._mid = m.id
        kind = _TYPE_LABEL.get(m.type, m.type)
        self.setWindowTitle(f"Run #{m.id} — {kind}")
        self.setObjectName("Page")
        self.resize(1180, 860)
        try:
            self._params = json.loads(m.params_json) if getattr(m, "params_json", None) else {}
        except (TypeError, ValueError):
            self._params = {}

        tb, body = page_scaffold(self, f"Run #{m.id} · {kind}",
                                 f"Sample {m.sample_id or '—'} · operator {m.operator or '—'} · "
                                 + (m.started_at.strftime("%Y-%m-%d %H:%M") if m.started_at else ""),
                                 scroll=True)
        text, k = STATUS_CHIP.get((m.status or "").lower(), ((m.status or "—").title(), "neutral"))
        tb.add_middle(Chip(text, k))
        if integrity is not None:
            tb.add_middle(Chip("Integrity verified" if integrity else "Integrity MISMATCH",
                               "success" if integrity else "danger"))
            if not integrity:
                tb.middle.itemAt(tb.middle.count() - 1).widget().setToolTip(
                    "The stored readings no longer match the hash recorded when the run ended.")
        backend = str(((self._params.get("run_context") or {}).get("visa_backend")) or "")
        if backend.lower().endswith("@sim"):
            sim = Chip("Simulated rig", "warning")
            sim.setToolTip(f"Recorded with simulated instruments ({backend}) — not a measurement.")
            tb.add_middle(sim)
        self._body = body
        self.btn_graphs = button("Save graphs…", icon="image")
        self.btn_data = button("Save data…", icon="download")
        tb.add_action(self.btn_graphs)
        tb.add_action(self.btn_data)
        tb.add_action(_hdf5_button(self, m.id, m.type))
        if m.end_reason:
            from ..widgets.ui_kit import Callout
            body.addWidget(Callout(m.end_reason, "warning" if (m.status or "") in
                                   ("stopped", "interrupted") else "danger", title="End reason"))
        if m.type == "iv":
            self._build_iv()
        else:
            self._build_seebeck()

    # ── Seebeck ───────────────────────────────────────────────────────
    def _build_seebeck(self):
        from .seebeck_page import _TABLE_COLS
        data = self._data
        nan = float("nan")

        def _v(lst):
            return [x if x is not None else nan for x in lst]

        live = pg.PlotWidget()
        style_plot(live, "Temperature (°C)", "Time (s)", right="TEMF (mV)")
        pi = live.getPlotItem()
        vb = pg.ViewBox()
        pi.scene().addItem(vb)
        pi.getAxis("right").linkToView(vb)
        vb.setXLink(pi)

        def _sync():
            vb.setGeometry(pi.vb.sceneBoundingRect())
            vb.linkedViewChanged(pi.vb, vb.XAxis)
        pi.vb.sigResized.connect(_sync)
        _sync()
        times = [r.get("Time [s]", 0) for r in data]
        # Long runs: draw a few points per pixel, full detail when zoomed in.
        fast_time_curve(pi.plot(times, _v([r.get("Temp1 [oC]") for r in data]),
                                pen=pen(T.SERIES_T1)))
        fast_time_curve(pi.plot(times, _v([r.get("Temp2 [oC]") for r in data]),
                                pen=pen(T.SERIES_T2)))
        temf_curve = pg.PlotDataItem(times, _v([r.get("TEMF [mV]") for r in data]),
                                     pen=pen(T.SERIES_TEMF, 1.6, dashed=True))
        vb.addItem(temf_curve)
        fast_time_curve(temf_curve)       # only once it is inside its ViewBox
        self._live = live

        temf_dt = pg.PlotWidget()
        style_plot(temf_dt, "TEMF (mV)", "ΔT (K)")
        heating = [r for r in data if r.get("branch") != "cooling"]
        cooling = [r for r in data if r.get("branch") == "cooling"]
        if heating and cooling:
            cooling = [heating[-1]] + cooling

        def _xy(rows):
            xs, ys = [], []
            for r in rows:
                if r.get("Delta Temp [oC]") is not None and r.get("TEMF [mV]") is not None:
                    xs.append(r["Delta Temp [oC]"])
                    ys.append(r["TEMF [mV]"])
            return xs, ys
        temf_dt.plot(*_xy(heating), pen=pen(T.SERIES_HEAT))
        temf_dt.plot(*_xy(cooling), pen=pen(T.SERIES_COOL))
        self._temf_dt = temf_dt

        s_t0 = pg.PlotWidget()
        style_plot(s_t0, "S (µV/K)", "T₀ (K)")
        pairs = [(r["T0 [K]"], r["S [µV/K]"]) for r in data
                 if r.get("T0 [K]") is not None and r.get("S [µV/K]") is not None]
        if pairs:
            s_t0.plot([p[0] for p in pairs], [p[1] for p in pairs], pen=pen("#C4B5FD", 1.2),
                      symbol="o", symbolSize=4, symbolBrush="#A78BFA", symbolPen=None)
        from ...instruments.seebeck_analysis import binned_seebeck_analysis
        bins = binned_seebeck_analysis(data, bin_width_k=10.0)
        if bins:
            import numpy as np
            xs = np.array([b["T0_center_K"] for b in bins])
            ys = np.array([b["S_uV_per_K"] for b in bins])
            es = np.array([2 * (b.get("S_uncertainty_uV_per_K") or 0.0) for b in bins])
            s_t0.addItem(pg.ErrorBarItem(x=xs, y=ys, height=es, pen=pen(T.SERIES_S, 1.2), beam=4))
            s_t0.addItem(pg.ScatterPlotItem(xs, ys, size=9, pen=pg.mkPen(T.SURFACE, width=1.5),
                                            brush=pg.mkBrush(T.SERIES_S)))
        self._s_t0 = s_t0

        grid = QGridLayout()
        grid.setSpacing(12)
        p1 = Panel("Temperatures and TEMF vs time")
        p1.body.addWidget(LegendStrip([(T.SERIES_T1, "T₁"), (T.SERIES_T2, "T₂"),
                                       (T.SERIES_TEMF, "TEMF · right axis")],
                                      kinds=["line", "line", "dash"]))
        live.setMinimumHeight(280)
        p1.body.addWidget(live)
        p2 = Panel("TEMF vs ΔT")
        p2.body.addWidget(LegendStrip([(T.SERIES_HEAT, "Heating"), (T.SERIES_COOL, "Cooling")]))
        temf_dt.setMinimumHeight(240)
        p2.body.addWidget(temf_dt)
        p3 = Panel("S vs T₀")
        p3.body.addWidget(LegendStrip([("#A78BFA", "Point-wise"), (T.SERIES_S, "Binned fit ± 1σ")],
                                      kinds=["dot", "dot"]))
        s_t0.setMinimumHeight(240)
        p3.body.addWidget(s_t0)
        grid.addWidget(p1, 0, 0, 1, 2)
        grid.addWidget(p2, 1, 0)
        grid.addWidget(p3, 1, 1)
        self._body.addLayout(grid)

        if bins:
            pb = Panel("Seebeck by T₀ bin", flush=True)
            tb = make_table(["T₀ [K]", "Range [K]", "S [µV/K]", "± [µV/K]", "n"], mono=True,
                            row_height=26)
            tb.setRowCount(len(bins))
            for i, b in enumerate(bins):
                unc = b.get("S_uncertainty_uV_per_K")
                tb.setItem(i, 0, cell(f"{b['T0_center_K']:.1f}", align="right"))
                tb.setItem(i, 1, cell(f"{b['T0_min_K']:.0f}–{b['T0_max_K']:.0f}", align="right"))
                tb.setItem(i, 2, cell(f"{b['S_uV_per_K']:.2f}", align="right", bold=True))
                tb.setItem(i, 3, cell("—" if unc is None else f"{unc:.2f}", align="right"))
                tb.setItem(i, 4, cell(str(b["n_points"]), align="right"))
            tb.setMinimumHeight(min(60 + 26 * len(bins), 260))
            pb.body.addWidget(tb)
            self._body.addWidget(pb)

        headers = [c[1] for c in _TABLE_COLS]
        keys = [c[0] for c in _TABLE_COLS]
        pt = Panel(f"Readings · {len(data)} rows", flush=True)
        tbl = make_table(headers, row_height=24, mono=True)
        tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tbl.setRowCount(len(data))
        for i, row in enumerate(data):
            for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                val = row.get(key)
                tbl.setItem(i, j, cell("—" if val is None else fmt.format(val), align="right"))
        for j in range(len(headers)):
            tbl.setColumnWidth(j, 96)
        tbl.setMinimumHeight(320)
        pt.body.addWidget(tbl)
        self._body.addWidget(pt)

        charts = {"live": live, "temf_dt": temf_dt, "s_t0": s_t0}
        mid = self._mid

        def _save_graphs():
            base, _ = QFileDialog.getSaveFileName(self, "Save graphs", f"seebeck_{mid}_graphs",
                                                  "PNG images (*.png)")
            if not base:
                return
            root, _ext = os.path.splitext(base)
            paths = []
            for key, suffix in (("live", "live"), ("temf_dt", "temf_vs_dt"), ("s_t0", "seebeck_vs_t0")):
                pix = charts[key].grab()
                if pix.isNull():
                    continue
                path = f"{root}_{suffix}.png"
                pix.save(path, "PNG")
                paths.append(path)
            if paths:
                QMessageBox.information(self, "Save graphs", "Graphs saved as:\n"
                                        + "\n".join(os.path.basename(p) for p in paths))

        def _save_data():
            path, selected = QFileDialog.getSaveFileName(
                self, "Save data", f"seebeck_{mid}_data.xlsx",
                "Excel workbook (*.xlsx);;CSV file (*.csv)")
            if not path:
                return
            if selected.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for row in data:
                        w.writerow([row.get(k, "") if row.get(k) is not None else "" for k in keys])
                QMessageBox.information(self, "Save data", f"CSV saved to:\n{path}")
                return
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self._write_xlsx(path, headers, [[row.get(k, "") if row.get(k) is not None else ""
                                              for k in keys] for row in data],
                             [(charts["live"], 0), (charts["temf_dt"], 20), (charts["s_t0"], 40)],
                             img_row=len(data) + 3)

        self.btn_graphs.clicked.connect(_save_graphs)
        self.btn_data.clicked.connect(_save_data)

    # ── I-V ───────────────────────────────────────────────────────────
    def _build_iv(self):
        from ...services.measurement_service import _linear_fit_resistance, _ohmic_status
        from ..widgets.ui_kit import Readout, ReadoutGrid
        data = self._data
        fit_R, fit_R2 = _linear_fit_resistance(data)
        ohmic = _ohmic_status(fit_R2)
        n_fwd = int(self._params.get("points") or 0)
        bidir = bool(self._params.get("bidirectional"))

        r1 = Readout("Resistance R (fit)", "")
        r1.set_value(_si(fit_R, "Ω"))
        r2 = Readout("Linearity R²", "")
        r2.set_value(f"{fit_R2:.4f}" if fit_R2 is not None else "—")
        text, tone = {"ohmic": ("Ohmic", "success"), "check_contacts": ("Check contacts", "warning"),
                      "non_ohmic": ("Non-ohmic", "danger")}.get(ohmic, ("—", None))
        r3 = Readout("Ohmic check", "", size="sm")
        r3.set_value(text)
        r3.set_tone(tone)
        r4 = Readout("Points", "")
        r4.set_value(str(len(data)))
        self._body.addWidget(ReadoutGrid([r1, r2, r3, r4], 4))

        headers = ["Current (A)", "Voltage (V)", "Resistance (Ω)", "Power (mW)",
                   "Resistivity (Ω·cm)", "Conductivity (S/cm)"]

        def _rows():
            out = []
            for r in data:
                cur, vol, res = r.get("current"), r.get("voltage"), r.get("resistance")
                pw = (cur * vol * 1000) if (cur is not None and vol is not None) else None
                out.append([cur, vol, res, pw, r.get("resistivity"), r.get("conductivity")])
            return out

        def _build_chart():
            chart = pg.PlotWidget()
            style_plot(chart, "Current (A)", "Voltage (V)")
            pts = [(r.get("voltage"), r.get("current")) for r in data
                   if r.get("voltage") is not None and r.get("current") is not None]
            if bidir and n_fwd and len(pts) > n_fwd:
                fwd, rev = pts[:n_fwd], pts[n_fwd:]
            else:
                fwd, rev = pts, []
            ys = [p[1] for p in pts]
            if fit_R is not None and abs(fit_R) > 1e-12 and ys:
                from .iv_page import fit_offset
                v0 = fit_offset(data, fit_R)
                chart.plot([fit_R * min(ys) + v0, fit_R * max(ys) + v0], [min(ys), max(ys)],
                           pen=pen(T.SERIES_FIT, 1.6))
            chart.addItem(pg.ScatterPlotItem([p[0] for p in fwd], [p[1] for p in fwd], size=7,
                                             pen=pg.mkPen(None), brush=pg.mkBrush(T.SERIES_T1)))
            if rev:
                chart.addItem(pg.ScatterPlotItem([p[0] for p in rev], [p[1] for p in rev], size=8,
                                                 pen=pg.mkPen(T.SERIES_T2, width=1.5),
                                                 brush=pg.mkBrush(None)))
            return chart

        pc = Panel("I-V characteristic")
        pc.body.addWidget(LegendStrip([(T.SERIES_T1, "Forward"), (T.SERIES_T2, "Reverse"),
                                       (T.SERIES_FIT, "Fit  V = R·I + V₀")],
                                      kinds=["dot", "ring", "line"]))
        chart = _build_chart()
        chart.setMinimumHeight(360)
        pc.body.addWidget(chart)
        self._body.addWidget(pc)

        pt = Panel(f"Points · {len(data)}", flush=True)
        tbl = make_table(headers, row_height=24, mono=True)
        tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rows = _rows()
        tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                tbl.setItem(i, j, cell("—" if val is None else f"{val:.6g}", align="right"))
        for j in range(len(headers)):
            tbl.setColumnWidth(j, 150)
        tbl.setMinimumHeight(300)
        pt.body.addWidget(tbl)
        self._body.addWidget(pt)

        mid = self._mid

        def _save_graph():
            path, _ = QFileDialog.getSaveFileName(self, "Save graph", f"iv_{mid}.png", "PNG (*.png)")
            if not path:
                return
            pix = chart.grab()
            if pix.isNull():
                QMessageBox.warning(self, "Save graph", "The chart image is empty.")
                return
            pix.save(path, "PNG")
            QMessageBox.information(self, "Save graph", f"Saved to:\n{path}")

        def _save_data():
            path, selected = QFileDialog.getSaveFileName(
                self, "Save data", f"iv_{mid}_data.xlsx",
                "Excel workbook (*.xlsx);;CSV file (*.csv)")
            if not path:
                return
            if selected.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for row in rows:
                        w.writerow(["" if v is None else v for v in row])
                QMessageBox.information(self, "Save data", f"CSV saved to:\n{path}")
                return
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            body = [["" if v is None else v for v in row] for row in rows]
            body += [[], ["Fit R (Ohm)", fit_R], ["R^2", fit_R2], ["Ohmic status", ohmic]]
            self._write_xlsx(path, headers, body, [(chart, 0)], img_row=len(rows) + 8)

        self.btn_graphs.setText("Save graph…")
        self.btn_graphs.clicked.connect(_save_graph)
        self.btn_data.clicked.connect(_save_data)

    # ── shared ────────────────────────────────────────────────────────
    def _write_xlsx(self, path, headers, rows, charts, img_row: int):
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XLImage
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"
        ws.append(headers)
        for row in rows:
            ws.append(row)
        try:
            import PIL  # type: ignore  # noqa: F401
            tmpdir = tempfile.mkdtemp(prefix="te_run_")
            files = []
            for i, (widget, offset) in enumerate(charts):
                pix = widget.grab()
                if pix.isNull():
                    continue
                fp = os.path.join(tmpdir, f"chart_{i}.png")
                pix.save(fp, "PNG")
                ws.add_image(XLImage(fp), f"A{img_row + offset}")
                files.append(fp)
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
            QMessageBox.warning(self, "Save data",
                                "Excel file saved without embedded graphs.\n\n"
                                "To include graphs, install Pillow:\n  pip install pillow")

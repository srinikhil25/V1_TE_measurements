"""Measurement History page — list of past sessions from the database."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QPushButton, QFileDialog, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)


class HistoryPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._build_ui()
        self._load()

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Measurement History")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        v.addLayout(header)

        hint = QLabel("Double-click on a row to open that measurement and download its graphs/data.")
        hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border: none; margin-bottom: 4px;"
        )
        v.addWidget(hint)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "Type", "Sample ID", "Operator", "Status", "Started"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; font-size: 13px; }}"
            f"QTableWidget::item:alternate {{ background: #FBFAF5; }}"
        )
        self.table.cellDoubleClicked.connect(self._open_detail)
        v.addWidget(self.table)

    def _load(self):
        from ...core.database import SessionLocal
        from ...models.db_models import Measurement

        db = SessionLocal()
        try:
            role = self._user.role
            uid  = self._user.id
            q = db.query(Measurement)
            if role == "researcher":
                q = q.filter_by(user_id=uid)
            elif role == "lab_admin":
                q = q.filter_by(lab_id=self._user.lab_id)
            rows = q.order_by(Measurement.started_at.desc()).limit(200).all()

            self.table.setRowCount(len(rows))
            for i, m in enumerate(rows):
                for col, val in enumerate([
                    str(m.id),
                    m.type,
                    m.sample_id or "—",
                    m.operator  or "—",
                    m.status,
                    m.started_at.strftime("%Y-%m-%d %H:%M") if m.started_at else "—",
                ]):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                    )
                    self.table.setItem(i, col, item)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Detail view
    # ------------------------------------------------------------------

    def _open_detail(self, row: int, _column: int):
        """Open a detail window for the selected measurement."""
        item = self.table.item(row, 0)
        if item is None:
            return
        try:
            measurement_id = int(item.text())
        except ValueError:
            return

        from ...core.database import SessionLocal
        from ...models.db_models import Measurement, MeasurementRow, MeasurementIntegrity
        import json, hashlib

        db = SessionLocal()
        try:
            m = db.query(Measurement).filter_by(id=measurement_id).first()
            if not m:
                QMessageBox.warning(self, "History", "Measurement not found in database.")
                return
            if m.type not in ("seebeck", "iv"):
                QMessageBox.information(
                    self,
                    "History",
                    f"Detail view for measurement type '{m.type}' is not implemented yet.",
                )
                return
            rows = (
                db.query(MeasurementRow)
                .filter_by(measurement_id=measurement_id)
                .order_by(MeasurementRow.seq.asc())
                .all()
            )
            data = [json.loads(r.data_json) for r in rows]

            # Integrity record (if present)
            integ = (
                db.query(MeasurementIntegrity)
                .filter_by(measurement_id=measurement_id)
                .first()
            )
        finally:
            db.close()

        if not data:
            QMessageBox.information(
                self, "History", "This measurement has no stored data rows."
            )
            return

        if m.type == "iv":
            self._show_iv_detail(m, measurement_id, data, integ)
            return

        # Lazy import to avoid circulars
        from .seebeck_page import _TABLE_COLS, SeebeckPage
        from ..theme import PRIMARY
        import pyqtgraph as pg
        import os
        import tempfile
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XLImage
        import csv

        # Build a simple detail window inline to avoid another file.
        # Scrollable so the three graphs + full data table are all reachable.
        win = QWidget(self, Qt.WindowType.Window)
        win.setWindowTitle(f"Measurement #{measurement_id} — Seebeck (history)")
        _win_v = QVBoxLayout(win)
        _win_v.setContentsMargins(0, 0, 0, 0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _win_v.addWidget(_scroll)
        _content = QWidget()
        _scroll.setWidget(_content)
        layout = QVBoxLayout(_content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel(
            f"Seebeck Measurement #{measurement_id}  ·  Sample: {m.sample_id or '—'}  ·  Operator: {m.operator or '—'}"
        )
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600;"
        )
        hdr.addWidget(title)
        hdr.addStretch()
        # Integrity status (if we have a recorded hash)
        if integ is not None:
            # Recompute hash for verification
            canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            ok = digest == integ.data_hash
            lbl_int = QLabel(
                "Integrity: OK"
                if ok
                else "Integrity: MISMATCH"
            )
            lbl_int.setStyleSheet(
                "color: %s; font-size: 11px; font-weight: 600;"
                % ("#4D7C5F" if ok else "#DC2626")
            )
            hdr.addWidget(lbl_int)
        layout.addLayout(hdr)

        # Export buttons
        btn_row = QHBoxLayout()
        btn_graphs = QPushButton("Save graphs…")
        btn_data = QPushButton("Save data…")
        for b in (btn_graphs, btn_data):
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { background: white; border: 1px solid #C7C0B0; "
                "border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #FBFAF5; }"
            )
        btn_row.addWidget(btn_graphs)
        btn_row.addWidget(btn_data)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        headers = [col[1] for col in _TABLE_COLS]
        keys = [col[0] for col in _TABLE_COLS]

        # Build the three charts (defined before display so we can show the
        # graphs first, then the numbers — like the I-V detail view).
        def _build_charts():
            charts = {}

            # Live chart: Temperature (left) + TEMF (right) vs time — matches G1.
            live = pg.PlotWidget()
            live.setBackground("white")
            live.showGrid(x=True, y=True, alpha=0.25)
            live.setLabel("left", "Temperature (°C)")
            live.setLabel("bottom", "Time (s)")
            pi = live.getPlotItem()
            pi.getAxis("left").setStyle(tickTextOffset=6)
            pi.showAxis("right")
            pi.setLabel("right", "TEMF (mV)")
            pi.getAxis("right").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9), tickTextOffset=6)
            vb_temf = pg.ViewBox()
            pi.scene().addItem(vb_temf)
            pi.getAxis("right").linkToView(vb_temf)
            vb_temf.setXLink(pi)

            def _sync_live():
                vb_temf.setGeometry(pi.vb.sceneBoundingRect())
                vb_temf.linkedViewChanged(pi.vb, vb_temf.XAxis)
            pi.vb.sigResized.connect(_sync_live)
            _sync_live()

            # T₁ red, T₂ blue on the left (Temperature); TEMF green on the right.
            curve_t1 = pi.plot(pen=pg.mkPen("#DC2626", width=2))
            curve_t2 = pi.plot(pen=pg.mkPen("#2563EB", width=2))
            curve_temf = pg.PlotCurveItem(pen=pg.mkPen("#2CA02C", width=2))
            vb_temf.addItem(curve_temf)

            times = [r.get("Time [s]", 0) for r in data]
            temf = [r.get("TEMF [mV]") for r in data]
            t1_vals = [r.get("Temp1 [oC]") for r in data]
            t2_vals = [r.get("Temp2 [oC]") for r in data]

            def _v(lst):
                nan = float("nan")
                return [x if x is not None else nan for x in lst]

            curve_temf.setData(times, _v(temf))
            curve_t1.setData(times, _v(t1_vals))
            curve_t2.setData(times, _v(t2_vals))
            charts["live"] = live

            # TEMF vs ΔT (heating / cooling)
            temf_dt = pg.PlotWidget()
            temf_dt.setBackground("white")
            temf_dt.showGrid(x=True, y=True, alpha=0.25)
            temf_dt.setLabel("left", "TEMF (mV)")
            temf_dt.setLabel("bottom", "ΔT (°C)")
            heating = [r for r in data if r.get("branch") != "cooling"]
            cooling = [r for r in data if r.get("branch") == "cooling"]
            # Bridge cooling to the heating peak so it continues from the peak.
            if heating and cooling:
                cooling = [heating[-1]] + cooling

            def _dt_tf(rows):
                xs, ys = [], []
                for r in rows:
                    dt = r.get("Delta Temp [oC]")
                    tf = r.get("TEMF [mV]")
                    if dt is not None and tf is not None:
                        xs.append(dt)
                        ys.append(tf)
                return xs, ys

            hx, hy = _dt_tf(heating)
            cx, cy = _dt_tf(cooling)
            temf_dt.plot(hx, hy, pen=pg.mkPen("#ED6C02", width=2))
            temf_dt.plot(cx, cy, pen=pg.mkPen("#2563EB", width=2))
            charts["temf_dt"] = temf_dt

            # S vs T0
            s_t0 = pg.PlotWidget()
            s_t0.setBackground("white")
            s_t0.showGrid(x=True, y=True, alpha=0.25)
            s_t0.setLabel("left", "S (µV/K)")
            s_t0.setLabel("bottom", "T₀ (K)")
            t0_vals, s_vals = [], []
            for r in data:
                t0k = r.get("T0 [K]")
                s = r.get("S [µV/K]")
                if t0k is None or s is None:
                    continue
                t0_vals.append(t0k)
                s_vals.append(s)
            s_t0.plot(t0_vals, s_vals, pen=pg.mkPen("#9C27B0", width=2), symbol="o")
            charts["s_t0"] = s_t0

            return charts

        # Graphs first, then the numbers (mirrors the I-V detail layout).
        charts = _build_charts()
        _legends = {
            "live": [("#2CA02C", "TEMF [mV]"), ("#DC2626", "T₁ [°C]"), ("#2563EB", "T₂ [°C]")],
            "temf_dt": [("#ED6C02", "Heating"), ("#2563EB", "Cooling")],
        }
        for _k in ("live", "temf_dt", "s_t0"):
            _c = charts.get(_k)
            if _c is None:
                continue
            if _k in _legends:
                layout.addWidget(SeebeckPage._legend_strip(_legends[_k]))
            _c.setMinimumHeight(220)
            layout.addWidget(_c)

        tbl = QTableWidget(len(data), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setMinimumHeight(260)
        for i, row in enumerate(data):
            for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                val = row.get(key)
                text = "—" if val is None else fmt.format(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(i, j, item)
        layout.addWidget(tbl)

        def _save_graphs():
            base, _ = QFileDialog.getSaveFileName(
                win,
                "Save graphs",
                f"seebeck_{measurement_id}_graphs",
                "PNG images (*.png)",
            )
            if not base:
                return
            root, _ext = os.path.splitext(base)
            paths = []
            for key, suffix in [
                ("live", "live"),
                ("temf_dt", "temf_vs_dt"),
                ("s_t0", "seebeck_vs_t0"),
            ]:
                w = charts[key]
                pix = w.grab()
                if pix.isNull():
                    continue
                path = f"{root}_{suffix}.png"
                pix.save(path, "PNG")
                paths.append(path)
            if paths:
                QMessageBox.information(
                    win,
                    "Save graphs",
                    "Graphs saved as:\n" + "\n".join(os.path.basename(p) for p in paths),
                )

        def _save_data():
            path, selected = QFileDialog.getSaveFileName(
                win,
                "Save data",
                f"seebeck_{measurement_id}_data.xlsx",
                "Excel workbook (*.xlsx);;CSV file (*.csv)",
            )
            if not path:
                return
            if selected.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                headers_local = headers
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers_local)
                    for row in data:
                        writer.writerow(
                            [row.get(k, "") if row.get(k) is not None else "" for k in keys]
                        )
                QMessageBox.information(win, "Save data", f"CSV saved to:\n{path}")
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                wb = Workbook()
                ws = wb.active
                ws.title = "Data"
                ws.append(headers)
                for row in data:
                    ws.append(
                        [row.get(k, "") if row.get(k) is not None else "" for k in keys]
                    )
                # Try to embed graphs if Pillow is installed; otherwise save data only.
                try:
                    import PIL  # type: ignore  # noqa: F401

                    img_start_row = len(data) + 3
                    tmpdir = tempfile.mkdtemp(prefix="seebeck_hist_graphs_")
                    files: list[str] = []

                    for key, name, row_offset in [
                        ("live", "chart_live.png", 0),
                        ("temf_dt", "chart_temf_dt.png", 20),
                        ("s_t0", "chart_s_t0.png", 40),
                    ]:
                        w = charts[key]
                        pix = w.grab()
                        if pix.isNull():
                            continue
                        fp = os.path.join(tmpdir, name)
                        pix.save(fp, "PNG")
                        img = XLImage(fp)
                        cell = f"A{img_start_row + row_offset}"
                        ws.add_image(img, cell)
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
                    QMessageBox.information(
                        win, "Save data", f"Excel workbook saved to:\n{path}"
                    )
                except ImportError:
                    wb.save(path)
                    QMessageBox.warning(
                        win,
                        "Save data",
                        "Excel file saved without embedded graphs.\n\n"
                        "To include graphs inside the Excel workbook, install Pillow in "
                        "the desktop virtual environment:\n\n"
                        "  pip install pillow",
                    )

        btn_graphs.clicked.connect(_save_graphs)
        btn_data.clicked.connect(_save_data)

        win.resize(980, 860)
        win.show()

    # ------------------------------------------------------------------
    # I-V detail view
    # ------------------------------------------------------------------

    def _show_iv_detail(self, m, measurement_id, data, integ):
        """Detail window for a stored I-V sweep: table + I-V chart + fit + export."""
        from ..theme import PRIMARY, WARNING
        from ...services.measurement_service import _linear_fit_resistance, _ohmic_status
        import pyqtgraph as pg
        import os
        import tempfile
        import csv
        import json
        import hashlib
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XLImage

        # The fit isn't persisted — recompute it from the stored points.
        fit_R, fit_R2 = _linear_fit_resistance(data)
        ohmic = _ohmic_status(fit_R2)

        # Bidirectional split (forward vs reverse) from the saved run params.
        try:
            params = json.loads(m.params_json) if getattr(m, "params_json", None) else {}
        except Exception:
            params = {}
        n_fwd = int(params.get("points") or 0)
        bidir = bool(params.get("bidirectional"))

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
            chart.setBackground("white")
            chart.showGrid(x=True, y=True, alpha=0.25)
            chart.getAxis("left").enableAutoSIPrefix(False)
            chart.getAxis("bottom").enableAutoSIPrefix(False)
            chart.setLabel("left", "Current (A)")
            chart.setLabel("bottom", "Voltage (V)")
            chart.setTitle("I-V Characteristic")
            pts = [(r.get("voltage"), r.get("current")) for r in data
                   if r.get("voltage") is not None and r.get("current") is not None]
            # Forward (teal) and reverse (orange), matching the live I-V page.
            if bidir and n_fwd and len(pts) > n_fwd:
                fwd, rev = pts[:n_fwd], pts[n_fwd:]
            else:
                fwd, rev = pts, []
            sc_f = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None), brush=pg.mkBrush(PRIMARY + "CC"))
            sc_f.setData([p[0] for p in fwd], [p[1] for p in fwd])
            chart.addItem(sc_f)
            if rev:
                sc_r = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None), brush=pg.mkBrush(WARNING + "CC"))
                sc_r.setData([p[0] for p in rev], [p[1] for p in rev])
                chart.addItem(sc_r)
            ys = [p[1] for p in pts]
            if fit_R is not None and abs(fit_R) > 1e-12 and ys:
                i_lo, i_hi = min(ys), max(ys)
                chart.plot([fit_R * i_lo, fit_R * i_hi], [i_lo, i_hi],
                           pen=pg.mkPen("#4D7C5F", width=2))
            return chart

        win = QWidget(self, Qt.WindowType.Window)
        win.setWindowTitle(f"Measurement #{measurement_id} — I-V (history)")
        layout = QVBoxLayout(win)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header + integrity
        hdr = QHBoxLayout()
        title = QLabel(
            f"I-V Measurement #{measurement_id}  ·  Sample: {m.sample_id or '—'}  ·  Operator: {m.operator or '—'}"
        )
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600;")
        hdr.addWidget(title)
        hdr.addStretch()
        if integ is not None:
            canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            ok = digest == integ.data_hash
            lbl_int = QLabel("Integrity: OK" if ok else "Integrity: MISMATCH")
            lbl_int.setStyleSheet(
                "color: %s; font-size: 11px; font-weight: 600;"
                % ("#4D7C5F" if ok else "#DC2626")
            )
            hdr.addWidget(lbl_int)
        layout.addLayout(hdr)

        # Fit summary
        parts = []
        if fit_R is not None:
            parts.append(f"R = {fit_R:.6g} Ω")
        if fit_R2 is not None:
            parts.append(f"R² = {fit_R2:.4f}")
        parts.append(f"status = {ohmic}")
        summ = QLabel("    ·    ".join(parts))
        summ.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(summ)

        # Export buttons
        btn_row = QHBoxLayout()
        btn_graph = QPushButton("Save graph…")
        btn_data = QPushButton("Save data…")
        for b in (btn_graph, btn_data):
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { background: white; border: 1px solid #C7C0B0; "
                "border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #FBFAF5; }"
            )
        btn_row.addWidget(btn_graph)
        btn_row.addWidget(btn_data)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Chart
        chart = _build_chart()
        chart.setMinimumHeight(280)
        layout.addWidget(chart)

        # Data table
        tbl = QTableWidget(len(data), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, row in enumerate(_rows()):
            for j, val in enumerate(row):
                text = "—" if val is None else f"{val:.6g}"
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(i, j, it)
        layout.addWidget(tbl)

        def _save_graph():
            path, _ = QFileDialog.getSaveFileName(
                win, "Save graph", f"iv_{measurement_id}.png", "PNG (*.png)"
            )
            if not path:
                return
            pix = _build_chart().grab()
            if pix.isNull():
                QMessageBox.warning(win, "Save graph", "Chart image is empty.")
                return
            pix.save(path, "PNG")
            QMessageBox.information(win, "Save graph", f"Saved to:\n{path}")

        def _save_data():
            path, selected = QFileDialog.getSaveFileName(
                win, "Save data", f"iv_{measurement_id}_data.xlsx",
                "Excel workbook (*.xlsx);;CSV file (*.csv)",
            )
            if not path:
                return
            if selected.startswith("CSV") or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for row in _rows():
                        w.writerow(["" if v is None else v for v in row])
                QMessageBox.information(win, "Save data", f"CSV saved to:\n{path}")
                return
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "Data"
            ws.append(headers)
            for row in _rows():
                ws.append(["" if v is None else v for v in row])
            ws.append([])
            ws.append(["Fit R (Ohm)", fit_R])
            ws.append(["R^2", fit_R2])
            ws.append(["Ohmic status", ohmic])
            try:
                import PIL  # type: ignore  # noqa: F401
                tmpdir = tempfile.mkdtemp(prefix="iv_hist_")
                fp = None
                pix = _build_chart().grab()
                if not pix.isNull():
                    fp = os.path.join(tmpdir, "iv_chart.png")
                    pix.save(fp, "PNG")
                    ws.add_image(XLImage(fp), f"A{len(data) + 8}")
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
                QMessageBox.information(win, "Save data", f"Excel workbook saved to:\n{path}")
            except ImportError:
                wb.save(path)
                QMessageBox.warning(
                    win, "Save data",
                    "Excel file saved without the embedded graph.\n\n"
                    "To include the graph, install Pillow:\n  pip install pillow",
                )

        btn_graph.clicked.connect(_save_graph)
        btn_data.clicked.connect(_save_data)

        win.resize(900, 640)
        win.show()

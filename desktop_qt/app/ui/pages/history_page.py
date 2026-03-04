"""Measurement History page — list of past sessions from the database."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QPushButton, QFileDialog, QMessageBox,
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
            f"QTableWidget::item:alternate {{ background: #F9FAFB; }}"
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
        from ...models.db_models import Measurement, MeasurementRow
        import json

        db = SessionLocal()
        try:
            m = db.query(Measurement).filter_by(id=measurement_id).first()
            if not m:
                QMessageBox.warning(self, "History", "Measurement not found in database.")
                return
            if m.type != "seebeck":
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
        finally:
            db.close()

        if not data:
            QMessageBox.information(
                self, "History", "This measurement has no stored data rows."
            )
            return

        # Lazy import to avoid circulars
        from .seebeck_page import _TABLE_COLS
        from ..theme import PRIMARY
        import pyqtgraph as pg
        import os
        import tempfile
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XLImage
        import csv

        # Build a simple detail window inline to avoid another file.
        win = QWidget(self, Qt.WindowType.Window)
        win.setWindowTitle(f"Measurement #{measurement_id} — Seebeck (history)")
        layout = QVBoxLayout(win)
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
        layout.addLayout(hdr)

        # Export buttons
        btn_row = QHBoxLayout()
        btn_graphs = QPushButton("Save graphs…")
        btn_data = QPushButton("Save data…")
        for b in (btn_graphs, btn_data):
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { background: white; border: 1px solid #CBD5E1; "
                "border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #F8FAFC; }"
            )
        btn_row.addWidget(btn_graphs)
        btn_row.addWidget(btn_data)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Data table (read-only)
        headers = [col[1] for col in _TABLE_COLS]
        keys = [col[0] for col in _TABLE_COLS]
        tbl = QTableWidget(len(data), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, row in enumerate(data):
            for j, (key, _, fmt) in enumerate(_TABLE_COLS):
                val = row.get(key)
                text = "—" if val is None else fmt.format(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )
                tbl.setItem(i, j, item)
        layout.addWidget(tbl)

        # Helper: rebuild charts off-screen for export
        def _build_charts():
            charts = {}

            # Live chart: TEMF + T1/T2 vs time
            live = pg.PlotWidget()
            live.setBackground("white")
            live.showGrid(x=True, y=True, alpha=0.25)
            live.setLabel("left", "TEMF (mV)")
            live.setLabel("bottom", "Time (s)")
            pi = live.getPlotItem()
            pi.showAxis("right")
            pi.setLabel("right", "Temperature (°C)")
            pi.getAxis("right").setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 9))
            vb_temp = pg.ViewBox()
            pi.scene().addItem(vb_temp)
            pi.getAxis("right").linkToView(vb_temp)
            vb_temp.setXLink(pi)

            curve_temf = pi.plot(pen=pg.mkPen("#7C3AED", width=2))
            curve_t1 = pg.PlotCurveItem(pen=pg.mkPen("#2563EB", width=2))
            curve_t2 = pg.PlotCurveItem(pen=pg.mkPen("#DC2626", width=2))
            vb_temp.addItem(curve_t1)
            vb_temp.addItem(curve_t2)

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
            heat_x, heat_y, cool_x, cool_y = [], [], [], []
            for r in data:
                dt = r.get("Delta Temp [oC]")
                tf = r.get("TEMF [mV]")
                if dt is None or tf is None:
                    continue
                if r.get("branch") == "cooling":
                    cool_x.append(dt)
                    cool_y.append(tf)
                else:
                    heat_x.append(dt)
                    heat_y.append(tf)
            temf_dt.plot(heat_x, heat_y, pen=pg.mkPen("#ED6C02", width=2))
            temf_dt.plot(cool_x, cool_y, pen=pg.mkPen("#2563EB", width=2))
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
            charts = _build_charts()
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

                    charts = _build_charts()
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

        win.resize(900, 600)
        win.show()

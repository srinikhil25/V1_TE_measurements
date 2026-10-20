"""Overview — what is running, which instruments answer, system health, recent runs."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme as T
from ..widgets.run_state import fmt_elapsed, instrument_status
from ..widgets.ui_kit import (
    Chip, Dot, EmptyState, KeyValueList, Panel, STATUS_CHIP, button, cell, chip_cell,
    hbox, label, make_table, page_scaffold, set_props,
)

_TYPE_LABEL = {"seebeck": "Seebeck", "iv": "I-V"}


def _greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"


class DashboardPage(QWidget):

    def __init__(self, user, navigate_cb: Callable, run_state=None):
        super().__init__()
        self._user = user
        self._navigate = navigate_cb
        self._run_state = run_state
        self._inst_rows = {}
        self._build_ui()
        instrument_status().updated.connect(self._on_scan)
        if run_state is not None:
            run_state.changed.connect(self._on_run_state)
            self._on_run_state(run_state.state)
        self._on_scan(instrument_status().available)

    # ------------------------------------------------------------------
    def _build_ui(self):
        can_measure = self._user.role in ("super_admin", "lab_admin", "researcher")
        tb, body = page_scaffold(
            self, "Overview",
            f"{_greeting()}, {self._user.username} · {datetime.now():%A %d %B %Y}",
            scroll=True)
        if can_measure:
            b_iv = button("New I-V sweep", icon="iv")
            b_iv.clicked.connect(lambda: self._navigate("iv"))
            b_sb = button("New Seebeck run", "primary", icon="seebeck")
            b_sb.clicked.connect(lambda: self._navigate("seebeck"))
            tb.add_action(b_iv)
            tb.add_action(b_sb)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self._build_run_panel(), 0, 0)
        grid.addWidget(self._build_instruments_panel(), 0, 1)
        grid.addWidget(self._build_system_panel(), 0, 2)
        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 4)
        body.addLayout(grid)
        body.addWidget(self._build_recent_panel(), 1)

    # ── Current run ───────────────────────────────────────────────────
    def _build_run_panel(self) -> Panel:
        p = Panel("Current run")
        self.run_chip = Chip("Idle", "neutral")
        p.add_action(self.run_chip)
        self.lbl_run_title = label("No measurement running", "h1")
        self.lbl_run_time = label("", "readout", scale="lg")
        self.lbl_run_time.setVisible(False)
        self.lbl_run_sub = label("Start a Seebeck run or an I-V sweep from the toolbar.",
                                 "secondary", wrap=True)
        p.body.addWidget(self.lbl_run_title)
        p.body.addWidget(self.lbl_run_time)
        p.body.addWidget(self.lbl_run_sub)
        p.body.addStretch()
        self.btn_open_run = button("Open live view", icon="external", size="sm")
        self.btn_open_run.setVisible(False)
        self.btn_open_run.clicked.connect(self._open_run)
        self.lbl_last = label("", "caption", wrap=True)
        p.body.addWidget(self.lbl_last)
        p.body.addLayout(hbox(self.btn_open_run, None))
        p.setMinimumHeight(220)
        return p

    def _open_run(self):
        st = self._run_state.state if self._run_state else {}
        self._navigate("iv" if st.get("kind") == "iv" else "seebeck")

    def _on_run_state(self, st: dict):
        if st.get("running"):
            self.run_chip.set("Running", "success")
            self.lbl_run_title.setText(st.get("label", "Measurement")
                                       + (f"  #{st['measurement_id']}" if st.get("measurement_id") else ""))
            self.lbl_run_time.setText(fmt_elapsed(st.get("elapsed_s")))
            self.lbl_run_time.setVisible(True)
            sub = []
            if st.get("phase"):
                sub.append("Phase: " + st["phase"].replace("_", " "))
            if st.get("db_warning"):
                sub.append("NOT SAVING — " + str(st["db_warning"]))
            elif st.get("running"):
                sub.append("Saving every reading to the database")
            self.lbl_run_sub.setText(" · ".join(sub))
            self.btn_open_run.setVisible(True)
        else:
            self.run_chip.set("Idle", "neutral")
            self.lbl_run_title.setText("No measurement running")
            self.lbl_run_time.setVisible(False)
            self.lbl_run_sub.setText("Start a Seebeck run or an I-V sweep from the toolbar.")
            self.btn_open_run.setVisible(False)

    # ── Instruments ───────────────────────────────────────────────────
    def _build_instruments_panel(self) -> Panel:
        p = Panel("Instruments", flush=True)
        self.btn_scan = button("Check now", icon="refresh", size="sm",
                               tooltip="Look for the configured addresses on the GPIB bus. "
                                       "Skipped while a measurement is running.")
        self.btn_scan.clicked.connect(self._rescan)
        p.add_action(self.btn_scan)
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(12, 10, 12, 10)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        from ...services.instrument_scan import INSTRUMENTS, instrument_addresses
        roles = {k: r for k, _s, _f, r in INSTRUMENTS}
        for r, (key, _short, full, addr) in enumerate(instrument_addresses()):
            dot = Dot(T.TEXT_DISABLED, 8, hollow=True)
            name = QWidget()
            nl = QVBoxLayout(name)
            nl.setContentsMargins(0, 0, 0, 0)
            nl.setSpacing(0)
            nl.addWidget(label(full, "body"))
            nl.addWidget(label(roles.get(key, ""), "caption"))
            a = label(addr, "mono")
            a.setStyleSheet(f"color: {T.TEXT_SECONDARY};")
            chip = Chip("Not checked", "neutral")
            g.addWidget(dot, r, 0, Qt.AlignmentFlag.AlignVCenter)
            g.addWidget(name, r, 1)
            g.addWidget(a, r, 2)
            g.addWidget(chip, r, 3, Qt.AlignmentFlag.AlignRight)
            self._inst_rows[addr] = (dot, chip)
        g.setColumnStretch(1, 1)
        p.body.addWidget(box)
        self.lbl_scan = label("", "caption")
        p.show_footer(self.lbl_scan, None)
        return p

    def _rescan(self):
        if instrument_status().refresh():
            self.lbl_scan.setText("Checking the GPIB bus…")
        else:
            self.lbl_scan.setText("Not checked — a measurement is running (scanning the bus "
                                  "could disturb the instruments).")

    def _on_scan(self, available):
        st = instrument_status()
        for addr, (dot, chip) in self._inst_rows.items():
            state = st.state_of(addr) if st.scanned_at else "unknown"
            if state == "online":
                dot.set_color(T.SUCCESS)
                chip.set("Answering", "success")
            elif state == "offline":
                dot.set_color(T.DANGER, hollow=True)
                chip.set("Not found", "danger")
            else:
                dot.set_color(T.TEXT_DISABLED, hollow=True)
                chip.set("VISA unavailable" if st.scanned_at else "Not checked", "neutral")
        if st.scanned_at:
            self.lbl_scan.setText(f"Last checked {datetime.fromtimestamp(st.scanned_at):%H:%M:%S}"
                                  + ("" if available is not None else " · NI-VISA not found"))

    # ── System ────────────────────────────────────────────────────────
    def _build_system_panel(self) -> Panel:
        p = Panel("System")
        self.kv_sys = KeyValueList(key_width=110)
        p.body.addWidget(self.kv_sys)
        p.body.addStretch()
        return p

    def _refresh_system(self):
        kv = self.kv_sys
        try:
            from ...core.config import get_config, load_warnings
            s = get_config().safety
            kv.set("Safety limits", f"{s.max_temperature_C:g} °C max · {s.max_rise_rate_C_per_min:g} °C/min")
            problems = load_warnings()
            kv.set("Configuration", f"{len(problems)} problem(s) — defaults in use" if problems
                   else "OK", tone="warning" if problems else "success")
        except Exception as exc:
            kv.set("Configuration", f"unreadable ({exc})", tone="danger")
        try:
            from ...core.backup import list_backups
            b = list_backups()
            if b:
                ts = datetime.fromtimestamp(os.path.getmtime(b[0]))
                kv.set("Last backup", f"{ts:%Y-%m-%d %H:%M} · {len(b)} kept",
                       tooltip=str(b[0]))
            else:
                kv.set("Last backup", "none yet", tone="warning")
        except Exception:
            kv.set("Last backup", "unknown", tone="muted")
        if self._user.role in ("super_admin", "lab_admin"):
            try:
                from ...core import audit
                res = audit.verify_chain()
                if res.get("ok"):
                    kv.set("Audit trail", f"Verified · {res.get('count', 0)} entries", tone="success")
                else:
                    kv.set("Audit trail", f"FAILED at #{res.get('first_bad_id')}", tone="danger")
            except Exception:
                kv.set("Audit trail", "not checked", tone="muted")
        try:
            from ...core.paths import get_db_path
            path = get_db_path()
            size = os.path.getsize(path) / 1e6
            kv.set("Database", f"{size:.1f} MB", tooltip=path)
        except Exception:
            pass

    # ── Recent runs ───────────────────────────────────────────────────
    def _build_recent_panel(self) -> Panel:
        p = Panel("Recent runs", flush=True)
        b = button("Open run library", "ghost", icon="chevron-right", size="sm")
        b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        b.clicked.connect(lambda: self._navigate("history"))
        p.add_action(b)
        self.tbl_recent = make_table(["Run", "Type", "Sample", "Operator", "Started", "Status", "Note"])
        self.tbl_recent.setMinimumHeight(260)
        for i, w in enumerate((70, 90, 180, 120, 150, 120)):
            self.tbl_recent.setColumnWidth(i, w)
        self.tbl_recent.cellDoubleClicked.connect(lambda *_: self._navigate("history"))
        p.body.addWidget(self.tbl_recent)
        self.recent_empty = EmptyState("history", "No runs yet",
                                       "Finished measurements will appear here.")
        self.recent_empty.setVisible(False)
        p.body.addWidget(self.recent_empty)
        return p

    def _refresh_recent(self):
        from ...core.database import SessionLocal
        from ...models.db_models import Measurement
        db = SessionLocal()
        try:
            q = db.query(Measurement)
            if self._user.role == "researcher":
                q = q.filter_by(user_id=self._user.id)
            elif self._user.role == "lab_admin":
                q = q.filter_by(lab_id=self._user.lab_id)
            rows = q.order_by(Measurement.started_at.desc()).limit(10).all()
            data = [(m.id, m.type, m.sample_id, m.operator, m.started_at, m.status, m.end_reason)
                    for m in rows]
        except Exception:
            data = []
        finally:
            db.close()
        t = self.tbl_recent
        t.setRowCount(len(data))
        for r, (mid, typ, sample, op, started, status, reason) in enumerate(data):
            t.setItem(r, 0, cell(f"#{mid}", mono=True))
            t.setItem(r, 1, cell(_TYPE_LABEL.get(typ, typ or "—")))
            t.setItem(r, 2, cell(sample or "—"))
            t.setItem(r, 3, cell(op or "—"))
            t.setItem(r, 4, cell(started.strftime("%Y-%m-%d %H:%M") if started else "—", mono=True))
            text, kind = STATUS_CHIP.get((status or "").lower(), ((status or "—").title(), "neutral"))
            t.setItem(r, 5, cell(text))
            chip_cell(t, r, 5, text, kind, tooltip=reason or "")
            t.setItem(r, 6, cell(reason or "", tooltip=reason or "", color=T.TEXT_SECONDARY))
        self.tbl_recent.setVisible(bool(data))
        self.recent_empty.setVisible(not data)
        if data:
            mid, typ, sample, _op, started, status, _r = data[0]
            self.lbl_last.setText(
                f"Last run: #{mid} {_TYPE_LABEL.get(typ, typ)} · {sample or 'no sample ID'} · "
                f"{STATUS_CHIP.get((status or '').lower(), (status or '—',))[0]}"
                + (f" · {started:%Y-%m-%d %H:%M}" if started else ""))

    # ------------------------------------------------------------------
    def refresh(self):
        self._refresh_recent()
        self._refresh_system()

    def on_shown(self):
        self.refresh()

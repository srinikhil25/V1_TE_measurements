"""Audit trail — read-only view of the append-only, hash-chained audit trail (admins)."""

import json
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QWidget,
)

from .. import theme as T
from ..icons import icon as _icon
from ..widgets.ui_kit import (
    Callout,
    EmptyState,
    KeyValueList,
    Panel,
    button,
    cell,
    label,
    make_table,
    page_scaffold,
)

_HEADERS = ["#", "Time", "User", "Event", "Run", "Details", "Reason"]

# Events shown in red: something went wrong or was refused.
_PROBLEM_ACTIONS = {"login_failed"}


def _local_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return iso or "—"


def _summary(details) -> str:
    """Compact one-line rendering of an entry's details."""
    if not details:
        return ""
    if isinstance(details, dict) and "changes" in details and isinstance(details["changes"], dict):
        parts = []
        for k, v in details["changes"].items():
            if isinstance(v, list) and len(v) == 2:
                parts.append(f"{k}: {v[0]} → {v[1]}")
            else:
                parts.append(f"{k}: {v}")
        return "; ".join(parts)
    if isinstance(details, dict):
        keep = {k: v for k, v in details.items() if k not in ("params", "safety", "run_context")}
        return ", ".join(f"{k}={v}" for k, v in keep.items())
    return str(details)


def _is_problem(r) -> bool:
    return r["action"] in _PROBLEM_ACTIONS or (
        r["action"] == "run_ended" and (r["details"] or {}).get("outcome") in ("aborted", "error"))


class AuditPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._rows = []
        self._build_ui()
        self._load()
        self._verify(quiet=True)

    def _build_ui(self):
        tb, body = page_scaffold(
            self, "Audit trail",
            "Sign-ins, configuration changes, runs, exports, backups and schema upgrades. "
            "Entries cannot be edited or deleted.")
        b_refresh = button("Refresh", icon="refresh", tooltip="Reload the newest 1000 entries.")
        b_refresh.clicked.connect(self._load)
        b_backup = button("Back up database", icon="database",
                          tooltip="Write a verified copy of the database to the backups folder.")
        b_backup.clicked.connect(self._backup_now)
        b_verify = button("Verify integrity", "primary", icon="shield",
                          tooltip="Recompute the SHA-256 hash chain over every entry.")
        b_verify.clicked.connect(lambda: self._verify(quiet=False))
        for b in (b_refresh, b_backup, b_verify):
            tb.add_action(b)

        self.banner = Callout("Checking the hash chain…", "info", title="Integrity")
        body.addWidget(self.banner)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.inp_filter = QLineEdit()
        self.inp_filter.setPlaceholderText("Filter by user, event, run, text…")
        self.inp_filter.addAction(_icon("search", T.TEXT_MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.inp_filter.setClearButtonEnabled(True)
        self.inp_filter.textChanged.connect(self._apply_filter)
        bar.addWidget(self.inp_filter, 2)
        self.cb_event = QComboBox()
        self.cb_event.addItem("All events", None)
        from ...core.audit import ACTIONS
        for key, text in ACTIONS.items():
            self.cb_event.addItem(text, key)
        self.cb_event.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.cb_event, 1)
        self.chk_problems = QCheckBox("Only problems")
        self.chk_problems.toggled.connect(lambda _c: self._apply_filter())
        bar.addWidget(self.chk_problems)
        bar.addStretch(1)
        body.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        split.setStyleSheet("QSplitter::handle { background: transparent; }")

        tp = Panel(flush=True)
        self.table = make_table(_HEADERS)
        for i, w in enumerate((60, 150, 110, 200, 60, 340)):
            self.table.setColumnWidth(i, w)
        self.table.itemSelectionChanged.connect(self._on_select)
        tp.body.addWidget(self.table)
        self.empty = EmptyState("audit", "No entries match", "Change the filter.")
        self.empty.setVisible(False)
        tp.body.addWidget(self.empty)
        self.lbl_status = label("", "caption")
        tp.show_footer(self.lbl_status, None)
        split.addWidget(tp)

        dp = Panel("Entry")
        dp.setMinimumWidth(320)
        dp.setMaximumWidth(460)
        self.kv = KeyValueList(key_width=84)
        dp.body.addWidget(self.kv)
        dp.body.addWidget(label("DETAILS", "overline"))
        self.txt_details = QPlainTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setProperty("mono", True)
        self.txt_details.setStyleSheet(f"font-family: '{T.mono_family()}'; font-size: 12px;")
        dp.body.addWidget(self.txt_details, 1)
        split.addWidget(dp)
        split.setSizes([900, 360])
        body.addWidget(split, 1)

    # ------------------------------------------------------------------
    def _load(self):
        from ...core import audit
        try:
            self._rows = audit.recent(limit=1000)
        except Exception as exc:
            self._rows = []
            self.lbl_status.setText(f"Could not read the audit trail: {exc}")
        t = self.table
        t.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            problem = _is_problem(r)
            color = T.DANGER if problem else None
            values = [
                (str(r.get("id", "")), dict(mono=True, align="right", color=T.TEXT_MUTED)),
                (_local_time(r["timestamp"]), dict(mono=True)),
                (r["username"] or "—", {}),
                (audit.describe(r["action"]), dict(bold=problem)),
                (f"#{r['measurement_id']}" if r["measurement_id"] is not None else "",
                 dict(mono=True)),
                (_summary(r["details"]), dict(color=T.TEXT_SECONDARY)),
                (r["reason"] or "", {}),
            ]
            for j, (val, kw) in enumerate(values):
                kw = dict(kw)
                if color and j in (3,):
                    kw["color"] = color
                it = cell(val, tooltip=val if j in (5, 6) and val else "", **kw)
                it.setData(Qt.ItemDataRole.UserRole, i)
                t.setItem(i, j, it)
        if self._rows:
            self.lbl_status.setText(f"Newest {len(self._rows)} entries")
        self._apply_filter(self.inp_filter.text())

    def _apply_filter(self, *_):
        t = self.inp_filter.text().strip().lower()
        action = self.cb_event.currentData()
        problems = self.chk_problems.isChecked()
        shown = 0
        for i in range(self.table.rowCount()):
            r = self._rows[i] if i < len(self._rows) else None
            ok = (r is not None
                  and not (action and r["action"] != action)
                  and not (problems and not _is_problem(r)))
            if ok and t:
                hay = " ".join((self.table.item(i, j).text() if self.table.item(i, j) else "")
                               for j in range(self.table.columnCount())).lower()
                ok = t in hay
            self.table.setRowHidden(i, not ok)
            shown += ok
        self.table.setVisible(shown > 0 or not self._rows)
        self.empty.setVisible(shown == 0 and bool(self._rows))
        if self._rows:
            self.lbl_status.setText(f"Showing {shown} of the newest {len(self._rows)} entries")

    def _on_select(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        from ...core import audit
        self.kv.set("Entry", f"#{r.get('id', '')}")
        self.kv.set("Time", _local_time(r["timestamp"]))
        self.kv.set("User", r["username"] or "—")
        self.kv.set("Event", audit.describe(r["action"]), tone="danger" if _is_problem(r) else None)
        self.kv.set("Run", f"#{r['measurement_id']}" if r["measurement_id"] is not None else "—")
        self.kv.set("Reason", r["reason"] or "—")
        self.txt_details.setPlainText(
            json.dumps(r["details"], indent=2, ensure_ascii=False, default=str)
            if r["details"] else "No details recorded.")

    def _verify(self, quiet: bool = False):
        from ...core import audit
        try:
            res = audit.verify_chain()
        except Exception as exc:
            self._set_banner("danger", f"The audit trail could not be checked: {exc}")
            return
        if res["ok"]:
            self._set_banner("success", f"Hash chain intact — all {res['count']} entries verified "
                                        f"at {datetime.now():%H:%M:%S}.")
        else:
            self._set_banner("danger", f"Verification FAILED at entry #{res['first_bad_id']}: "
                                       f"{res['problem']}. Compare with the daily backups and "
                                       "report it to the lab administrator.")
            if not quiet:
                QMessageBox.critical(
                    self, "Audit trail integrity",
                    f"The audit trail failed verification at entry #{res['first_bad_id']} "
                    f"({res['problem']}).\n\nCompare with the daily backups and report it "
                    "to the lab administrator.")

    def _set_banner(self, kind: str, text: str):
        self.banner.set(text, kind)

    def _backup_now(self):
        from ...core import audit
        from ...core.backup import backup_now
        from ...core.paths import get_db_path
        try:
            path = backup_now(get_db_path(), tag="manual")
        except Exception as exc:
            QMessageBox.critical(self, "Back up database", f"Backup failed:\n{exc}")
            return
        audit.record("db_backup", details={"file": path.name, "manual": True})
        QMessageBox.information(self, "Back up database", f"Verified backup written to:\n{path}")
        self._load()

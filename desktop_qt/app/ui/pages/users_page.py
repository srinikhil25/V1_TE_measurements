"""Users — account management (super_admin only)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...core import audit
from .. import theme as T
from ..icons import icon as _icon
from ..widgets.ui_kit import (
    ROLE_LABELS,
    EmptyState,
    Panel,
    button,
    cell,
    chip_cell,
    field,
    hide_item_text,
    initials,
    label,
    make_table,
    page_scaffold,
)

_ROLES = ["researcher", "lab_admin", "super_admin"]
_ROLE_HELP = {
    "researcher":  "Runs measurements and sees their own runs.",
    "lab_admin":   "Sees the lab's runs, the audit trail and can change the rig configuration.",
    "super_admin": "Full access, including user accounts.",
}


class _UserDialog(QDialog):
    """Add / edit user dialog."""

    def __init__(self, parent=None, user_data: dict | None = None):
        super().__init__(parent)
        self._editing = user_data is not None
        self.setWindowTitle("Edit user" if self._editing else "Add user")
        self.setFixedWidth(440)
        self._build(user_data or {})

    def _build(self, data: dict):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(label("Edit user" if self._editing else "Add user", "h1"))
        lay.addWidget(label("Changes are recorded in the audit trail.", "secondary"))

        self.inp_username = QLineEdit(data.get("username", ""))
        self.inp_email = QLineEdit(data.get("email", ""))
        self.inp_email.setPlaceholderText("name@example.ac.jp")
        self.inp_password = QLineEdit()
        self.inp_password.setPlaceholderText(
            "Leave blank to keep the current password" if self._editing else "At least 6 characters")
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.cb_role = QComboBox()
        for r in _ROLES:
            self.cb_role.addItem(ROLE_LABELS.get(r, r), r)
        if data.get("role") in _ROLES:
            self.cb_role.setCurrentIndex(_ROLES.index(data["role"]))
        self.lbl_role_help = label("", "caption", wrap=True)
        self.cb_role.currentIndexChanged.connect(self._on_role)
        self._on_role()

        self.chk_active = QCheckBox("Account is active (can sign in)")
        self.chk_active.setChecked(data.get("active", True))

        lay.addWidget(field("Username", self.inp_username, required=True))
        lay.addWidget(field("Email", self.inp_email, required=True))
        lay.addWidget(field("Password", self.inp_password, required=not self._editing))
        lay.addWidget(field("Role", self.cb_role))
        lay.addWidget(self.lbl_role_help)
        lay.addWidget(self.chk_active)

        self.lbl_err = label("", "error", wrap=True)
        self.lbl_err.setVisible(False)
        lay.addWidget(self.lbl_err)

        div = QFrame()
        div.setObjectName("Divider")
        lay.addWidget(div)
        row = QHBoxLayout()
        row.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        save = button("Save" if self._editing else "Create user", "primary")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(save)
        lay.addLayout(row)

    def _on_role(self, *_):
        self.lbl_role_help.setText(_ROLE_HELP.get(self.cb_role.currentData(), ""))

    def _accept(self):
        v = self.get_values()
        problems = []
        if not v["username"]:
            problems.append("Enter a username.")
        if not v["email"] or "@" not in v["email"]:
            problems.append("Enter a valid email address.")
        if not self._editing and not v["password"]:
            problems.append("Enter a password for the new account.")
        if v["password"] and len(v["password"]) < 6:
            problems.append("The password must be at least 6 characters.")
        if problems:
            self.lbl_err.setText(" ".join(problems))
            self.lbl_err.setVisible(True)
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "username": self.inp_username.text().strip(),
            "email":    self.inp_email.text().strip(),
            "password": self.inp_password.text() or None,
            "role":     self.cb_role.currentData() or "researcher",
            "active":   self.chk_active.isChecked(),
        }


class UsersPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._users = []
        self._build_ui()
        self._load()

    def _build_ui(self):
        tb, body = page_scaffold(self, "Users", "")
        self.toolbar = tb
        self.btn_add = button("Add user", "primary", icon="user-plus")
        self.btn_add.clicked.connect(self._add_user)
        tb.add_action(self.btn_add)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Search name or email…")
        self.inp_search.addAction(_icon("search", T.TEXT_MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.inp_search.setClearButtonEnabled(True)
        self.inp_search.setMaximumWidth(360)
        self.inp_search.textChanged.connect(self._apply_filter)
        bar.addWidget(self.inp_search, 1)
        self.cb_role = QComboBox()
        self.cb_role.addItem("All roles", None)
        for r in _ROLES:
            self.cb_role.addItem(ROLE_LABELS.get(r, r), r)
        self.cb_role.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.cb_role)
        self.chk_inactive = QCheckBox("Show inactive accounts")
        self.chk_inactive.setChecked(True)
        self.chk_inactive.toggled.connect(lambda _c: self._apply_filter())
        bar.addWidget(self.chk_inactive)
        bar.addStretch(1)
        body.addLayout(bar)

        p = Panel(flush=True)
        self.table = make_table(["User", "Email", "Role", "Status", "Last sign-in", "Created", ""],
                                row_height=44)
        for i, w in enumerate((220, 240, 130, 110, 150, 120)):
            self.table.setColumnWidth(i, w)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._edit_row(r))
        p.body.addWidget(self.table)
        self.empty = EmptyState("users", "No users match", "Change the search or filters.")
        self.empty.setVisible(False)
        p.body.addWidget(self.empty)
        body.addWidget(p, 1)

    def _load(self):
        from ...core.database import SessionLocal
        from ...models.db_models import User

        db = SessionLocal()
        try:
            self._users: list[dict] = [dict(id=u.id, username=u.username, email=u.email, role=u.role,
                                active=u.active, last_login=u.last_login, created_at=u.created_at)
                           for u in db.query(User).order_by(User.id).all()]
        finally:
            db.close()

        t = self.table
        t.setRowCount(len(self._users))
        for i, u in enumerate(self._users):
            t.setItem(i, 0, cell(u["username"]))
            t.setCellWidget(i, 0, self._user_cell(u))
            hide_item_text(t, i, 0)
            t.setItem(i, 1, cell(u["email"] or "—", color=T.TEXT_SECONDARY))
            role_text = ROLE_LABELS.get(u["role"]) or str(u["role"])
            t.setItem(i, 2, cell(role_text))
            chip_cell(t, i, 2, role_text, "info" if u["role"] != "researcher" else "neutral",
                      tooltip=_ROLE_HELP.get(u["role"], ""))
            st = "Active" if u["active"] else "Disabled"
            t.setItem(i, 3, cell(st))
            chip_cell(t, i, 3, st, "success" if u["active"] else "neutral")
            t.setItem(i, 4, cell(u["last_login"].strftime("%Y-%m-%d %H:%M") if u["last_login"] else "never",
                                 mono=bool(u["last_login"]), color=T.TEXT_SECONDARY))
            t.setItem(i, 5, cell(u["created_at"].strftime("%Y-%m-%d") if u["created_at"] else "—",
                                 mono=True, color=T.TEXT_SECONDARY))
            host = QWidget()
            hl = QHBoxLayout(host)
            hl.setContentsMargins(8, 0, 8, 0)
            hl.addStretch()
            b = button("Edit", size="sm", icon="edit")
            b.clicked.connect(lambda _=False, uid=u["id"]: self._edit_user(uid))
            hl.addWidget(b)
            t.setCellWidget(i, 6, host)
            for c in range(7):
                it = t.item(i, c) or cell("")
                it.setData(Qt.ItemDataRole.UserRole, u["id"])
                t.setItem(i, c, it)
        active = sum(1 for u in self._users if u["active"])
        self.toolbar.set_subtitle(f"{len(self._users)} accounts · {active} active")
        self._apply_filter()

    def _user_cell(self, u) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(10)
        av = label(initials(u["username"]))
        av.setFixedSize(28, 28)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(f"background: {T.ACCENT_SOFT if u['active'] else T.SURFACE_SUNKEN}; "
                         f"color: {T.ACCENT_TEXT if u['active'] else T.TEXT_MUTED}; "
                         "border-radius: 14px; font-size: 11px; font-weight: 700;")
        lay.addWidget(av)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(u["username"], "body"))
        col.addWidget(label(f"ID {u['id']}" + ("  ·  you" if u["id"] == self._user.id else ""),
                            "caption"))
        lay.addLayout(col)
        lay.addStretch()
        return w

    def _apply_filter(self, *_):
        text = self.inp_search.text().strip().lower()
        role = self.cb_role.currentData()
        show_inactive = self.chk_inactive.isChecked()
        shown = 0
        for i, u in enumerate(self._users):
            ok = (not role or u["role"] == role) and (show_inactive or u["active"])
            if ok and text:
                ok = text in f"{u['username']} {u['email']}".lower()
            self.table.setRowHidden(i, not ok)
            shown += ok
        self.table.setVisible(shown > 0)
        self.empty.setVisible(shown == 0)

    def _edit_row(self, row: int):
        it = self.table.item(row, 1)
        if it is not None:
            self._edit_user(it.data(Qt.ItemDataRole.UserRole))

    # ------------------------------------------------------------------
    def _add_user(self):
        dlg = _UserDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if not vals["username"] or not vals["email"] or not vals["password"]:
            QMessageBox.warning(self, "Add user", "Username, email and password are required.")
            return
        from ...core.database import SessionLocal
        from ...core.security import hash_password
        from ...models.db_models import User

        db = SessionLocal()
        try:
            user = User(
                username=vals["username"],
                email=vals["email"],
                password_hash=hash_password(vals["password"]),
                role=vals["role"],
                active=vals["active"],
            )
            db.add(user)
            db.commit()
            audit.record("user_created", details={
                "user_id": user.id, "username": user.username,
                "role": user.role, "active": user.active})
        except Exception as exc:
            db.rollback()
            QMessageBox.critical(self, "Add user",
                                 f"The account could not be created:\n{exc}\n\n"
                                 "The username and email must be unique.")
        finally:
            db.close()
        self._load()

    def _edit_user(self, uid: int):
        from ...core.database import SessionLocal
        from ...core.security import hash_password
        from ...models.db_models import User

        db = SessionLocal()
        try:
            u = db.query(User).filter_by(id=uid).first()
            if not u:
                return
            data = {"id": u.id, "username": u.username, "email": u.email,
                    "role": u.role, "active": u.active}
        finally:
            db.close()

        dlg = _UserDialog(self, data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if uid == self._user.id and (not vals["active"] or vals["role"] != "super_admin"):
            QMessageBox.warning(self, "Edit user",
                                "You cannot disable your own account or remove your own "
                                "super-admin role.")
            return

        db2 = SessionLocal()
        try:
            u = db2.query(User).filter_by(id=uid).first()
            if u:
                before = {"username": u.username, "email": u.email,
                          "role": u.role, "active": u.active}
                u.username = vals["username"]
                u.email = vals["email"]
                u.role = vals["role"]
                u.active = vals["active"]
                if vals["password"]:
                    u.password_hash = hash_password(vals["password"])
                db2.commit()
                after = {"username": u.username, "email": u.email,
                         "role": u.role, "active": u.active}
                changes: dict = {k: [before[k], after[k]] for k in before
                                 if before[k] != after[k]}
                if vals["password"]:
                    changes["password"] = "reset by admin"
                audit.record("user_updated", details={"user_id": uid, "changes": changes})
        except Exception as exc:
            db2.rollback()
            QMessageBox.critical(self, "Edit user", f"The changes could not be saved:\n{exc}")
        finally:
            db2.close()
        self._load()

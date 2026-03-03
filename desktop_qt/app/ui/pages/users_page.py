"""User Management page — super_admin only."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QFormLayout, QLineEdit, QComboBox, QCheckBox, QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ERROR,
)


class _UserDialog(QDialog):
    """Add / Edit user dialog."""

    def __init__(self, parent=None, user_data: dict = None):
        super().__init__(parent)
        self._editing = user_data is not None
        self.setWindowTitle("Edit User" if self._editing else "Add User")
        self.setFixedWidth(400)
        self._build(user_data or {})

    def _build(self, data: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.inp_username = QLineEdit(data.get("username", ""))
        self.inp_email    = QLineEdit(data.get("email", ""))
        self.inp_password = QLineEdit()
        self.inp_password.setPlaceholderText(
            "Leave blank to keep current" if self._editing else "Required"
        )
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.cb_role = QComboBox()
        self.cb_role.addItems(["researcher", "lab_admin", "super_admin"])
        if data.get("role"):
            idx = self.cb_role.findText(data["role"])
            if idx >= 0:
                self.cb_role.setCurrentIndex(idx)

        self.chk_active = QCheckBox("Active")
        self.chk_active.setChecked(data.get("active", True))

        form.addRow("Username",  self.inp_username)
        form.addRow("Email",     self.inp_email)
        form.addRow("Password",  self.inp_password)
        form.addRow("Role",      self.cb_role)
        form.addRow("",          self.chk_active)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> dict:
        return {
            "username": self.inp_username.text().strip(),
            "email":    self.inp_email.text().strip(),
            "password": self.inp_password.text() or None,
            "role":     self.cb_role.currentText(),
            "active":   self.chk_active.isChecked(),
        }


class UsersPage(QWidget):

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

        hdr = QHBoxLayout()
        title = QLabel("User Management")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; border: none;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self.btn_add = QPushButton("+ Add User")
        self.btn_add.setFixedHeight(34)
        self.btn_add.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 6px; padding: 0 16px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1D4ED8; }}"
        )
        self.btn_add.clicked.connect(self._add_user)
        hdr.addWidget(self.btn_add)
        v.addLayout(hdr)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Username", "Email", "Role", "Active", "Actions"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; font-size: 13px; }}"
            f"QTableWidget::item:alternate {{ background: #F9FAFB; }}"
        )
        v.addWidget(self.table)

    def _load(self):
        from ...core.database import SessionLocal
        from ...models.db_models import User

        db = SessionLocal()
        try:
            users = db.query(User).order_by(User.id).all()
            self.table.setRowCount(len(users))
            for i, u in enumerate(users):
                self.table.setItem(i, 0, QTableWidgetItem(str(u.id)))
                self.table.setItem(i, 1, QTableWidgetItem(u.username))
                self.table.setItem(i, 2, QTableWidgetItem(u.email))
                self.table.setItem(i, 3, QTableWidgetItem(u.role))
                self.table.setItem(i, 4, QTableWidgetItem("Yes" if u.active else "No"))

                edit_btn = QPushButton("Edit")
                edit_btn.setFixedHeight(26)
                edit_btn.setStyleSheet(
                    f"QPushButton {{ border: 1px solid {BORDER}; border-radius: 4px; "
                    f"font-size: 11px; padding: 0 10px; background: white; }}"
                    f"QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
                )
                edit_btn.clicked.connect(
                    lambda _, uid=u.id: self._edit_user(uid)
                )
                self.table.setCellWidget(i, 5, edit_btn)
        finally:
            db.close()

    def _add_user(self):
        dlg = _UserDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if not vals["username"] or not vals["email"] or not vals["password"]:
            QMessageBox.warning(self, "Validation",
                                "Username, email, and password are required.")
            return
        from ...core.database import SessionLocal
        from ...models.db_models import User
        from ...core.security import hash_password

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
        finally:
            db.close()
        self._load()

    def _edit_user(self, uid: int):
        from ...core.database import SessionLocal
        from ...models.db_models import User
        from ...core.security import hash_password

        db = SessionLocal()
        try:
            u = db.query(User).filter_by(id=uid).first()
            if not u:
                return
            data = {
                "id": u.id, "username": u.username,
                "email": u.email, "role": u.role, "active": u.active,
            }
        finally:
            db.close()

        dlg = _UserDialog(self, data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()

        db2 = SessionLocal()
        try:
            u = db2.query(User).filter_by(id=uid).first()
            if u:
                u.username = vals["username"]
                u.email    = vals["email"]
                u.role     = vals["role"]
                u.active   = vals["active"]
                if vals["password"]:
                    u.password_hash = hash_password(vals["password"])
                db2.commit()
        finally:
            db2.close()
        self._load()

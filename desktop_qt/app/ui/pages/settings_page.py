"""Settings page — GPIB addresses, change password."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QGroupBox, QFormLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SUCCESS, ERROR,
)


def _card(title: str) -> tuple:
    """Return (QFrame card, inner QVBoxLayout)."""
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; }}"
    )
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(12)

    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px; border: none;"
    )
    v.addWidget(lbl)
    return f, v


class SettingsPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(20)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)

        if self._user.role == "super_admin":
            v.addWidget(self._build_gpib_card())

        v.addWidget(self._build_password_card())
        v.addStretch()

    # ── GPIB address card ────────────────────────────────────────────────

    def _build_gpib_card(self) -> QFrame:
        DEFAULT_ADDRS = {
            "Keithley 2182A": "GPIB0::7::INSTR",
            "Keithley 2700":  "GPIB0::16::INSTR",
            "PK160":          "GPIB0::15::INSTR",
            "Keithley 6221":  "GPIB0::24::INSTR",
        }

        card, cv = _card("GPIB Instrument Addresses")

        field_style = (
            f"QLineEdit {{ background: white; border: 1px solid {BORDER}; "
            f"border-radius: 6px; padding: 7px 10px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {PRIMARY}; }}"
        )
        label_style = (
            f"color: {TEXT_SECONDARY}; font-size: 12px; border: none;"
        )

        self._addr_fields = {}
        for name, default in DEFAULT_ADDRS.items():
            row = QHBoxLayout()
            lbl = QLabel(name)
            lbl.setFixedWidth(160)
            lbl.setStyleSheet(label_style)

            inp = QLineEdit(default)
            inp.setStyleSheet(field_style)
            inp.setFixedHeight(36)

            row.addWidget(lbl)
            row.addWidget(inp)
            cv.addLayout(row)
            self._addr_fields[name] = inp

        note = QLabel(
            "Note: GPIB address changes take effect the next time instruments are connected."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border: none;"
        )
        cv.addWidget(note)

        save_btn = QPushButton("Save Addresses")
        save_btn.setFixedHeight(36)
        save_btn.setFixedWidth(160)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1D4ED8; }}"
        )
        save_btn.clicked.connect(self._save_gpib)
        cv.addWidget(save_btn)

        return card

    def _save_gpib(self):
        # Currently saves to in-memory only; extend to DB/config file as needed
        from ...instruments import instrument as instr_module
        MAP = {
            "Keithley 2182A": "ADDR_2182A",
            "Keithley 2700":  "ADDR_2700",
            "PK160":          "ADDR_PK160",
            "Keithley 6221":  "ADDR_6221",
        }
        for name, field in self._addr_fields.items():
            attr = MAP.get(name)
            if attr:
                setattr(instr_module, attr, field.text().strip())
        QMessageBox.information(
            self, "Saved",
            "GPIB addresses updated for this session.\n"
            "Restart the application to make them permanent."
        )

    # ── Change password card ─────────────────────────────────────────────

    def _build_password_card(self) -> QFrame:
        card, cv = _card("Change Password")

        field_style = (
            f"QLineEdit {{ background: white; border: 1px solid {BORDER}; "
            f"border-radius: 6px; padding: 7px 10px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {PRIMARY}; }}"
        )

        self.inp_old = QLineEdit()
        self.inp_old.setPlaceholderText("Current password")
        self.inp_old.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_old.setFixedHeight(36)
        self.inp_old.setMaximumWidth(400)
        self.inp_old.setStyleSheet(field_style)

        self.inp_new1 = QLineEdit()
        self.inp_new1.setPlaceholderText("New password")
        self.inp_new1.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new1.setFixedHeight(36)
        self.inp_new1.setMaximumWidth(400)
        self.inp_new1.setStyleSheet(field_style)

        self.inp_new2 = QLineEdit()
        self.inp_new2.setPlaceholderText("Confirm new password")
        self.inp_new2.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new2.setFixedHeight(36)
        self.inp_new2.setMaximumWidth(400)
        self.inp_new2.setStyleSheet(field_style)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; border: none;")
            return l

        for label, widget in [
            ("Current password", self.inp_old),
            ("New password",     self.inp_new1),
            ("Confirm new",      self.inp_new2),
        ]:
            cv.addWidget(lbl(label))
            cv.addWidget(widget)

        self.lbl_pw_msg = QLabel("")
        self.lbl_pw_msg.setStyleSheet(f"color: {ERROR}; font-size: 12px; border: none;")
        cv.addWidget(self.lbl_pw_msg)

        btn = QPushButton("Change Password")
        btn.setFixedHeight(36)
        btn.setFixedWidth(180)
        btn.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 6px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1D4ED8; }}"
        )
        btn.clicked.connect(self._change_password)
        cv.addWidget(btn)

        return card

    def _change_password(self):
        old   = self.inp_old.text()
        new1  = self.inp_new1.text()
        new2  = self.inp_new2.text()

        if not old or not new1:
            self.lbl_pw_msg.setText("All fields are required.")
            return
        if new1 != new2:
            self.lbl_pw_msg.setText("New passwords do not match.")
            return
        if len(new1) < 6:
            self.lbl_pw_msg.setText("Password must be at least 6 characters.")
            return

        from ...services.auth_service import change_password
        ok = change_password(self._user.id, old, new1)
        if ok:
            self.lbl_pw_msg.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px; border: none;"
            )
            self.lbl_pw_msg.setText("Password changed successfully.")
            self.inp_old.clear()
            self.inp_new1.clear()
            self.inp_new2.clear()
        else:
            self.lbl_pw_msg.setStyleSheet(
                f"color: {ERROR}; font-size: 12px; border: none;"
            )
            self.lbl_pw_msg.setText("Incorrect current password.")

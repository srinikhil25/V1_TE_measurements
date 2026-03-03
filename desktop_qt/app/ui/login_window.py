"""Login window — the first screen the user sees."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QPalette

from .theme import (
    PRIMARY, CONTENT_BG, CARD_BG, BORDER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ERROR,
)


class LoginWindow(QWidget):
    """Frameless login card, centred on screen."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TE Measurement — Login")
        self.setFixedSize(420, 500)
        self.setWindowFlags(Qt.WindowType.Window)
        self._build_ui()
        self._center()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Outer background
        self.setStyleSheet(f"background-color: {CONTENT_BG};")

        # Card
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 12px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(44, 48, 44, 48)
        card_layout.setSpacing(0)

        # ── Logo badge ──────────────────────────────────────────────────
        badge = QLabel("TE")
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {PRIMARY}; color: white; border-radius: 10px; "
            f"font-size: 18px; font-weight: 700;"
        )
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addWidget(badge)
        badge_row.addStretch()
        card_layout.addLayout(badge_row)
        card_layout.addSpacing(20)

        # ── Title ───────────────────────────────────────────────────────
        title = QLabel("TE Measurement")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: 700; border: none;"
        )
        card_layout.addWidget(title)

        subtitle = QLabel("Laboratory Management System")
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; border: none;"
        )
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(36)

        # ── Form ────────────────────────────────────────────────────────
        field_style = (
            f"QLineEdit {{ background: white; border: 1.5px solid {BORDER}; "
            f"border-radius: 7px; padding: 10px 12px; font-size: 13px; "
            f"color: {TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color: {PRIMARY}; }}"
        )
        label_style = (
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            f"border: none; margin-bottom: 4px;"
        )

        lbl_user = QLabel("Username")
        lbl_user.setStyleSheet(label_style)
        card_layout.addWidget(lbl_user)

        self.inp_username = QLineEdit()
        self.inp_username.setPlaceholderText("Enter username")
        self.inp_username.setStyleSheet(field_style)
        self.inp_username.setFixedHeight(42)
        card_layout.addWidget(self.inp_username)
        card_layout.addSpacing(16)

        lbl_pass = QLabel("Password")
        lbl_pass.setStyleSheet(label_style)
        card_layout.addWidget(lbl_pass)

        self.inp_password = QLineEdit()
        self.inp_password.setPlaceholderText("Enter password")
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.setStyleSheet(field_style)
        self.inp_password.setFixedHeight(42)
        card_layout.addWidget(self.inp_password)
        card_layout.addSpacing(12)

        # ── Error label ─────────────────────────────────────────────────
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(
            f"color: {ERROR}; font-size: 12px; border: none;"
        )
        self.lbl_error.setVisible(False)
        card_layout.addWidget(self.lbl_error)
        card_layout.addSpacing(8)

        # ── Login button ────────────────────────────────────────────────
        self.btn_login = QPushButton("Sign In")
        self.btn_login.setObjectName("btn_primary")
        self.btn_login.setFixedHeight(44)
        self.btn_login.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 7px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1D4ED8; }}"
            f"QPushButton:pressed {{ background: #1E40AF; }}"
        )
        card_layout.addWidget(self.btn_login)

        card_layout.addStretch()

        # ── Version footer ──────────────────────────────────────────────
        ver = QLabel("v1.0.0  ·  Ikeda-Hamasaki Laboratory")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border: none; padding-top: 12px;"
        )
        card_layout.addWidget(ver)

        root.addStretch()
        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(card)
        wrapper.addStretch()
        root.addLayout(wrapper)
        root.addStretch()

        # ── Signals ─────────────────────────────────────────────────────
        self.btn_login.clicked.connect(self._on_login)
        self.inp_password.returnPressed.connect(self._on_login)
        self.inp_username.returnPressed.connect(self.inp_password.setFocus)

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _center(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width()  - self.width())  // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _on_login(self):
        from ..services.auth_service import authenticate
        from .main_window import MainWindow

        username = self.inp_username.text().strip()
        password = self.inp_password.text()

        if not username or not password:
            self._show_error("Please enter both username and password.")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Signing in…")

        user = authenticate(username, password)

        if user:
            self._show_error("")
            self.main_window = MainWindow(user)
            self.main_window.show()
            self.close()
        else:
            self._show_error("Invalid username or password.")
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Sign In")
            self.inp_password.clear()
            self.inp_password.setFocus()

    def _show_error(self, msg: str):
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(bool(msg))

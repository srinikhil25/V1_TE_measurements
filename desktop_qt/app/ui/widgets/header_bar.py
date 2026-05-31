"""Top header bar — sidebar toggle · page title · session timer · user · logout."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer, QElapsedTimer

from ..theme import (
    HEADER_BG, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ERROR,
    CONTENT_BG, PRIMARY,
)
from ..icons import icon as _icon

ROLE_LABELS = {
    "super_admin": "Super Admin",
    "lab_admin":   "Lab Admin",
    "researcher":  "Researcher",
}


class HeaderBar(QWidget):
    logout_requested = pyqtSignal()
    sidebar_toggled  = pyqtSignal()

    def __init__(self, username: str, role: str = ""):
        super().__init__()
        self._username  = username
        self._role      = role
        self._collapsed = False
        self.setObjectName("header_bar")
        self.setFixedHeight(54)
        self.setStyleSheet(
            f"QWidget#header_bar {{ background-color: {HEADER_BG}; "
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        self._build()

        # Session timer
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_session)
        self._tick.start()
        self._update_session()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 16, 0)
        layout.setSpacing(8)

        # ── Sidebar toggle ────────────────────────────────────────────────
        self.btn_toggle = QPushButton()
        self.btn_toggle.setFixedSize(36, 36)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setToolTip("Collapse sidebar  (Ctrl+\\)")
        self.btn_toggle.setIcon(_icon("menu", TEXT_SECONDARY, 18))
        self.btn_toggle.setIconSize(QSize(18, 18))
        self.btn_toggle.setStyleSheet(self._toggle_btn_style())
        self.btn_toggle.clicked.connect(self._on_toggle)
        layout.addWidget(self.btn_toggle)
        layout.addSpacing(4)

        # ── Page title ────────────────────────────────────────────────────
        self.lbl_title = QLabel("Dashboard")
        self.lbl_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_title)
        layout.addStretch()

        # ── Session timer ─────────────────────────────────────────────────
        sess = QHBoxLayout()
        sess.setSpacing(6)
        sess_lbl = QLabel("Session")
        sess_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.lbl_session = QLabel("00:00:00")
        self.lbl_session.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600; "
            f"font-family: 'Consolas', monospace;"
        )
        sess.addWidget(sess_lbl)
        sess.addWidget(self.lbl_session)
        layout.addLayout(sess)
        layout.addSpacing(14)

        # ── User chip ─────────────────────────────────────────────────────
        chip = QFrame()
        chip.setStyleSheet(
            f"QFrame {{ background: transparent; border: 1px solid {BORDER}; border-radius: 7px; }}"
        )
        cl = QHBoxLayout(chip)
        cl.setContentsMargins(7, 4, 11, 4)
        cl.setSpacing(9)
        initials = ("".join(p[0] for p in self._username.split()[:2]).upper()
                    or self._username[:2].upper())
        avatar = QLabel(initials)
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {PRIMARY}; color: white; border-radius: 13px; "
            f"font-size: 10px; font-weight: 700;"
        )
        ucol = QVBoxLayout()
        ucol.setSpacing(0)
        u = QLabel(self._username)
        u.setStyleSheet(f"background: transparent; border: none; color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        r = QLabel(ROLE_LABELS.get(self._role, self._role))
        r.setStyleSheet(f"background: transparent; border: none; color: {TEXT_MUTED}; font-size: 10px;")
        ucol.addWidget(u)
        if self._role:
            ucol.addWidget(r)
        cl.addWidget(avatar)
        cl.addLayout(ucol)
        layout.addWidget(chip)

        # ── Sign out ──────────────────────────────────────────────────────
        btn_logout = QPushButton("Sign Out")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.setFixedHeight(32)
        btn_logout.setStyleSheet(
            f"QPushButton {{ background: {CONTENT_BG}; color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 0 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {ERROR}; border-color: {ERROR}; background: white; }}"
        )
        btn_logout.clicked.connect(self.logout_requested)
        layout.addWidget(btn_logout)

    # ------------------------------------------------------------------
    def _update_session(self):
        secs = self._elapsed.elapsed() // 1000
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        self.lbl_session.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _on_toggle(self):
        self._collapsed = not self._collapsed
        self.btn_toggle.setToolTip(
            "Expand sidebar  (Ctrl+\\)" if self._collapsed else "Collapse sidebar  (Ctrl+\\)"
        )
        self.sidebar_toggled.emit()

    def set_title(self, title: str):
        self.lbl_title.setText(title)

    @staticmethod
    def _toggle_btn_style() -> str:
        return (
            "QPushButton { background: #EFECE4; color: #1F2937; border: 1px solid #C7C0B0; "
            "  border-radius: 7px; font-size: 17px; font-weight: 400; padding: 0; }"
            "QPushButton:hover { background: #1E293B; color: white; border-color: #1E293B; }"
            "QPushButton:pressed { background: #1F2937; color: white; border-color: #1F2937; }"
        )

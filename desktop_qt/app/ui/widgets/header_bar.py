"""Top header bar — page title + sidebar toggle + logout."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt

from ..theme import HEADER_BG, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ERROR, CONTENT_BG


class HeaderBar(QWidget):
    logout_requested = pyqtSignal()
    sidebar_toggled  = pyqtSignal()

    def __init__(self, username: str):
        super().__init__()
        self._username  = username
        self._collapsed = False          # tracks sidebar state for arrow direction
        self.setObjectName("header_bar")
        self.setFixedHeight(52)
        self.setStyleSheet(
            f"QWidget#header_bar {{ background-color: {HEADER_BG}; "
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 16, 0)
        layout.setSpacing(8)

        # ── Sidebar toggle ────────────────────────────────────────────────
        self.btn_toggle = QPushButton("☰")
        self.btn_toggle.setFixedSize(36, 36)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setToolTip("Collapse sidebar  (Ctrl+\\)")
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

        # ── Username ──────────────────────────────────────────────────────
        user_lbl = QLabel(f"  {self._username}")
        user_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(user_lbl)

        # ── Sign out ──────────────────────────────────────────────────────
        btn_logout = QPushButton("Sign Out")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.setFixedHeight(30)
        btn_logout.setStyleSheet(
            f"QPushButton {{"
            f"  background: {CONTENT_BG};"
            f"  color: {TEXT_SECONDARY};"
            f"  border: 1px solid {BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 0 12px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{ color: {ERROR}; border-color: {ERROR}; background: white; }}"
        )
        btn_logout.clicked.connect(self.logout_requested)
        layout.addWidget(btn_logout)

    # ------------------------------------------------------------------

    def _on_toggle(self):
        self._collapsed = not self._collapsed
        self.btn_toggle.setToolTip(
            "Expand sidebar  (Ctrl+\\)" if self._collapsed
            else "Collapse sidebar  (Ctrl+\\)"
        )
        self.sidebar_toggled.emit()

    def set_title(self, title: str):
        self.lbl_title.setText(title)

    @staticmethod
    def _toggle_btn_style() -> str:
        return (
            "QPushButton {"
            "  background: #F1F5F9;"
            "  color: #0F172A;"
            "  border: 1px solid #CBD5E1;"
            "  border-radius: 7px;"
            "  font-size: 17px;"
            "  font-weight: 400;"
            "  padding: 0;"
            "}"
            "QPushButton:hover {"
            "  background: #1E293B;"
            "  color: white;"
            "  border-color: #1E293B;"
            "}"
            "QPushButton:pressed {"
            "  background: #0F172A;"
            "  color: white;"
            "  border-color: #0F172A;"
            "}"
        )

"""Main application window — sidebar + stacked pages."""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QStatusBar, QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from .theme import CONTENT_BG, BORDER, TEXT_SECONDARY
from .widgets.sidebar import Sidebar
from .widgets.header_bar import HeaderBar

# Page titles keyed by page_key
PAGE_TITLES = {
    "dashboard":  "Dashboard",
    "seebeck":    "Seebeck Measurement",
    "iv":         "I-V Sweep",
    "history":    "Measurement History",
    "users":      "User Management",
    "settings":   "Settings",
}


class MainWindow(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self._user = user
        self.setWindowTitle("TE Measurement")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 760)
        self._pages: dict = {}
        self._build_ui()
        self._navigate("dashboard")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {CONTENT_BG};")

        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self._user.role, self._user.username)
        self.sidebar.page_requested.connect(self._navigate)
        root.addWidget(self.sidebar)


        # Right side
        right = QWidget()
        right.setStyleSheet(f"background-color: {CONTENT_BG};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Header bar
        self.header = HeaderBar(self._user.username)
        self.header.logout_requested.connect(self._on_logout)
        self.header.sidebar_toggled.connect(self.sidebar.toggle)
        right_layout.addWidget(self.header)

        # Ctrl+\ toggles sidebar — also fires the button's visual state update
        sc = QShortcut(QKeySequence("Ctrl+\\"), self)
        sc.activated.connect(self.header._on_toggle)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background-color: {CONTENT_BG};")
        right_layout.addWidget(self.stack)

        root.addWidget(right)

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet(
            f"QStatusBar {{ background: white; border-top: 1px solid {BORDER}; "
            f"color: {TEXT_SECONDARY}; font-size: 11px; }}"
        )
        self.status_lbl = QLabel("Ready")
        sb.addPermanentWidget(self.status_lbl)
        self.setStatusBar(sb)

    # ------------------------------------------------------------------
    # Page factory — lazy instantiation
    # ------------------------------------------------------------------

    def _get_page(self, key: str) -> QWidget:
        if key not in self._pages:
            page = self._make_page(key)
            self._pages[key] = page
            self.stack.addWidget(page)
        return self._pages[key]

    def _make_page(self, key: str) -> QWidget:
        role = self._user.role

        if key == "dashboard":
            from .pages.dashboard import DashboardPage
            return DashboardPage(self._user, navigate_cb=self._navigate)

        if key == "seebeck":
            from .pages.seebeck_page import SeebeckPage
            return SeebeckPage(self._user)

        if key == "iv":
            from .pages.iv_page import IVPage
            return IVPage(self._user)

        if key == "history":
            from .pages.history_page import HistoryPage
            return HistoryPage(self._user)

        if key == "users" and role == "super_admin":
            from .pages.users_page import UsersPage
            return UsersPage(self._user)

        if key == "settings":
            from .pages.settings_page import SettingsPage
            return SettingsPage(self._user)

        # Fallback placeholder
        placeholder = QWidget()
        lbl = QLabel(f"{PAGE_TITLES.get(key, key)}\n\nComing soon.")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 15px;")
        layout = QVBoxLayout(placeholder)
        layout.addWidget(lbl)
        return placeholder

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        page = self._get_page(key)
        self.stack.setCurrentWidget(page)
        self.header.set_title(PAGE_TITLES.get(key, key))
        self.sidebar.set_active(key)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _on_logout(self):
        reply = QMessageBox.question(
            self, "Sign Out",
            "Are you sure you want to sign out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from ..services.auth_service import logout
        from .login_window import LoginWindow
        logout()
        self.login_window = LoginWindow()
        self.login_window.show()
        self.close()

"""Main application window — sidebar + stacked pages."""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QStatusBar, QLabel, QMessageBox, QApplication,
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
        self.header = HeaderBar(self._user.username, self._user.role)
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
        if not self._stop_running_measurements("Signing out"):
            return
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

    # ------------------------------------------------------------------
    # Run guard: never leave the heater / SourceMeter driving with no UI
    # ------------------------------------------------------------------

    def _stop_running_measurements(self, action: str) -> bool:
        """If a measurement is running, confirm, stop it and switch sources off.

        Returns True when it is safe to continue (nothing running, or the run
        was stopped), False if the operator cancelled.
        """
        from ..services.measurement_service import (
            any_measurement_running, stop_all_measurements)
        if not any_measurement_running():
            return True
        reply = QMessageBox.warning(
            self, "Measurement running",
            f"A measurement is still running.\n\n{action} will stop it and "
            "switch the heater / SourceMeter output off. Data measured so far "
            "is kept.\n\nStop the measurement?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        self.status_lbl.setText("Stopping measurement — switching heater off…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok = stop_all_measurements()
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            QMessageBox.critical(
                self, "Heater may still be on",
                "The measurement did not confirm it stopped.\n\n"
                "Check the power supply and switch its output OFF by hand.",
            )
        return True

    def closeEvent(self, event):
        if not self._stop_running_measurements("Closing the application"):
            event.ignore()
            return
        event.accept()

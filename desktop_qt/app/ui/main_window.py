"""Main application window — top bar · navigation rail · pages · status footer."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .widgets.header_bar import HeaderBar
from .widgets.run_state import RunStateMonitor
from .widgets.sidebar import LABEL_OF, SECTION_OF, Sidebar
from .widgets.status_footer import StatusFooter
from .widgets.ui_kit import EmptyState

# Page titles keyed by page_key
PAGE_TITLES = {
    "dashboard": "Overview",
    "seebeck":   "Seebeck",
    "iv":        "I-V sweep",
    "history":   "Run library",
    "users":     "Users",
    "audit":     "Audit trail",
    "settings":  "Settings",
}


class MainWindow(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self._user = user
        self.setWindowTitle("TE Measurement")
        self.setMinimumSize(1180, 720)
        self.resize(1440, 900)
        self._pages: dict = {}
        self._build_ui()
        self._navigate("dashboard")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("Page")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = HeaderBar(self._user.username, self._user.role)
        self.header.logout_requested.connect(self._on_logout)
        self.header.navigate_requested.connect(self._navigate)
        root.addWidget(self.header)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.sidebar = Sidebar(self._user.role, self._user.username)
        self.sidebar.page_requested.connect(self._navigate)
        self.header.sidebar_toggled.connect(self.sidebar.toggle)
        middle.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Page")
        middle.addWidget(self.stack, 1)
        root.addLayout(middle, 1)

        self.footer = StatusFooter()
        root.addWidget(self.footer)
        # Kept for the run guard below (shows "Stopping…" while it waits).
        self.status_lbl = self.footer.lbl_run

        # Ctrl+\ toggles the navigation rail
        sc = QShortcut(QKeySequence("Ctrl+\\"), self)
        sc.activated.connect(self.header._on_toggle)

        self.run_state = RunStateMonitor(self)
        self.run_state.changed.connect(self.header.set_run_state)
        self.run_state.changed.connect(self.footer.set_run_state)

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
            return DashboardPage(self._user, navigate_cb=self._navigate,
                                 run_state=self.run_state)

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

        if key == "audit" and role in ("super_admin", "lab_admin"):
            from .pages.audit_page import AuditPage
            return AuditPage(self._user)

        if key == "settings":
            from .pages.settings_page import SettingsPage
            page = SettingsPage(self._user)
            if hasattr(page, "config_saved"):
                page.config_saved.connect(self.footer.refresh_safety)
            return page

        return EmptyState("lock", PAGE_TITLES.get(key, key),
                          "You do not have access to this page.")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, key: str):
        page = self._get_page(key)
        self.stack.setCurrentWidget(page)
        self.header.set_title(PAGE_TITLES.get(key, LABEL_OF.get(key, key)),
                              SECTION_OF.get(key, ""))
        self.sidebar.set_active(key)
        on_shown = getattr(page, "on_shown", None)
        if callable(on_shown):
            on_shown()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _on_logout(self):
        if not self._stop_running_measurements("Signing out"):
            return
        reply = QMessageBox.question(
            self, "Sign out",
            "Sign out of TE Measurement?",
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
        from ..services.measurement_service import any_measurement_running, stop_all_measurements
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

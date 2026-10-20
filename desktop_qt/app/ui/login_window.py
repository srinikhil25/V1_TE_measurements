"""Sign-in window — the first screen the user sees."""

from PyQt6.QtCore import QEvent, Qt, QSize
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from . import theme as T
from .icons import icon as _icon, pixmap
from .widgets.ui_kit import Callout, button, label


def _caps_lock_on() -> bool:
    try:
        import ctypes
        return bool(ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1)
    except Exception:
        return False


class LoginWindow(QWidget):

    def __init__(self):
        super().__init__()
        from .. import version
        self._version = getattr(version, "APP_VERSION", "")
        self.setObjectName("LoginWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("TE Measurement — Sign in")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(900, 580)
        self.resize(1040, 640)
        self._build_ui()
        self._center()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_hero(), 0)
        root.addWidget(self._build_form(), 1)

    def _build_hero(self) -> QFrame:
        hero = QFrame()
        hero.setObjectName("LoginHero")
        hero.setFixedWidth(420)
        v = QVBoxLayout(hero)
        v.setContentsMargins(40, 40, 40, 32)
        v.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        badge = QLabel("TE")
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {T.ACCENT}; color: #FFFFFF; border-radius: 6px; "
            f"font-family: '{T.mono_family()}'; font-weight: 700; font-size: 13px;")
        brand.addWidget(badge)
        name = QLabel("TE Measurement")
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        brand.addWidget(name)
        brand.addStretch()
        v.addLayout(brand)
        v.addStretch(2)

        title = label("Thermoelectric\ncharacterisation", "hero-title")
        v.addWidget(title)
        v.addSpacing(10)
        v.addWidget(label("Seebeck coefficient and I-V resistivity measurements "
                          "for the MX-Energy team.", "hero-sub", wrap=True))
        v.addSpacing(28)

        for ic, text in (
            ("seebeck", "Live Seebeck runs with software safety limits"),
            ("iv", "I-V sweeps and resistivity — bar, van der Pauw, 4-point probe"),
            ("audit", "Tamper-evident audit trail and verified daily backups"),
        ):
            row = QHBoxLayout()
            row.setSpacing(12)
            icl = QLabel()
            icl.setPixmap(pixmap(ic, "#7FA6E3", 18))
            icl.setFixedWidth(20)
            row.addWidget(icl, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label(text, "hero-item", wrap=True), 1)
            v.addLayout(row)
            v.addSpacing(14)

        v.addStretch(3)
        div = QFrame()
        div.setObjectName("HeroDivider")
        v.addWidget(div)
        v.addSpacing(12)
        v.addWidget(label("Ikeda-Hamasaki Laboratory · Shizuoka University", "hero-foot"))
        v.addSpacing(2)
        v.addWidget(label(f"Version {self._version}" if self._version else "", "hero-foot"))
        return hero

    def _build_form(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("LoginForm")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(48, 40, 48, 32)
        outer.addStretch(1)

        col_host = QHBoxLayout()
        col_host.addStretch()
        col = QWidget()
        col.setFixedWidth(340)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(label("Sign in", "display"))
        v.addSpacing(6)
        v.addWidget(label("Use your laboratory account.", "secondary"))
        v.addSpacing(28)

        v.addWidget(label("Username", "label"))
        v.addSpacing(6)
        self.inp_username = QLineEdit()
        self.inp_username.setProperty("scale", "lg")
        self.inp_username.setPlaceholderText("e.g. tanaka")
        self.inp_username.addAction(_icon("user", T.TEXT_MUTED, 16),
                                    QLineEdit.ActionPosition.LeadingPosition)
        v.addWidget(self.inp_username)
        v.addSpacing(16)

        v.addWidget(label("Password", "label"))
        v.addSpacing(6)
        self.inp_password = QLineEdit()
        self.inp_password.setProperty("scale", "lg")
        self.inp_password.setPlaceholderText("Password")
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.addAction(_icon("lock", T.TEXT_MUTED, 16),
                                    QLineEdit.ActionPosition.LeadingPosition)
        self._act_reveal = QAction(_icon("eye", T.TEXT_MUTED, 16), "Show password", self)
        self._act_reveal.triggered.connect(self._toggle_reveal)
        self.inp_password.addAction(self._act_reveal, QLineEdit.ActionPosition.TrailingPosition)
        self.inp_password.installEventFilter(self)
        v.addWidget(self.inp_password)
        v.addSpacing(6)

        self.lbl_caps = label("Caps Lock is on", "caption")
        self.lbl_caps.setStyleSheet(f"color: {T.WARNING};")
        self.lbl_caps.setVisible(False)
        v.addWidget(self.lbl_caps)
        v.addSpacing(10)

        self.err_box = Callout("", "danger")
        self.err_box.setVisible(False)
        v.addWidget(self.err_box)
        # Kept for callers/tests that read the message text.
        self.lbl_error = self.err_box.text_lbl
        v.addSpacing(14)

        self.btn_login = button("Sign in", "primary", size="lg")
        self.btn_login.setDefault(True)
        v.addWidget(self.btn_login)
        v.addSpacing(18)
        v.addWidget(label("Accounts are created by the lab administrator. "
                          "Every sign-in is recorded in the audit trail.", "caption", wrap=True))

        col_host.addWidget(col)
        col_host.addStretch()
        outer.addLayout(col_host)
        outer.addStretch(1)

        # ── Signals ─────────────────────────────────────────────────────
        self.btn_login.clicked.connect(self._on_login)
        self.inp_password.returnPressed.connect(self._on_login)
        self.inp_username.returnPressed.connect(self.inp_password.setFocus)
        self.inp_username.textEdited.connect(lambda _t: self._show_error(""))
        self.inp_password.textEdited.connect(lambda _t: self._show_error(""))
        return wrap

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def showEvent(self, e):
        super().showEvent(e)
        self.inp_username.setFocus()

    def eventFilter(self, obj, ev):
        if obj is self.inp_password and ev.type() in (QEvent.Type.KeyPress, QEvent.Type.FocusIn,
                                                     QEvent.Type.KeyRelease):
            self.lbl_caps.setVisible(_caps_lock_on())
        elif obj is self.inp_password and ev.type() == QEvent.Type.FocusOut:
            self.lbl_caps.setVisible(False)
        return super().eventFilter(obj, ev)

    def _toggle_reveal(self):
        hidden = self.inp_password.echoMode() == QLineEdit.EchoMode.Password
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Normal if hidden
                                      else QLineEdit.EchoMode.Password)
        self._act_reveal.setIcon(_icon("eye-off" if hidden else "eye", T.TEXT_MUTED, 16))
        self._act_reveal.setText("Hide password" if hidden else "Show password")

    def _center(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        g = screen.availableGeometry()
        self.move(g.x() + (g.width() - self.width()) // 2,
                  g.y() + (g.height() - self.height()) // 2)

    def _on_login(self):
        from ..services.auth_service import authenticate
        from .main_window import MainWindow

        username = self.inp_username.text().strip()
        password = self.inp_password.text()

        if not username or not password:
            self._show_error("Enter both your username and password.")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Signing in…")
        QApplication.processEvents()

        user = authenticate(username, password)

        if user:
            self._show_error("")
            self.main_window = MainWindow(user)
            self.main_window.show()
            self.close()
            self._warn_missing_prerequisites(self.main_window)
        else:
            self._show_error("The username or password is incorrect.")
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Sign in")
            self.inp_password.clear()
            self.inp_password.setFocus()

    def _show_error(self, msg: str):
        self.err_box.set_text(msg)
        self.err_box.setVisible(bool(msg))

    def _warn_missing_prerequisites(self, parent):
        """After login, warn once if NI-VISA / the Optris SDK are not installed.

        The dialog is skipped when everything is present, or when the user has
        already ticked "Don't remind me again" for the same set of missing items.
        """
        try:
            from ..core.prereqs import (
                check_prerequisites, missing_items, load_acked, save_acked,
            )
            from PyQt6.QtWidgets import QMessageBox, QCheckBox

            status = check_prerequisites()
            items = missing_items(status)
            if not items:
                return

            keys = {k for k, _, _ in items}
            acked = load_acked()
            if keys.issubset(acked):
                return  # user already dismissed this (or a broader) set

            body = "Some hardware prerequisites were not detected on this PC:\n\n"
            for _key, title, desc in items:
                body += f"•  {title}\n     {desc}\n\n"
            body += ("The application will run normally — the features above stay "
                     "unavailable until these are installed.")

            box = QMessageBox(parent)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Hardware prerequisites")
            box.setText(body)
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            cb = QCheckBox("Don't remind me again")
            box.setCheckBox(cb)
            box.exec()
            if cb.isChecked():
                save_acked(acked | keys)
        except Exception:
            # A diagnostic convenience must never block login.
            import logging
            logging.getLogger(__name__).warning(
                "prerequisite check failed", exc_info=True)

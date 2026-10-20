"""Top bar — navigation toggle · product · breadcrumb · run state · account menu."""

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from .. import theme as T
from ..icons import icon as _icon
from .run_state import fmt_elapsed
from .ui_kit import Dot, ROLE_LABELS, initials, set_props, vline


class HeaderBar(QWidget):
    logout_requested = pyqtSignal()
    sidebar_toggled = pyqtSignal()
    navigate_requested = pyqtSignal(str)

    def __init__(self, username: str, role: str = ""):
        super().__init__()
        self._username = username
        self._role = role
        self._collapsed = False
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(48)
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 12, 0)
        lay.setSpacing(12)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("NavToggle")
        self.btn_toggle.setIcon(_icon("menu", T.CHROME_TEXT_2, 18))
        self.btn_toggle.setIconSize(QSize(18, 18))
        self.btn_toggle.setToolTip("Collapse navigation  (Ctrl+\\)")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._on_toggle)
        lay.addWidget(self.btn_toggle)

        badge = QLabel("TE")
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {T.ACCENT}; color: #FFFFFF; border-radius: 5px; "
            f"font-family: '{T.mono_family()}'; font-weight: 700; font-size: 12px;")
        lay.addWidget(badge)
        brand = QLabel("TE Measurement")
        brand.setObjectName("Brand")
        lay.addWidget(brand)

        sep = vline()
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"background: {T.CHROME_BORDER};")
        lay.addWidget(sep)

        self.lbl_section = QLabel("")
        self.lbl_section.setProperty("role", "crumb")
        self.lbl_slash = QLabel("/")
        self.lbl_slash.setProperty("role", "crumb")
        self.lbl_title = QLabel("Overview")
        self.lbl_title.setProperty("role", "crumb-current")
        lay.addWidget(self.lbl_section)
        lay.addWidget(self.lbl_slash)
        lay.addWidget(self.lbl_title)
        lay.addStretch()

        # Run-state pill
        self.pill = QFrame()
        self.pill.setObjectName("RunPill")
        self.pill.setProperty("state", "idle")
        pl = QHBoxLayout(self.pill)
        pl.setContentsMargins(10, 4, 10, 4)
        pl.setSpacing(8)
        self.pill_dot = Dot(T.CHROME_MUTED, 8)
        self.pill_text = QLabel("IDLE")
        self.pill_text.setObjectName("RunPillText")
        self.pill_time = QLabel("")
        self.pill_time.setObjectName("RunPillTime")
        self.pill_time.setVisible(False)
        pl.addWidget(self.pill_dot)
        pl.addWidget(self.pill_text)
        pl.addWidget(self.pill_time)
        self.pill.setToolTip("No measurement is running.")
        self.pill.setFixedHeight(28)
        lay.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)

        # Account menu
        self.btn_user = QPushButton()
        self.btn_user.setCursor(Qt.CursorShape.PointingHandCursor)
        ul = QHBoxLayout(self.btn_user)
        ul.setContentsMargins(6, 0, 8, 0)
        ul.setSpacing(8)
        av = QLabel(initials(self._username))
        av.setFixedSize(22, 22)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(f"background: #2E3542; color: {T.CHROME_TEXT}; border-radius: 11px; "
                         "font-size: 10px; font-weight: 700;")
        nm = QLabel(self._username)
        nm.setStyleSheet(f"color: {T.CHROME_TEXT}; font-size: 13px;")
        chev = QLabel()
        from ..icons import pixmap
        chev.setPixmap(pixmap("chevron-down", T.CHROME_MUTED, 14))
        for w in (av, nm, chev):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            ul.addWidget(w)
        self.btn_user.setMinimumWidth(av.width() + nm.sizeHint().width() + 46)
        menu = QMenu(self)
        who = QAction(f"{self._username}  ·  {ROLE_LABELS.get(self._role, self._role)}", menu)
        who.setEnabled(False)
        menu.addAction(who)
        menu.addSeparator()
        act_settings = QAction(_icon("key", T.TEXT_SECONDARY, 16), "Change password…", menu)
        act_settings.triggered.connect(lambda: self.navigate_requested.emit("settings"))
        menu.addAction(act_settings)
        menu.addSeparator()
        act_out = QAction(_icon("logout", T.TEXT_SECONDARY, 16), "Sign out", menu)
        act_out.triggered.connect(self.logout_requested)
        menu.addAction(act_out)
        self.btn_user.setMenu(menu)
        lay.addWidget(self.btn_user)

    # ------------------------------------------------------------------
    def _on_toggle(self):
        self._collapsed = not self._collapsed
        self.btn_toggle.setToolTip(
            "Expand navigation  (Ctrl+\\)" if self._collapsed else "Collapse navigation  (Ctrl+\\)")
        self.sidebar_toggled.emit()

    def set_title(self, title: str, section: str = ""):
        self.lbl_title.setText(title)
        self.lbl_section.setText(section)
        self.lbl_section.setVisible(bool(section))
        self.lbl_slash.setVisible(bool(section))

    def set_run_state(self, st: dict):
        if st.get("running"):
            state = "running"
            text = "RUNNING"
            self.pill_dot.set_color(T.SUCCESS_LIVE)
            self.pill_time.setText(fmt_elapsed(st.get("elapsed_s")))
            self.pill_time.setVisible(True)
            mid = st.get("measurement_id")
            tip = st.get("label", "Measurement") + (f" · run #{mid}" if mid else "")
            if st.get("phase"):
                tip += f" · phase: {st['phase'].replace('_', ' ')}"
            self.pill.setToolTip(tip)
        else:
            state = "idle"
            text = "IDLE"
            self.pill_dot.set_color(T.CHROME_MUTED)
            self.pill_time.setVisible(False)
            self.pill.setToolTip("No measurement is running.")
        if self.pill_text.text() != text:
            self.pill_text.setText(text)
        if self.pill.property("state") != state:
            set_props(self.pill, state=state)
            set_props(self.pill_text)
            set_props(self.pill_time)

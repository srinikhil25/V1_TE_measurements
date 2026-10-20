"""Status footer — instruments · safety limits · run / saving state · version."""

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .. import theme as T
from ..icons import icon as _icon
from .run_state import instrument_status
from .ui_kit import Dot, set_props, vline


class StatusFooter(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("StatusFooter")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(28)
        self._dots = {}
        self._build()
        status = instrument_status()
        status.updated.connect(self._on_scan)
        # First scan shortly after start-up. The timer is a child of the footer,
        # so it dies with it: a bare singleShot to the app-wide status object
        # would still fire after the footer (or a test's window) is gone.
        self._first_scan = QTimer(self)
        self._first_scan.setSingleShot(True)
        self._first_scan.timeout.connect(status.refresh)
        self._first_scan.start(900)

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(14)

        from ...services.instrument_scan import instrument_addresses
        for _key, short, full, addr in instrument_addresses():
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(6)
            d = Dot(T.CHROME_MUTED, 7, hollow=True)
            cl.addWidget(d)
            cl.addWidget(QLabel(short))
            cell.setToolTip(f"{full} · {addr} · not checked yet")
            self._dots[addr] = (d, cell, full)
            lay.addWidget(cell)

        self.btn_rescan = QPushButton()
        self.btn_rescan.setIcon(_icon("refresh", T.CHROME_MUTED, 13))
        self.btn_rescan.setIconSize(QSize(13, 13))
        self.btn_rescan.setFixedSize(22, 20)
        self.btn_rescan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rescan.setToolTip("Check which instruments answer on the GPIB bus "
                                   "(skipped while a measurement is running)")
        self.btn_rescan.setStyleSheet(
            "QPushButton { background: transparent; border: none; min-height: 0; padding: 0; }"
            f"QPushButton:hover {{ background: {T.NAV_HOVER}; border-radius: 3px; }}")
        self.btn_rescan.clicked.connect(lambda: instrument_status().refresh())
        lay.addWidget(self.btn_rescan)

        lay.addWidget(self._sep())
        self.lbl_safety = QLabel("")
        lay.addWidget(self.lbl_safety)
        self.refresh_safety()

        lay.addStretch()
        self.lbl_run = QLabel("No run active")
        lay.addWidget(self.lbl_run)
        lay.addWidget(self._sep())
        from ...version import APP_VERSION
        ver = QLabel(f"v{APP_VERSION}")
        ver.setProperty("tone", "muted")
        lay.addWidget(ver)

    def _sep(self):
        s = vline()
        s.setFixedHeight(14)
        return s

    # ------------------------------------------------------------------
    def refresh_safety(self):
        try:
            from ...core.config import get_config
            s = get_config().safety
            self.lbl_safety.setText(
                f"Safety limits  {s.max_temperature_C:g} °C · {s.max_rise_rate_C_per_min:g} °C/min")
            self.lbl_safety.setToolTip(
                "Software safety limits (Settings → Safety). The software switches the heater "
                "off when a limit is exceeded — it is not a hardware interlock.")
        except Exception:
            self.lbl_safety.setText("Safety limits unavailable")

    def _on_scan(self, available):
        for addr, (dot, cell, full) in self._dots.items():
            if available is None:
                dot.set_color(T.CHROME_MUTED, hollow=True)
                cell.setToolTip(f"{full} · {addr} · VISA not available")
            elif addr in available:
                dot.set_color(T.SUCCESS_LIVE)
                cell.setToolTip(f"{full} · {addr} · answering")
            else:
                dot.set_color(T.DANGER_LIVE, hollow=True)
                cell.setToolTip(f"{full} · {addr} · not found on the bus")

    def set_run_state(self, st: dict):
        if st.get("running"):
            mid = st.get("measurement_id")
            text = st.get("label", "Run")
            if mid:
                text += f" #{mid}"
            if st.get("db_warning"):
                text += " · NOT SAVING"
                tone = "danger"
            else:
                text += " · saving"
                tone = "success"
            if st.get("invalid_reads"):
                text += f" · {st['invalid_reads']} invalid reading(s)"
                tone = "warning" if tone == "success" else tone
        else:
            text, tone = "No run active", ""
        if self.lbl_run.text() != text:
            self.lbl_run.setText(text)
        if (self.lbl_run.property("tone") or "") != tone:
            set_props(self.lbl_run, tone=tone)

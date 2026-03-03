"""Dashboard page — welcome, instrument status badges, quick actions."""

from datetime import datetime
from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY, PRIMARY_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_BG, WARNING, WARNING_BG, ERROR, ERROR_BG,
)


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; }}"
    )
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px;"
    )
    return lbl


# ---------------------------------------------------------------------------
# Instrument status badge
# ---------------------------------------------------------------------------

class _InstrumentBadge(QFrame):
    """Small pill showing instrument name + online/offline state."""

    def __init__(self, name: str):
        super().__init__()
        self._name = name
        self.setFixedHeight(40)
        self.setStyleSheet(
            f"QFrame {{ background: {WARNING_BG}; border: 1px solid {WARNING}; "
            f"border-radius: 6px; padding: 0px 12px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {WARNING}; font-size: 11px; border: none;")

        self._lbl = QLabel(name)
        self._lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none;"
        )

        self._status = QLabel("checking…")
        self._status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; border: none;"
        )

        layout.addWidget(self._dot)
        layout.addWidget(self._lbl)
        layout.addWidget(self._status)
        layout.addStretch()

    def set_online(self, online: bool):
        if online:
            self.setStyleSheet(
                f"QFrame {{ background: {SUCCESS_BG}; border: 1px solid {SUCCESS}; "
                f"border-radius: 6px; }}"
            )
            self._dot.setStyleSheet(f"color: {SUCCESS}; font-size: 11px; border: none;")
            self._status.setText("Connected")
            self._status.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px; border: none;"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background: {ERROR_BG}; border: 1px solid #FECACA; "
                f"border-radius: 6px; }}"
            )
            self._dot.setStyleSheet(f"color: {ERROR}; font-size: 11px; border: none;")
            self._status.setText("Not connected")
            self._status.setStyleSheet(
                f"color: {ERROR}; font-size: 11px; border: none;"
            )


# ---------------------------------------------------------------------------
# Quick-action card
# ---------------------------------------------------------------------------

class _ActionCard(QFrame):
    def __init__(self, title: str, description: str, key: str,
                 navigate_cb: Callable):
        super().__init__()
        self.setObjectName("card")
        self.setFixedWidth(220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; }}"
            f"QFrame#card:hover {{ border-color: {PRIMARY}; "
            f"background: {PRIMARY_LIGHT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        icon_lbl = QLabel("▶")
        icon_lbl.setStyleSheet(
            f"color: {PRIMARY}; font-size: 20px; border: none;"
        )

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600; border: none;"
        )

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; border: none;"
        )

        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)

        self._key = key
        self._navigate_cb = navigate_cb

    def mousePressEvent(self, event):
        self._navigate_cb(self._key)


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------

class DashboardPage(QWidget):

    def __init__(self, user, navigate_cb: Callable):
        super().__init__()
        self._user = user
        self._navigate = navigate_cb
        self._badges: dict = {}
        self._build_ui()

        # Check instrument status once at startup (non-blocking: try to
        # detect via pyvisa list_resources; we never connect to instruments here)
        QTimer.singleShot(800, self._check_instruments)

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {CONTENT_BG};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        v = QVBoxLayout(content)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(28)

        # ── Welcome banner ───────────────────────────────────────────────
        today = datetime.now().strftime("%A, %B %d, %Y")

        greeting_card = _card()
        g_layout = QVBoxLayout(greeting_card)
        g_layout.setContentsMargins(24, 20, 24, 20)
        g_layout.setSpacing(4)

        lbl_welcome = QLabel(f"Welcome back, {self._user.username}")
        lbl_welcome.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700; border: none;"
        )

        lbl_date = QLabel(datetime.now().strftime("%A, %B %d, %Y"))
        lbl_date.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; border: none;"
        )

        role_display = {
            "super_admin": "Super Administrator",
            "lab_admin":   "Lab Administrator",
            "researcher":  "Researcher",
        }.get(self._user.role, self._user.role)

        lbl_role = QLabel(f"Role: {role_display}")
        lbl_role.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; border: none;"
        )

        g_layout.addWidget(lbl_welcome)
        g_layout.addWidget(lbl_date)
        g_layout.addWidget(lbl_role)
        v.addWidget(greeting_card)

        # ── Instrument status ────────────────────────────────────────────
        v.addWidget(_section_label("Instrument Status"))

        badge_row = QHBoxLayout()
        badge_row.setSpacing(12)
        for name in ["Keithley 2182A", "Keithley 2700", "PK160", "Keithley 2401"]:
            badge = _InstrumentBadge(name)
            self._badges[name] = badge
            badge_row.addWidget(badge)
        badge_row.addStretch()
        v.addLayout(badge_row)

        # ── Quick actions ────────────────────────────────────────────────
        role = self._user.role
        if role in ("super_admin", "lab_admin", "researcher"):
            v.addWidget(_section_label("Quick Actions"))

            actions_row = QHBoxLayout()
            actions_row.setSpacing(16)
            actions_row.addWidget(_ActionCard(
                "Seebeck Measurement",
                "Measure thermoelectric Seebeck coefficient (S) with live chart.",
                "seebeck", self._navigate,
            ))
            actions_row.addWidget(_ActionCard(
                "I-V Sweep",
                "Sweep voltage and record current via Keithley 2401.",
                "iv", self._navigate,
            ))
            actions_row.addStretch()
            v.addLayout(actions_row)

        v.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _check_instruments(self):
        """
        Non-destructive instrument check: query pyvisa for visible resources.
        Sets badges without connecting.
        """
        ADDR_MAP = {
            "Keithley 2182A": "GPIB0::7::INSTR",
            "Keithley 2700":  "GPIB0::16::INSTR",
            "PK160":          "GPIB0::15::INSTR",
            "Keithley 2401":  "GPIB0::24::INSTR",
        }
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            available = set(rm.list_resources())
            for name, addr in ADDR_MAP.items():
                self._badges[name].set_online(addr in available)
            rm.close()
        except Exception:
            for badge in self._badges.values():
                badge.set_online(False)

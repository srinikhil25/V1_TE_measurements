"""Left navigation sidebar — dark, role-filtered, collapsible.

Sections: brand · WORKSPACE nav · ADMIN nav · instrument status · user footer.
"""

from typing import List, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen

from ..icons import icon as _icon

# (label, key, allowed-roles or None, section)  — icon name = key
NAV_ITEMS: List[tuple] = [
    ("Dashboard",       "dashboard", None,                                          "workspace"),
    ("Seebeck",         "seebeck",   ("super_admin", "lab_admin", "researcher"),    "workspace"),
    ("I-V Sweep",       "iv",        ("super_admin", "lab_admin", "researcher"),    "workspace"),
    ("History",         "history",   ("super_admin", "lab_admin", "researcher"),    "workspace"),
    ("User Management", "users",     ("super_admin",),                              "admin"),
    ("Settings",        "settings",  None,                                          "admin"),
]

ROLE_LABELS = {
    "super_admin": "Super Admin",
    "lab_admin":   "Lab Admin",
    "researcher":  "Researcher",
}

INSTRUMENTS = {
    "2182A":   "GPIB0::7::INSTR",
    "2700":    "GPIB0::16::INSTR",
    "PK4-80M": "GPIB0::15::INSTR",
    "6221":    "GPIB0::24::INSTR",
}

# Sidebar colour constants
_BG     = "#1F242C"
_HOVER  = "#2A2F38"
_ACTIVE = "#2F6F7A"
_TEXT   = "#EDEAE0"
_MUTED  = "#A3A096"
_DIV    = "#2D333C"


class Sidebar(QWidget):
    page_requested = pyqtSignal(str)

    def __init__(self, role: str, username: str):
        super().__init__()
        self._role     = role
        self._username = username
        self._buttons: List[Tuple[str, QPushButton]] = []
        self._dots: dict = {}
        self._expanded = True
        self._EXPANDED_W  = 220
        self._COLLAPSED_W = 0
        self._anim_group: QParallelAnimationGroup | None = None

        self.setFixedWidth(self._EXPANDED_W)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_BG))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self._build()
        QTimer.singleShot(900, self._poll_instruments)

    # ------------------------------------------------------------------
    def toggle(self):
        if (self._anim_group and
                self._anim_group.state() == QParallelAnimationGroup.State.Running):
            return
        start_w = self._EXPANDED_W if self._expanded else self._COLLAPSED_W
        end_w   = self._COLLAPSED_W if self._expanded else self._EXPANDED_W

        def _anim(prop: bytes) -> QPropertyAnimation:
            a = QPropertyAnimation(self, prop)
            a.setDuration(220)
            a.setEasingCurve(QEasingCurve.Type.InOutQuad)
            a.setStartValue(start_w)
            a.setEndValue(end_w)
            return a

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(_anim(b"minimumWidth"))
        self._anim_group.addAnimation(_anim(b"maximumWidth"))
        self._anim_group.start()
        self._expanded = not self._expanded

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    # ------------------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Brand ─────────────────────────────────────────────────────────
        header = self._make_widget(_BG, fixed_h=70, border_bottom=_DIV)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(11)

        badge = QLabel("TE")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {_ACTIVE}; color: white; "
            f"border-radius: 8px; font-size: 12px; font-weight: 700;"
        )
        col = QVBoxLayout()
        col.setSpacing(1)
        t1 = QLabel("TE Measurement")
        t1.setStyleSheet(f"background: transparent; color: {_TEXT}; font-size: 13px; font-weight: 600;")
        t2 = QLabel("Ikeda-Hamasaki Lab")
        t2.setStyleSheet(f"background: transparent; color: {_MUTED}; font-size: 10px;")
        col.addWidget(t1)
        col.addWidget(t2)
        hl.addWidget(badge)
        hl.addLayout(col)
        hl.addStretch()
        layout.addWidget(header)
        layout.addSpacing(8)

        # ── Nav (grouped by section) ──────────────────────────────────────
        last_section = None
        for label, key, roles, section in NAV_ITEMS:
            if roles is not None and self._role not in roles:
                continue
            if section != last_section:
                layout.addWidget(self._section_label(section.upper()))
                last_section = section
            layout.addWidget(self._nav_button(label, key))

        layout.addStretch()

        # ── Instrument status ─────────────────────────────────────────────
        instr = self._make_widget(_BG, border_top=_DIV)
        il = QVBoxLayout(instr)
        il.setContentsMargins(18, 12, 18, 10)
        il.setSpacing(8)
        lbl = QLabel("INSTRUMENTS")
        lbl.setStyleSheet(
            f"background: transparent; color: {_MUTED}; font-size: 9.5px; "
            f"font-weight: 700; letter-spacing: 1.2px;"
        )
        il.addWidget(lbl)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        for i, name in enumerate(INSTRUMENTS):
            row = QHBoxLayout()
            row.setSpacing(7)
            dot = QLabel("●")
            dot.setStyleSheet("background: transparent; color: #6B7280; font-size: 9px;")
            self._dots[name] = dot
            nm = QLabel(name)
            nm.setStyleSheet(f"background: transparent; color: {_MUTED}; font-size: 11px;")
            row.addWidget(dot)
            row.addWidget(nm)
            row.addStretch()
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cell.setLayout(row)
            grid.addWidget(cell, i // 2, i % 2)
        il.addLayout(grid)
        layout.addWidget(instr)

        # ── User footer ───────────────────────────────────────────────────
        footer = self._make_widget(_BG, border_top=_DIV)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 12, 16, 16)
        fl.setSpacing(10)

        avatar = QLabel("".join([p[0] for p in self._username.split()[:2]]).upper()
                        or self._username[:2].upper())
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {_ACTIVE}; color: white; border-radius: 16px; "
            f"font-size: 11px; font-weight: 700;"
        )
        ucol = QVBoxLayout()
        ucol.setSpacing(1)
        u_lbl = QLabel(self._username)
        u_lbl.setStyleSheet(f"background: transparent; color: {_TEXT}; font-size: 12.5px; font-weight: 600;")
        r_lbl = QLabel(ROLE_LABELS.get(self._role, self._role))
        r_lbl.setStyleSheet(f"background: transparent; color: {_MUTED}; font-size: 10.5px;")
        ucol.addWidget(u_lbl)
        ucol.addWidget(r_lbl)
        fl.addWidget(avatar)
        fl.addLayout(ucol)
        fl.addStretch()
        layout.addWidget(footer)

    # ------------------------------------------------------------------
    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"background: {_BG}; color: {_MUTED}; font-size: 9.5px; "
            f"font-weight: 700; letter-spacing: 1.4px; padding: 10px 22px 4px;"
        )
        return lbl

    def _nav_button(self, label: str, key: str) -> QPushButton:
        btn = QPushButton("   " + label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.setIcon(_icon(key, _MUTED, 18))
        btn.setIconSize(QSize(18, 18))
        btn.setStyleSheet(self._inactive_style())
        btn.clicked.connect(lambda _, k=key: self._on_nav(k))
        self._buttons.append((key, btn))
        return btn

    # ------------------------------------------------------------------
    def set_active(self, key: str):
        for k, btn in self._buttons:
            active = (k == key)
            btn.setStyleSheet(self._active_style() if active else self._inactive_style())
            # Recolour the icon to match the active/inactive text colour.
            btn.setIcon(_icon(k, "#FFFFFF" if active else _MUTED, 18))

    def _on_nav(self, key: str):
        self.set_active(key)
        self.page_requested.emit(key)

    def _poll_instruments(self):
        """Light, non-blocking check of which GPIB resources are visible."""
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            available = set(rm.list_resources())
            for name, addr in INSTRUMENTS.items():
                online = addr in available
                self._dots[name].setStyleSheet(
                    f"background: transparent; font-size: 9px; "
                    f"color: {'#5BAD6E' if online else '#C66262'};"
                )
            rm.close()
        except Exception:
            for dot in self._dots.values():
                dot.setStyleSheet("background: transparent; color: #6B7280; font-size: 9px;")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor("#2D333C"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

    # ------------------------------------------------------------------
    @staticmethod
    def _make_widget(bg: str, fixed_h: int = 0, border_top: str = "", border_bottom: str = "") -> QWidget:
        w = QWidget()
        borders = ""
        if border_top:
            borders += f"border-top: 1px solid {border_top};"
        if border_bottom:
            borders += f"border-bottom: 1px solid {border_bottom};"
        w.setStyleSheet(f"QWidget {{ background: {bg}; {borders} }}")
        if fixed_h:
            w.setFixedHeight(fixed_h)
        return w

    @staticmethod
    def _inactive_style() -> str:
        return (
            f"QPushButton {{ background: {_BG}; color: {_TEXT}; border: none; "
            f"text-align: left; padding: 0 14px; font-size: 13px; font-weight: 400; "
            f"border-radius: 6px; margin: 1px 10px; }}"
            f"QPushButton:hover {{ background: {_HOVER}; color: white; }}"
        )

    @staticmethod
    def _active_style() -> str:
        return (
            f"QPushButton {{ background: {_ACTIVE}; color: white; border: none; "
            f"text-align: left; padding: 0 14px; font-size: 13px; font-weight: 600; "
            f"border-radius: 6px; margin: 1px 10px; }}"
        )

"""Left navigation sidebar — dark, role-filtered, collapsible."""

from typing import List, Tuple
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen

from ..theme import (
    SIDEBAR_BG, SIDEBAR_HOVER, SIDEBAR_ACTIVE,
    SIDEBAR_TEXT, PRIMARY,
)

NAV_ITEMS: List[Tuple[str, str, tuple | None]] = [
    ("Dashboard",       "dashboard", None),
    ("Seebeck",         "seebeck",   ("super_admin", "lab_admin", "researcher")),
    ("I-V Sweep",       "iv",        ("super_admin", "lab_admin", "researcher")),
    ("History",         "history",   ("super_admin", "lab_admin", "researcher")),
    ("User Management", "users",     ("super_admin",)),
    ("Settings",        "settings",  ("super_admin", "lab_admin")),
]

ROLE_LABELS = {
    "super_admin": "Super Admin",
    "lab_admin":   "Lab Admin",
    "researcher":  "Researcher",
}

# Sidebar colour constants (self-contained — no theme import needed for QSS strings)
_BG     = "#111827"
_HOVER  = "#1F2937"
_ACTIVE = "#2563EB"
_TEXT   = "#E2E8F0"   # clearly readable on dark sidebar
_MUTED  = "#94A3B8"   # subdued but still visible
_DIV    = "#1F2937"   # divider lines


class Sidebar(QWidget):
    page_requested = pyqtSignal(str)

    def __init__(self, role: str, username: str):
        super().__init__()
        self._role     = role
        self._username = username
        self._buttons: List[Tuple[str, QPushButton]] = []
        self._expanded = True
        self._EXPANDED_W  = 220
        self._COLLAPSED_W = 0
        self._anim_group: QParallelAnimationGroup | None = None

        self.setFixedWidth(self._EXPANDED_W)

        # Force dark background via palette (survives Fusion style)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_BG))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def toggle(self):
        """Animate the sidebar between expanded (220 px) and hidden (0 px)."""
        if (self._anim_group and
                self._anim_group.state() == QParallelAnimationGroup.State.Running):
            return  # ignore clicks while animating

        start_w = self._EXPANDED_W  if self._expanded else self._COLLAPSED_W
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

        # ── Header ───────────────────────────────────────────────────────
        header = self._make_widget(_BG, fixed_h=68, border_bottom=_DIV)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(10)

        badge = QLabel("TE")
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {_ACTIVE}; color: white; "
            f"border-radius: 8px; font-size: 12px; font-weight: 700;"
        )

        col = QVBoxLayout()
        col.setSpacing(1)
        t1 = QLabel("Measurement")
        t1.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 600;")
        # t2 = QLabel("Ikeda-Hamasaki Lab")
        # t2.setStyleSheet(f"color: {_MUTED}; font-size: 10px;")
        col.addWidget(t1)
        # col.addWidget(t2)

        hl.addWidget(badge)
        hl.addLayout(col)
        hl.addStretch()
        layout.addWidget(header)
        layout.addSpacing(10)

        # ── Section label ─────────────────────────────────────────────────
        # sec = QLabel("NAVIGATION")
        # sec.setFixedHeight(22)
        # sec.setStyleSheet(
        #     f"background: {_BG}; color: {_MUTED}; "
        #     f"font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
        # )
        # layout.addWidget(sec)
        # layout.addSpacing(4)

        # ── Nav buttons ───────────────────────────────────────────────────
        for label, key, roles in NAV_ITEMS:
            if roles is not None and self._role not in roles:
                continue
            btn = QPushButton(f"  {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.setStyleSheet(self._inactive_style())
            btn.clicked.connect(lambda _, k=key: self._on_nav(k))
            self._buttons.append((key, btn))
            layout.addWidget(btn)

        layout.addStretch()

        # ── User footer ───────────────────────────────────────────────────
        footer = self._make_widget(_BG, border_top=_DIV)
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(16, 12, 16, 16)
        fl.setSpacing(2)

        u_lbl = QLabel(self._username)
        u_lbl.setStyleSheet(
            f"background: transparent; color: {_TEXT}; "
            f"font-size: 13px; font-weight: 600;"
        )
        r_lbl = QLabel(ROLE_LABELS.get(self._role, self._role))
        r_lbl.setStyleSheet(
            f"background: transparent; color: {_MUTED}; font-size: 11px;"
        )
        fl.addWidget(u_lbl)
        fl.addWidget(r_lbl)
        layout.addWidget(footer)

    # ------------------------------------------------------------------
    def set_active(self, key: str):
        for k, btn in self._buttons:
            btn.setStyleSheet(
                self._active_style() if k == key else self._inactive_style()
            )

    def _on_nav(self, key: str):
        self.set_active(key)
        self.page_requested.emit(key)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor("#2D3748"))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

    # ------------------------------------------------------------------
    @staticmethod
    def _make_widget(
        bg: str, fixed_h: int = 0,
        border_top: str = "", border_bottom: str = ""
    ) -> QWidget:
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
        # Use solid background (not transparent) so Fusion palette can't bleed through
        return (
            f"QPushButton {{"
            f"  background: {_BG};"
            f"  color: {_TEXT};"
            f"  border: none;"
            f"  text-align: left;"
            f"  padding: 0 14px;"
            f"  font-size: 13px;"
            f"  font-weight: 400;"
            f"  border-radius: 6px;"
            f"  margin: 1px 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {_HOVER};"
            f"  color: white;"
            f"}}"
        )

    @staticmethod
    def _active_style() -> str:
        return (
            f"QPushButton {{"
            f"  background: {_ACTIVE};"
            f"  color: white;"
            f"  border: none;"
            f"  text-align: left;"
            f"  padding: 0 14px;"
            f"  font-size: 13px;"
            f"  font-weight: 600;"
            f"  border-radius: 6px;"
            f"  margin: 1px 8px;"
            f"}}"
        )

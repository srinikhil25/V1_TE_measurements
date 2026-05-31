"""Tile — a titled panel with an enlarge button, used by the Seebeck cockpit.

Each tile has a header (id badge + title + optional action widgets + enlarge
button) and a body area the caller fills with content. The page owns the
enlarge behaviour; the tile only emits ``enlarge_clicked``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QWidget,
)

from ..theme import (
    CARD_BG, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, PRIMARY,
)
from ..icons import icon as _icon


class Tile(QFrame):
    """A titled content panel with an enlarge toggle in its header."""

    enlarge_clicked = pyqtSignal(object)  # emits self

    def __init__(self, tile_id: str, title: str, badge: str | None = None):
        super().__init__()
        self.tile_id = tile_id
        self._enlarged = False

        self.setObjectName("tile")
        self.setStyleSheet(
            f"QFrame#tile {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 10px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("tileHead")
        header.setFixedHeight(40)
        header.setStyleSheet(
            f"QFrame#tileHead {{ background: #FBFAF5; "
            f"border-bottom: 1px solid {BORDER}; "
            f"border-top-left-radius: 10px; border-top-right-radius: 10px; }}"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 8, 0)
        h.setSpacing(8)

        if badge:
            badge_lbl = QLabel(badge.upper())
            badge_lbl.setStyleSheet(
                f"color: {PRIMARY}; background: #E9F1F2; "
                f"border: 1px solid #BBD3D6; border-radius: 9px; "
                f"padding: 1px 7px; font-size: 9px; font-weight: 700; "
                f"letter-spacing: 1px;"
            )
            h.addWidget(badge_lbl)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12.5px; font-weight: 600;"
        )
        h.addWidget(self._title)
        h.addStretch()

        self._actions_host = QHBoxLayout()
        self._actions_host.setSpacing(6)
        h.addLayout(self._actions_host)

        self.enlarge_btn = QToolButton()
        self.enlarge_btn.setToolTip("Enlarge")
        self.enlarge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enlarge_btn.setFixedSize(26, 26)
        self.enlarge_btn.setIconSize(QSize(15, 15))
        self._style_enlarge(False)
        self.enlarge_btn.clicked.connect(lambda: self.enlarge_clicked.emit(self))
        h.addWidget(self.enlarge_btn)

        outer.addWidget(header)

        # ── Body ─────────────────────────────────────────────────────────
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        outer.addWidget(self.body, 1)

    # ------------------------------------------------------------------
    def add_action(self, widget: QWidget) -> None:
        """Add a custom action widget to the header, before the enlarge button."""
        self._actions_host.addWidget(widget)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_enlarged(self, value: bool) -> None:
        self._enlarged = value
        self.enlarge_btn.setToolTip("Restore" if value else "Enlarge")
        self._style_enlarge(value)

    def is_enlarged(self) -> bool:
        return self._enlarged

    # ------------------------------------------------------------------
    def _style_enlarge(self, active: bool) -> None:
        name = "collapse" if active else "expand"
        if active:
            self.enlarge_btn.setIcon(_icon(name, PRIMARY, 15))
            self.enlarge_btn.setStyleSheet(
                f"QToolButton {{ background: #E9F1F2; border: 1px solid {PRIMARY}; "
                f"border-radius: 5px; }}"
            )
        else:
            self.enlarge_btn.setIcon(_icon(name, TEXT_MUTED, 15))
            self.enlarge_btn.setStyleSheet(
                f"QToolButton {{ background: white; border: 1px solid {BORDER}; "
                f"border-radius: 5px; }}"
                f"QToolButton:hover {{ border-color: {PRIMARY}; }}"
            )

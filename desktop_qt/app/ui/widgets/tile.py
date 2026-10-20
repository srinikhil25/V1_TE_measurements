"""Tile — a titled chart / table panel with an enlarge toggle.

The page owns the enlarge behaviour; the tile only emits ``enlarge_clicked``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import theme as T
from ..icons import icon as _icon
from .ui_kit import label


class Tile(QFrame):
    """A titled content panel with an enlarge toggle in its header."""

    enlarge_clicked = pyqtSignal(object)  # emits self

    def __init__(self, tile_id: str, title: str, badge: str | None = None, *,
                 subtitle: str = ""):
        super().__init__()
        self.tile_id = tile_id
        self._enlarged = False
        self.setProperty("panel", True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        header.setFixedHeight(38)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 6, 0)
        h.setSpacing(8)
        self._title = label(title, "h2")
        h.addWidget(self._title)
        self._sub = label(subtitle, "caption")
        self._sub.setVisible(bool(subtitle))
        h.addWidget(self._sub)
        h.addStretch()

        self._actions_host = QHBoxLayout()
        self._actions_host.setSpacing(4)
        h.addLayout(self._actions_host)

        self.enlarge_btn = QPushButton()
        self.enlarge_btn.setProperty("variant", "ghost")
        self.enlarge_btn.setProperty("iconOnly", True)
        self.enlarge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enlarge_btn.setIconSize(QSize(14, 14))
        self.enlarge_btn.clicked.connect(lambda: self.enlarge_clicked.emit(self))
        h.addWidget(self.enlarge_btn)
        self._style_enlarge(False)
        outer.addWidget(header)

        self.body = QWidget()
        self.body.setObjectName("PanelBody")
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

    def set_subtitle(self, text: str) -> None:
        self._sub.setText(text)
        self._sub.setVisible(bool(text))

    def set_enlarged(self, value: bool) -> None:
        self._enlarged = value
        self._style_enlarge(value)

    def is_enlarged(self) -> bool:
        return self._enlarged

    def _style_enlarge(self, active: bool) -> None:
        self.enlarge_btn.setIcon(_icon("collapse" if active else "expand", T.TEXT_SECONDARY, 14))
        self.enlarge_btn.setToolTip("Restore layout" if active else "Enlarge")


def icon_button(name: str, tooltip: str, slot=None) -> QPushButton:
    """28-px ghost icon button for tile / panel headers."""
    b = QPushButton()
    b.setProperty("variant", "ghost")
    b.setProperty("iconOnly", True)
    b.setIcon(_icon(name, T.TEXT_SECONDARY, 14))
    b.setIconSize(QSize(14, 14))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot is not None:
        b.clicked.connect(slot)
    return b

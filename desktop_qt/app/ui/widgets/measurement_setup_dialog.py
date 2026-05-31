"""
MeasurementSetupDialog — fixed-size heater-profile setup (VB-form style).

A modal dialog holding the on-graph heater profile editor + cooling target.
Because it never resizes, the on-graph inputs sit at fixed positions with no
responsive-layout fragility — exactly like the original VB tool.

Returns the profile params (get_params) + cooling target on accept.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QFrame,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, BORDER_STRONG, CONTENT_BG, PRIMARY, PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from .waveform_widget import SeebeckWaveformWidget


class MeasurementSetupDialog(QDialog):
    def __init__(self, params: dict | None, cooling_target: float,
                 max_current_A: float | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Measurement — Heater Profile")
        self.setModal(True)
        self.setFixedSize(560, 560)
        self.setStyleSheet(f"QDialog {{ background: {CONTENT_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Heading
        title = QLabel("Heater Profile")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;")
        sub = QLabel("Configure the current ramp for the next run.")
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        root.addWidget(title)
        root.addWidget(sub)

        # On-graph editor (fixed size container)
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 10, 10, 10)
        self.editor = SeebeckWaveformWidget()
        self.editor.setMinimumHeight(340)
        if max_current_A is not None:
            self.editor.set_max_current_A(max_current_A)
        if params:
            self.editor.set_params(params)
        cl.addWidget(self.editor)
        root.addWidget(card)

        # Cooling target
        cool_row = QHBoxLayout()
        cool_lbl = QLabel("Cooling target |ΔT|")
        cool_lbl.setStyleSheet(f"background: transparent; color: {TEXT_SECONDARY}; font-size: 12px;")
        self.sb_cooling = QDoubleSpinBox()
        self.sb_cooling.setRange(0.1, 100.0)
        self.sb_cooling.setDecimals(1)
        self.sb_cooling.setValue(cooling_target)
        self.sb_cooling.setSuffix("  °C")
        self.sb_cooling.setFixedHeight(32)
        self.sb_cooling.setFixedWidth(120)
        cool_row.addWidget(cool_lbl)
        cool_row.addStretch()
        cool_row.addWidget(self.sb_cooling)
        root.addLayout(cool_row)
        hint = QLabel("Cooling tail ends when |ΔT| falls below this, or after the timeout.")
        hint.setStyleSheet(f"background: transparent; color: {TEXT_MUTED}; font-size: 10.5px;")
        root.addWidget(hint)

        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(36)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT_SECONDARY}; "
            f"border: 1.5px solid {BORDER_STRONG}; border-radius: 8px; "
            f"padding: 0 18px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ color: {PRIMARY}; border-color: {PRIMARY}; }}"
        )
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply")
        ok.setFixedHeight(36)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 8px; padding: 0 22px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
        )
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)

    def _on_accept(self):
        wp = self.editor.get_params()
        if wp["start_volt"] >= wp["stop_volt"]:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Invalid Parameters",
                "I₀ (start current) must be less than I peak current."
            )
            return
        self.accept()

    # ── results ──────────────────────────────────────────────────────────────
    def get_profile_params(self) -> dict:
        return self.editor.get_params()

    def get_cooling_target(self) -> float:
        return self.sb_cooling.value()

"""
MeasurementSetupDialog — heater-profile editor.

A modal dialog holding the on-graph heater profile editor + cooling target.
Fixed size, so the on-graph inputs sit at stable positions.

Returns the profile params (get_profile_params) + cooling target on accept.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
)

from .ui_kit import Panel, button, label
from .waveform_widget import SeebeckWaveformWidget


class MeasurementSetupDialog(QDialog):
    def __init__(self, params: dict | None, cooling_target: float,
                 max_current_A: float | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Heater profile")
        self.setModal(True)
        self.setFixedSize(600, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        root.addWidget(label("Heater profile", "h1"))
        sub = "Set the current ramp for the next run. Values are entered directly on the diagram."
        if max_current_A is not None:
            sub += f"  Current limit for this geometry: {max_current_A:g} A."
        root.addWidget(label(sub, "secondary", wrap=True))

        card = Panel(flush=True)
        self.editor = SeebeckWaveformWidget()
        self.editor.setMinimumHeight(340)
        if max_current_A is not None:
            self.editor.set_max_current_A(max_current_A)
        if params:
            self.editor.set_params(params)
        card.body.setContentsMargins(8, 8, 8, 8)
        card.body.addWidget(self.editor)
        root.addWidget(card, 1)

        cool_row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Cooling target |ΔT|", "label"))
        col.addWidget(label("The cooling tail ends when |ΔT| falls below this, or at the timeout.",
                            "caption", wrap=True))
        cool_row.addLayout(col, 1)
        self.sb_cooling = QDoubleSpinBox()
        self.sb_cooling.setRange(0.1, 100.0)
        self.sb_cooling.setDecimals(1)
        self.sb_cooling.setValue(cooling_target)
        self.sb_cooling.setSuffix("  K")
        self.sb_cooling.setProperty("mono", True)
        self.sb_cooling.setFixedWidth(120)
        cool_row.addWidget(self.sb_cooling)
        root.addLayout(cool_row)

        line = QFrame()
        line.setObjectName("Divider")
        root.addWidget(line)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        ok = button("Apply profile", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)

    def _on_accept(self):
        wp = self.editor.get_params()
        if wp["start_volt"] >= wp["stop_volt"]:
            QMessageBox.warning(self, "Heater profile",
                                "The start current I₀ must be lower than the peak current.")
            return
        self.accept()

    # ── results ──────────────────────────────────────────────────────────────
    def get_profile_params(self) -> dict:
        return self.editor.get_params()

    def get_cooling_target(self) -> float:
        return self.sb_cooling.value()

"""IR camera live-view widget.

Displays a real-time false-colour (iron colormap) thermal image from the
IrCameraService, along with a colorbar temperature scale and per-frame
Min / Center / Max readings.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ..theme import (
    BORDER, CARD_BG, ERROR, PRIMARY, PRIMARY_HOVER,
    SUCCESS, TEXT_MUTED, TEXT_PRIMARY,
)

# ---------------------------------------------------------------------------
# Iron colormap — standard for Optris IR cameras
# ---------------------------------------------------------------------------

_IRON_LUT: np.ndarray | None = None


def _iron_lut() -> np.ndarray:
    """Return the 256-entry iron colormap as (256, 3) uint8.  Cached."""
    global _IRON_LUT
    if _IRON_LUT is None:
        t     = np.linspace(0.0, 1.0, 256)
        stops = np.array([0.00, 0.20, 0.45, 0.65, 0.85, 1.00])
        r_v   = np.array([  0,   60,  200,  255,  255,  255], dtype=float)
        g_v   = np.array([  0,    0,    0,   80,  210,  255], dtype=float)
        b_v   = np.array([  0,  110,  100,    0,    0,  255], dtype=float)
        _IRON_LUT = np.stack([
            np.interp(t, stops, r_v).astype(np.uint8),
            np.interp(t, stops, g_v).astype(np.uint8),
            np.interp(t, stops, b_v).astype(np.uint8),
        ], axis=1)                        # (256, 3)
    return _IRON_LUT


def _frame_to_pixmap(arr: np.ndarray, disp_w: int, disp_h: int) -> QPixmap:
    """Convert a (H, W) float temperature array to a false-colour QPixmap."""
    lut  = _iron_lut()
    lo, hi = arr.min(), arr.max()
    norm = ((arr - lo) / max(hi - lo, 1e-6) * 255).clip(0, 255).astype(np.uint8)
    rgb  = np.ascontiguousarray(lut[norm])              # (H, W, 3) uint8
    h, w = rgb.shape[:2]
    data = rgb.tobytes()
    img  = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img).scaled(
        disp_w, disp_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _colorbar_pixmap(bar_w: int, bar_h: int) -> QPixmap:
    """Horizontal iron colormap strip of size bar_w × bar_h."""
    lut     = _iron_lut()
    indices = np.linspace(0, 255, bar_w, dtype=int)
    bar     = np.ascontiguousarray(
        np.tile(lut[indices], (bar_h, 1, 1))           # (bar_h, bar_w, 3)
    )
    data = bar.tobytes()
    img  = QImage(data, bar_w, bar_h, bar_w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)


# ---------------------------------------------------------------------------
# Reading pair helper
# ---------------------------------------------------------------------------

def _reading_pair(title: str, value_color: str) -> tuple[QLabel, QFrame]:
    """Return (value_label, container_frame) for a single temperature reading."""
    f = QFrame()
    f.setStyleSheet("background: transparent; border: none;")
    v = QVBoxLayout(f)
    v.setContentsMargins(4, 2, 4, 2)
    v.setSpacing(1)

    t_lbl = QLabel(title)
    t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    t_lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; "
        f"letter-spacing: 0.8px; border: none;"
    )

    val = QLabel("—")
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val.setStyleSheet(
        f"color: {value_color}; font-size: 13px; font-weight: 700; border: none;"
    )

    v.addWidget(t_lbl)
    v.addWidget(val)
    return val, f


# ---------------------------------------------------------------------------
# IrCameraWidget
# ---------------------------------------------------------------------------

class IrCameraWidget(QFrame):
    """Self-contained IR camera live-view card.

    Handles its own connection lifecycle via IrCameraService and updates
    at ``_FPS`` frames per second while connected.
    """

    _FPS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; }}"
        )
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._update_frame)
        self._build_ui()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_header())
        root.addWidget(self._build_image_label())
        root.addLayout(self._build_colorbar_section())
        root.addLayout(self._build_readings_row())

    def _build_header(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)

        sec = QLabel("IR CAMERA")
        sec.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1.2px;"
        )
        h.addWidget(sec)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; padding: 0;")
        h.addWidget(self._dot)

        self._status_lbl = QLabel("Not connected")
        self._status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        h.addWidget(self._status_lbl)
        h.addStretch()

        self._btn = QPushButton("Connect")
        self._btn.setFixedHeight(24)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_connect_style()
        self._btn.clicked.connect(self._toggle_connection)
        h.addWidget(self._btn)

        return h

    def _build_image_label(self) -> QLabel:
        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumHeight(260)
        self._img_lbl.setStyleSheet(
            f"background: #111827; border-radius: 5px; border: 1px solid {BORDER};"
        )
        self._show_placeholder()
        return self._img_lbl

    def _build_colorbar_section(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(2)
        v.setContentsMargins(0, 0, 0, 0)

        self._colorbar_lbl = QLabel()
        self._colorbar_lbl.setFixedHeight(14)
        self._colorbar_lbl.setStyleSheet("border-radius: 3px; background: transparent;")
        v.addWidget(self._colorbar_lbl)

        scale_row = QHBoxLayout()
        self._scale_min = QLabel("—")
        self._scale_min.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self._scale_max = QLabel("—")
        self._scale_max.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._scale_max.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        scale_row.addWidget(self._scale_min)
        scale_row.addStretch()
        scale_row.addWidget(self._scale_max)
        v.addLayout(scale_row)

        return v

    def _build_readings_row(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(0)

        self._val_min, w_min = _reading_pair("MIN",    "#60A5FA")
        self._val_ctr, w_ctr = _reading_pair("CENTER", TEXT_PRIMARY)
        self._val_max, w_max = _reading_pair("MAX",    "#F87171")

        for w in (w_min, w_ctr, w_max):
            h.addWidget(w, stretch=1)
        return h

    # ------------------------------------------------------------------ logic

    def _toggle_connection(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        svc = IrCameraService()

        if svc.is_connected():
            svc.disconnect()
            self._timer.stop()
            self._set_status(connected=False)
            self._show_placeholder()
            self._clear_readings()
            self._colorbar_lbl.clear()
            self._scale_min.setText("—")
            self._scale_max.setText("—")
        else:
            if svc.connect():
                backend = svc.backend or ""
                label = {
                    "otc":        "OTC SDK",
                    "legacy":     "Legacy SDK",
                    "simulation": "Simulation",
                }.get(backend, backend)
                self._set_status(connected=True, label=label)
                self._timer.start()
            else:
                self._status_lbl.setText("Connection failed")
                self._status_lbl.setStyleSheet(f"color: {ERROR}; font-size: 11px;")

    def _update_frame(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        frame = IrCameraService().get_frame()
        if frame is None:
            return

        # Thermal image
        img_w = self._img_lbl.width()  - 2
        img_h = self._img_lbl.height() - 2
        if img_w > 4 and img_h > 4:
            self._img_lbl.setPixmap(_frame_to_pixmap(frame, img_w, img_h))

        # Colorbar
        cb_w = max(self._colorbar_lbl.width(), 100)
        cb_h = self._colorbar_lbl.height()
        self._colorbar_lbl.setPixmap(_colorbar_pixmap(cb_w, cb_h))

        # Temperature stats
        lo  = float(frame.min())
        hi  = float(frame.max())
        cy, cx = frame.shape[0] // 2, frame.shape[1] // 2
        ctr = float(frame[cy, cx])

        self._val_min.setText(f"{lo:.1f}°C")
        self._val_ctr.setText(f"{ctr:.1f}°C")
        self._val_max.setText(f"{hi:.1f}°C")
        self._scale_min.setText(f"{lo:.1f}°C")
        self._scale_max.setText(f"{hi:.1f}°C")

    # ---------------------------------------------------------------- helpers

    def _show_placeholder(self) -> None:
        self._img_lbl.clear()
        self._img_lbl.setText(
            '<span style="color: #94A3B8; font-size: 12px;">No camera signal</span>'
        )

    def _clear_readings(self) -> None:
        for lbl in (self._val_min, self._val_ctr, self._val_max):
            lbl.setText("—")

    def _set_status(self, *, connected: bool, label: str = "") -> None:
        if connected:
            self._dot.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; padding: 0;")
            self._status_lbl.setText(label if label else "Connected")
            self._status_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
            self._apply_disconnect_style()
        else:
            self._dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; padding: 0;")
            self._status_lbl.setText("Not connected")
            self._status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self._apply_connect_style()

    def _apply_connect_style(self) -> None:
        self._btn.setText("Connect")
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
            f"border-radius: 5px; font-size: 11px; font-weight: 600; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: {PRIMARY_HOVER}; }}"
        )

    def _apply_disconnect_style(self) -> None:
        self._btn.setText("Disconnect")
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {ERROR}; color: white; border: none; "
            f"border-radius: 5px; font-size: 11px; font-weight: 600; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: #B91C1C; }}"
        )

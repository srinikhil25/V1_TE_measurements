"""IR camera live-view widget.

Displays a real-time false-colour thermal image from IrCameraService with a
colorbar scale and per-frame Min / Center / Max temperature readings.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QFileDialog, QMessageBox,
)

from ..theme import BORDER, CARD_BG, ERROR, PRIMARY, PRIMARY_HOVER, SUCCESS, WARNING, TEXT_MUTED, TEXT_PRIMARY


# ─────────────────────────────────────────────────────────────────────────────
# Iron colormap helpers
# ─────────────────────────────────────────────────────────────────────────────

_IRON_LUT: np.ndarray | None = None


def _iron_lut() -> np.ndarray:
    """Return the 256-entry iron colormap as (256, 3) uint8 — cached."""
    global _IRON_LUT
    if _IRON_LUT is None:
        t      = np.linspace(0.0, 1.0, 256)
        stops  = np.array([0.00, 0.20, 0.45, 0.65, 0.85, 1.00])
        r_vals = np.array([  0,   60,  200,  255,  255,  255], dtype=float)
        g_vals = np.array([  0,    0,    0,   80,  210,  255], dtype=float)
        b_vals = np.array([  0,  110,  100,    0,    0,  255], dtype=float)
        _IRON_LUT = np.stack([
            np.interp(t, stops, r_vals).astype(np.uint8),
            np.interp(t, stops, g_vals).astype(np.uint8),
            np.interp(t, stops, b_vals).astype(np.uint8),
        ], axis=1)
    return _IRON_LUT


def _frame_to_pixmap(arr: np.ndarray, w: int, h: int) -> QPixmap:
    """Convert a (H, W) float32 °C array to a false-colour QPixmap."""
    lut  = _iron_lut()
    lo, hi = arr.min(), arr.max()
    norm = ((arr - lo) / max(hi - lo, 1e-6) * 255).clip(0, 255).astype(np.uint8)
    rgb  = np.ascontiguousarray(lut[norm])
    fh, fw = rgb.shape[:2]
    img  = QImage(rgb.tobytes(), fw, fh, fw * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img).scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _colorbar_pixmap(w: int, h: int) -> QPixmap:
    """Horizontal iron colormap strip of size w × h."""
    lut  = _iron_lut()
    idxs = np.linspace(0, 255, w, dtype=int)
    bar  = np.ascontiguousarray(np.tile(lut[idxs], (h, 1, 1)))
    img  = QImage(bar.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)


# ─────────────────────────────────────────────────────────────────────────────
# Background connect thread
# ─────────────────────────────────────────────────────────────────────────────

class _ConnectThread(QThread):
    """Runs IrCameraService.connect() off the UI thread.

    connect() can block for several seconds while the SDK probes hardware.
    Running it here keeps the Qt event loop alive during that time.
    """
    done = pyqtSignal(bool, str)   # (success, backend_name)

    def run(self) -> None:
        try:
            from ...services.ir_camera_service import IrCameraService
            svc = IrCameraService()
            ok  = svc.connect()
            self.done.emit(ok, svc.backend or "")
        except Exception:
            self.done.emit(False, "")


# ─────────────────────────────────────────────────────────────────────────────
# Widget
# ─────────────────────────────────────────────────────────────────────────────

class IrCameraWidget(QFrame):
    """Self-contained IR camera live-view card.

    Manages its own connection lifecycle via IrCameraService and repaints
    at _FPS frames per second while connected.
    """

    _FPS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px; }}"
        )
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._tick)
        self._thread: _ConnectThread | None = None
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addLayout(self._build_header())
        root.addWidget(self._build_view())
        root.addLayout(self._build_colorbar())
        root.addLayout(self._build_readings())

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        title = QLabel("IR CAMERA")
        title.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;"
        )
        row.addWidget(title)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; padding: 0;")
        row.addWidget(self._dot)

        self._status = QLabel("Not connected")
        self._status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        row.addWidget(self._status)
        row.addStretch()

        self._btn = QPushButton("Connect")
        self._btn.setFixedHeight(24)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._toggle)
        self._style_btn(connected=False)
        row.addWidget(self._btn)

        # Screenshot button — enabled only when a camera is connected
        self._btn_capture = QPushButton("Take Screenshot")
        self._btn_capture.setFixedHeight(24)
        self._btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_capture.setStyleSheet(
            "QPushButton { background: white; color: #0F172A; border: 1px solid #CBD5E1; "
            "border-radius: 5px; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { background: #F8FAFC; }"
            "QPushButton:disabled { color: #CBD5E1; border-color: #E2E8F0; }"
        )
        self._btn_capture.setEnabled(False)
        self._btn_capture.clicked.connect(self._capture_screenshot)
        row.addWidget(self._btn_capture)

        return row

    def _build_view(self) -> QLabel:
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumHeight(260)
        self._view.setStyleSheet(
            f"background: #111827; border-radius: 5px; border: 1px solid {BORDER};"
        )
        self._show_placeholder()
        return self._view

    def _build_colorbar(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        self._bar = QLabel()
        self._bar.setFixedHeight(14)
        self._bar.setStyleSheet("border-radius: 3px; background: transparent;")
        col.addWidget(self._bar)

        scale = QHBoxLayout()
        self._scale_lo = QLabel("—")
        self._scale_lo.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self._scale_hi = QLabel("—")
        self._scale_hi.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._scale_hi.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        scale.addWidget(self._scale_lo)
        scale.addStretch()
        scale.addWidget(self._scale_hi)
        col.addLayout(scale)

        return col

    def _build_readings(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(0)
        self._lbl_min, wmin = self._reading_cell("MIN",    "#60A5FA")
        self._lbl_ctr, wctr = self._reading_cell("CENTER", TEXT_PRIMARY)
        self._lbl_max, wmax = self._reading_cell("MAX",    "#F87171")
        for w in (wmin, wctr, wmax):
            row.addWidget(w, stretch=1)
        return row

    @staticmethod
    def _reading_cell(title: str, color: str) -> tuple[QLabel, QFrame]:
        cell = QFrame()
        cell.setStyleSheet("background: transparent; border: none;")
        col = QVBoxLayout(cell)
        col.setContentsMargins(4, 2, 4, 2)
        col.setSpacing(1)

        hdr = QLabel(title)
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 0.8px; border: none;"
        )
        val = QLabel("—")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 700; border: none;")

        col.addWidget(hdr)
        col.addWidget(val)
        return val, cell

    # ── connection logic ─────────────────────────────────────────────────────

    def _toggle(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        svc = IrCameraService()

        if svc.is_connected():
            svc.disconnect()
            self._timer.stop()
            self._set_disconnected()
        else:
            self._btn.setEnabled(False)
            self._dot.setStyleSheet(f"color: {WARNING}; font-size: 12px; padding: 0;")
            self._status.setText("Connecting…")
            self._status.setStyleSheet(f"color: {WARNING}; font-size: 11px;")

            self._thread = _ConnectThread(self)
            self._thread.done.connect(self._on_connect)
            self._thread.start()

    def _on_connect(self, ok: bool, backend: str) -> None:
        self._btn.setEnabled(True)
        if ok:
            label = {"otc": "OTC SDK", "legacy": "Legacy SDK"}.get(backend, backend)
            self._dot.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; padding: 0;")
            self._status.setText(label)
            self._status.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
            self._style_btn(connected=True)
            self._btn_capture.setEnabled(True)
            self._timer.start()
        else:
            self._dot.setStyleSheet(f"color: {ERROR}; font-size: 12px; padding: 0;")
            self._status.setText("No camera found")
            self._status.setStyleSheet(f"color: {ERROR}; font-size: 11px;")
            self._style_btn(connected=False)
            self._btn_capture.setEnabled(False)

    # ── frame update ─────────────────────────────────────────────────────────

    def _tick(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        svc   = IrCameraService()
        frame = svc.get_frame()

        if not svc.is_connected():
            self._timer.stop()
            self._set_disconnected()
            return

        if frame is None:
            return

        iw = self._view.width()  - 2
        ih = self._view.height() - 2
        if iw > 4 and ih > 4:
            self._view.setPixmap(_frame_to_pixmap(frame, iw, ih))

        bw = max(self._bar.width(), 100)
        bh = self._bar.height()
        self._bar.setPixmap(_colorbar_pixmap(bw, bh))

        lo  = float(frame.min())
        hi  = float(frame.max())
        cy, cx = frame.shape[0] // 2, frame.shape[1] // 2
        ctr = float(frame[cy, cx])

        self._lbl_min.setText(f"{lo:.1f}°C")
        self._lbl_ctr.setText(f"{ctr:.1f}°C")
        self._lbl_max.setText(f"{hi:.1f}°C")
        self._scale_lo.setText(f"{lo:.1f}°C")
        self._scale_hi.setText(f"{hi:.1f}°C")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _set_disconnected(self) -> None:
        self._show_placeholder()
        self._dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; padding: 0;")
        self._status.setText("Not connected")
        self._status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._style_btn(connected=False)
        if hasattr(self, "_btn_capture"):
            self._btn_capture.setEnabled(False)
        self._bar.clear()
        self._scale_lo.setText("—")
        self._scale_hi.setText("—")
        for lbl in (self._lbl_min, self._lbl_ctr, self._lbl_max):
            lbl.setText("—")

    def _show_placeholder(self) -> None:
        self._view.clear()
        self._view.setText('<span style="color:#94A3B8;font-size:12px;">No camera signal</span>')

    def _style_btn(self, *, connected: bool) -> None:
        if connected:
            self._btn.setText("Disconnect")
            self._btn.setStyleSheet(
                f"QPushButton {{ background:{ERROR}; color:white; border:none; "
                f"border-radius:5px; font-size:11px; font-weight:600; padding:0 10px; }}"
                f"QPushButton:hover {{ background:#B91C1C; }}"
            )
        else:
            self._btn.setText("Connect")
            self._btn.setStyleSheet(
                f"QPushButton {{ background:{PRIMARY}; color:white; border:none; "
                f"border-radius:5px; font-size:11px; font-weight:600; padding:0 10px; }}"
                f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
            )
            
    def _capture_screenshot(self) -> None:
        """Capture the current IR frame as a PNG image."""
        pix = self._view.pixmap()
        if pix is None or pix.isNull():
            QMessageBox.information(
                self,
                "IR Screenshot",
                "No image is currently available to capture.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save IR screenshot",
            "ir_screenshot.png",
            "PNG image (*.png)",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pix.save(path, "PNG")


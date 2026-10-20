"""IR camera live-view widget.

Displays a real-time false-colour thermal image from IrCameraService with a
colorbar scale and per-frame Min / Center / Max temperature readings.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QFileDialog, QMessageBox, QSizePolicy,
)

from .. import theme as T
from ..icons import pixmap as _icon_pixmap


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
    """Self-contained IR camera live-view.

    Manages its own connection lifecycle via IrCameraService and repaints
    at _FPS frames per second while connected.
    """

    _FPS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IrCamera")
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._tick)
        self._thread: _ConnectThread | None = None
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        root.addLayout(self._build_header())
        root.addWidget(self._build_view(), 1)
        root.addLayout(self._build_colorbar())
        root.addLayout(self._build_readings())

    def _build_header(self) -> QHBoxLayout:
        from .ui_kit import Dot, button
        row = QHBoxLayout()
        row.setSpacing(6)
        self._dot = Dot(T.TEXT_DISABLED, 8, hollow=True)
        row.addWidget(self._dot)
        self._status = QLabel("Not connected")
        self._status.setProperty("role", "caption")
        row.addWidget(self._status)
        row.addStretch()

        self._btn_capture = button("", icon="image", size="sm",
                                   tooltip="Save the current thermal image as PNG")
        self._btn_capture.setEnabled(False)
        self._btn_capture.clicked.connect(self._capture_screenshot)
        row.addWidget(self._btn_capture)

        self._btn = button("Connect", "primary", size="sm")
        self._btn.clicked.connect(self._toggle)
        row.addWidget(self._btn)
        return row

    def _build_view(self) -> QLabel:
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumHeight(150)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setStyleSheet(f"background: {T.CHROME_BG}; border-radius: 4px;")
        self._show_placeholder()
        return self._view

    def _build_colorbar(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)
        self._bar = QLabel()
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(f"border-radius: 2px; background: {T.SURFACE_SUNKEN};")
        col.addWidget(self._bar)
        scale = QHBoxLayout()
        self._scale_lo = QLabel("—")
        self._scale_hi = QLabel("—")
        self._scale_hi.setAlignment(Qt.AlignmentFlag.AlignRight)
        for w in (self._scale_lo, self._scale_hi):
            w.setStyleSheet(f"color: {T.TEXT_MUTED}; font-size: 11px; "
                            f"font-family: '{T.mono_family()}';")
        scale.addWidget(self._scale_lo)
        scale.addStretch()
        scale.addWidget(self._scale_hi)
        col.addLayout(scale)
        return col

    def _build_readings(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self._lbl_min, wmin = self._reading_cell("Min", T.SERIES_T2)
        self._lbl_ctr, wctr = self._reading_cell("Centre", T.TEXT_PRIMARY)
        self._lbl_max, wmax = self._reading_cell("Max", T.SERIES_T1)
        for w in (wmin, wctr, wmax):
            row.addWidget(w, stretch=1)
        return row

    @staticmethod
    def _reading_cell(title: str, color: str) -> tuple[QLabel, QFrame]:
        cell = QFrame()
        cell.setObjectName("IrCell")
        cell.setStyleSheet(f"QFrame#IrCell {{ background: {T.SURFACE_ALT}; border-radius: 4px; }}")
        col = QVBoxLayout(cell)
        col.setContentsMargins(8, 5, 8, 6)
        col.setSpacing(0)
        hdr = QLabel(title)
        hdr.setProperty("role", "caption")
        val = QLabel("—")
        val.setStyleSheet(f"color: {color}; font-family: '{T.mono_family()}'; "
                          "font-size: 15px; font-weight: 500;")
        col.addWidget(hdr)
        col.addWidget(val)
        return val, cell

    def _set_status(self, text: str, color: str, hollow: bool = False) -> None:
        self._dot.set_color(color, hollow=hollow)
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")

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
            self._set_status("Connecting…", T.WARNING)
            self._thread = _ConnectThread(self)
            self._thread.done.connect(self._on_connect)
            self._thread.start()

    def _on_connect(self, ok: bool, backend: str) -> None:
        self._btn.setEnabled(True)
        if ok:
            label = {"otc": "OTC SDK", "legacy": "Legacy SDK"}.get(backend, backend)
            self._set_status(f"Live · {label}", T.SUCCESS)
            self._style_btn(connected=True)
            self._btn_capture.setEnabled(True)
            self._timer.start()
        else:
            self._set_status("No camera found", T.DANGER, hollow=True)
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

        self._lbl_min.setText(f"{lo:.1f} °C")
        self._lbl_ctr.setText(f"{ctr:.1f} °C")
        self._lbl_max.setText(f"{hi:.1f} °C")
        self._scale_lo.setText(f"{lo:.1f} °C")
        self._scale_hi.setText(f"{hi:.1f} °C")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _set_disconnected(self) -> None:
        self._show_placeholder()
        self._set_status("Not connected", T.TEXT_MUTED, hollow=True)
        self._style_btn(connected=False)
        if hasattr(self, "_btn_capture"):
            self._btn_capture.setEnabled(False)
        self._bar.clear()
        self._scale_lo.setText("—")
        self._scale_hi.setText("—")
        for lbl in (self._lbl_min, self._lbl_ctr, self._lbl_max):
            lbl.setText("—")

    def _show_placeholder(self) -> None:
        """Centered camera icon + guidance so the dark panel reads as idle, not broken."""
        self._view.clear()
        w, h = 240, 120
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cam = _icon_pixmap("camera", "#5B6472", 36, width=1.6)
        p.drawPixmap((w - 36) // 2, 14, cam)
        f = QFont(T.ui_family())
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T.CHROME_TEXT_2))
        p.drawText(0, 62, w, 20, Qt.AlignmentFlag.AlignHCenter, "No camera connected")
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(T.CHROME_MUTED))
        p.drawText(0, 84, w, 18, Qt.AlignmentFlag.AlignHCenter, "Press Connect to start the live view")
        p.end()
        self._view.setPixmap(pm)

    def _style_btn(self, *, connected: bool) -> None:
        from .ui_kit import set_props
        self._btn.setText("Disconnect" if connected else "Connect")
        set_props(self._btn, variant="danger-outline" if connected else "primary")

    def _capture_screenshot(self) -> None:
        """Capture the current IR frame as a PNG image."""
        pix = self._view.pixmap()
        if pix is None or pix.isNull():
            QMessageBox.information(self, "Thermal image",
                                    "No image is currently available to capture.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save thermal image", "ir_screenshot.png", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pix.save(path, "PNG")

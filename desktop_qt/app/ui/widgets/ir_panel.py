"""Thermal camera panel — live IR image with regions of interest.

``ThermalView`` draws the frame aspect-correct (optionally rotated 90° so the
sample runs hot → cold from top to bottom), the regions, a colour bar and the
temperature under the cursor. Click = spot region, drag = box region (the
selected one, R1 or R2). Click the colour bar to lock / unlock its range.

``IrPanel`` adds the tool row, the camera connection and the region readouts
(min / mean / max; camera ΔT when there are two regions). Regions live in
``app.services.ir_regions`` so the measurement records them with every reading.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...services.ir_regions import MAX_REGIONS, SPOT, Region, get_store, stats
from .. import theme as T
from .ui_kit import button, label, set_props

REGION_COLORS = {"R1": "#3DDC84", "R2": "#5CC8FF"}
REGION_LABELS = {"R1": ("sample centre", "hot side"), "R2": ("cold side", "cold side")}
_CBAR_W = 40          # px kept on the right for the colour bar


# ─────────────────────────────────────────────────────────────────────────────
# Iron palette
# ─────────────────────────────────────────────────────────────────────────────
_IRON_LUT: Optional[np.ndarray] = None


def iron_lut() -> np.ndarray:
    """256 × 3 uint8 iron colour map (cached)."""
    global _IRON_LUT
    if _IRON_LUT is None:
        t = np.linspace(0.0, 1.0, 256)
        stops = np.array([0.00, 0.20, 0.45, 0.65, 0.85, 1.00])
        r = np.array([0, 60, 200, 255, 255, 255], dtype=float)
        g = np.array([0, 0, 0, 80, 210, 255], dtype=float)
        b = np.array([0, 110, 100, 0, 0, 255], dtype=float)
        _IRON_LUT = np.stack([np.interp(t, stops, c).astype(np.uint8) for c in (r, g, b)], axis=1)
    return _IRON_LUT


def colorize(arr: np.ndarray, lo: float, hi: float) -> QImage:
    norm = ((arr - lo) / max(hi - lo, 1e-6) * 255).clip(0, 255)
    norm = np.nan_to_num(norm).astype(np.uint8)
    rgb = np.ascontiguousarray(iron_lut()[norm])
    h, w = rgb.shape[:2]
    return QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()


# ─────────────────────────────────────────────────────────────────────────────
# The image
# ─────────────────────────────────────────────────────────────────────────────
class ThermalView(QWidget):
    """Frame + regions + colour bar. Coordinates: *sensor* (frame column x,
    row y) for regions; *view* for the possibly rotated image on screen."""

    regions_edited = pyqtSignal()       # the operator moved / redrew a region
    range_lock_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(220, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.frame: Optional[np.ndarray] = None
        self.regions: List[Region] = []
        self.selected = 0
        self.tool = "box"               # "box" | "spot"
        self.portrait = True
        self.locked = False
        self.levels: Tuple[float, float] = (20.0, 40.0)
        self.stamp = ""
        self.placeholder: Tuple[str, str] = ("No camera connected", "Press Connect to start the live view")
        self._img: Optional[QImage] = None
        self._press: Optional[Tuple[int, int]] = None
        self._dragging = False
        self._hover: Optional[Tuple[QPointF, str]] = None

    # ── data ─────────────────────────────────────────────────────────────────
    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        self.frame = frame
        if frame is not None:
            if not self.locked:
                finite = frame[np.isfinite(frame)]
                if finite.size:
                    lo, hi = float(finite.min()), float(finite.max())
                    self.levels = (np.floor(lo), np.ceil(hi) if hi - lo >= 1 else np.floor(lo) + 1)
            self._img = colorize(self._view_array(), *self.levels)
        else:
            self._img = None
        self.update()

    def set_locked(self, on: bool) -> None:
        self.locked = on
        self.range_lock_changed.emit(on)
        self.update()

    def set_portrait(self, on: bool) -> None:
        self.portrait = on
        if self.frame is not None:
            self._img = colorize(self._view_array(), *self.levels)
        self.update()

    # ── coordinates ──────────────────────────────────────────────────────────
    def _sensor_shape(self) -> Tuple[int, int]:
        return self.frame.shape[:2] if self.frame is not None else (288, 382)

    def _view_shape(self) -> Tuple[int, int]:
        rows, cols = self._sensor_shape()
        return (cols, rows) if self.portrait else (rows, cols)

    def _view_array(self) -> np.ndarray:
        assert self.frame is not None
        return np.rot90(self.frame, k=-1) if self.portrait else self.frame

    def view_to_sensor(self, vx: int, vy: int) -> Tuple[int, int]:
        rows, _ = self._sensor_shape()
        return (vy, rows - 1 - vx) if self.portrait else (vx, vy)

    def sensor_rect_to_view(self, r: Region) -> QRectF:
        rows, _ = self._sensor_shape()
        if self.portrait:
            return QRectF(rows - r.y - r.h, r.x, r.h, r.w)
        return QRectF(r.x, r.y, r.w, r.h)

    def image_rect(self) -> QRectF:
        """Where the (view) image is drawn on the widget."""
        vr, vc = self._view_shape()
        aw, ah = self.width() - _CBAR_W - 8, self.height() - 8
        s = max(min(aw / vc, ah / vr), 0.01)
        w, h = vc * s, vr * s
        return QRectF(4 + (aw - w) / 2, 4 + (ah - h) / 2, w, h)

    def _cbar_rect(self) -> QRectF:
        return QRectF(self.width() - _CBAR_W + 14, 22, 12, max(self.height() - 44, 20))

    def widget_to_view(self, p: QPointF) -> Optional[Tuple[int, int]]:
        ir = self.image_rect()
        if not ir.contains(p):
            return None
        vr, vc = self._view_shape()
        vx = int((p.x() - ir.left()) / ir.width() * vc)
        vy = int((p.y() - ir.top()) / ir.height() * vr)
        return min(max(vx, 0), vc - 1), min(max(vy, 0), vr - 1)

    def _set_selected_from_view(self, a: Tuple[int, int], b: Tuple[int, int]) -> None:
        if not self.regions:
            return
        (ax, ay), (bx, by) = self.view_to_sensor(*a), self.view_to_sensor(*b)
        r = self.regions[self.selected]
        r.x, r.y = min(ax, bx), min(ay, by)
        r.w, r.h = abs(bx - ax) + 1, abs(by - ay) + 1

    def _spot_at(self, v: Tuple[int, int]) -> None:
        if not self.regions:
            return
        sx, sy = self.view_to_sensor(*v)
        rows, cols = self._sensor_shape()
        r = self.regions[self.selected]
        r.x = min(max(sx - SPOT // 2, 0), cols - SPOT)
        r.y = min(max(sy - SPOT // 2, 0), rows - SPOT)
        r.w = r.h = SPOT

    # ── mouse ────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._cbar_rect().adjusted(-6, -16, 6, 16).contains(e.position()):
            self.set_locked(not self.locked)
            return
        if self.frame is None:
            return
        self._press = self.widget_to_view(e.position())
        self._dragging = False

    def mouseMoveEvent(self, e):
        v = self.widget_to_view(e.position())
        if v is not None and self.frame is not None:
            sx, sy = self.view_to_sensor(*v)
            self._hover = (e.position(), f"{self.frame[sy, sx]:.1f} °C")
        else:
            self._hover = None
        moved = (self._press is not None and v is not None
                 and (self._dragging or max(abs(v[0] - self._press[0]), abs(v[1] - self._press[1])) > 1))
        if moved and self.tool == "box":
            assert self._press is not None and v is not None
            self._dragging = True
            self._set_selected_from_view(self._press, v)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        v = self.widget_to_view(e.position()) or self._press
        if self.tool == "spot" or not self._dragging:
            self._spot_at(v)
        self._press, self._dragging = None, False
        self.regions_edited.emit()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    # ── painting ─────────────────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T.CHROME_BG))
        if self._img is None or self.frame is None:
            self._paint_placeholder(p)
            return
        ir = self.image_rect()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(ir, self._img)
        self._paint_regions(p, ir)
        self._paint_colorbar(p)
        mono = QFont(T.mono_family())
        mono.setPixelSize(10)
        p.setFont(mono)
        if self.stamp:
            p.setPen(QColor(255, 255, 255, 200))
            p.fillRect(QRectF(ir.left() + 6, ir.top() + 6, p.fontMetrics().horizontalAdvance(self.stamp) + 10, 16),
                       QColor(0, 0, 0, 110))
            p.drawText(QPointF(ir.left() + 11, ir.top() + 18), self.stamp)
        if self._hover is not None:
            pos, text = self._hover
            mono.setPixelSize(11)
            p.setFont(mono)
            w = p.fontMetrics().horizontalAdvance(text) + 12
            x = min(pos.x() + 12, self.width() - w - 2)
            y = min(pos.y() + 14, self.height() - 22)
            p.fillRect(QRectF(x, y, w, 18), QColor(0, 0, 0, 190))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QPointF(x + 6, y + 13), text)

    def _paint_regions(self, p: QPainter, ir: QRectF):
        vr, vc = self._view_shape()
        kx, ky = ir.width() / vc, ir.height() / vr
        centres = []
        font = QFont(T.mono_family())
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        for i, r in enumerate(self.regions):
            color = QColor(REGION_COLORS.get(r.name, "#FFFFFF"))
            v = self.sensor_rect_to_view(r)
            rect = QRectF(ir.left() + v.x() * kx, ir.top() + v.y() * ky, v.width() * kx, v.height() * ky)
            centres.append(rect.center())
            p.setPen(QPen(color, 2.4 if i == self.selected else 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if r.is_spot:
                c = rect.center()
                p.drawEllipse(c, 7, 7)
                p.drawLine(QPointF(c.x() - 12, c.y()), QPointF(c.x() + 12, c.y()))
                p.drawLine(QPointF(c.x(), c.y() - 12), QPointF(c.x(), c.y() + 12))
            else:
                p.drawRect(rect)
            st = stats(self.frame, r) if self.frame is not None else None
            text = f"{r.name} {st['mean']:.1f} °C" if st else r.name
            tw = p.fontMetrics().horizontalAdvance(text) + 8
            lx = min(rect.right() + 4, ir.right() - tw)
            ly = max(rect.top() - 2, ir.top() + 14)
            p.fillRect(QRectF(lx, ly - 12, tw, 15), QColor(0, 0, 0, 170))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QPointF(lx + 4, ly), text)
        if len(centres) == 2:
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.2, Qt.PenStyle.DashLine))
            p.drawLine(centres[0], centres[1])

    def _paint_colorbar(self, p: QPainter):
        cb = self._cbar_rect()
        lut = iron_lut()
        n = int(cb.height())
        for i in range(n):
            c = lut[255 - int(i / max(n - 1, 1) * 255)]
            p.fillRect(QRectF(cb.left(), cb.top() + i, cb.width(), 1), QColor(int(c[0]), int(c[1]), int(c[2])))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRect(cb)
        f = QFont(T.mono_family())
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 210))
        lo, hi = self.levels
        p.drawText(QRectF(cb.left() - 14, 4, 40, 16), Qt.AlignmentFlag.AlignCenter, f"{hi:.0f}")
        p.drawText(QRectF(cb.left() - 14, cb.bottom() + 2, 40, 16), Qt.AlignmentFlag.AlignCenter, f"{lo:.0f}")
        if self.locked:
            p.drawText(QRectF(cb.left() - 14, cb.center().y() - 8, 40, 16),
                       Qt.AlignmentFlag.AlignCenter, "🔒")

    def _paint_placeholder(self, p: QPainter):
        f = QFont(T.ui_family())
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T.CHROME_TEXT_2))
        r = self.rect()
        p.drawText(QRectF(0, r.height() / 2 - 22, r.width(), 20), Qt.AlignmentFlag.AlignHCenter,
                   self.placeholder[0])
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(T.CHROME_MUTED))
        p.drawText(QRectF(8, r.height() / 2 + 2, r.width() - 16, 40),
                   Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.placeholder[1])


# ─────────────────────────────────────────────────────────────────────────────
# Connection off the UI thread
# ─────────────────────────────────────────────────────────────────────────────
class _ConnectThread(QThread):
    done = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            from ...services.ir_camera_service import IrCameraService
            svc = IrCameraService()
            ok = svc.connect()
            self.done.emit(ok, svc.backend or "")
        except Exception:
            self.done.emit(False, "")


# ─────────────────────────────────────────────────────────────────────────────
# Panel
# ─────────────────────────────────────────────────────────────────────────────
class _RegionCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IrRegion")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 6, 9, 6)
        lay.setSpacing(8)
        self.swatch = QLabel()
        self.swatch.setFixedSize(10, 10)
        lay.addWidget(self.swatch)
        self.name = label("", "body")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.name, 1)
        self.vals = {}
        for k in ("min", "mean", "max"):
            v = QLabel("—")
            v.setTextFormat(Qt.TextFormat.RichText)
            v.setStyleSheet(f"font-family: '{T.mono_family()}'; font-size: 11px; color: {T.TEXT_MUTED};")
            lay.addWidget(v)
            self.vals[k] = v

    def set(self, r: Region, st: Optional[dict], selected: bool):
        color = REGION_COLORS.get(r.name, "#888")
        self.swatch.setStyleSheet(f"background: {color}; border-radius: 2px;")
        size = "spot" if r.is_spot else f"{r.w}×{r.h} px"
        self.name.setText(f"<b>{r.name}</b> · {r.label} "
                          f"<span style='color:{T.TEXT_MUTED}'>{size}</span>")
        for k, lbl in self.vals.items():
            v = "—" if st is None else f"{st[k]:.1f}"
            lbl.setText(f"{k} <b style='color:{T.TEXT_PRIMARY}; font-size:13px'>{v}</b>")
        border = T.ACCENT if selected else T.BORDER_SUBTLE
        self.setStyleSheet(f"QFrame#IrRegion {{ border: 1px solid {border}; border-radius: 7px; "
                           f"background: {T.SURFACE if selected else T.SURFACE_ALT}; }}")

    def mousePressEvent(self, e):
        self.clicked.emit()


class IrPanel(QFrame):
    """Camera connection, tools, the image and the region readouts."""

    _FPS = 8
    regions_changed = pyqtSignal(str)       # human-readable note for the run log

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("IrPanel")
        self._store = get_store()
        self._thread: Optional[_ConnectThread] = None
        self._tc_delta: Optional[float] = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self._FPS)
        self._timer.timeout.connect(self._tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        self.btn_box = button("", "ghost", size="sm", icon="square", checkable=True,
                              tooltip="Box region: drag on the image")
        self.btn_spot = button("", "ghost", size="sm", icon="crosshair", checkable=True,
                               tooltip="Spot region: click on the image")
        self.btn_box.setChecked(True)
        self.btn_box.clicked.connect(lambda: self.set_tool("box"))
        self.btn_spot.clicked.connect(lambda: self.set_tool("spot"))
        self.btn_region = button("+ Region", size="sm",
                                 tooltip="Add a second region (hot side / cold side) for a camera ΔT")
        self.btn_region.clicked.connect(self.toggle_second_region)
        self.btn_rotate = button("", "ghost", size="sm", icon="rotate",
                                 tooltip="Rotate the view 90° (portrait: hot side at the top)")
        self.btn_rotate.clicked.connect(lambda: self.view.set_portrait(not self.view.portrait))
        self.btn_snap = button("", "ghost", size="sm", icon="image",
                               tooltip="Save the thermal image as PNG")
        self.btn_snap.clicked.connect(self._snapshot)
        self.btn_connect = button("Connect", "primary", size="sm")
        self.btn_connect.clicked.connect(self.toggle_connection)
        for w in (self.btn_box, self.btn_spot, self.btn_region, self.btn_rotate, self.btn_snap):
            tools.addWidget(w)
        tools.addStretch(1)
        tools.addWidget(self.btn_connect)
        root.addLayout(tools)

        self.view = ThermalView()
        self.view.regions = self._store.regions()
        self.view.regions_edited.connect(self._on_edited)
        root.addWidget(self.view, 1)

        self.status = label("Not connected", "caption")
        self.cards_host = QVBoxLayout()
        self.cards_host.setSpacing(6)
        self.cards: List[_RegionCard] = []
        root.addLayout(self.cards_host)
        self.lbl_camdt = label("", "caption")
        self.lbl_camdt.setVisible(False)
        root.addWidget(self.lbl_camdt)
        self.hint = label("", "caption", wrap=True)
        root.addWidget(self.hint)
        self._sync_cards()
        self._update_hint()

    # ── regions ──────────────────────────────────────────────────────────────
    def set_geometry(self, geometry: str) -> None:
        """Regions are remembered per sample geometry."""
        self._store.set_geometry(geometry)
        self.view.regions = self._store.regions()
        self.view.selected = 0
        self._sync_cards()
        self.view.update()

    def set_tool(self, tool: str) -> None:
        self.view.tool = tool
        self.btn_box.setChecked(tool == "box")
        self.btn_spot.setChecked(tool == "spot")
        self._update_hint()

    def toggle_second_region(self) -> None:
        rs = self.view.regions
        if len(rs) >= MAX_REGIONS:
            del rs[1:]
            rs[0].label = REGION_LABELS["R1"][0]
            self.view.selected = 0
            note = "Camera region R2 removed"
        else:
            rows, cols = self.view._sensor_shape()
            w = h = max(SPOT, rows // 14)
            rs[0].label = REGION_LABELS["R1"][1]
            rs[0].x, rs[0].y, rs[0].w, rs[0].h = int(cols * .25), (rows - h) // 2, w, h
            rs.append(Region("R2", REGION_LABELS["R2"][1], int(cols * .72), (rows - h) // 2, w, h))
            self.view.selected = 1
            note = "Camera region R2 added (hot side R1 / cold side R2)"
        self._commit(note)

    def _on_edited(self) -> None:
        r = self.view.regions[self.view.selected]
        self._commit(f"Camera region {r.name} set to "
                     + ("a spot" if r.is_spot else f"a {r.w}×{r.h} px box")
                     + f" at ({r.x}, {r.y})")

    def _commit(self, note: str) -> None:
        self._store.set_regions(self.view.regions)
        self._sync_cards()
        self.view.update()
        self.regions_changed.emit(note)

    def _select(self, i: int) -> None:
        self.view.selected = i
        self._sync_cards()
        self.view.update()

    def _sync_cards(self) -> None:
        rs = self.view.regions
        while len(self.cards) < len(rs):
            c = _RegionCard()
            idx = len(self.cards)
            c.clicked.connect(lambda i=idx: self._select(i))
            self.cards_host.addWidget(c)
            self.cards.append(c)
        while len(self.cards) > len(rs):
            self.cards.pop().deleteLater()
        frame = self.view.frame
        for i, (card, r) in enumerate(zip(self.cards, rs)):
            card.set(r, stats(frame, r) if frame is not None else None, i == self.view.selected)
        self.btn_region.setText("− Region" if len(rs) >= MAX_REGIONS else "+ Region")
        if len(rs) == 2 and frame is not None:
            a, b = stats(frame, rs[0]), stats(frame, rs[1])
            if a and b:
                tc = (f" · thermocouples {self._tc_delta:+.2f} K"
                      if self._tc_delta is not None else "")
                # Same sign convention as the thermocouples: ΔT = cold − hot.
                self.lbl_camdt.setText(f"Camera ΔT (R2 − R1)  <b>{b['mean'] - a['mean']:+.2f} K</b>{tc}")
                self.lbl_camdt.setVisible(True)
                return
        self.lbl_camdt.setVisible(False)

    def set_thermocouple_delta(self, dt: Optional[float]) -> None:
        self._tc_delta = dt

    def _update_hint(self) -> None:
        how = "Drag" if self.view.tool == "box" else "Click"
        self.hint.setText(f"{how} on the image to place the selected region · "
                          "R1 is recorded with every reading.")

    # ── camera ───────────────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        from ...services.ir_camera_service import IrCameraService
        return IrCameraService().is_connected()

    def toggle_connection(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        svc = IrCameraService()
        if svc.is_connected():
            svc.disconnect()
            self._set_disconnected()
            return
        self.btn_connect.setEnabled(False)
        self.view.placeholder = ("Connecting…", "Looking for the thermal camera")
        self.view.update()
        self._thread = _ConnectThread(self)
        self._thread.done.connect(self._on_connect)
        self._thread.start()

    def _on_connect(self, ok: bool, backend: str) -> None:
        self.btn_connect.setEnabled(True)
        if not ok:
            self.view.placeholder = ("No camera found",
                                     "Check the USB cable and that the camera is on, then Connect again")
            self.view.update()
            return
        self._backend = {"otc": "OTC", "legacy": "Legacy SDK", "sim": "SIMULATED"}.get(backend, backend)
        self.btn_connect.setText("Disconnect")
        set_props(self.btn_connect, variant="danger-outline")
        self._timer.start()

    def _set_disconnected(self) -> None:
        self._timer.stop()
        self.btn_connect.setText("Connect")
        set_props(self.btn_connect, variant="primary")
        self.view.placeholder = ("No camera connected", "Press Connect to start the live view")
        self.view.set_frame(None)
        self._sync_cards()

    def _tick(self) -> None:
        from ...services.ir_camera_service import IrCameraService
        svc = IrCameraService()
        frame = svc.get_frame()
        if not svc.is_connected():
            self._set_disconnected()
            return
        if frame is None:
            return
        rows, cols = frame.shape[:2]
        self.view.stamp = f"{getattr(self, '_backend', '')} · {cols}×{rows}".strip(" ·")
        self.view.set_frame(frame)
        self._sync_cards()

    def _snapshot(self) -> None:
        from .export_ui import save_graphs
        save_graphs(self, [(self.view, "thermal")], kind="seebeck",
                    has_data=self.view.frame is not None)

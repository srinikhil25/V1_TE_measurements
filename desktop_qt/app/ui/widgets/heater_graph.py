"""
HeaterProfileGraphicsEditor — on-graph waveform editor, the robust modern way.

Replicates the original VB/VBA tool: editable fields sit directly ON the
trapezoid diagram. Built with a QGraphicsScene in a FIXED logical coordinate
space + QGraphicsProxyWidget inputs placed once. The view scales the whole
scene as a single unit (uniform transform), so fields and curve can never
drift apart or overlap — unlike per-widget repositioning.

Public API matches the other editors:
    get_params() -> dict
    set_max_current_A(amps | None)
    params_changed (signal)
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QDoubleSpinBox, QSpinBox, QComboBox,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QPen, QColor, QFont, QBrush, QLinearGradient, QPolygonF,
)

from ..theme import PRIMARY, BORDER_STRONG, TEXT_SECONDARY, TEXT_MUTED

# ── Fixed design coordinate space (the scene never changes size) ──────────────
_W, _H = 384, 326

# trapezoid geometry (design coords)
_X_AXIS   = 70          # Y-axis x
_Y_PEAK   = 96          # plateau (I peak) y
_Y_BASE   = 244         # baseline (I₀) y
_X_PRE    = 122         # end of pre segment
_X_PLAT0  = 168         # plateau start
_X_PLAT1  = 266         # plateau end
_X_RAMP1  = 316         # ramp-down end (back to baseline)
_X_END    = 350         # x-axis end

_BOX_QSS = (
    "QAbstractSpinBox, QComboBox {"
    "  background: #FFFBEA; color: #1F2937;"   # soft yellow, echoing the VB boxes
    "  border: 1px solid #C7C0B0; border-radius: 4px;"
    "  padding: 1px 4px; font-size: 12px; font-family: 'Consolas', monospace; }"
    "QAbstractSpinBox:focus, QComboBox:focus { border: 1.5px solid %s; background: #FFFFFF; }"
    "QComboBox::drop-down { border: none; width: 14px; }"
) % PRIMARY


class HeaterProfileGraphicsEditor(QGraphicsView):
    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_current_A = None

        self._scene = QGraphicsScene(0, 0, _W, _H, self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet("background: #FBFAF5; border: 1px solid #E2DED4; border-radius: 8px;")
        self.setMinimumHeight(300)

        self._draw_diagram()
        self._add_inputs()

    # ── static diagram ───────────────────────────────────────────────────────
    def _draw_diagram(self):
        sc = self._scene

        # fill under the trapezoid
        grad = QLinearGradient(0, _Y_PEAK, 0, _Y_BASE)
        c1 = QColor(PRIMARY); c1.setAlpha(48)
        c2 = QColor(PRIMARY); c2.setAlpha(6)
        grad.setColorAt(0, c1); grad.setColorAt(1, c2)
        poly = QPolygonF([
            QPointF(_X_AXIS, _Y_BASE), QPointF(_X_PRE, _Y_BASE),
            QPointF(_X_PLAT0, _Y_PEAK), QPointF(_X_PLAT1, _Y_PEAK),
            QPointF(_X_RAMP1, _Y_BASE),
        ])
        sc.addPolygon(poly, QPen(Qt.PenStyle.NoPen), QBrush(grad))

        # dashed peak reference line
        dpen = QPen(QColor(BORDER_STRONG), 1, Qt.PenStyle.DashLine)
        sc.addLine(_X_AXIS, _Y_PEAK, _X_RAMP1, _Y_PEAK, dpen)

        # axes
        axpen = QPen(QColor("#1E293B"), 1.5)
        sc.addLine(_X_AXIS, 60, _X_AXIS, _Y_BASE, axpen)       # Y
        sc.addLine(_X_AXIS, _Y_BASE, _X_END, _Y_BASE, axpen)   # X
        # arrowheads
        for (x, y, dx1, dy1, dx2, dy2) in [
            (_X_AXIS, 60, -4, 10, 4, 10),
            (_X_END, _Y_BASE, -8, -4, -8, 4),
        ]:
            sc.addLine(x, y, x + dx1, y + dy1, axpen)
            sc.addLine(x, y, x + dx2, y + dy2, axpen)

        # trapezoid outline
        wpen = QPen(QColor(PRIMARY), 2.6)
        wpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        wpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        path = QPainterPath()
        path.moveTo(_X_AXIS, _Y_BASE)
        path.lineTo(_X_PRE, _Y_BASE)
        path.lineTo(_X_PLAT0, _Y_PEAK)
        path.lineTo(_X_PLAT1, _Y_PEAK)
        path.lineTo(_X_RAMP1, _Y_BASE)
        path.lineTo(_X_END - 6, _Y_BASE)
        sc.addPath(path, wpen)

        # dimension brackets for t_pre and t_hold
        bpen = QPen(QColor(TEXT_SECONDARY), 1)
        self._bracket(sc, _X_AXIS, _X_PRE, _Y_BASE + 14, bpen)            # t_pre below axis
        self._bracket(sc, _X_PLAT0, _X_PLAT1, _Y_PEAK - 12, bpen, up=True)  # t_hold above plateau

        # text labels
        self._text("t_Pre",     (_X_AXIS + _X_PRE) / 2 - 16, _Y_BASE + 16, 8.5, TEXT_MUTED)
        self._text("t_Hold",    (_X_PLAT0 + _X_PLAT1) / 2 - 18, _Y_PEAK - 30, 9, TEXT_SECONDARY)
        self._text("Inc. Rate", (_X_PRE + _X_PLAT0) / 2 - 4, _Y_PEAK + 18, 8.5, TEXT_SECONDARY)
        self._text("Dec. Rate", (_X_PLAT1 + _X_RAMP1) / 2 - 4, _Y_PEAK + 18, 8.5, TEXT_SECONDARY)
        self._text("Interval",  198, 18, 9, TEXT_SECONDARY)
        self._lbl_iunit = self._text("I (mA)", 30, 70, 9, "#1E293B", bold=True)
        self._text("t", _X_END - 2, _Y_BASE + 8, 9, "#1E293B", bold=True)
        # peak/base tick marks
        sc.addLine(_X_AXIS - 5, _Y_PEAK, _X_AXIS, _Y_PEAK, axpen)
        sc.addLine(_X_AXIS - 5, _Y_BASE, _X_AXIS, _Y_BASE, axpen)

        self._lbl_inc_unit = self._text("mA/s", 0, 0, 8.5, TEXT_MUTED)
        self._lbl_dec_unit = self._text("mA/s", 0, 0, 8.5, TEXT_MUTED)

    @staticmethod
    def _bracket(sc, x1, x2, y, pen, up=False):
        tick = -4 if up else 4
        sc.addLine(x1 + 2, y, x2 - 2, y, pen)
        sc.addLine(x1 + 2, y, x1 + 2, y + tick, pen)
        sc.addLine(x2 - 2, y, x2 - 2, y + tick, pen)

    def _text(self, s, x, y, pt, color, bold=False):
        it = self._scene.addText(s, QFont("Segoe UI", int(pt), QFont.Weight.Bold if bold else QFont.Weight.Normal))
        it.setDefaultTextColor(QColor(color))
        it.setPos(x, y)
        return it

    # ── editable inputs (proxy widgets, fixed positions) ─────────────────────
    def _add_inputs(self):
        self.sb_interval = self._isb(1, 60, 2)
        self.sb_t_pre    = self._isb(0, 3600, 5)
        self.sb_t_hold   = self._isb(0, 3600, 600)
        self.sb_i0       = self._dsb(0, 2000, 0.0, 2)
        self.sb_ipeak    = self._dsb(0.1, 2000, 1.0, 2)
        self.sb_inc      = self._dsb(0.01, 200, 1.0, 2)
        self.sb_dec      = self._dsb(0.01, 200, 1.0, 2)
        self.cb_unit     = QComboBox(); self.cb_unit.addItems(["mA", "A"])
        self.cb_unit.setFixedSize(54, 24); self.cb_unit.setStyleSheet(_BOX_QSS)
        self.cb_unit.currentTextChanged.connect(self._on_unit_changed)

        # place each at fixed scene coords (echoing the VB layout)
        self._place(self.sb_interval, 262, 10, 60)
        self._place(self.sb_ipeak,     6, _Y_PEAK - 14, 58)
        self._place(self.sb_i0,        6, _Y_BASE - 14, 58)
        self._place(self.sb_t_hold,  192, _Y_PEAK - 8, 64)
        self._place(self.sb_inc,     118, _Y_PEAK + 34, 64)
        self._place(self.sb_dec,     236, _Y_PEAK + 34, 64)
        self._place(self.sb_t_pre,    82, _Y_BASE + 30, 56)
        self._place(self.cb_unit,    300, _Y_BASE + 30)

        # unit suffix labels next to the rate boxes
        self._lbl_inc_unit.setPos(118 + 66, _Y_PEAK + 36)
        self._lbl_dec_unit.setPos(236 + 66, _Y_PEAK + 36)

        for sb in (self.sb_interval, self.sb_t_pre, self.sb_t_hold,
                   self.sb_i0, self.sb_ipeak, self.sb_inc, self.sb_dec):
            sb.valueChanged.connect(self._on_changed)

        self._update_unit_labels("mA")

    def _dsb(self, lo, hi, val, dec):
        sb = QDoubleSpinBox(); sb.setRange(lo, hi); sb.setDecimals(dec); sb.setValue(val)
        sb.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        sb.setStyleSheet(_BOX_QSS); sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return sb

    def _isb(self, lo, hi, val):
        sb = QSpinBox(); sb.setRange(lo, hi); sb.setValue(val)
        sb.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        sb.setStyleSheet(_BOX_QSS); sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return sb

    def _place(self, widget, x, y, w=None):
        if w is not None:
            widget.setFixedSize(w, 24)
        proxy = self._scene.addWidget(widget)
        proxy.setPos(x, y)
        return proxy

    # ── reactions ────────────────────────────────────────────────────────────
    def _on_changed(self):
        self.params_changed.emit()

    def _on_unit_changed(self, unit: str):
        self._update_unit_labels(unit)
        self._apply_current_limit()
        self.params_changed.emit()

    def _update_unit_labels(self, unit: str):
        self._unit = unit
        self._lbl_inc_unit.setPlainText(f"{unit}/s")
        self._lbl_dec_unit.setPlainText(f"{unit}/s")
        self._lbl_iunit.setPlainText(f"I ({unit})")

    # ── current cap ──────────────────────────────────────────────────────────
    def set_max_current_A(self, amps):
        self._max_current_A = amps
        self._apply_current_limit()

    def _apply_current_limit(self):
        if self._max_current_A is None:
            return
        unit = getattr(self, "_unit", "mA")
        cap = self._max_current_A * (1000.0 if unit == "mA" else 1.0)
        self.sb_ipeak.setMaximum(cap)
        self.sb_i0.setMaximum(cap)
        if self.sb_ipeak.value() > cap:
            self.sb_ipeak.setValue(cap)
        if self.sb_i0.value() > cap:
            self.sb_i0.setValue(cap)

    # ── uniform scaling (the whole scene scales as one unit) ─────────────────
    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        self.fitInView(QRectF(0, 0, _W, _H), Qt.AspectRatioMode.KeepAspectRatio)

    # ── public API ───────────────────────────────────────────────────────────
    def set_params(self, p: dict):
        """Load values from a params dict (the inverse of get_params)."""
        if not p:
            return
        unit = p.get("pk160_current_unit", "mA")
        # set unit first so suffix labels / caps use the right scale
        idx = self.cb_unit.findText(unit)
        if idx >= 0:
            self.cb_unit.setCurrentIndex(idx)
        self.sb_interval.setValue(int(p.get("interval", 2)))
        self.sb_t_pre.setValue(int(p.get("pre_time", 5)))
        self.sb_t_hold.setValue(int(p.get("hold_time", 600)))
        self.sb_i0.setValue(float(p.get("start_volt", 0.0)))
        self.sb_ipeak.setValue(float(p.get("stop_volt", 1.0)))
        self.sb_inc.setValue(float(p.get("inc_rate", 1.0)))
        self.sb_dec.setValue(float(p.get("dec_rate", 1.0)))

    def get_params(self) -> dict:
        return {
            "interval":           int(self.sb_interval.value()),
            "pre_time":           int(self.sb_t_pre.value()),
            "start_volt":         self.sb_i0.value(),
            "stop_volt":          self.sb_ipeak.value(),
            "inc_rate":           self.sb_inc.value(),
            "dec_rate":           self.sb_dec.value(),
            "hold_time":          int(self.sb_t_hold.value()),
            "pk160_current_unit": self.cb_unit.currentText(),
        }

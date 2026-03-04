"""
SeebeckWaveformWidget
─────────────────────
QPainter canvas that draws the trapezoidal current profile.
Every input spinbox is a child widget positioned directly ON the diagram,
each with its own floating QLabel name-tag above it.

Visual zones
────────────
  ┌──── top bar (Interval) ───────────────────────────────────────────────┐
  │  I peak │  ·· Peak ─────────────────────────────── ··                │
  │ [200.0] │          [ t_hold: 200 s ]                                  │
  │         │        ╱ [Inc. Rate 5 mA/s]  [Dec. Rate 5 mA/s] ╲          │
  │  I₀     │       ╱                                           ╲         │
  │ [0.0]   │──────╱                                             ╲────── →│
  ├──── bottom bar ───────────────────────────────────────────────────────┤
  │         [ t_pre: 60 s ]                           Unit [mA▼]          │
  └───────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QDoubleSpinBox, QSpinBox, QLabel, QComboBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QPalette, QBrush, QPolygon,
    QLinearGradient,
)
from PyQt6.QtCore import QPoint, QRect

# ── Layout margins (px) ────────────────────────────────────────────────────
_ML = 96    # left  — I₀/I_peak spinboxes + Y-axis label
_MR = 22    # right
_MT = 44    # top   — Interval row
_MB = 62    # bottom — t_Pre row + Unit combo

# ── Spinbox sizes ──────────────────────────────────────────────────────────
_SW  = 80   # standard width
_SWL = 102  # wide (rate fields include unit suffix)
_SH  = 26   # height

# ── Label above each spinbox ───────────────────────────────────────────────
_LH = 17    # label height
_LF = QFont("Segoe UI", 8)

# ── Colour tokens ──────────────────────────────────────────────────────────
_BG_CHART   = "#F8FAFF"
_BG_WIDGET  = "#FFFFFF"
_C_GRID     = "#E2E8F0"
_C_AXIS     = "#1E293B"
_C_WAVE     = "#1D4ED8"
_C_FILL1    = "#BFDBFE"   # fill top
_C_FILL2    = "#EFF6FF"   # fill bottom
_C_DASH     = "#94A3B8"
_C_ANN      = "#475569"   # annotation / bracket
_C_LBL      = "#64748B"   # floating label text
_C_TICK     = "#334155"

# Minimum visual fraction for each segment (pre, ramp-up, hold, ramp-down)
_MIN_F = [0.12, 0.15, 0.32, 0.15]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─────────────────────────────────────────────────────────────────────────────
class SeebeckWaveformWidget(QWidget):
    """
    Trapezoidal current-profile diagram with overlaid input widgets.
    All QSpinBox / QDoubleSpinBox / QLabel children are repositioned every
    time a parameter changes or the widget is resized.
    """

    params_changed = pyqtSignal()

    # ── init ─────────────────────────────────────────────────────────────────

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(430, 310)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_BG_WIDGET))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self._build_inputs()
        for sb in self._spinboxes():
            sb.valueChanged.connect(self._on_changed)
        self.cb_unit.currentTextChanged.connect(self._on_unit_changed)

    # ── input widgets ────────────────────────────────────────────────────────

    def _build_inputs(self):
        def _dsb(lo, hi, val, dec=1, w=_SW):
            sb = QDoubleSpinBox(self)
            sb.setRange(lo, hi); sb.setValue(val); sb.setDecimals(dec)
            sb.setFixedSize(w, _SH)
            return sb

        def _isb(lo, hi, val, w=_SW):
            sb = QSpinBox(self)
            sb.setRange(lo, hi); sb.setValue(val)
            sb.setFixedSize(w, _SH)
            return sb

        def _lbl(text):
            lb = QLabel(text, self)
            lb.setFont(_LF)
            lb.setStyleSheet(f"color: {_C_LBL}; background: transparent;")
            lb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lb.setFixedHeight(_LH)
            return lb

        # ── Spinboxes ────────────────────────────────
        self.sb_interval = _isb(1,    60,    2)
        self.sb_t_pre    = _isb(0,    3600,  5)
        self.sb_i0       = _dsb(0,    2000,  0.0)
        self.sb_ipeak    = _dsb(0.1,  2000,  1.0)
        self.sb_inc      = _dsb(0.01, 200,   1.0, w=_SWL)
        self.sb_dec      = _dsb(0.01, 200,   1.0, w=_SWL)
        self.sb_t_hold   = _isb(0,    3600,  600)

        self.cb_unit = QComboBox(self)
        self.cb_unit.addItems(["mA", "A"])
        self.cb_unit.setFixedSize(66, _SH)
        # Explicit light style — widget's custom QPalette would otherwise
        # propagate the dark sidebar palette into the popup view.
        self.cb_unit.setStyleSheet(
            "QComboBox {"
            "  background: #FFFFFF; color: #0F172A;"
            "  border: 1.5px solid #CBD5E1; border-radius: 5px;"
            "  padding: 3px 6px;"
            "}"
            "QComboBox::drop-down { border: none; width: 18px; }"
            "QComboBox QAbstractItemView {"
            "  background: white; color: #0F172A;"
            "  border: 1px solid #CBD5E1;"
            "  selection-background-color: #EFF6FF;"
            "  selection-color: #0F172A;"
            "  outline: 0px;"
            "}"
        )

        # ── Labels ───────────────────────────────────
        self.lb_interval = _lbl("Interval")
        self.lb_t_pre    = _lbl("t_pre")
        self.lb_i0       = _lbl("I₀")
        self.lb_ipeak    = _lbl("I peak")
        self.lb_inc      = _lbl("Inc. Rate")
        self.lb_dec      = _lbl("Dec. Rate")
        self.lb_t_hold   = _lbl("t_hold")
        self.lb_unit     = _lbl("Unit")

        self._unit = "mA"
        self._update_suffixes("mA")

    def _spinboxes(self):
        return [self.sb_interval, self.sb_t_pre, self.sb_i0,
                self.sb_ipeak, self.sb_inc, self.sb_dec, self.sb_t_hold]

    def _inputs(self):
        return self._spinboxes() + [
            self.cb_unit,
            self.lb_interval, self.lb_t_pre, self.lb_i0, self.lb_ipeak,
            self.lb_inc, self.lb_dec, self.lb_t_hold, self.lb_unit,
        ]

    def _on_unit_changed(self, unit: str):
        self._unit = unit
        self._update_suffixes(unit)
        self.update()
        self._reposition()

    def _update_suffixes(self, unit: str):
        sfx = f" {unit}/s"
        self.sb_inc.setSuffix(sfx)
        self.sb_dec.setSuffix(sfx)
        self.sb_interval.setSuffix(" s")
        self.sb_t_pre.setSuffix(" s")
        self.sb_t_hold.setSuffix(" s")

    def _on_changed(self):
        self.update()
        self._reposition()
        self.params_changed.emit()

    # ── geometry helpers ─────────────────────────────────────────────────────

    def _chart(self):
        """(cx, cy, cw, ch) — inner chart rectangle."""
        return _ML, _MT, self.width() - _ML - _MR, self.height() - _MT - _MB

    def _y_px(self, cy, ch):
        y_base = cy + ch
        y_peak = cy + int(ch * 0.20)   # 20 % from top → enough gap for t_hold
        return y_base, y_peak

    def _fracs(self):
        """Segment time fractions with enforced minimums, normalised to sum=1."""
        i0  = self.sb_i0.value()
        ip  = self.sb_ipeak.value()
        di  = max(ip - i0, 0.01)
        tp  = float(self.sb_t_pre.value())
        th  = float(self.sb_t_hold.value())
        tu  = di / max(self.sb_inc.value(), 0.001)
        td  = di / max(self.sb_dec.value(), 0.001)
        raw = [tp, tu, th, td]
        total = max(sum(raw), 0.001)
        fracs = [max(r / total, m) for r, m in zip(raw, _MIN_F)]
        s = sum(fracs)
        return [f / s for f in fracs]

    def _key_x(self, cx, cw):
        f = self._fracs()
        xA = cx + int(f[0] * cw)
        xB = cx + int((f[0] + f[1]) * cw)
        xC = cx + int((f[0] + f[1] + f[2]) * cw)
        xD = cx + cw
        return xA, xB, xC, xD

    # ── paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy, cw, ch = self._chart()
        yb, yp = self._y_px(cy, ch)
        xA, xB, xC, xD = self._key_x(cx, cw)

        # ── Chart background ─────────────────────────────────────────────
        p.fillRect(cx, cy, cw, ch, QColor(_BG_CHART))

        # ── Grid ─────────────────────────────────────────────────────────
        grid_pen = QPen(QColor(_C_GRID), 1, Qt.PenStyle.SolidLine)
        p.setPen(grid_pen)
        for frac in (0.25, 0.5, 0.75):
            gy = cy + int(ch * frac)
            p.drawLine(cx, gy, cx + cw, gy)
        for frac in (0.25, 0.5, 0.75):
            gx = cx + int(cw * frac)
            p.drawLine(gx, cy, gx, cy + ch)

        # ── Gradient fill under waveform ──────────────────────────────────
        grad = QLinearGradient(0, yp, 0, yb)
        c1 = QColor(_C_FILL1); c1.setAlpha(160)
        c2 = QColor(_C_FILL2); c2.setAlpha(60)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        poly = QPolygon([
            QPoint(cx, yb), QPoint(xA, yb), QPoint(xB, yp),
            QPoint(xC, yp), QPoint(xD, yb),
        ])
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── Dashed I_peak reference line ──────────────────────────────────
        p.setPen(QPen(QColor(_C_DASH), 1, Qt.PenStyle.DashLine))
        p.drawLine(cx, yp, xD, yp)

        # ── Axes ──────────────────────────────────────────────────────────
        p.setPen(QPen(QColor(_C_AXIS), 1.5))
        p.drawLine(cx, cy + 4, cx, yb)      # Y
        p.drawLine(cx, yb, xD + 6, yb)      # X
        # Arrowheads
        p.drawLine(cx, cy + 4, cx - 4, cy + 14)
        p.drawLine(cx, cy + 4, cx + 4, cy + 14)
        p.drawLine(xD + 6, yb, xD - 2, yb - 4)
        p.drawLine(xD + 6, yb, xD - 2, yb + 4)

        # Y-axis ticks + value labels
        tick_font = QFont("Segoe UI", 8)
        p.setFont(tick_font)
        p.setPen(QPen(QColor(_C_TICK)))
        for yp_val, sb in [(yp, self.sb_ipeak), (yb, self.sb_i0)]:
            p.drawLine(cx - 5, yp_val, cx, yp_val)   # tick mark
            val_str = f"{sb.value():.0f}"
            p.drawText(cx - 36, yp_val + 5, val_str)

        # ── Waveform ──────────────────────────────────────────────────────
        wave_pen = QPen(QColor(_C_WAVE), 2.5)
        wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        wave_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(wave_pen)
        pts = [(cx, yb), (xA, yb), (xB, yp), (xC, yp), (xD, yb)]
        for i in range(len(pts) - 1):
            p.drawLine(int(pts[i][0]), pts[i][1], int(pts[i+1][0]), pts[i+1][1])

        # ── t_Pre dimension bracket (below x-axis) ────────────────────────
        ann_pen = QPen(QColor(_C_ANN), 1)
        p.setPen(ann_pen)
        self._bracket(p, cx, xA, yb + 10, yb + 17)

        # ── t_Hold dimension bracket (above plateau, inside chart) ────────
        self._bracket(p, xB, xC, yp - 9, yp - 15)

        # ── Axis labels ───────────────────────────────────────────────────
        y_unit = "A" if self._unit == "A" else "mA"

        # Y-axis label (rotated)
        p.save()
        p.translate(11, cy + ch // 2)
        p.rotate(-90)
        bf = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(bf)
        p.setPen(QPen(QColor(_C_AXIS)))
        p.drawText(-22, 0, f"I ({y_unit})")
        p.restore()

        # X-axis label
        nf = QFont("Segoe UI", 8)
        p.setFont(nf)
        p.setPen(QPen(QColor(_C_ANN)))
        p.drawText(cx + cw // 2 - 22, yb + _MB - 10, "Time (s)")

        p.end()

    @staticmethod
    def _bracket(p: QPainter, x1: int, x2: int, y_outer: int, y_inner: int):
        """  ─|────────|─   dimension bracket """
        x1, x2, yi, yo = int(x1) + 3, int(x2) - 3, int(y_inner), int(y_outer)
        p.drawLine(x1, yi, x2, yi)
        p.drawLine(x1, yi, x1, yo)
        p.drawLine(x2, yi, x2, yo)

    # ── layout ───────────────────────────────────────────────────────────────

    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        self._reposition()

    def showEvent(self, evt):
        super().showEvent(evt)
        self._reposition()

    def _reposition(self):
        if not self.isVisible():
            return

        cx, cy, cw, ch = self._chart()
        yb, yp = self._y_px(cy, ch)
        xA, xB, xC, xD = self._key_x(cx, cw)
        W, H = self.width(), self.height()

        def place(sb, lbl, x, y):
            """Place spinbox at (x,y) and its label above it."""
            x = _clamp(int(x), 0, W - sb.width())
            y = _clamp(int(y), _LH + 2, H - sb.height())
            sb.move(x, y)
            # Centre label over spinbox
            lx = _clamp(x + (sb.width() - lbl.width()) // 2, 0, W - lbl.width())
            lbl.setFixedWidth(max(sb.width(), 70))
            lbl.move(lx, max(0, y - _LH - 1))

        # ── Interval — top-right corner ───────────────────────────────────
        x_int = W - _MR - self.sb_interval.width()
        y_int = _MT - _SH - 4
        self.sb_interval.move(_clamp(x_int, 0, W - self.sb_interval.width()),
                               _clamp(y_int, 2, H - _SH))
        iw = self.sb_interval.width()
        self.lb_interval.setFixedWidth(iw)
        self.lb_interval.move(x_int, max(0, y_int - _LH - 1))

        # ── I peak — left margin, at peak level ───────────────────────────
        place(self.sb_ipeak, self.lb_ipeak,
              cx - self.sb_ipeak.width() - 6,
              yp - _SH // 2)

        # ── I₀ — left margin, at baseline ────────────────────────────────
        place(self.sb_i0, self.lb_i0,
              cx - self.sb_i0.width() - 6,
              yb - _SH)

        # ── t_Hold — just below peak line, centred on hold segment ───────
        mid_hold = (xB + xC) // 2
        place(self.sb_t_hold, self.lb_t_hold,
              mid_hold - self.sb_t_hold.width() // 2,
              yp + 6)

        # ── Inc. Rate — mid-point of rising slope ─────────────────────────
        mid_up_x = (xA + xB) // 2
        mid_up_y = (yb + yp) // 2
        place(self.sb_inc, self.lb_inc,
              mid_up_x - self.sb_inc.width() // 2,
              mid_up_y)

        # ── Dec. Rate — mid-point of falling slope ────────────────────────
        mid_dn_x = (xC + xD) // 2
        mid_dn_y = (yp + yb) // 2
        place(self.sb_dec, self.lb_dec,
              mid_dn_x - self.sb_dec.width() // 2,
              mid_dn_y)

        # ── t_Pre — below x-axis, centred in pre-heat segment ────────────
        mid_pre = (cx + xA) // 2
        place(self.sb_t_pre, self.lb_t_pre,
              mid_pre - self.sb_t_pre.width() // 2,
              yb + 20)

        # ── Unit combo — bottom-right ─────────────────────────────────────
        ux = W - _MR - self.cb_unit.width()
        uy = H - self.cb_unit.height() - 10
        self.cb_unit.move(_clamp(ux, 0, W - self.cb_unit.width()),
                           _clamp(uy, 0, H - _SH))
        uw = self.cb_unit.width()
        self.lb_unit.setFixedWidth(uw)
        self.lb_unit.move(ux, max(0, uy - _LH - 1))

    # ── public API ───────────────────────────────────────────────────────────

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

"""ProfilePreview — read-only sketch of the trapezoidal heater profile.

Shows the four segments (pre-heat · power up · hold · power down) with the
current levels, and highlights the active segment during a run.
"""

from __future__ import annotations

from itertools import pairwise

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .. import theme as T

_SEG_KEYS = ("pre", "ramp_up", "hold", "ramp_down")
_MIN_F = (0.10, 0.16, 0.34, 0.16)


class ProfilePreview(QWidget):
    def __init__(self):
        super().__init__()
        self._p: dict = {}
        self._active: str | None = None
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_params(self, params: dict) -> None:
        self._p = dict(params or {})
        self.update()

    def set_active(self, phase: str | None) -> None:
        if phase != self._active:
            self._active = phase
            self.update()

    def _fractions(self):
        p = self._p
        i0 = float(p.get("start_volt", 0.0))
        ip = float(p.get("stop_volt", 1.0))
        di = max(ip - i0, 1e-6)
        raw = [float(p.get("pre_time", 0)),
               di / max(float(p.get("inc_rate", 1.0)), 1e-6),
               float(p.get("hold_time", 0)),
               di / max(float(p.get("dec_rate", 1.0)), 1e-6)]
        tot = max(sum(raw), 1e-6)
        f = [max(r / tot, m) for r, m in zip(raw, _MIN_F)]
        s = sum(f)
        return [x / s for x in f]

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 34, 8, 12, 20
        cw, ch = w - left - right, h - top - bottom
        y0, y1 = top + ch, top + 4
        f = self._fractions()
        xs: list[float] = [left]
        for fr in f:
            xs.append(xs[-1] + fr * cw * 0.92)
        x_end = left + cw
        pts = [QPointF(left, y0), QPointF(xs[1], y0), QPointF(xs[2], y1),
               QPointF(xs[3], y1), QPointF(xs[4], y0), QPointF(x_end, y0)]

        # active segment band
        if self._active in _SEG_KEYS:
            i = _SEG_KEYS.index(self._active)
            p.fillRect(QRectF(xs[i], top - 4, xs[i + 1] - xs[i], ch + 8), QColor(T.ACCENT_SOFT))
        elif self._active == "cooling_tail":
            p.fillRect(QRectF(xs[4], top - 4, x_end - xs[4], ch + 8), QColor(T.ACCENT_SOFT))

        # baseline + fill + stroke
        p.setPen(QPen(QColor(T.BORDER_STRONG), 1))
        p.drawLine(QPointF(left, y0), QPointF(x_end, y0))
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(QPointF(x_end, y0))
        fill.closeSubpath()
        c = QColor(T.ACCENT)
        c.setAlpha(28)
        p.fillPath(fill, c)
        p.setPen(QPen(QColor(T.ACCENT), 1.8))
        p.drawPath(path)

        font = QFont(T.mono_family())
        font.setPixelSize(10)
        p.setFont(font)
        unit = self._p.get("pk160_current_unit", "mA")
        p.setPen(QColor(T.TEXT_SECONDARY))
        p.drawText(QRectF(0, y1 - 7, left - 4, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{float(self._p.get('stop_volt', 0)):g}")
        p.drawText(QRectF(0, y0 - 7, left - 4, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{float(self._p.get('start_volt', 0)):g}")
        f2 = QFont(T.ui_family())
        f2.setPixelSize(10)
        p.setFont(f2)
        p.setPen(QColor(T.TEXT_MUTED))
        fm = p.fontMetrics()
        spans = [*pairwise(xs[:5]), (xs[4], x_end)]
        for (a, b), t in zip(spans, ("pre", "up", "hold", "down", "cool")):
            if fm.horizontalAdvance(t) + 4 <= b - a:
                p.drawText(QRectF(a, y0 + 3, b - a, 14), Qt.AlignmentFlag.AlignCenter, t)
        p.drawText(QRectF(0, top - 12, left + 40, 12), Qt.AlignmentFlag.AlignLeft, unit)
        p.end()


def profile_duration_s(params: dict) -> float:
    """Pre-heat + ramp up + hold + ramp down (cooling tail not included)."""
    i0 = float(params.get("start_volt", 0.0))
    ip = float(params.get("stop_volt", 1.0))
    di = max(ip - i0, 0.0)
    return (float(params.get("pre_time", 0)) + di / max(float(params.get("inc_rate", 1.0)), 1e-9)
            + float(params.get("hold_time", 0)) + di / max(float(params.get("dec_rate", 1.0)), 1e-9))


def fmt_duration(s: float) -> str:
    s = round(float(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {sec:02d} s"
    return f"{sec} s"

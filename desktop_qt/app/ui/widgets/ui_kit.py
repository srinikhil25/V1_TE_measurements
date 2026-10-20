"""Shared UI building blocks for the instrument-console design.

Everything here is styled by the global style sheet in ``theme.py`` through
object names and dynamic properties, so pages do not carry inline CSS.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as T
from ..icons import icon as _icon

# ---------------------------------------------------------------------------
# Property helpers
# ---------------------------------------------------------------------------

def set_props(w: QWidget, **props) -> QWidget:
    """Set dynamic properties and re-apply the style sheet to ``w``."""
    for k, v in props.items():
        w.setProperty(k, v)
    st = w.style()
    st.unpolish(w)
    st.polish(w)
    w.update()
    return w


def label(text: str = "", role: str = "body", *, wrap: bool = False,
          selectable: bool = False, **props) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", role)
    for k, v in props.items():
        lbl.setProperty(k, v)
    if wrap:
        lbl.setWordWrap(True)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def button(text: str = "", variant: str = "secondary", *, icon: Optional[str] = None,
           size: Optional[str] = None, tooltip: Optional[str] = None,
           checkable: bool = False, icon_color: Optional[str] = None) -> QPushButton:
    b = QPushButton(text)
    if variant != "secondary":
        b.setProperty("variant", variant)
    if size:
        b.setProperty("scale", size)
    if icon:
        color = icon_color or {
            "primary": "#FFFFFF", "danger": "#FFFFFF",
            "danger-outline": T.DANGER, "link": T.ACCENT,
        }.get(variant, T.TEXT_SECONDARY)
        px = 14 if size == "sm" else 16
        b.setIcon(_icon(icon, color, px, width=2.2))
        b.setIconSize(QSize(px, px))
        if not text:
            b.setProperty("iconOnly", True)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFixedHeight(1)
    return f


def vline() -> QFrame:
    f = QFrame()
    f.setObjectName("VDivider")
    f.setFixedWidth(1)
    return f


def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def vbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def _add(lay, it):
    if it is None:
        lay.addStretch()
    elif isinstance(it, int):
        lay.addSpacing(it)
    elif isinstance(it, QWidget):
        lay.addWidget(it)
    else:
        lay.addLayout(it)


# ---------------------------------------------------------------------------
# Panel — the white card used everywhere
# ---------------------------------------------------------------------------

class Panel(QFrame):
    """White panel with an optional header (title · subtitle · actions).

    Fill ``panel.body`` (a QVBoxLayout). ``flush=True`` removes body padding
    (for tables and charts that should run edge to edge).
    """

    def __init__(self, title: str = "", subtitle: str = "", *, flush: bool = False,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("panel", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("PanelHeader")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(8)
        tcol = QVBoxLayout()
        tcol.setSpacing(1)
        self.title_lbl = label(title, "h2")
        tcol.addWidget(self.title_lbl)
        self.subtitle_lbl = label(subtitle, "caption")
        self.subtitle_lbl.setVisible(bool(subtitle))
        tcol.addWidget(self.subtitle_lbl)
        h.addLayout(tcol)
        h.addStretch()
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(6)
        h.addLayout(self.actions_row)
        self.header.setMinimumHeight(40)
        self.header.setVisible(bool(title))
        outer.addWidget(self.header)

        self.body_widget = QWidget()
        self.body_widget.setObjectName("PanelBody")
        self.body = QVBoxLayout(self.body_widget)
        m = 0 if flush else 12
        self.body.setContentsMargins(m, m, m, m)
        self.body.setSpacing(10)
        outer.addWidget(self.body_widget, 1)

        self.footer = QFrame()
        self.footer.setObjectName("PanelFooter")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 6, 12, 6)
        self.footer_layout.setSpacing(8)
        self.footer.setVisible(False)
        outer.addWidget(self.footer)

    def add_action(self, w: QWidget) -> QWidget:
        self.actions_row.addWidget(w)
        return w

    def set_title(self, text: str) -> None:
        self.title_lbl.setText(text)
        self.header.setVisible(True)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_lbl.setText(text)
        self.subtitle_lbl.setVisible(bool(text))

    def show_footer(self, *widgets) -> QHBoxLayout:
        for w in widgets:
            _add(self.footer_layout, w)
        self.footer.setVisible(True)
        return self.footer_layout


# ---------------------------------------------------------------------------
# Page scaffolding
# ---------------------------------------------------------------------------

class PageToolbar(QFrame):
    """White strip at the top of a page: title / subtitle left, actions right."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("PageToolbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_lbl = label(title, "h1")
        self.subtitle_lbl = label(subtitle, "secondary")
        self.subtitle_lbl.setVisible(bool(subtitle))
        col.addWidget(self.title_lbl)
        col.addWidget(self.subtitle_lbl)
        lay.addLayout(col)
        self.middle = QHBoxLayout()
        self.middle.setSpacing(12)
        lay.addLayout(self.middle)
        lay.addStretch()
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(8)
        lay.addLayout(self.actions_row)
        self.setMinimumHeight(58)

    def add_action(self, w) -> None:
        _add(self.actions_row, w)

    def add_middle(self, w) -> None:
        _add(self.middle, w)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_lbl.setText(text)
        self.subtitle_lbl.setVisible(bool(text))


def page_scaffold(page: QWidget, title: str, subtitle: str = "", *,
                  scroll: bool = False, margins: int = 12, spacing: int = 12
                  ) -> Tuple[PageToolbar, QVBoxLayout]:
    """Give ``page`` a toolbar and a padded body. Returns (toolbar, body layout)."""
    from PyQt6.QtWidgets import QScrollArea
    page.setObjectName("Page")
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    tb = PageToolbar(title, subtitle)
    root.addWidget(tb)
    body = QWidget()
    body.setObjectName("PageBody")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    if scroll:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(body)
        sa.viewport().setAutoFillBackground(False)
        root.addWidget(sa, 1)
    else:
        root.addWidget(body, 1)
    return tb, lay


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------

class Segmented(QFrame):
    """Exclusive button group that looks like one control.

    Mirrors the parts of the QComboBox API the pages use: ``currentIndex``,
    ``setCurrentIndex``, ``currentText`` and ``currentIndexChanged``.
    """

    currentIndexChanged = pyqtSignal(int)

    def __init__(self, options: Sequence[str], current: int = 0,
                 tooltips: Optional[Sequence[str]] = None):
        super().__init__()
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QPushButton] = []
        for i, text in enumerate(options):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0:
                b.setProperty("first", True)
            if i == len(options) - 1:
                b.setProperty("last", True)
            if tooltips and i < len(tooltips) and tooltips[i]:
                b.setToolTip(tooltips[i])
            self._group.addButton(b, i)
            self._buttons.append(b)
            lay.addWidget(b, 1)
        if self._buttons:
            self._buttons[max(0, min(current, len(self._buttons) - 1))].setChecked(True)
        self._group.idToggled.connect(self._on_toggled)

    def _on_toggled(self, idx: int, checked: bool):
        if checked:
            self.currentIndexChanged.emit(idx)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def setCurrentIndex(self, idx: int) -> None:
        if 0 <= idx < len(self._buttons):
            self._buttons[idx].setChecked(True)

    def currentText(self) -> str:
        i = self.currentIndex()
        return self._buttons[i].text() if i >= 0 else ""

    def count(self) -> int:
        return len(self._buttons)

    def button(self, idx: int) -> QPushButton:
        return self._buttons[idx]


# ---------------------------------------------------------------------------
# Status chip and dot
# ---------------------------------------------------------------------------

class Chip(QLabel):
    """Small status label: neutral · info · success · warning · danger."""

    def __init__(self, text: str = "", kind: str = "neutral"):
        super().__init__(text)
        self.setProperty("chip", kind)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set(self, text: str, kind: Optional[str] = None) -> None:
        self.setText(text)
        if kind is not None and kind != self.property("chip"):
            set_props(self, chip=kind)


class Dot(QWidget):
    """Filled or hollow status dot."""

    def __init__(self, color: str = T.TEXT_DISABLED, size: int = 8, hollow: bool = False):
        super().__init__()
        self._color = color
        self._hollow = hollow
        self._d = size
        self.setFixedSize(size + 2, size + 2)

    def set_color(self, color: str, hollow: bool = False) -> None:
        self._color, self._hollow = color, hollow
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._color)
        if self._hollow:
            p.setPen(QPen(c, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
        p.drawEllipse(1, 1, self._d, self._d)
        p.end()


# Status vocabulary shared by the run library, overview and detail views.
#: I-V ohmic verdict → (label, tone, explanation). Shared by every page.
OHMIC_LABEL = {
    "ohmic":          ("Ohmic", "success", "R² ≥ 0.999"),
    "check_contacts": ("Check contacts", "warning", "0.99 ≤ R² < 0.999"),
    "non_ohmic":      ("Non-ohmic", "danger", "R² < 0.99"),
    "too_few_points": ("Too few points", "warning",
                       "At least 5 valid points are needed to judge linearity."),
}


def ohmic_label(status: Optional[str]):
    """(label, tone, explanation) for an ohmic status; ("—", None, "") if unknown."""
    return OHMIC_LABEL.get(status or "", ("—", None, ""))


def bin_n_text(b: dict):
    """(text, tooltip) for a Seebeck bin's point count, showing rejected outliers."""
    n, k = b.get("n_points", ""), b.get("n_rejected") or 0
    if b.get("fit_warning"):
        return f"{n} ⚠", b["fit_warning"]
    if not k:
        return str(n), f"{n} points in the fit"
    return f"{n} −{k}", (f"{n} points in the fit; {k} spike(s) rejected "
                        "(residual > 5 robust σ)")


STATUS_CHIP = {
    "finished":    ("Finished", "success"),
    "completed":   ("Finished", "success"),
    "running":     ("Running", "info"),
    "stopped":     ("Stopped", "neutral"),
    "aborted":     ("Aborted", "danger"),
    "error":       ("Error", "danger"),
    "interrupted": ("Interrupted", "warning"),
}


def status_chip(status: Optional[str]) -> Chip:
    text, kind = STATUS_CHIP.get((status or "").lower(), ((status or "—").title(), "neutral"))
    return Chip(text, kind)


# ---------------------------------------------------------------------------
# Readouts
# ---------------------------------------------------------------------------

class Readout(QFrame):
    """Label + large monospaced value + unit, for live numbers."""

    def __init__(self, caption: str, unit: str = "", *, size: Optional[str] = None,
                 tone: Optional[str] = None, tooltip: str = ""):
        super().__init__()
        self.setObjectName("ReadoutCell")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 9)
        lay.setSpacing(1)
        self.caption = label(caption, "caption")
        lay.addWidget(self.caption)
        row = QHBoxLayout()
        row.setSpacing(5)
        self.value = label("—", "readout")
        if size:
            self.value.setProperty("scale", size)
        self.unit = label(unit, "unit")
        row.addWidget(self.value, 0, Qt.AlignmentFlag.AlignBaseline)
        row.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBaseline)
        row.addStretch()
        lay.addLayout(row)
        self.note = label("", "caption")
        self.note.setVisible(False)
        lay.addWidget(self.note)
        if tooltip:
            self.setToolTip(tooltip)
        self._tone = None
        if tone:
            self.set_tone(tone)

    def set_value(self, text: str, unit: Optional[str] = None) -> None:
        self.value.setText(text)
        if unit is not None:
            self.unit.setText(unit)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_tone(self, tone: Optional[str]) -> None:
        if tone == self._tone:
            return
        self._tone = tone
        set_props(self, tone=tone or "")
        set_props(self.value, tone=tone or "")


class ReadoutGrid(QFrame):
    """Readouts separated by 1-px rules, in ``columns`` columns."""

    def __init__(self, readouts: Sequence[Readout], columns: int):
        super().__init__()
        self.setObjectName("ReadoutGrid")
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(1)
        for i, r in enumerate(readouts):
            g.addWidget(r, i // columns, i % columns)
        for c in range(columns):
            g.setColumnStretch(c, 1)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class FieldWidget(QWidget):
    """A field(): caption, input, optional hint and an (initially hidden) error."""

    error_lbl: QLabel


def field(caption: str, widget: QWidget, hint: str = "", *,
          required: bool = False) -> FieldWidget:
    """Label above an input, with an optional hint below."""
    w = FieldWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addWidget(label(caption + ("  *" if required else ""), "label"))
    lay.addWidget(widget)
    if hint:
        lay.addWidget(label(hint, "caption", wrap=True))
    w.error_lbl = label("", "caption", wrap=True, tone="danger")
    w.error_lbl.setVisible(False)
    lay.addWidget(w.error_lbl)
    return w


def set_field_error(fw: QWidget, text: str = "") -> None:
    """Show (or clear, with "") an inline error under a field() and mark its input."""
    lbl = getattr(fw, "error_lbl", None)
    if lbl is not None:
        lbl.setText(text)
        lbl.setVisible(bool(text))
    for inp in fw.findChildren(QWidget):
        if inp.property("invalid") is not None or inp.inherits("QLineEdit") \
                or inp.inherits("QAbstractSpinBox"):
            set_props(inp, invalid=bool(text))
            break


class KeyValueList(QWidget):
    """Two-column list of label → value (like an HTML <dl>)."""

    def __init__(self, rows: Iterable[Tuple[str, str]] = (), *, mono_values: bool = False,
                 key_width: int = 0):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(6)
        self._grid.setColumnStretch(1, 1)
        if key_width:
            self._grid.setColumnMinimumWidth(0, key_width)
        self._mono = mono_values
        self._values: dict = {}
        for k, v in rows:
            self.set(k, v)

    def clear(self) -> None:
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._values.clear()

    def set(self, key: str, value: str, tone: Optional[str] = None, tooltip: str = "") -> QLabel:
        if key not in self._values:
            r = len(self._values)
            k = label(key, "label")
            k.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            v = label(value, "mono" if self._mono else "body", selectable=True)
            v.setWordWrap(True)
            self._grid.addWidget(k, r, 0)
            self._grid.addWidget(v, r, 1)
            self._values[key] = v
        lbl = self._values[key]
        lbl.setText(value)
        color = {"success": T.SUCCESS, "warning": T.WARNING, "danger": T.DANGER,
                 "muted": T.TEXT_MUTED}.get(tone or "")
        lbl.setStyleSheet(f"color: {color};" if color else "")
        lbl.setToolTip(tooltip)
        return lbl


class Callout(QFrame):
    """Tinted message box: info · warning · danger · success."""

    def __init__(self, text: str, kind: str = "info", *, title: str = "", icon: Optional[str] = None):
        super().__init__()
        self.setProperty("callout", kind)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        color = {"info": T.ACCENT_TEXT, "warning": T.WARNING, "danger": T.DANGER,
                 "success": T.SUCCESS}.get(kind, T.TEXT_SECONDARY)
        name = icon or {"info": "info", "warning": "alert", "danger": "alert",
                        "success": "check-circle"}.get(kind, "info")
        self._ic = QLabel()
        from ..icons import pixmap
        self._ic.setPixmap(pixmap(name, color, 16))
        self._ic.setFixedWidth(18)
        lay.addWidget(self._ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setVisible(bool(title))
        col.addWidget(self.title_lbl)
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setStyleSheet("font-size: 12px;")
        col.addWidget(self.text_lbl)
        lay.addLayout(col, 1)

    def set_text(self, text: str) -> None:
        self.text_lbl.setText(text)

    def set_title(self, title: str) -> None:
        self.title_lbl.setText(title)
        self.title_lbl.setVisible(bool(title))

    def set(self, text: str, kind: str) -> None:
        """Change message and kind (info · warning · danger · success) in place."""
        from ..icons import pixmap
        color = {"info": T.ACCENT_TEXT, "warning": T.WARNING, "danger": T.DANGER,
                 "success": T.SUCCESS}.get(kind, T.TEXT_SECONDARY)
        name = {"info": "info", "warning": "alert", "danger": "alert",
                "success": "check-circle"}.get(kind, "info")
        self._ic.setPixmap(pixmap(name, color, 16))
        self.text_lbl.setText(text)
        set_props(self, callout=kind)
        for lbl in self.findChildren(QLabel):
            set_props(lbl)


def hide_item_text(table, row: int, col: int) -> None:
    """Keep a cell's text for sorting / filtering but do not draw it (a widget covers it)."""
    it = table.item(row, col)
    if it is not None:
        it.setData(Qt.ItemDataRole.UserRole + 1, it.text())
        it.setText("")


class EmptyState(QWidget):
    """Centered icon + title + explanation for empty tables / panels."""

    def __init__(self, icon_name: str, title: str, text: str = ""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 32, 24, 32)
        lay.setSpacing(6)
        lay.addStretch()
        from ..icons import pixmap
        ic = QLabel()
        ic.setPixmap(pixmap(icon_name, T.TEXT_DISABLED, 32, width=1.6))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        t = label(title, "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        self.text_lbl = label(text, "muted", wrap=True)
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.text_lbl)
        lay.addStretch()


# ---------------------------------------------------------------------------
# Phase stepper
# ---------------------------------------------------------------------------

class Stepper(QWidget):
    """Horizontal run-phase indicator: done (✓) · current (accent) · pending."""

    def __init__(self, steps: Sequence[str]):
        super().__init__()
        self._steps = list(steps)
        self._current = -1
        self._all_done = False
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_state(self, current: int, all_done: bool = False) -> None:
        self._current, self._all_done = current, all_done
        self.update()

    def sizeHint(self):
        return QSize(120 * len(self._steps), 28)

    def paintEvent(self, _e):
        from PyQt6.QtGui import QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._steps)
        if not n:
            return
        w = self.width()
        h = self.height()
        seg = w / n
        f = QFont(T.ui_family())
        f.setPixelSize(12)
        p.setFont(f)
        cy = h / 2
        for i, name in enumerate(self._steps):
            x0 = i * seg
            done = self._all_done or (self._current >= 0 and i < self._current)
            cur = (i == self._current) and not self._all_done
            # connector
            if i > 0:
                p.setPen(QPen(QColor(T.ACCENT if done or cur else T.BORDER_STRONG), 1.2))
                p.drawLine(int(x0 - 10), int(cy), int(x0 + 2), int(cy))
            r = 9
            cx = x0 + 6 + r
            if done:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T.ACCENT))
                p.drawEllipse(int(cx - r), int(cy - r), 2 * r, 2 * r)
                p.setPen(QPen(QColor("#FFFFFF"), 1.8))
                p.drawLine(int(cx - 4), int(cy), int(cx - 1), int(cy + 3))
                p.drawLine(int(cx - 1), int(cy + 3), int(cx + 4), int(cy - 3))
            elif cur:
                p.setPen(QPen(QColor(T.ACCENT), 2))
                p.setBrush(QColor(T.ACCENT_SOFT))
                p.drawEllipse(int(cx - r), int(cy - r), 2 * r, 2 * r)
                p.setPen(QColor(T.ACCENT_TEXT))
                p.drawText(int(cx - r), int(cy - r), 2 * r, 2 * r,
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                p.setPen(QPen(QColor(T.BORDER_STRONG), 1.2))
                p.setBrush(QColor(T.SURFACE))
                p.drawEllipse(int(cx - r), int(cy - r), 2 * r, 2 * r)
                p.setPen(QColor(T.TEXT_MUTED))
                p.drawText(int(cx - r), int(cy - r), 2 * r, 2 * r,
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))
            tx = cx + r + 6
            avail = int(x0 + seg - tx - 12)
            fb = QFont(f)
            fb.setWeight(QFont.Weight.DemiBold if cur else QFont.Weight.Normal)
            p.setFont(fb)
            p.setPen(QColor(T.TEXT_PRIMARY if (cur or done) else T.TEXT_MUTED))
            text = p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, max(avail, 10))
            p.drawText(int(tx), 0, max(avail, 10), h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            p.setFont(f)
        p.end()


# ---------------------------------------------------------------------------
# Charts (pyqtgraph)
# ---------------------------------------------------------------------------

def style_plot(plot, left: str = "", bottom: str = "", *, right: str = "") -> None:
    """Apply the house chart style to a pyqtgraph PlotWidget / PlotItem."""
    import pyqtgraph as pg
    from PyQt6.QtGui import QFont
    pi = plot.getPlotItem() if hasattr(plot, "getPlotItem") else plot
    if hasattr(plot, "setBackground"):
        plot.setBackground(T.SURFACE)
    pi.showGrid(x=True, y=True, alpha=0.18)
    tick_font = QFont(T.mono_family())
    tick_font.setPixelSize(11)
    label_style = {"color": T.TEXT_SECONDARY, "font-size": "11px",
                   "font-family": T.ui_family()}
    for name in ("left", "bottom", "right"):
        ax = pi.getAxis(name)
        ax.setPen(pg.mkPen(T.CHART_AXIS, width=1))
        ax.setTextPen(pg.mkPen(T.TEXT_SECONDARY))
        ax.setStyle(tickFont=tick_font, tickTextOffset=6, tickLength=-4)
        # pyqtgraph 0.14's enableAutoSIPrefix(False) still computes a scale from
        # the current range and keeps it, so set the state directly.
        ax.autoSIPrefix = False
        ax.autoSIPrefixScale = 1.0
        ax.labelUnitPrefix = ""
        ax.picture = None
        ax.update()
    if left:
        pi.setLabel("left", left, **label_style)
    if bottom:
        pi.setLabel("bottom", bottom, **label_style)
    if right:
        pi.showAxis("right")
        pi.setLabel("right", right, **label_style)
    pi.setContentsMargins(4, 6, 8, 4)
    if hasattr(plot, "setMenuEnabled"):
        plot.setMenuEnabled(False)
    pi.hideButtons()


def pen(color: str, width: float = 1.8, dashed: bool = False):
    import pyqtgraph as pg
    p = pg.mkPen(color, width=width)
    if dashed:
        p.setStyle(Qt.PenStyle.DashLine)
    return p


class LegendStrip(QWidget):
    """Legend drawn above a chart (never over the data)."""

    def __init__(self, items: Sequence[Tuple[str, str]], *, kinds: Optional[Sequence[str]] = None):
        """items: (color, text). kinds: 'line' (default), 'dash', 'dot', 'ring'."""
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(14)
        for i, (color, text) in enumerate(items):
            kind = kinds[i] if kinds and i < len(kinds) else "line"
            lay.addLayout(hbox(_Swatch(color, kind), label(text, "caption"), spacing=5))
        lay.addStretch()


class _Swatch(QWidget):
    def __init__(self, color: str, kind: str):
        super().__init__()
        self._c, self._k = color, kind
        self.setFixedSize(16, 12)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._c)
        if self._k in ("dot", "ring"):
            if self._k == "dot":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
            else:
                p.setPen(QPen(c, 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(4, 2, 8, 8)
        else:
            pn = QPen(c, 2)
            if self._k == "dash":
                pn.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pn)
            p.drawLine(1, 6, 15, 6)
        p.end()


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def make_table(headers: Sequence[str], *, flat: bool = True, row_height: int = 32,
               mono: bool = False, stretch_last: bool = True):
    """QTableWidget with the house defaults (no grid, row selection, read-only)."""
    from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(list(headers))
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(row_height)
    t.verticalHeader().setMinimumSectionSize(row_height)
    hh = t.horizontalHeader()
    hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    hh.setHighlightSections(False)
    hh.setStretchLastSection(stretch_last)
    hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    if flat:
        t.setProperty("flat", True)
    if mono:
        t.setProperty("mono", True)
    return t


def _sort_item_class():
    from PyQt6.QtWidgets import QTableWidgetItem

    class _SortItem(QTableWidgetItem):
        """Sorts by the UserRole+1 key when present (numbers, hidden chip text)."""

        def __lt__(self, other):
            a = self.data(Qt.ItemDataRole.UserRole + 1)
            b = other.data(Qt.ItemDataRole.UserRole + 1)
            if a is not None and b is not None:
                try:
                    return a < b
                except TypeError:
                    return str(a) < str(b)
            return super().__lt__(other)

    return _SortItem


class _Lazy:
    cls: Optional[type] = None


def SortItem(text: str = ""):
    if _Lazy.cls is None:
        _Lazy.cls = _sort_item_class()
    return _Lazy.cls(text)  # pyright: ignore[reportOptionalCall]


def cell(text: str, *, align: str = "left", mono: bool = False, tooltip: str = "",
         color: Optional[str] = None, bold: bool = False, data=None):
    """QTableWidgetItem helper. align: left · right · center."""
    from PyQt6.QtGui import QBrush, QFont
    it = SortItem(text)
    a = {"left": Qt.AlignmentFlag.AlignLeft, "right": Qt.AlignmentFlag.AlignRight,
         "center": Qt.AlignmentFlag.AlignHCenter}[align]
    it.setTextAlignment(a | Qt.AlignmentFlag.AlignVCenter)
    if mono or bold:
        f = QFont(T.mono_family() if mono else T.ui_family())
        f.setPixelSize(12 if mono else 13)
        if bold:
            f.setWeight(QFont.Weight.DemiBold)
        it.setFont(f)
    if tooltip:
        it.setToolTip(tooltip)
    if color:
        it.setForeground(QBrush(QColor(color)))
    if data is not None:
        it.setData(Qt.ItemDataRole.UserRole, data)
    return it


def chip_cell(table, row: int, col: int, text: str, kind: str, tooltip: str = "") -> Chip:
    """Put a status chip into a table cell (left-aligned, vertically centred)."""
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(8, 0, 8, 0)
    c = Chip(text, kind)
    if tooltip:
        host.setToolTip(tooltip)
    it = table.item(row, col)
    if it is not None:          # the chip shows the text; keep it only as the sort key
        it.setData(Qt.ItemDataRole.UserRole + 1, it.text())
        it.setText("")
    lay.addWidget(c)
    lay.addStretch()
    table.setCellWidget(row, col, host)
    return c


def fmt_num(v, fmt: str = "{:.3g}", none: str = "—") -> str:
    if v is None:
        return none
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return str(v)


def fmt_sci(v, digits: int = 3, unit: str = "") -> str:
    """3.14 × 10⁻⁵ style for very small / large values, plain otherwise."""
    if v is None:
        return "—"
    import math
    if v == 0 or (1e-3 <= abs(v) < 1e4):
        decimals = max(0, digits - 1 - math.floor(math.log10(abs(v)))) if v else digits - 1
        s = f"{v:.{decimals}f}"
    else:
        e = math.floor(math.log10(abs(v)))
        m = v / 10 ** e
        sup = str(e).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
        s = f"{m:.{max(digits - 1, 0)}f} × 10{sup}"
    return f"{s} {unit}".strip()


def initials(name: str) -> str:
    parts = [p for p in (name or "").replace("_", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (name or "?")[:2].upper()


ROLE_LABELS = {
    "super_admin": "Super admin",
    "lab_admin":   "Lab admin",
    "researcher":  "Researcher",
}

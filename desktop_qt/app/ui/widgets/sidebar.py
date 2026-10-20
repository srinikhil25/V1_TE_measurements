"""Navigation rail — dark, role-filtered, collapses to icons only."""

from typing import Dict, List

from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import theme as T
from ..icons import icon_states

# (label, key, allowed roles or None, section)
NAV_ITEMS: List[tuple] = [
    ("Overview",     "dashboard", None,                                       ""),
    ("Seebeck",      "seebeck",   ("super_admin", "lab_admin", "researcher"), "Measure"),
    ("I-V sweep",    "iv",        ("super_admin", "lab_admin", "researcher"), "Measure"),
    ("Run library",  "history",   ("super_admin", "lab_admin", "researcher"), "Data"),
    ("Audit trail",  "audit",     ("super_admin", "lab_admin"),               "Data"),
    ("Users",        "users",     ("super_admin",),                           "System"),
    ("Settings",     "settings",  None,                                       "System"),
]

SECTION_OF: Dict[str, str] = {key: section for _l, key, _r, section in NAV_ITEMS}
LABEL_OF: Dict[str, str] = {key: lbl for lbl, key, _r, _s in NAV_ITEMS}


class Sidebar(QWidget):
    page_requested = pyqtSignal(str)

    EXPANDED_W = 208
    COLLAPSED_W = 56

    def __init__(self, role: str, username: str = ""):
        super().__init__()
        self._role = role
        self._expanded = True
        self._buttons: Dict[str, QPushButton] = {}
        self._labels: Dict[str, str] = {}
        self._section_lbls: List[QLabel] = []
        self._anim_group = None
        self.setObjectName("NavRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self.EXPANDED_W)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(2)
        last = None
        for text, key, roles, section in NAV_ITEMS:
            if roles is not None and self._role not in roles:
                continue
            if section and section != last:
                lay.addSpacing(10 if last is not None else 4)
                s = QLabel(section.upper())
                s.setProperty("role", "nav-section")
                s.setFixedHeight(20)
                self._section_lbls.append(s)
                lay.addWidget(s)
                last = section
            elif last is None:
                last = ""
            b = QPushButton("  " + text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(icon_states(key, T.CHROME_MUTED, "#FFFFFF", 16))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(text)
            b.clicked.connect(lambda _=False, k=key: self._on_nav(k))
            self._group.addButton(b)
            self._buttons[key] = b
            self._labels[key] = text
            lay.addWidget(b)
        lay.addStretch()
        div = QFrame()
        div.setObjectName("NavDivider")
        lay.addWidget(div)
        lay.addSpacing(6)
        self.foot = QLabel("Ikeda-Hamasaki Lab\nShizuoka University")
        self.foot.setObjectName("NavFootText")
        self.foot.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(self.foot)

    # ------------------------------------------------------------------
    def set_active(self, key: str):
        b = self._buttons.get(key)
        if b is not None:
            b.setChecked(True)

    def _on_nav(self, key: str):
        self.page_requested.emit(key)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self):
        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            return
        start = self.EXPANDED_W if self._expanded else self.COLLAPSED_W
        end = self.COLLAPSED_W if self._expanded else self.EXPANDED_W
        self._expanded = not self._expanded
        if not self._expanded:
            self._apply_labels()

        def _anim(prop: bytes) -> QPropertyAnimation:
            a = QPropertyAnimation(self, prop)
            a.setDuration(180)
            a.setEasingCurve(QEasingCurve.Type.InOutQuad)
            a.setStartValue(start)
            a.setEndValue(end)
            return a

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(_anim(b"minimumWidth"))
        self._anim_group.addAnimation(_anim(b"maximumWidth"))
        if self._expanded:
            self._anim_group.finished.connect(self._apply_labels)
        self._anim_group.start()

    def _apply_labels(self):
        for key, b in self._buttons.items():
            b.setText(("  " + self._labels[key]) if self._expanded else "")
        for s in self._section_lbls:
            s.setVisible(self._expanded)
        self.foot.setVisible(self._expanded)

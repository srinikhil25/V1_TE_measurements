"""Vector icon factory — crisp SVG icons rendered to QIcon / QPixmap.

Replaces Unicode-glyph "icons" (↓ ⤢ ▦ …) which render as empty boxes when the
system font lacks the glyph. These render identically on every machine.

Usage:
    from ..icons import icon
    btn.setIcon(icon("download", "#8A8578"))
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

# Feather-style stroke icons (24×24 viewBox, stroke = currentColor).
_PATHS = {
    # actions
    "download":  '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                 '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "expand":    '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>'
                 '<line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>',
    "collapse":  '<polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/>'
                 '<line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/>',
    "crosshair": '<circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/>'
                 '<line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/>'
                 '<line x1="12" y1="22" x2="12" y2="18"/>',
    "camera":    '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
                 '<circle cx="12" cy="13" r="4"/>',
    "menu":      '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
                 '<line x1="3" y1="18" x2="21" y2="18"/>',
    "plus":      '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    # navigation
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
                 '<rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    "seebeck":   '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "iv":        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "history":   '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "users":     '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                 '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "settings":  '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
                 '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
                 '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
                 '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
                 '<line x1="17" y1="16" x2="23" y2="16"/>',
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">'
    '{inner}</svg>'
)


def pixmap(name: str, color: str = "#4B5563", size: int = 20, width: float = 2.0) -> QPixmap:
    svg = _TEMPLATE.format(color=color, w=width, inner=_PATHS[name])
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    scale = 2  # render at 2× for crisp edges on hi-DPI
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str = "#4B5563", size: int = 20, width: float = 2.0) -> QIcon:
    return QIcon(pixmap(name, color, size, width))

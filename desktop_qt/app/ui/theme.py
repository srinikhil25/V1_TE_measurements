"""
Design tokens, global Qt Style Sheet and theme setup — "instrument console".

Graphite chrome (top bar, navigation, status bar) around a light, neutral work
area. One accent colour; green / amber / red are reserved for status. Numeric
readouts use a monospaced face so digits do not jump while they update.

Widgets opt into styles through dynamic properties rather than inline style
sheets, e.g. ``button.setProperty("variant", "primary")`` or
``label.setProperty("role", "h1")`` — see ``widgets/ui_kit.py`` for helpers.
Call ``apply_theme(app)`` once, right after the QApplication is created.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

# Chrome (top bar, navigation rail, status bar)
CHROME_BG       = "#12161D"
NAV_BG          = "#171C24"
NAV_HOVER       = "#1F2631"
NAV_ACTIVE      = "#263041"
CHROME_BORDER   = "#2A313D"
CHROME_TEXT     = "#E8EBF0"
CHROME_TEXT_2   = "#C9D0DB"
CHROME_MUTED    = "#8B94A3"

# Work area
BG              = "#EEF0F3"
SURFACE         = "#FFFFFF"
SURFACE_ALT     = "#F6F7F9"
SURFACE_SUNKEN  = "#E9ECF0"
BORDER          = "#D8DCE2"
BORDER_SUBTLE   = "#E6E9ED"
BORDER_STRONG   = "#B9BFC9"
INPUT_BORDER    = "#C9CED6"

TEXT_PRIMARY    = "#151922"
TEXT_SECONDARY  = "#4A5160"
TEXT_MUTED      = "#6B7280"
TEXT_DISABLED   = "#9AA1AC"

# Accent
ACCENT          = "#1F5FBF"
ACCENT_HOVER    = "#1A51A3"
ACCENT_PRESSED  = "#154287"
ACCENT_SOFT     = "#E3EBF7"
ACCENT_TEXT     = "#1F4E8C"

# Status
SUCCESS         = "#1E7B4A"
SUCCESS_BG      = "#E6F4EC"
SUCCESS_BORDER  = "#A7D7BA"
SUCCESS_LIVE    = "#3DDC84"   # on dark chrome
WARNING         = "#8A4B00"
WARNING_BG      = "#FFF4E0"
WARNING_BORDER  = "#F2C987"
WARNING_LIVE    = "#F2B866"
DANGER          = "#B42318"
DANGER_HOVER    = "#9A1D14"
DANGER_BG       = "#FDECEA"
DANGER_BORDER   = "#F2B8B5"
DANGER_LIVE     = "#FF6B5E"

# Chart series
SERIES_T1       = "#C2410C"
SERIES_T2       = "#1D4ED8"
SERIES_TEMF     = "#374151"
SERIES_HEAT     = "#C2410C"
SERIES_COOL     = "#1D4ED8"
SERIES_S        = "#6D28D9"
SERIES_FIT      = ACCENT
CHART_GRID      = "#E3E6EB"
CHART_AXIS      = "#9AA3B0"

# ---------------------------------------------------------------------------
# Back-compat aliases (older widgets import these names)
# ---------------------------------------------------------------------------
SIDEBAR_BG      = NAV_BG
SIDEBAR_HOVER   = NAV_HOVER
SIDEBAR_ACTIVE  = NAV_ACTIVE
SIDEBAR_TEXT    = CHROME_TEXT
SIDEBAR_MUTED   = CHROME_MUTED
CONTENT_BG      = BG
CARD_BG         = SURFACE
HEADER_BG       = SURFACE
SUNKEN_BG       = SURFACE_SUNKEN
ELEVATED_BG     = SURFACE_ALT
PRIMARY         = ACCENT
PRIMARY_HOVER   = ACCENT_HOVER
PRIMARY_PRESSED = ACCENT_PRESSED
PRIMARY_LIGHT   = ACCENT_SOFT
ERROR           = DANGER
ERROR_BG        = DANGER_BG

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

UI_FONT_CANDIDATES = ("IBM Plex Sans", "Segoe UI Variable Text", "Segoe UI", "Arial")
MONO_FONT_CANDIDATES = ("IBM Plex Mono", "Cascadia Mono", "Consolas", "Courier New")

_ui_family = "Segoe UI"
_mono_family = "Consolas"


def ui_family() -> str:
    return _ui_family


def mono_family() -> str:
    """Monospaced family for numeric readouts (resolved by apply_theme)."""
    return _mono_family


def _load_bundled_fonts() -> None:
    """Register any .ttf/.otf in app/ui/fonts (e.g. IBM Plex) with Qt."""
    from PyQt6.QtGui import QFontDatabase
    folder = Path(__file__).with_name("fonts")
    if not folder.is_dir():
        return
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in (".ttf", ".otf"):
            QFontDatabase.addApplicationFont(str(f))


def _pick(candidates) -> str:
    from PyQt6.QtGui import QFontDatabase
    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return name
    return candidates[-1]


# ---------------------------------------------------------------------------
# Small SVG assets for spin boxes, combo boxes, check boxes and radios.
# QSS can only reference images by path, so they are written once to a
# per-user temp folder (no packaging changes needed).
# ---------------------------------------------------------------------------

_ASSETS = {
    "chev-down.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="M3 4.5l3 3 3-3" '
        f'fill="none" stroke="{TEXT_SECONDARY}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>',
    "chev-up.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="M3 7.5l3-3 3 3" '
        f'fill="none" stroke="{TEXT_SECONDARY}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>',
    "chev-down-dis.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="M3 4.5l3 3 3-3" '
        f'fill="none" stroke="{TEXT_DISABLED}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>',
    "chev-up-dis.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="M3 7.5l3-3 3 3" '
        f'fill="none" stroke="{TEXT_DISABLED}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>',
    "check.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" '
        'fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>',
    "radio-dot.svg":
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<circle cx="8" cy="8" r="7" fill="{ACCENT}"/><circle cx="8" cy="8" r="3" fill="#FFFFFF"/></svg>',
}


def _asset_dir() -> str:
    d = Path(tempfile.gettempdir()) / "te_measurement_ui_v2"
    try:
        d.mkdir(parents=True, exist_ok=True)
        for name, svg in _ASSETS.items():
            p = d / name
            if not p.exists() or p.read_text(encoding="utf-8") != svg:
                p.write_text(svg, encoding="utf-8")
    except OSError:
        return ""
    return d.as_posix()


# ---------------------------------------------------------------------------
# Style sheet
# ---------------------------------------------------------------------------

def build_qss(ui: str = "Segoe UI", mono: str = "Consolas", assets: str = "") -> str:
    a = (lambda n: f"url({assets}/{n})") if assets else (lambda n: "none")
    return f"""
/* ── Base ───────────────────────────────────────────────────────────── */
QWidget {{
    font-family: "{ui}";
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#Page, QWidget#PageBody {{ background: {BG}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QLabel {{ background: transparent; }}

/* ── Typography roles ───────────────────────────────────────────────── */
QLabel[role="display"]  {{ font-size: 24px; font-weight: 600; }}
QLabel[role="h1"]       {{ font-size: 16px; font-weight: 600; }}
QLabel[role="h2"]       {{ font-size: 13px; font-weight: 600; }}
QLabel[role="body"]     {{ font-size: 13px; color: {TEXT_PRIMARY}; }}
QLabel[role="secondary"]{{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel[role="caption"]  {{ font-size: 11px; color: {TEXT_SECONDARY}; }}
QLabel[role="muted"]    {{ font-size: 12px; color: {TEXT_MUTED}; }}
QLabel[role="overline"] {{ font-size: 11px; font-weight: 600; color: {TEXT_MUTED};
                           letter-spacing: 0.8px; }}
QLabel[role="label"]    {{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel[role="mono"]     {{ font-family: "{mono}"; font-size: 12px; }}
QLabel[role="readout"]  {{ font-family: "{mono}"; font-size: 22px; font-weight: 500;
                           color: {TEXT_PRIMARY}; }}
QLabel[role="readout"][scale="lg"] {{ font-size: 26px; }}
QLabel[role="readout"][scale="sm"] {{ font-size: 17px; }}
QLabel[role="readout"][tone="accent"]  {{ color: {ACCENT_TEXT}; font-weight: 600; }}
QLabel[role="readout"][tone="warning"] {{ color: {WARNING}; }}
QLabel[role="readout"][tone="danger"]  {{ color: {DANGER}; }}
QLabel[role="readout"][tone="success"] {{ color: {SUCCESS}; }}
QLabel[role="readout"][tone="muted"]   {{ color: {TEXT_DISABLED}; }}
QLabel[role="unit"]     {{ font-size: 12px; color: {TEXT_MUTED}; }}
QLabel[role="error"]    {{ font-size: 12px; color: {DANGER}; }}
QLabel[role="success"]  {{ font-size: 12px; color: {SUCCESS}; }}
QLabel[role="link"]     {{ font-size: 12px; color: {ACCENT}; }}

/* ── Panels ─────────────────────────────────────────────────────────── */
QFrame[panel="true"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QFrame[panel="true"] QFrame#PanelHeader {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    border-radius: 0;
}}
QFrame[panel="true"] QFrame#PanelFooter {{
    background: {SURFACE_ALT};
    border: none;
    border-top: 1px solid {BORDER_SUBTLE};
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QFrame[panel="true"] QWidget#PanelBody {{ background: transparent; }}
QFrame#Divider {{ background: {BORDER_SUBTLE}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#VDivider {{ background: {BORDER}; border: none; max-width: 1px; min-width: 1px; }}

/* Page toolbar (white strip under the top bar) */
QFrame#PageToolbar {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* Callouts */
QFrame[callout="warning"] {{ background: {WARNING_BG}; border: 1px solid {WARNING_BORDER}; border-radius: 6px; }}
QFrame[callout="info"]    {{ background: {ACCENT_SOFT}; border: 1px solid #BCD0EE; border-radius: 6px; }}
QFrame[callout="danger"]  {{ background: {DANGER_BG}; border: 1px solid {DANGER_BORDER}; border-radius: 6px; }}
QFrame[callout="success"] {{ background: {SUCCESS_BG}; border: 1px solid {SUCCESS_BORDER}; border-radius: 6px; }}
QFrame[callout="warning"] QLabel {{ color: {WARNING}; }}
QFrame[callout="info"] QLabel    {{ color: {ACCENT_TEXT}; }}
QFrame[callout="danger"] QLabel  {{ color: {DANGER}; }}
QFrame[callout="success"] QLabel {{ color: {SUCCESS}; }}

/* Readout cells */
QFrame#ReadoutCell {{ background: {SURFACE}; border: none; }}
QFrame#ReadoutCell[tone="accent"]  {{ background: #F3F7FD; }}
QFrame#ReadoutCell[tone="warning"] {{ background: #FFF8EB; }}
QFrame#ReadoutCell[tone="danger"]  {{ background: #FEF3F2; }}
QFrame#ReadoutCell[tone="success"] {{ background: #F1FAF4; }}
QFrame#ReadoutGrid {{ background: {BORDER}; border: 1px solid {BORDER}; border-radius: 6px; }}

/* ── Chips / pills ──────────────────────────────────────────────────── */
QLabel[chip="neutral"] {{ background: {SURFACE_SUNKEN}; color: {TEXT_SECONDARY};
    border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel[chip="info"]    {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT};
    border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel[chip="success"] {{ background: {SUCCESS_BG}; color: {SUCCESS};
    border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel[chip="warning"] {{ background: {WARNING_BG}; color: {WARNING};
    border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel[chip="danger"]  {{ background: {DANGER_BG}; color: {DANGER};
    border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton, QToolButton[button="true"] {{
    background: {SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    padding: 0 14px;
    min-height: 30px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {SURFACE_ALT}; border-color: #9AA3B0; }}
QPushButton:pressed {{ background: {SURFACE_SUNKEN}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER}; background: {SURFACE_ALT}; }}
QPushButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; border-color: #9DB8E3; }}

QPushButton[variant="primary"] {{ background: {ACCENT}; color: #FFFFFF; border: 1px solid {ACCENT}; }}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[variant="primary"]:focus {{ border-color: {ACCENT_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{ background: #A9C0E3; border-color: #A9C0E3; color: #F2F6FC; }}

QPushButton[variant="danger"] {{ background: {DANGER}; color: #FFFFFF; border: 1px solid {DANGER}; }}
QPushButton[variant="danger"]:hover {{ background: {DANGER_HOVER}; border-color: {DANGER_HOVER}; }}
QPushButton[variant="danger"]:disabled {{ background: #E3A9A4; border-color: #E3A9A4; color: #FDF2F1; }}

QPushButton[variant="danger-outline"] {{ background: {SURFACE}; color: {DANGER}; border: 1px solid #E5938C; }}
QPushButton[variant="danger-outline"]:hover {{ background: {DANGER_BG}; border-color: {DANGER}; }}
QPushButton[variant="danger-outline"]:disabled {{ color: #E3A9A4; border-color: {BORDER}; background: {SURFACE_ALT}; }}

QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {TEXT_SECONDARY}; }}
QPushButton[variant="ghost"]:hover {{ background: {SURFACE_SUNKEN}; color: {TEXT_PRIMARY}; }}
QPushButton[variant="ghost"]:checked {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}

QPushButton[variant="link"] {{ background: transparent; border: none; color: {ACCENT};
    padding: 0; min-height: 0; font-weight: 500; }}
QPushButton[variant="link"]:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}

QPushButton[scale="sm"] {{ min-height: 24px; padding: 0 10px; font-size: 12px; }}
QPushButton[scale="lg"] {{ min-height: 38px; padding: 0 20px; font-size: 14px; }}
QPushButton[iconOnly="true"] {{ padding: 0; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }}

/* Segmented control */
QFrame#Segmented {{ background: {SURFACE}; border: 1px solid {INPUT_BORDER}; border-radius: 4px; }}
QFrame#Segmented QPushButton {{
    background: transparent; border: none; border-radius: 0;
    border-left: 1px solid {INPUT_BORDER};
    color: {TEXT_PRIMARY}; font-weight: 500; min-height: 28px; padding: 0 12px;
}}
QFrame#Segmented QPushButton[first="true"] {{ border-left: none; border-top-left-radius: 3px; border-bottom-left-radius: 3px; }}
QFrame#Segmented QPushButton[last="true"] {{ border-top-right-radius: 3px; border-bottom-right-radius: 3px; }}
QFrame#Segmented QPushButton:hover {{ background: {SURFACE_ALT}; }}
QFrame#Segmented QPushButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; font-weight: 600; }}
QFrame#Segmented QPushButton:disabled {{ color: {TEXT_DISABLED}; }}
QFrame#Segmented QPushButton:checked:disabled {{ background: {SURFACE_SUNKEN}; color: {TEXT_SECONDARY}; }}

/* ── Inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {SURFACE};
    border: 1px solid {INPUT_BORDER};
    border-radius: 4px;
    padding: 0 8px;
    min-height: 30px;
    color: {TEXT_PRIMARY};
    selection-background-color: #C7D8F3;
    selection-color: {TEXT_PRIMARY};
}}
QPlainTextEdit, QTextEdit {{ padding: 6px 8px; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QDateEdit:hover {{ border-color: #9AA3B0; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QDateEdit:disabled {{
    background: {SURFACE_ALT}; color: {TEXT_DISABLED}; border-color: {BORDER};
}}
QLineEdit:read-only {{ background: {SURFACE_ALT}; }}
QLineEdit[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"] {{ border-color: {DANGER}; }}
QLineEdit[scale="lg"] {{ min-height: 38px; font-size: 14px; padding: 0 12px; }}
QLineEdit[mono="true"], QSpinBox[mono="true"], QDoubleSpinBox[mono="true"] {{ font-family: "{mono}"; }}

QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border: none; border-left: 1px solid {BORDER_SUBTLE};
    border-top-right-radius: 4px; background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: none; border-left: 1px solid {BORDER_SUBTLE};
    border-bottom-right-radius: 4px; background: transparent;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {SURFACE_SUNKEN}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: {a("chev-up.svg")}; width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: {a("chev-down.svg")}; width: 10px; height: 10px; }}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off {{ image: {a("chev-up-dis.svg")}; }}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off {{ image: {a("chev-down-dis.svg")}; }}
QSpinBox[buttons="none"], QDoubleSpinBox[buttons="none"] {{ padding-right: 8px; }}

QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border: none; }}
QComboBox::down-arrow {{ image: {a("chev-down.svg")}; width: 10px; height: 10px; }}
QComboBox::down-arrow:disabled {{ image: {a("chev-down-dis.svg")}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; outline: 0;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT_PRIMARY}; padding: 4px;
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 0 8px; }}

QCheckBox, QRadioButton {{ spacing: 8px; color: {TEXT_PRIMARY}; font-size: 13px; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {TEXT_DISABLED}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_STRONG};
    border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: {a("check.svg")}; }}
QCheckBox::indicator:checked:disabled {{ background: #A9C0E3; border-color: #A9C0E3; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_STRONG};
    border-radius: 8px; background: {SURFACE}; }}
QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{ border: none; image: {a("radio-dot.svg")}; }}

/* ── Tables ─────────────────────────────────────────────────────────── */
QTableView, QTableWidget, QTreeView, QListView {{
    background: {SURFACE};
    alternate-background-color: #FAFBFC;
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER_SUBTLE};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT_PRIMARY};
    outline: 0;
}}
QTableView[flat="true"], QTableWidget[flat="true"], QListView[flat="true"] {{ border: none; border-radius: 0; }}
QTableView::item, QTableWidget::item {{ padding: 0 10px; border: none; border-bottom: 1px solid #EEF0F3; }}
QTableView::item:selected, QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT_PRIMARY}; }}
QTableView::item:hover, QTableWidget::item:hover {{ background: #F3F6FA; }}
QTableView[mono="true"], QTableWidget[mono="true"] {{ font-family: "{mono}"; font-size: 12px; }}
QHeaderView {{ background: {SURFACE_ALT}; border: none; }}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_SECONDARY};
    font-family: "{ui}";
    font-size: 12px;
    font-weight: 600;
    padding: 0 10px;
    min-height: 30px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QHeaderView::section:hover {{ color: {TEXT_PRIMARY}; }}
QTableCornerButton::section {{ background: {SURFACE_ALT}; border: none; }}
QListView::item {{ min-height: 28px; padding: 0 8px; }}
QListView::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}

/* ── Tabs ───────────────────────────────────────────────────────────── */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_SECONDARY}; border: none;
    border-bottom: 2px solid transparent; padding: 8px 14px; font-weight: 600; font-size: 12px;
}}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}
QTabBar::tab:selected {{ color: {ACCENT_TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ── Scroll bars ────────────────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C3C8D0; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #9AA3B0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C3C8D0; border-radius: 3px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: #9AA3B0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ── Misc ───────────────────────────────────────────────────────────── */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QProgressBar {{ background: {SURFACE_SUNKEN}; border: none; border-radius: 2px; max-height: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QToolTip {{ background: {CHROME_BG}; color: {CHROME_TEXT}; border: 1px solid {CHROME_BORDER};
    padding: 5px 8px; border-radius: 4px; font-size: 12px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 4px; color: {TEXT_PRIMARY}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER_SUBTLE}; margin: 4px 6px; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}
QDialogButtonBox QPushButton {{ min-width: 84px; }}
QStatusBar {{ background: {CHROME_BG}; color: {CHROME_TEXT_2}; border: none; }}

/* ── Chrome: top bar ────────────────────────────────────────────────── */
QWidget#TopBar {{ background: {CHROME_BG}; border-bottom: 1px solid {CHROME_BORDER}; }}
QWidget#TopBar QLabel {{ color: {CHROME_TEXT}; }}
QWidget#TopBar QLabel[role="crumb"] {{ color: {CHROME_MUTED}; font-size: 13px; }}
QWidget#TopBar QLabel[role="crumb-current"] {{ color: {CHROME_TEXT}; font-size: 13px; font-weight: 500; }}
QWidget#TopBar QLabel#Brand {{ font-size: 14px; font-weight: 600; }}
QWidget#TopBar QLabel#BrandSub {{ color: {CHROME_MUTED}; font-size: 11px; }}
QWidget#TopBar QPushButton {{ background: transparent; color: {CHROME_TEXT}; border: 1px solid {CHROME_BORDER};
    border-radius: 4px; min-height: 30px; padding: 0 10px; font-weight: 500; }}
QWidget#TopBar QPushButton:hover {{ background: {NAV_HOVER}; border-color: #3A4352; }}
QWidget#TopBar QPushButton::menu-indicator {{ image: none; width: 0; }}
QWidget#TopBar QPushButton#NavToggle {{ border: none; min-width: 32px; max-width: 32px; padding: 0; }}
QFrame#RunPill {{ border-radius: 4px; border: 1px solid #3A4352; background: #1B212B; }}
QFrame#RunPill[state="running"] {{ background: #0F2A1C; border-color: #1E7B4A; }}
QFrame#RunPill[state="ready"]   {{ background: #10233F; border-color: #2F6DC2; }}
QFrame#RunPill[state="fault"]   {{ background: #3A1512; border-color: {DANGER}; }}
QFrame#RunPill QLabel#RunPillText {{ font-size: 12px; font-weight: 700; letter-spacing: 0.6px; color: {CHROME_TEXT_2}; }}
QFrame#RunPill[state="running"] QLabel#RunPillText {{ color: #BFF2D3; }}
QFrame#RunPill[state="ready"] QLabel#RunPillText   {{ color: #CFE0FF; }}
QFrame#RunPill[state="fault"] QLabel#RunPillText   {{ color: #FFD2CC; }}
QFrame#RunPill QLabel#RunPillTime {{ font-family: "{mono}"; font-size: 12px; color: {CHROME_TEXT}; }}

/* ── Chrome: navigation rail ────────────────────────────────────────── */
QWidget#NavRail {{ background: {NAV_BG}; border-right: 1px solid {CHROME_BORDER}; }}
QWidget#NavRail QLabel[role="nav-section"] {{ color: {CHROME_MUTED}; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; padding: 0 12px; }}
QWidget#NavRail QPushButton {{
    background: transparent; color: {CHROME_TEXT_2}; border: none; border-radius: 4px;
    text-align: left; padding: 0 10px; min-height: 34px; font-weight: 400; font-size: 13px;
}}
QWidget#NavRail QPushButton:hover {{ background: {NAV_HOVER}; color: #FFFFFF; }}
QWidget#NavRail QPushButton:checked {{ background: {NAV_ACTIVE}; color: #FFFFFF; font-weight: 600; }}
QWidget#NavRail QFrame#NavDivider {{ background: {CHROME_BORDER}; max-height: 1px; min-height: 1px; }}
QWidget#NavRail QLabel#NavFootText {{ color: {CHROME_MUTED}; font-size: 11px; }}

/* ── Chrome: status footer ──────────────────────────────────────────── */
QWidget#StatusFooter {{ background: {CHROME_BG}; border-top: 1px solid {CHROME_BORDER}; }}
QWidget#StatusFooter QLabel {{ color: {CHROME_TEXT_2}; font-size: 12px; }}
QWidget#StatusFooter QLabel[tone="muted"] {{ color: {CHROME_MUTED}; }}
QWidget#StatusFooter QLabel[tone="warning"] {{ color: {WARNING_LIVE}; }}
QWidget#StatusFooter QLabel[tone="danger"] {{ color: {DANGER_LIVE}; }}
QWidget#StatusFooter QLabel[tone="success"] {{ color: {SUCCESS_LIVE}; }}
QWidget#StatusFooter QFrame#VDivider {{ background: {CHROME_BORDER}; }}

/* ── Sign-in window ─────────────────────────────────────────────────── */
QWidget#LoginWindow {{ background: {SURFACE}; }}
QFrame#LoginHero {{ background: {CHROME_BG}; border: none; }}
QFrame#LoginHero QLabel {{ color: {CHROME_TEXT}; }}
QFrame#LoginHero QLabel[role="hero-sub"] {{ color: {CHROME_MUTED}; font-size: 13px; }}
QFrame#LoginHero QLabel[role="hero-title"] {{ font-size: 26px; font-weight: 600; }}
QFrame#LoginHero QLabel[role="hero-item"] {{ color: {CHROME_TEXT_2}; font-size: 13px; }}
QFrame#LoginHero QLabel[role="hero-foot"] {{ color: {CHROME_MUTED}; font-size: 11px; }}
QFrame#LoginHero QFrame#HeroDivider {{ background: {CHROME_BORDER}; max-height: 1px; min-height: 1px; }}
QFrame#LoginForm {{ background: {SURFACE}; border: none; }}
"""


# Default style sheet (fonts resolved properly by apply_theme).
QSS = build_qss()


def apply_theme(app) -> None:
    """Fusion style + palette + fonts + global style sheet."""
    global _ui_family, _mono_family, QSS
    from PyQt6.QtGui import QColor, QFont, QPalette

    app.setStyle("Fusion")
    _load_bundled_fonts()
    _ui_family = _pick(UI_FONT_CANDIDATES)
    _mono_family = _pick(MONO_FONT_CANDIDATES)

    font = QFont(_ui_family)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#FAFBFC"))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_SOFT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(CHROME_BG))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(CHROME_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DISABLED))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    app.setPalette(pal)

    QSS = build_qss(_ui_family, _mono_family, _asset_dir())
    app.setStyleSheet(QSS)

    try:
        import pyqtgraph as pg
        pg.setConfigOptions(antialias=True, background=SURFACE, foreground=TEXT_SECONDARY)
    except Exception:
        pass

"""
Global colour tokens and Qt Style Sheet — "quiet scientific" warm palette.

Design: calm, instrument-grade. Warm off-white surfaces, muted deep-teal
accent, soft warm-grey lines. Dark sidebar. All widget styling is defined
here and applied once at QApplication level.
"""

# ---------------------------------------------------------------------------
# Tokens — warm scientific palette
# ---------------------------------------------------------------------------

SIDEBAR_BG      = "#1F242C"
SIDEBAR_HOVER   = "#2A2F38"
SIDEBAR_ACTIVE  = "#2F6F7A"   # teal accent for the active nav item
SIDEBAR_TEXT    = "#EDEAE0"
SIDEBAR_MUTED   = "#A3A096"

CONTENT_BG      = "#F7F5F0"   # warm off-white
CARD_BG         = "#FFFFFF"
HEADER_BG       = "#FFFFFF"
SUNKEN_BG       = "#EFECE4"   # warm sunken surface (sliders, tracks)
ELEVATED_BG     = "#FBFAF5"   # subtle elevated fill (table headers, inputs)

PRIMARY         = "#2F6F7A"   # deep teal
PRIMARY_HOVER   = "#26606A"
PRIMARY_PRESSED = "#1F4D54"
PRIMARY_LIGHT   = "#E9F1F2"

SUCCESS         = "#4D7C5F"
SUCCESS_BG      = "#EDF3EE"
WARNING         = "#B5772E"
WARNING_BG      = "#FBF1E3"
ERROR           = "#9B3C3C"
ERROR_BG        = "#F7EAEA"

TEXT_PRIMARY    = "#1F2937"
TEXT_SECONDARY  = "#4B5563"
TEXT_MUTED      = "#8A8578"

BORDER          = "#E2DED4"   # barely-there warm grey
BORDER_STRONG   = "#C7C0B0"

# ---------------------------------------------------------------------------
# Global QSS  (applied to QApplication once in main.py)
# ---------------------------------------------------------------------------

QSS = f"""

/* ── Base ────────────────────────────────────────────────────────────────── */
QWidget {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

QMainWindow, QDialog {{
    background-color: {CONTENT_BG};
}}

/* ── Sidebar ──────────────────────────────────────────────────────────────  */
QWidget#sidebar {{
    background-color: {SIDEBAR_BG};
}}

/* ── Header bar ──────────────────────────────────────────────────────────── */
QWidget#header_bar {{
    background-color: {HEADER_BG};
    border-bottom: 1px solid {BORDER};
}}

/* ── Cards ───────────────────────────────────────────────────────────────── */
QFrame#card {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

/* ── Input fields ────────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {ELEVATED_BG};
    border: 1.5px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {PRIMARY_LIGHT};
}}
QLineEdit:focus {{
    border-color: {PRIMARY};
    background-color: {CARD_BG};
}}
QLineEdit:disabled {{
    background-color: {SUNKEN_BG};
    color: {TEXT_MUTED};
}}

QDoubleSpinBox, QSpinBox {{
    background-color: {ELEVATED_BG};
    border: 1.5px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT_PRIMARY};
}}
QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {PRIMARY};
    background-color: {CARD_BG};
}}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    width: 20px;
    background: {ELEVATED_BG};
    border-left: 1px solid {BORDER};
}}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
    background: {SUNKEN_BG};
}}

QComboBox {{
    background-color: {ELEVATED_BG};
    border: 1.5px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 5px 10px;
    color: {TEXT_PRIMARY};
}}
QComboBox:focus {{
    border-color: {PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    selection-background-color: {PRIMARY_LIGHT};
    selection-color: {TEXT_PRIMARY};
}}

/* ── Check boxes ─────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT_SECONDARY};
    spacing: 9px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1.5px solid {BORDER_STRONG};
    border-radius: 5px;
    background: {ELEVATED_BG};
}}
QCheckBox::indicator:hover {{
    border-color: {PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QCheckBox::indicator:checked:hover {{
    background: {PRIMARY_HOVER};
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 600;
    font-size: 13px;
    border: none;
}}

QPushButton#btn_primary {{
    background-color: {PRIMARY};
    color: white;
}}
QPushButton#btn_primary:hover   {{ background-color: {PRIMARY_HOVER}; }}
QPushButton#btn_primary:pressed {{ background-color: {PRIMARY_PRESSED}; }}
QPushButton#btn_primary:disabled {{
    background-color: #BBD3D6;
    color: #8FB6BA;
}}

QPushButton#btn_danger {{
    background-color: {ERROR};
    color: white;
}}
QPushButton#btn_danger:hover   {{ background-color: #883333; }}
QPushButton#btn_danger:pressed {{ background-color: #742B2B; }}
QPushButton#btn_danger:disabled {{
    background-color: #D8B4B4;
    color: #C99B9B;
}}

QPushButton#btn_ghost {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1.5px solid {BORDER_STRONG};
}}
QPushButton#btn_ghost:hover {{
    background-color: {ELEVATED_BG};
    color: {PRIMARY};
    border-color: {PRIMARY};
}}

/* ── Tables ──────────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {SUNKEN_BG};
    color: {TEXT_PRIMARY};
}}
QTableWidget::item {{
    padding: 5px 10px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {PRIMARY_LIGHT};
    color: {TEXT_PRIMARY};
}}
QTableWidget::item:alternate {{
    background-color: {ELEVATED_BG};
}}
QHeaderView::section {{
    background-color: {ELEVATED_BG};
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 700;
    padding: 7px 10px;
    border: none;
    border-bottom: 1.5px solid {BORDER};
    letter-spacing: 0.5px;
}}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ────────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER};
}}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {HEADER_BG};
    border-top: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}

/* ── Tooltips ────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {SIDEBAR_BG};
    color: {SIDEBAR_TEXT};
    border: none;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
}}

/* ── Message boxes ───────────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {CARD_BG};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
}}
"""

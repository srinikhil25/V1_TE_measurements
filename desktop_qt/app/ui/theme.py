"""
Global colour tokens and Qt Style Sheet.

Design: clean, minimal, professional.
Sidebar dark. Content area light.
All widget styling is defined here and applied once at QApplication level.
"""

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

SIDEBAR_BG      = "#111827"
SIDEBAR_HOVER   = "#1F2937"
SIDEBAR_ACTIVE  = "#2563EB"
SIDEBAR_TEXT    = "#F9FAFB"
SIDEBAR_MUTED   = "#CBD5E1"   # lighter than before — better readability

CONTENT_BG      = "#F1F5F9"
CARD_BG         = "#FFFFFF"
HEADER_BG       = "#FFFFFF"

PRIMARY         = "#2563EB"
PRIMARY_HOVER   = "#1D4ED8"
PRIMARY_LIGHT   = "#EFF6FF"

SUCCESS         = "#16A34A"
SUCCESS_BG      = "#F0FDF4"
WARNING         = "#D97706"
WARNING_BG      = "#FFFBEB"
ERROR           = "#DC2626"
ERROR_BG        = "#FEF2F2"

TEXT_PRIMARY    = "#0F172A"
TEXT_SECONDARY  = "#475569"
TEXT_MUTED      = "#94A3B8"

BORDER          = "#CBD5E1"    # slightly darker — more visible borders
BORDER_STRONG   = "#94A3B8"

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
    background-color: {CARD_BG};
    border: 1.5px solid {BORDER};
    border-radius: 5px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {PRIMARY_LIGHT};
}}
QLineEdit:focus {{
    border-color: {PRIMARY};
}}
QLineEdit:disabled {{
    background-color: #F8FAFC;
    color: {TEXT_MUTED};
}}

QDoubleSpinBox, QSpinBox {{
    background-color: {CARD_BG};
    border: 1.5px solid {BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT_PRIMARY};
}}
QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {PRIMARY};
}}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    width: 20px;
    background: #F8FAFC;
    border-left: 1px solid {BORDER};
}}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
    background: #E2E8F0;
}}

QComboBox {{
    background-color: {CARD_BG};
    border: 1.5px solid {BORDER};
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
QPushButton#btn_primary:pressed {{ background-color: #1E40AF; }}
QPushButton#btn_primary:disabled {{
    background-color: #BFDBFE;
    color: #93C5FD;
}}

QPushButton#btn_danger {{
    background-color: {ERROR};
    color: white;
}}
QPushButton#btn_danger:hover   {{ background-color: #B91C1C; }}
QPushButton#btn_danger:pressed {{ background-color: #991B1B; }}
QPushButton#btn_danger:disabled {{
    background-color: #FCA5A5;
    color: #FECACA;
}}

QPushButton#btn_ghost {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1.5px solid {BORDER};
}}
QPushButton#btn_ghost:hover {{
    background-color: {CONTENT_BG};
    color: {TEXT_PRIMARY};
    border-color: {BORDER_STRONG};
}}

/* ── Tables ──────────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: #F1F5F9;
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
    background-color: #F8FAFC;
}}
QHeaderView::section {{
    background-color: #F8FAFC;
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
    background: {BORDER};
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
    background: {BORDER};
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

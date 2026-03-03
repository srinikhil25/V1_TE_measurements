# TE Measurement — PyQt6 Desktop App

Native Windows desktop application for thermoelectric measurement management.
No browser, no WebView — pure Python + Qt widgets.

---

## Quick Start

```powershell
cd desktop_qt

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Launch
python main.py
```

---

## Dev Accounts

| Username     | Password     | Role          |
|--------------|--------------|---------------|
| `superadmin` | `superadmin` | Super Admin   |
| `labadmin`   | `labadmin`   | Lab Admin     |
| `researcher` | `researcher` | Researcher    |

> ⚠ Change these before any shared deployment.

---

## Project Structure

```
desktop_qt/
├── main.py                        # Entry point
├── requirements.txt
└── app/
    ├── core/
    │   ├── database.py            # SQLAlchemy engine + seeding
    │   ├── security.py            # bcrypt helpers
    │   └── paths.py               # %APPDATA% paths
    ├── models/
    │   └── db_models.py           # SQLAlchemy ORM models
    ├── instruments/               # Copied from backend (no HTTP)
    │   ├── instrument.py          # Keithley/PK160 drivers
    │   ├── session_manager.py     # Measurement loop thread
    │   └── seebeck_analysis.py    # Binned S analysis
    ├── services/
    │   ├── auth_service.py        # Login / logout / session state
    │   └── measurement_service.py # SeebeckService + run_iv_sweep
    └── ui/
        ├── theme.py               # Colour tokens + QSS
        ├── login_window.py
        ├── main_window.py
        ├── widgets/
        │   ├── sidebar.py
        │   └── header_bar.py
        └── pages/
            ├── dashboard.py
            ├── seebeck_page.py    # Live charts via pyqtgraph
            ├── iv_page.py         # IV sweep + scatter chart
            ├── history_page.py
            ├── users_page.py      # super_admin only
            └── settings_page.py
```

---

## Database

SQLite at `%APPDATA%\TEMeasurement\te_measurement.db`, WAL mode.

---

## Tech Stack

| Layer       | Technology              |
|-------------|-------------------------|
| UI          | PyQt6 (native Qt widgets) |
| Charts      | pyqtgraph               |
| ORM         | SQLAlchemy 2.x          |
| Database    | SQLite (WAL mode)       |
| Auth        | bcrypt                  |
| Instruments | PyVISA + custom drivers |
| Packaging   | PyInstaller             |

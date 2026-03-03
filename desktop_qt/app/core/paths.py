"""Application data path helpers (Windows-first)."""

import os
from pathlib import Path


def get_app_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home()
    app_dir = base / "TEMeasurement"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_db_path() -> str:
    return str(get_app_dir() / "te_measurement.db")

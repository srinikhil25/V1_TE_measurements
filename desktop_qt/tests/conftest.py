"""Shared test setup.

Tests never touch the real rig configuration or the real measurement
database: TE_CONFIG_PATH points at a temporary file, and database tests build
their own engine on a temporary SQLite file.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Redirect the application data folder (database, config, lock file) BEFORE any
# app module is imported, so no test can touch the real lab database.
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="te-tests-")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own config file and a fresh config cache."""
    from app.core import config

    monkeypatch.setenv("TE_CONFIG_PATH", str(tmp_path / "config.toml"))
    monkeypatch.setattr(config, "_cached", None)
    monkeypatch.setattr(config, "_warnings", [])
    yield tmp_path / "config.toml"


@pytest.fixture
def temp_db(tmp_path):
    """A migrated temporary database. Returns (db_path, session_factory)."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.migrations import upgrade_database

    db_path = str(tmp_path / "test.db")
    upgrade_database(db_path)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield db_path, factory
    engine.dispose()

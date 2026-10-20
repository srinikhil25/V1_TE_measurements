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


# ── Real instruments are off limits ─────────────────────────────────────────
# Opening the default VISA library (NI-VISA) from a test reaches the real GPIB
# bus — on the lab PC that can disturb a running measurement, and a scan still
# inside NI-VISA when the test process exits can hang it. Tests use the
# simulated rig (TE_VISA_BACKEND=sim) or fakes; anything else fails here.
import pyvisa  # noqa: E402

_real_rm_new = pyvisa.ResourceManager.__new__


def _no_real_visa(cls, visa_library="", *args, **kwargs):
    if isinstance(visa_library, str) and not visa_library.strip():
        raise RuntimeError("Tests must not open the real VISA library; use the "
                           "simulated rig (TE_VISA_BACKEND=sim) or a fake.")
    return _real_rm_new(cls, visa_library, *args, **kwargs)


pyvisa.ResourceManager.__new__ = _no_real_visa


@pytest.fixture(autouse=True)
def no_instrument_scan(monkeypatch):
    """No background GPIB scan in any test.

    Widgets schedule a scan with a delayed timer, and pytest-qt processes Qt
    events after EVERY test — so a timer from one test fires in a later one.
    Stubbing per file let that later scan reach the real library.
    """
    from app.services import instrument_scan
    monkeypatch.setattr(instrument_scan, "start_resource_scan", lambda cb: False)


def pytest_sessionfinish(session, exitstatus):
    """Turn a hang at interpreter exit into a diagnosis instead of silence:
    if the process is still alive 60 s after the last test, print every
    thread's stack and exit."""
    import faulthandler
    faulthandler.dump_traceback_later(60, exit=True)


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


@pytest.fixture
def app_db(temp_db, monkeypatch):
    """temp_db wired in as the application's database (SessionLocal / get_session)."""
    from app.core import database

    _path, factory = temp_db
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(database, "get_session", factory)
    return temp_db


@pytest.fixture
def make_user(app_db):
    from datetime import datetime

    from app.models.db_models import User

    _path, factory = app_db

    def _make(username="u1", role="researcher", lab_id=None):
        s = factory()
        u = User(username=username, email=f"{username}@x", password_hash="h", role=role,
                 lab_id=lab_id, active=True, created_at=datetime.utcnow())
        s.add(u)
        s.commit()
        uid = u.id
        s.close()
        return uid
    return _make

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect

from app.migrations import HEAD, upgrade_database


def _schema(db_path):
    """{table: {column: nullable}} plus index names, ignoring alembic_version."""
    eng = create_engine(f"sqlite:///{db_path}")
    try:
        insp = inspect(eng)
        tables = {}
        for t in insp.get_table_names():
            if t == "alembic_version":
                continue
            tables[t] = {
                "cols": {c["name"]: c["nullable"] for c in insp.get_columns(t)},
                "idx": sorted(i["name"] for i in insp.get_indexes(t)),
            }
        return tables
    finally:
        eng.dispose()


def _create_all(db_path):
    from app.core.database import Base
    from app.models import db_models  # noqa: F401
    eng = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    eng.dispose()


def _version(db_path):
    with sqlite3.connect(db_path) as c:
        return c.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_fresh_database_matches_models(tmp_path):
    migrated = tmp_path / "migrated.db"
    modelled = tmp_path / "models.db"
    assert upgrade_database(str(migrated)) == ["0001", "0002"]
    _create_all(str(modelled))
    assert _schema(str(migrated)) == _schema(str(modelled))
    assert _version(str(migrated)) == HEAD


def test_upgrade_is_idempotent(tmp_path):
    db = str(tmp_path / "x.db")
    upgrade_database(db)
    assert upgrade_database(db) == []


LEGACY_DDL = """
CREATE TABLE labs (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(100) NOT NULL,
  department VARCHAR(100), contact_email VARCHAR(120), created_at DATETIME NOT NULL,
  active BOOLEAN NOT NULL);
CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY, username VARCHAR(50) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE, password_hash VARCHAR(200) NOT NULL,
  role VARCHAR(11) NOT NULL, lab_id INTEGER REFERENCES labs(id),
  created_at DATETIME NOT NULL, last_login DATETIME, active BOOLEAN NOT NULL);
CREATE TABLE measurements (id INTEGER NOT NULL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id), lab_id INTEGER NOT NULL REFERENCES labs(id),
  type VARCHAR(30) NOT NULL, status VARCHAR(20), sample_id VARCHAR(100),
  operator VARCHAR(100), notes TEXT, params_json TEXT, started_at DATETIME NOT NULL,
  finished_at DATETIME);
CREATE INDEX ix_measurements_id ON measurements (id);
CREATE TABLE measurement_rows (id INTEGER NOT NULL PRIMARY KEY,
  measurement_id INTEGER NOT NULL REFERENCES measurements(id), seq INTEGER NOT NULL,
  elapsed_s INTEGER, data_json TEXT NOT NULL);
CREATE TABLE extra_sidecar_table (id INTEGER PRIMARY KEY);
INSERT INTO labs VALUES (1, 'Lab', NULL, NULL, '2026-01-01', 1);
INSERT INTO users VALUES (1, 'u', 'u@x', 'h', 'researcher', 1, '2026-01-01', NULL, 1);
INSERT INTO measurements VALUES (1, 1, 1, 'seebeck', 'finished', 'S1', 'u', NULL, '{}',
  '2026-01-01', '2026-01-01');
INSERT INTO measurement_rows VALUES (1, 1, 1, 0, '{"a": 1}');
INSERT INTO measurement_rows VALUES (2, 1, 2, 1, '{"a": 2}');
"""


def test_legacy_unversioned_database_is_upgraded_without_data_loss(tmp_path):
    db = str(tmp_path / "legacy.db")
    with sqlite3.connect(db) as c:
        c.executescript(LEGACY_DDL)
        c.execute("PRAGMA journal_mode=WAL")

    applied = upgrade_database(db)
    assert applied == ["0001", "0002"]
    assert _version(db) == HEAD

    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*) FROM measurement_rows").fetchone()[0] == 2
        assert c.execute("SELECT sample_id FROM measurements").fetchone()[0] == "S1"
        # baseline created the table the legacy DB was missing
        assert c.execute("SELECT count(*) FROM measurement_integrity").fetchone()[0] == 0
        # other tables are left alone
        assert c.execute("SELECT count(*) FROM extra_sidecar_table").fetchone()[0] == 0
        # lab_id is now nullable and end_reason exists
        c.execute("INSERT INTO measurements (user_id, lab_id, type, started_at, end_reason) "
                  "VALUES (1, NULL, 'iv', '2026-01-02', 'test')")
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    backups = list(tmp_path.glob("legacy.backup-pre-0001-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(str(backups[0])) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(measurements)")]
        assert "end_reason" not in cols          # backup is the pre-migration state
        assert c.execute("SELECT count(*) FROM measurement_rows").fetchone()[0] == 2


def test_newer_database_is_refused(tmp_path):
    db = str(tmp_path / "future.db")
    upgrade_database(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE alembic_version SET version_num = '9999'")
    with pytest.raises(RuntimeError, match="newer"):
        upgrade_database(db)


def test_interrupted_runs_are_marked(tmp_path, monkeypatch, temp_db):
    from datetime import datetime

    from app.core import database
    from app.models.db_models import Lab, Measurement, User

    _db_path, factory = temp_db
    s = factory()
    lab = Lab(name="L", active=True, created_at=datetime.utcnow())
    s.add(lab)
    s.flush()
    u = User(username="u", email="u@x", password_hash="h", role="researcher",
             lab_id=lab.id, active=True, created_at=datetime.utcnow())
    s.add(u)
    s.flush()
    s.add_all([
        Measurement(user_id=u.id, lab_id=None, type="seebeck", status="running",
                    started_at=datetime.utcnow()),
        Measurement(user_id=u.id, lab_id=lab.id, type="iv", status="finished",
                    started_at=datetime.utcnow()),
    ])
    s.commit()
    s.close()

    monkeypatch.setattr(database, "SessionLocal", factory)
    database._mark_interrupted_runs()

    s = factory()
    statuses = sorted((m.type, m.status, bool(m.end_reason)) for m in s.query(Measurement))
    s.close()
    assert statuses == [("iv", "finished", False), ("seebeck", "interrupted", True)]

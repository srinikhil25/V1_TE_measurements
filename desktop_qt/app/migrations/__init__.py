"""Versioned database schema migrations (Alembic operations, batch mode).

Replaces ``metadata.create_all()``, which can create missing tables but can
never change an existing one, so a schema change never reached installed
labs. Each revision is a plain module in this package exposing ``upgrade(op)``,
where ``op`` is an ``alembic.operations.Operations`` bound to a SQLite
connection in batch mode.

The applied revision is stored in the standard ``alembic_version`` table.
Revisions are imported as ordinary modules (no Alembic script directory or
``env.py`` on disk), so the frozen PyInstaller build needs nothing extra.

Every revision must be idempotent (inspect first, then change), because
databases created before migrations existed (by ``create_all``) carry no
version stamp and are upgraded from the start.

Adding a schema change:
  1. change ``app/models/db_models.py``;
  2. add ``rNNNN_<name>.py`` with ``REVISION = "NNNN"`` and ``upgrade(op)``;
  3. append it to ``_REVISIONS`` below;
  4. ``pytest tests/test_migrations.py`` checks migrated schema == model schema.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from . import r0001_baseline, r0002_measurement_outcome

logger = logging.getLogger(__name__)

_REVISIONS = [r0001_baseline, r0002_measurement_outcome]

HEAD = _REVISIONS[-1].REVISION
VERSION_TABLE = "alembic_version"


def current_revision(conn) -> Optional[str]:
    if not inspect(conn).has_table(VERSION_TABLE):
        return None
    row = conn.execute(text(f"SELECT version_num FROM {VERSION_TABLE}")).first()
    return row[0] if row else None


def _pending(current: Optional[str]) -> list:
    ids = [m.REVISION for m in _REVISIONS]
    if current is None:
        return list(_REVISIONS)
    if current not in ids:
        raise RuntimeError(
            f"Database schema revision {current!r} is newer than this application "
            f"(knows up to {HEAD}). Install the newer version of TE Measurement."
        )
    return _REVISIONS[ids.index(current) + 1:]


def _stamp(conn, revision: str) -> None:
    if not inspect(conn).has_table(VERSION_TABLE):
        conn.execute(text(
            f"CREATE TABLE {VERSION_TABLE} (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
    conn.execute(text(f"DELETE FROM {VERSION_TABLE}"))
    conn.execute(text(f"INSERT INTO {VERSION_TABLE} (version_num) VALUES (:v)"),
                 {"v": revision})


def backup_database(db_path: str, tag: str) -> Optional[str]:
    """Copy the database (WAL-safe, via the SQLite backup API). Returns the path."""
    src = Path(db_path)
    if not src.exists() or src.stat().st_size == 0:
        return None
    dst = src.with_name(
        f"{src.stem}.backup-{tag}-{datetime.now():%Y%m%d-%H%M%S}{src.suffix}")
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    return str(dst)


def upgrade_database(db_path: str) -> List[str]:
    """Bring the database at ``db_path`` to HEAD. Returns the revisions applied.

    An existing database is backed up before any change. Raises on failure;
    each revision runs in its own transaction, so a failed one is rolled back
    and the database stays at the previous revision.
    """
    logging.getLogger("alembic").setLevel(logging.WARNING)   # quiet plugin chatter
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    # Dedicated engine: foreign keys must be OFF while batch mode rebuilds
    # tables (dropping a referenced table would otherwise fail).
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    applied: List[str] = []
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            current = current_revision(conn)
            pending = _pending(current)
            had_tables = bool(inspect(conn).get_table_names())
            conn.commit()
            if not pending:
                return applied
            if had_tables:
                path = backup_database(db_path, f"pre-{pending[0].REVISION}")
                if path:
                    logger.warning("Database backed up before migration: %s", path)
            ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
            op = Operations(ctx)
            for mod in pending:
                with conn.begin():
                    logger.info("Applying schema migration %s",
                                mod.__name__.rsplit(".", 1)[-1])
                    mod.upgrade(op)
                    _stamp(conn, mod.REVISION)
                applied.append(mod.REVISION)
            bad = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            conn.commit()
            if bad:
                logger.error("Foreign-key check after migration reported %d issue(s): %s",
                             len(bad), bad[:5])
    finally:
        engine.dispose()
    return applied

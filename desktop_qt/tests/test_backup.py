import sqlite3
from datetime import date, timedelta

from app.core import backup


def _db(tmp_path):
    p = tmp_path / "live.db"
    with sqlite3.connect(p) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (42)")
    return p


def test_daily_backup_once_per_day_and_verified(tmp_path):
    src = _db(tmp_path)
    folder = tmp_path / "backups"
    folder.mkdir()
    today = date(2026, 10, 19)
    first = backup.daily_backup(str(src), folder=folder, today=today)
    assert first is not None and first.name == "te_measurement-20261019.db"
    assert backup.daily_backup(str(src), folder=folder, today=today) is None   # same day
    with sqlite3.connect(first) as c:
        assert c.execute("SELECT x FROM t").fetchone()[0] == 42


def test_old_backups_are_pruned(tmp_path):
    src = _db(tmp_path)
    folder = tmp_path / "backups"
    folder.mkdir()
    today = date(2026, 10, 19)
    for days in (0, 10, 29, 31, 60):
        d = today - timedelta(days=days)
        (folder / f"te_measurement-{d:%Y%m%d}.db").write_bytes(b"x")
    (folder / "te_measurement-20200101-manual-101010.db").write_bytes(b"x")
    (folder / "unrelated.db").write_bytes(b"x")
    backup.daily_backup(str(src), folder=folder, today=today, keep_days=30)
    names = sorted(p.name for p in folder.iterdir())
    assert names == sorted([
        "te_measurement-20261019.db",
        f"te_measurement-{today - timedelta(days=10):%Y%m%d}.db",
        f"te_measurement-{today - timedelta(days=29):%Y%m%d}.db",
        "unrelated.db",
    ])


def test_missing_database_is_not_an_error(tmp_path):
    assert backup.daily_backup(str(tmp_path / "nope.db"), folder=tmp_path) is None


def test_backup_now(tmp_path):
    src = _db(tmp_path)
    p = backup.backup_now(str(src), tag="manual", folder=tmp_path)
    assert p.exists() and "manual" in p.name

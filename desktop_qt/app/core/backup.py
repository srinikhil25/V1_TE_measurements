"""Automatic database backups.

One verified copy per day, taken at startup, kept for ``KEEP_DAYS`` days, in
``%APPDATA%\\TEMeasurement\\backups``. Uses the SQLite online-backup API, so it is
consistent even with WAL mode and an open connection. Backups taken before a
schema upgrade (app.migrations) sit next to the database and are not pruned.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .paths import get_app_dir

logger = logging.getLogger(__name__)

KEEP_DAYS = 30
_NAME = re.compile(r"^te_measurement-(\d{8})(?:-[\w-]+)?\.db$")


def backups_dir() -> Path:
    d = get_app_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy(src: Path, dst: Path) -> None:
    tmp = dst.with_suffix(".db.part")
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(tmp))
    try:
        s.backup(d)
        ok = d.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        d.close()
        s.close()
    if ok != "ok":
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backup failed integrity check: {ok}")
    tmp.replace(dst)


def backup_now(db_path: str, tag: str = "manual", folder: Optional[Path] = None) -> Path:
    """Take a verified backup immediately. Raises on failure."""
    folder = folder or backups_dir()
    dst = folder / f"te_measurement-{date.today():%Y%m%d}-{tag}-{datetime.now():%H%M%S}.db"
    _copy(Path(db_path), dst)
    logger.info("Database backup written: %s", dst)
    return dst


def daily_backup(db_path: str, keep_days: int = KEEP_DAYS,
                 folder: Optional[Path] = None, today: Optional[date] = None) -> Optional[Path]:
    """Back up once per day and prune old copies. Returns the new backup or None.

    Never raises — a failed backup must not stop the application starting.
    """
    try:
        src = Path(db_path)
        if not src.exists() or src.stat().st_size == 0:
            return None
        folder = folder or backups_dir()
        today = today or date.today()
        dst = folder / f"te_measurement-{today:%Y%m%d}.db"
        made = None
        if not dst.exists():
            _copy(src, dst)
            made = dst
            logger.info("Daily database backup written: %s", dst)
        prune(folder, keep_days, today)
        return made
    except Exception as exc:
        logger.error("Daily database backup failed: %s", exc)
        return None


def prune(folder: Path, keep_days: int, today: Optional[date] = None) -> List[Path]:
    """Delete dated backups older than ``keep_days``. Returns the removed paths."""
    today = today or date.today()
    cutoff = today - timedelta(days=keep_days)
    removed = []
    for p in folder.glob("te_measurement-*.db"):
        m = _NAME.match(p.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if d < cutoff:
            try:
                p.unlink()
                removed.append(p)
            except OSError as exc:
                logger.warning("Could not remove old backup %s: %s", p, exc)
    if removed:
        logger.info("Pruned %d backup(s) older than %d days", len(removed), keep_days)
    return removed


def list_backups(folder: Optional[Path] = None) -> List[Path]:
    folder = folder or backups_dir()
    return sorted(folder.glob("te_measurement-*.db"), reverse=True)

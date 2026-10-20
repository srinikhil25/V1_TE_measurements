"""Append-only, hash-chained audit trail (ALCOA+: attributable, contemporaneous).

Usage::

    from app.core import audit
    audit.record("config_changed", details={"safety.max_temperature_C": [120, 95]})

``record`` never raises: auditing must not be able to break a measurement.
Failures are logged at ERROR level.

Each entry stores ``entry_hash = SHA-256(prev_hash + canonical JSON of the
entry)``. ``verify_chain`` recomputes the chain and reports the first entry
whose content or ordering no longer matches. UPDATE and DELETE on the table
are blocked by triggers (migration 0003). Limitation: someone with direct
file access who drops the triggers and removes the *newest* entries leaves a
consistent, shorter chain; daily backups (app.core.backup) bound that.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GENESIS = "0" * 64
_lock = threading.Lock()

# Actions recorded by the application (free text is allowed, these are the
# ones the UI knows how to describe).
ACTIONS = {
    "app_started": "Application started",
    "login": "Signed in",
    "login_failed": "Failed sign-in",
    "logout": "Signed out",
    "password_changed": "Password changed",
    "user_created": "User created",
    "user_updated": "User updated",
    "config_changed": "Rig configuration changed",
    "run_started": "Measurement started",
    "run_ended": "Measurement ended",
    "export": "Data exported",
    "db_migrated": "Database schema upgraded",
    "db_backup": "Database backed up",
    "runs_interrupted": "Unfinished runs marked interrupted",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _canonical(entry: Dict[str, Any]) -> str:
    fields = {k: entry.get(k) for k in (
        "timestamp", "user_id", "username", "action", "measurement_id", "details", "reason")}
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, entry: Dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()


def _current_user():
    try:
        from ..services.auth_service import get_current_user
        return get_current_user()
    except Exception:
        return None


def record(
    action: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    measurement_id: Optional[int] = None,
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    use_current_user: bool = True,
) -> bool:
    """Append one entry. Returns True on success; never raises."""
    from . import database
    from ..models.db_models import AuditEntry

    if use_current_user and user_id is None and username is None:
        u = _current_user()
        if u is not None:
            user_id, username = getattr(u, "id", None), getattr(u, "username", None)

    entry = {
        "timestamp": _now(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "measurement_id": measurement_id,
        "details": json.dumps(details, sort_keys=True, default=str, ensure_ascii=False)
        if details is not None else None,
        "reason": reason,
    }
    with _lock:
        db = None
        try:
            db = database.SessionLocal()
            last = db.query(AuditEntry.entry_hash).order_by(AuditEntry.id.desc()).first()
            prev = last[0] if last else GENESIS
            db.add(AuditEntry(prev_hash=prev, entry_hash=compute_hash(prev, entry), **entry))
            db.commit()
            return True
        except Exception as exc:
            logger.error("Audit record %r failed: %s", action, exc)
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            return False
        finally:
            if db is not None:
                db.close()


def verify_chain() -> Dict[str, Any]:
    """Recompute the chain. Returns {"ok", "count", "first_bad_id", "problem"}."""
    from . import database
    from ..models.db_models import AuditEntry

    db = database.SessionLocal()
    try:
        prev = GENESIS
        count = 0
        for e in db.query(AuditEntry).order_by(AuditEntry.id).yield_per(500):
            count += 1
            entry = {k: getattr(e, k) for k in (
                "timestamp", "user_id", "username", "action", "measurement_id", "details", "reason")}
            if e.prev_hash != prev:
                return {"ok": False, "count": count, "first_bad_id": e.id,
                        "problem": "entry missing or reordered before this one"}
            if compute_hash(prev, entry) != e.entry_hash:
                return {"ok": False, "count": count, "first_bad_id": e.id,
                        "problem": "entry content was changed"}
            prev = e.entry_hash
        return {"ok": True, "count": count, "first_bad_id": None, "problem": None}
    finally:
        db.close()


def recent(limit: int = 500, measurement_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Newest entries first, as plain dicts (for the UI)."""
    from . import database
    from ..models.db_models import AuditEntry

    db = database.SessionLocal()
    try:
        q = db.query(AuditEntry)
        if measurement_id is not None:
            q = q.filter(AuditEntry.measurement_id == measurement_id)
        rows = q.order_by(AuditEntry.id.desc()).limit(limit).all()
        return [{
            "id": r.id, "timestamp": r.timestamp, "username": r.username,
            "action": r.action, "measurement_id": r.measurement_id,
            "details": json.loads(r.details) if r.details else None,
            "reason": r.reason,
        } for r in rows]
    finally:
        db.close()


def describe(action: str) -> str:
    return ACTIONS.get(action, action.replace("_", " ").capitalize())

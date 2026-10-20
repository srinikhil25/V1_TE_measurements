import sqlite3
from contextlib import closing

import pytest

from app.core import audit
from app.core.config import AppConfig, diff_configs


def test_record_and_verify_chain(app_db):
    assert audit.record("login", user_id=1, username="a", details={"role": "x"})
    assert audit.record("config_changed", details={"changes": {"safety.max_temperature_C": [120, 95]}},
                        use_current_user=False)
    assert audit.record("run_ended", measurement_id=7, reason="Safety abort: over-temperature",
                        details={"outcome": "aborted"}, use_current_user=False)
    res = audit.verify_chain()
    assert res == {"ok": True, "count": 3, "first_bad_id": None, "problem": None}
    rows = audit.recent()
    assert [r["action"] for r in rows] == ["run_ended", "config_changed", "login"]
    assert rows[0]["details"] == {"outcome": "aborted"}
    assert audit.recent(measurement_id=7)[0]["reason"].startswith("Safety abort")


def test_update_and_delete_are_blocked(app_db):
    path, _ = app_db
    audit.record("login", username="a", use_current_user=False)
    with closing(sqlite3.connect(path)) as c, c:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            c.execute("UPDATE audit_trail SET username = 'b'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            c.execute("DELETE FROM audit_trail")


def test_tampering_is_detected(app_db):
    path, _ = app_db
    for i in range(4):
        audit.record("export", details={"n": i}, use_current_user=False)
    with closing(sqlite3.connect(path)) as c, c:      # an attacker with file access drops the guard
        c.execute("DROP TRIGGER audit_trail_no_update")
        c.execute("DROP TRIGGER audit_trail_no_delete")
        c.execute("UPDATE audit_trail SET details = '{\"n\": 99}' WHERE id = 2")
    res = audit.verify_chain()
    assert not res["ok"] and res["first_bad_id"] == 2 and "changed" in res["problem"]


def test_deleted_middle_entry_is_detected(app_db):
    path, _ = app_db
    for i in range(4):
        audit.record("export", details={"n": i}, use_current_user=False)
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("DROP TRIGGER audit_trail_no_delete")
        c.execute("DELETE FROM audit_trail WHERE id = 2")
    res = audit.verify_chain()
    assert not res["ok"] and res["first_bad_id"] == 3 and "missing" in res["problem"]


def test_record_never_raises_without_table(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core import database
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng))
    try:
        assert audit.record("login", use_current_user=False) is False
    finally:
        eng.dispose()


def test_current_user_is_attributed(app_db, monkeypatch):
    from types import SimpleNamespace

    from app.services import auth_service
    monkeypatch.setattr(auth_service, "_current_user", SimpleNamespace(id=5, username="alice"))
    audit.record("export", details={})
    r = audit.recent()[0]
    assert r["username"] == "alice"


def test_config_diff():
    a = AppConfig()
    b = a.copy()
    b.safety.max_temperature_C = 90.0
    b.instruments.k2700 = "GPIB0::17::INSTR"
    assert diff_configs(a, b) == {
        "safety.max_temperature_C": [120.0, 90.0],
        "instruments.k2700": ["GPIB0::16::INSTR", "GPIB0::17::INSTR"],
    }
    assert diff_configs(a, a.copy()) == {}


def test_login_logout_are_audited(app_db, monkeypatch):
    from datetime import datetime

    from app.core.security import hash_password
    from app.models.db_models import User
    from app.services import auth_service

    _p, factory = app_db
    monkeypatch.setattr(auth_service, "SessionLocal", factory)
    s = factory()
    s.add(User(username="bob", email="b@x", password_hash=hash_password("pw123456"),
               role="researcher", active=True, created_at=datetime.utcnow()))
    s.commit()
    s.close()
    assert auth_service.authenticate("bob", "wrong") is None
    assert auth_service.authenticate("bob", "pw123456") is not None
    auth_service.logout()
    actions = [r["action"] for r in reversed(audit.recent())]
    assert actions == ["login_failed", "login", "logout"]
    assert audit.verify_chain()["ok"]

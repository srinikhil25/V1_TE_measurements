"""Users, Audit trail and Sign-in: account management rules, the audit view and
login outcomes (pytest-qt, temporary database)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")


@pytest.fixture
def boxes(monkeypatch):
    """Record QMessageBox calls instead of showing them."""
    from PyQt6.QtWidgets import QMessageBox

    seen = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(
            lambda parent, title, text, *a, k=kind, **kw: seen.append((k, title, text))))
    return seen


def _admin(uid):
    return SimpleNamespace(id=uid, username="boss", role="super_admin", lab_id=None)


def _actions(factory, action):
    from app.core import audit
    return [r for r in audit.recent(limit=100) if r["action"] == action]


# ── Users ────────────────────────────────────────────────────────────────────
@pytest.fixture
def users_page(qtbot, app_db, make_user, monkeypatch):
    from app.ui.pages import users_page as up

    boss = make_user("boss", "super_admin")
    make_user("alice", "researcher")
    make_user("bob", "lab_admin")
    page = up.UsersPage(_admin(boss))
    qtbot.addWidget(page)
    page.show()

    script = {}

    def fake_exec(dlg):
        """Fill the dialog from `script` and press Save."""
        for key, val in script.items():
            if key == "role":
                dlg.cb_role.setCurrentIndex(up._ROLES.index(val))
            elif key == "active":
                dlg.chk_active.setChecked(val)
            else:
                getattr(dlg, f"inp_{key}").setText(val)
        dlg._accept()
        return dlg.result()

    monkeypatch.setattr(up._UserDialog, "exec", fake_exec)
    page.script = script
    page.boss_id = boss
    return page


def _visible(page):
    return sorted(u["username"] for i, u in enumerate(page._users)
                  if not page.table.isRowHidden(i))


def test_users_list_and_filters(users_page):
    assert _visible(users_page) == ["alice", "bob", "boss"]
    users_page.inp_search.setText("ali")
    assert _visible(users_page) == ["alice"]
    users_page.inp_search.setText("")
    users_page.cb_role.setCurrentIndex(users_page.cb_role.findData("lab_admin"))
    assert _visible(users_page) == ["bob"]
    users_page.inp_search.setText("nobody")
    assert users_page.empty.isVisibleTo(users_page)


def test_user_dialog_validates_before_saving(qtbot):
    from PyQt6.QtWidgets import QDialog

    from app.ui.pages.users_page import _UserDialog
    dlg = _UserDialog()
    qtbot.addWidget(dlg)
    dlg.inp_email.setText("not-an-email")
    dlg.inp_password.setText("123")
    dlg._accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    text = dlg.lbl_err.text()
    assert "username" in text and "valid email" in text and "at least 6" in text


def test_add_user_hashes_the_password_and_is_audited(users_page, app_db, boxes):
    from app.core.security import verify_password
    from app.models.db_models import User

    users_page.script.update(username="carol", email="carol@x", password="secret1",
                             role="researcher")
    users_page._add_user()
    _path, factory = app_db
    s = factory()
    u = s.query(User).filter_by(username="carol").one()
    assert u.password_hash != "secret1" and verify_password("secret1", u.password_hash)
    s.close()
    assert "carol" in _visible(users_page)
    created = _actions(factory, "user_created")
    assert created and created[0]["details"]["username"] == "carol"


def test_duplicate_username_is_refused(users_page, boxes):
    users_page.script.update(username="alice", email="other@x", password="secret1")
    users_page._add_user()
    assert boxes and boxes[-1][0] == "critical" and "unique" in boxes[-1][2]


def test_edit_user_records_what_changed(users_page, app_db, boxes):
    from app.models.db_models import User
    _path, factory = app_db
    s = factory()
    alice = s.query(User).filter_by(username="alice").one().id
    s.close()
    users_page.script.update(role="lab_admin", password="newpass1")
    users_page._edit_user(alice)
    changes = _actions(factory, "user_updated")[0]["details"]["changes"]
    assert changes["role"] == ["researcher", "lab_admin"]
    assert changes["password"] == "reset by admin"


def test_admin_cannot_disable_or_demote_themselves(users_page, app_db, boxes):
    users_page.script.update(active=False)
    users_page._edit_user(users_page.boss_id)
    assert boxes[-1][0] == "warning" and "your own account" in boxes[-1][2]
    from app.models.db_models import User
    s = app_db[1]()
    assert s.get(User, users_page.boss_id).active
    s.close()


# ── Audit trail ──────────────────────────────────────────────────────────────
@pytest.fixture
def audit_page(qtbot, app_db, boxes):
    from app.core import audit
    audit.record("login", user_id=1, username="boss", use_current_user=False)
    audit.record("login_failed", username="mallory", use_current_user=False)
    audit.record("run_ended", measurement_id=7, use_current_user=False,
                 details={"outcome": "error", "params": {"x": 1}})
    audit.record("user_updated", use_current_user=False,
                 details={"changes": {"role": ["researcher", "lab_admin"]}})
    from app.ui.pages.audit_page import AuditPage
    page = AuditPage(_admin(1))
    qtbot.addWidget(page)
    page.show()
    return page


def _shown(page):
    return [page._rows[i]["action"] for i in range(page.table.rowCount())
            if not page.table.isRowHidden(i)]


def test_audit_page_lists_entries_and_verifies_the_chain(audit_page):
    assert sorted(_shown(audit_page)) == ["login", "login_failed", "run_ended", "user_updated"]
    assert "intact" in audit_page.banner.text_lbl.text()
    row = next(i for i, r in enumerate(audit_page._rows) if r["action"] == "user_updated")
    assert "role: researcher → lab_admin" in audit_page.table.item(row, 5).text()


def test_audit_page_filters(audit_page):
    audit_page.chk_problems.setChecked(True)
    assert sorted(_shown(audit_page)) == ["login_failed", "run_ended"]
    audit_page.chk_problems.setChecked(False)
    audit_page.inp_filter.setText("mallory")
    assert _shown(audit_page) == ["login_failed"]


def test_audit_page_shows_entry_details(audit_page):
    row = next(i for i, r in enumerate(audit_page._rows) if r["action"] == "run_ended")
    audit_page.table.setCurrentCell(row, 0)
    audit_page._on_select()
    assert '"outcome": "error"' in audit_page.txt_details.toPlainText()


def test_audit_page_reports_a_broken_chain(audit_page, monkeypatch, boxes):
    from app.core import audit
    monkeypatch.setattr(audit, "verify_chain", lambda: {
        "ok": False, "count": 4, "first_bad_id": 3, "problem": "hash mismatch"})
    audit_page._verify()
    assert "FAILED at entry #3" in audit_page.banner.text_lbl.text()
    assert boxes[-1][0] == "critical"


def test_audit_page_manual_backup(audit_page, monkeypatch, boxes, tmp_path):
    from app.core import backup
    monkeypatch.setattr(backup, "backup_now", lambda db, tag: tmp_path / "te_backup.db")
    audit_page._backup_now()
    assert boxes[-1][0] == "information" and "te_backup.db" in boxes[-1][2]
    assert "db_backup" in _shown(audit_page)


# ── Sign-in ──────────────────────────────────────────────────────────────────
@pytest.fixture
def login(qtbot, app_db, monkeypatch):
    from datetime import datetime

    from app.core.security import hash_password
    from app.models.db_models import User
    from app.services import auth_service
    from app.ui import login_window, main_window

    _path, factory = app_db
    monkeypatch.setattr(auth_service, "SessionLocal", factory)
    s = factory()
    s.add(User(username="alice", email="a@x", password_hash=hash_password("secret1"),
               role="researcher", active=True, created_at=datetime.utcnow()))
    s.commit()
    s.close()

    opened = []

    class FakeMain:
        def __init__(self, user):
            opened.append(user)

        def show(self):
            pass

    monkeypatch.setattr(main_window, "MainWindow", FakeMain)
    monkeypatch.setattr(login_window.LoginWindow, "_warn_missing_prerequisites",
                        lambda self, parent: None)
    w = login_window.LoginWindow()
    qtbot.addWidget(w)
    w.opened = opened
    yield w
    auth_service._current_user = None


def test_login_needs_both_fields(login):
    login._on_login()
    assert "Enter both" in login.err_box.text_lbl.text() and not login.opened


def test_wrong_password_is_rejected_and_cleared(login, app_db):
    login.inp_username.setText("alice")
    login.inp_password.setText("wrong")
    login._on_login()
    assert "incorrect" in login.err_box.text_lbl.text()
    assert login.inp_password.text() == "" and login.btn_login.isEnabled()
    assert _actions(app_db[1], "login_failed")


def test_correct_password_opens_the_main_window(login, app_db):
    login.inp_username.setText("  alice ")
    login.inp_password.setText("secret1")
    login._on_login()
    assert [u.username for u in login.opened] == ["alice"]
    assert _actions(app_db[1], "login")


def test_password_can_be_revealed(login):
    from PyQt6.QtWidgets import QLineEdit
    login._toggle_reveal()
    assert login.inp_password.echoMode() == QLineEdit.EchoMode.Normal
    login._toggle_reveal()
    assert login.inp_password.echoMode() == QLineEdit.EchoMode.Password

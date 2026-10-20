"""Append-only audit trail.

A new ``audit_trail`` table (the web backend's unused ``audit_log`` table is
left alone). Triggers reject UPDATE and DELETE so entries cannot be changed
through the application or any SQL client that honours triggers; the hash
chain (see ``app.core.audit``) detects changes made by other means.

Note for future migrations: a batch-mode rebuild of this table would drop the
triggers. Recreate them with ``create_triggers(op)`` afterwards.
"""

import sqlalchemy as sa

REVISION = "0003"

_TRIGGERS = {
    "audit_trail_no_update":
        "CREATE TRIGGER audit_trail_no_update BEFORE UPDATE ON audit_trail "
        "BEGIN SELECT RAISE(ABORT, 'audit trail is append-only'); END",
    "audit_trail_no_delete":
        "CREATE TRIGGER audit_trail_no_delete BEFORE DELETE ON audit_trail "
        "BEGIN SELECT RAISE(ABORT, 'audit trail is append-only'); END",
}


def create_triggers(op) -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    for name, ddl in _TRIGGERS.items():
        if name not in existing:
            bind.exec_driver_sql(ddl)


def upgrade(op) -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("audit_trail"):
        op.create_table(
            "audit_trail",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("timestamp", sa.String(32), nullable=False),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("username", sa.String(50), nullable=True),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("measurement_id", sa.Integer, nullable=True),
            sa.Column("details", sa.Text, nullable=True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("prev_hash", sa.String(64), nullable=False),
            sa.Column("entry_hash", sa.String(64), nullable=False),
        )
        op.create_index("ix_audit_trail_timestamp", "audit_trail", ["timestamp"])
        op.create_index("ix_audit_trail_measurement_id", "audit_trail", ["measurement_id"])
    create_triggers(op)

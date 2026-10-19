"""Baseline: the schema as created by ``create_all`` before migrations existed.

Idempotent: creates only the tables that are missing, so it is safe both on a
fresh database and on an older, unversioned one.
"""

import sqlalchemy as sa

REVISION = "0001"


def upgrade(op) -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "labs" not in existing:
        op.create_table(
            "labs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("department", sa.String(100), nullable=True),
            sa.Column("contact_email", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("active", sa.Boolean, nullable=False),
        )
        op.create_index("ix_labs_id", "labs", ["id"])

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("email", sa.String(120), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(200), nullable=False),
            sa.Column("role", sa.Enum("super_admin", "lab_admin", "researcher",
                                      name="user_role"), nullable=False),
            sa.Column("lab_id", sa.Integer, sa.ForeignKey("labs.id"), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("last_login", sa.DateTime, nullable=True),
            sa.Column("active", sa.Boolean, nullable=False),
        )
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if "measurements" not in existing:
        op.create_table(
            "measurements",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("lab_id", sa.Integer, sa.ForeignKey("labs.id"), nullable=False),
            sa.Column("type", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("sample_id", sa.String(100), nullable=True),
            sa.Column("operator", sa.String(100), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("params_json", sa.Text, nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=False),
            sa.Column("finished_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_measurements_id", "measurements", ["id"])

    if "measurement_rows" not in existing:
        op.create_table(
            "measurement_rows",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("measurement_id", sa.Integer, sa.ForeignKey("measurements.id"),
                      nullable=False),
            sa.Column("seq", sa.Integer, nullable=False),
            sa.Column("elapsed_s", sa.Integer, nullable=True),
            sa.Column("data_json", sa.Text, nullable=False),
        )
        op.create_index("ix_measurement_rows_id", "measurement_rows", ["id"])

    if "measurement_integrity" not in existing:
        op.create_table(
            "measurement_integrity",
            sa.Column("measurement_id", sa.Integer, sa.ForeignKey("measurements.id"),
                      primary_key=True, nullable=False),
            sa.Column("data_hash", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )

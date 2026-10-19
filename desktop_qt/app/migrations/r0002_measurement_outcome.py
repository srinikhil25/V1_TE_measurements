"""Run outcome + runs by users without a lab.

* ``measurements.lab_id`` becomes nullable, so a user without a lab
  (super_admin) can save measurements instead of silently losing them.
* ``measurements.end_reason`` records why a run ended early
  (safety abort text, instrument error, operator stop, crash).
* Index on ``measurement_rows.measurement_id``: History loads rows by it.
"""

import sqlalchemy as sa

REVISION = "0002"


def upgrade(op) -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"]: c for c in insp.get_columns("measurements")}
    make_nullable = cols["lab_id"]["nullable"] is False
    add_reason = "end_reason" not in cols

    if make_nullable or add_reason:
        with op.batch_alter_table("measurements") as batch:
            if make_nullable:
                batch.alter_column("lab_id", existing_type=sa.Integer, nullable=True)
            if add_reason:
                batch.add_column(sa.Column("end_reason", sa.Text, nullable=True))

    idx = {i["name"] for i in insp.get_indexes("measurement_rows")}
    if "ix_measurement_rows_measurement_id" not in idx:
        op.create_index("ix_measurement_rows_measurement_id",
                        "measurement_rows", ["measurement_id"])

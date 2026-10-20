"""SQLAlchemy ORM models — identical schema to the web sidecar."""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import relationship

from ..core.database import Base


class Lab(Base):
    __tablename__ = "labs"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(100), nullable=False)
    department   = Column(String(100), nullable=True)
    contact_email = Column(String(120), nullable=True)
    created_at   = Column(DateTime, default=func.now(), nullable=False)
    active       = Column(Boolean, default=True, nullable=False)

    users        = relationship("User", back_populates="lab")
    measurements = relationship("Measurement", back_populates="lab")


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String(50), unique=True, nullable=False, index=True)
    email         = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role          = Column(
        Enum("super_admin", "lab_admin", "researcher", name="user_role"),
        nullable=False,
    )
    lab_id        = Column(Integer, ForeignKey("labs.id"), nullable=True)
    created_at    = Column(DateTime, default=func.now(), nullable=False)
    last_login    = Column(DateTime, nullable=True)
    active        = Column(Boolean, default=True, nullable=False)

    lab           = relationship("Lab", back_populates="users")
    measurements  = relationship("Measurement", back_populates="user")


class Measurement(Base):
    __tablename__ = "measurements"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Nullable: a super_admin (no lab) can still run and save measurements.
    lab_id      = Column(Integer, ForeignKey("labs.id"), nullable=True)
    type        = Column(String(30), nullable=False)   # seebeck | iv
    # running | finished | stopped | aborted | error | interrupted
    status      = Column(String(20), default="running")
    end_reason  = Column(Text, nullable=True)          # why the run ended early
    sample_id   = Column(String(100), nullable=True)
    operator    = Column(String(100), nullable=True)
    notes       = Column(Text, nullable=True)
    params_json = Column(Text, nullable=True)
    started_at  = Column(DateTime, default=func.now(), nullable=False)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="measurements")
    lab  = relationship("Lab",  back_populates="measurements")
    rows = relationship(
        "MeasurementRow", back_populates="measurement",
        cascade="all, delete-orphan",
    )


class MeasurementRow(Base):
    __tablename__ = "measurement_rows"

    id             = Column(Integer, primary_key=True, index=True)
    measurement_id = Column(Integer, ForeignKey("measurements.id"), nullable=False,
                            index=True)
    seq           = Column(Integer, nullable=False)
    elapsed_s      = Column(Integer, nullable=True)
    data_json      = Column(Text, nullable=False)

    measurement = relationship("Measurement", back_populates="rows")


class MeasurementIntegrity(Base):
    """Integrity meta-data for a measurement — SHA-256 hash of all data rows."""

    __tablename__ = "measurement_integrity"

    measurement_id = Column(
        Integer, ForeignKey("measurements.id"), primary_key=True, nullable=False
    )
    data_hash   = Column(String(128), nullable=False)
    created_at  = Column(DateTime, default=func.now(), nullable=False)


class AuditEntry(Base):
    """Append-only, hash-chained audit trail (ALCOA+).

    Rows are never updated or deleted (enforced by database triggers, see
    migration 0003). Each row's ``entry_hash`` covers its content plus the
    previous row's hash, so any later edit or removal breaks the chain and is
    detected by ``app.core.audit.verify_chain``.
    """

    __tablename__ = "audit_trail"

    id             = Column(Integer, primary_key=True)
    timestamp      = Column(String(32), nullable=False, index=True)  # ISO-8601 UTC
    user_id        = Column(Integer, nullable=True)   # no FK: the trail outlives accounts
    username       = Column(String(50), nullable=True)
    action         = Column(String(50), nullable=False)
    measurement_id = Column(Integer, nullable=True, index=True)
    details        = Column(Text, nullable=True)      # JSON
    reason         = Column(Text, nullable=True)
    prev_hash      = Column(String(64), nullable=False)
    entry_hash     = Column(String(64), nullable=False)

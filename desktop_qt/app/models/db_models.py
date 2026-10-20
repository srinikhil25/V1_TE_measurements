"""SQLAlchemy ORM models — identical schema to the web sidecar."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str]         = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]]   = mapped_column(String(100), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime, default=func.now(), nullable=False)
    active: Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="lab")
    measurements: Mapped[List["Measurement"]] = relationship("Measurement", back_populates="lab")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str]      = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str]         = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str]          = mapped_column(
        Enum("super_admin", "lab_admin", "researcher", name="user_role"),
        nullable=False,
    )
    lab_id: Mapped[Optional[int]]        = mapped_column(Integer, ForeignKey("labs.id"), nullable=True)
    created_at: Mapped[datetime]    = mapped_column(DateTime, default=func.now(), nullable=False)
    last_login: Mapped[Optional[datetime]]    = mapped_column(DateTime, nullable=True)
    active: Mapped[bool]        = mapped_column(Boolean, default=True, nullable=False)

    lab: Mapped[Optional["Lab"]] = relationship("Lab", back_populates="users")
    measurements: Mapped[List["Measurement"]] = relationship("Measurement", back_populates="user")


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int]          = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int]     = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Nullable: a super_admin (no lab) can still run and save measurements.
    lab_id: Mapped[Optional[int]]      = mapped_column(Integer, ForeignKey("labs.id"), nullable=True)
    type: Mapped[str]        = mapped_column(String(30), nullable=False)   # seebeck | iv
    # running | finished | stopped | aborted | error | interrupted
    status: Mapped[Optional[str]]      = mapped_column(String(20), default="running")
    end_reason: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)          # why the run ended early
    sample_id: Mapped[Optional[str]]   = mapped_column(String(100), nullable=True)
    operator: Mapped[Optional[str]]    = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]]       = mapped_column(Text, nullable=True)
    params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime]  = mapped_column(DateTime, default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="measurements")
    lab: Mapped[Optional["Lab"]] = relationship("Lab", back_populates="measurements")
    rows: Mapped[List["MeasurementRow"]] = relationship(
        "MeasurementRow", back_populates="measurement",
        cascade="all, delete-orphan",
    )


class MeasurementRow(Base):
    __tablename__ = "measurement_rows"

    id: Mapped[int]             = mapped_column(Integer, primary_key=True, index=True)
    measurement_id: Mapped[int] = mapped_column(Integer, ForeignKey("measurements.id"), nullable=False,
                            index=True)
    seq: Mapped[int]           = mapped_column(Integer, nullable=False)
    elapsed_s: Mapped[Optional[int]]      = mapped_column(Integer, nullable=True)
    data_json: Mapped[str]      = mapped_column(Text, nullable=False)

    measurement: Mapped["Measurement"] = relationship("Measurement", back_populates="rows")


class MeasurementIntegrity(Base):
    """Integrity meta-data for a measurement — SHA-256 hash of all data rows."""

    __tablename__ = "measurement_integrity"

    measurement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("measurements.id"), primary_key=True, nullable=False
    )
    data_hash: Mapped[str]   = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=func.now(), nullable=False)


class AuditEntry(Base):
    """Append-only, hash-chained audit trail (ALCOA+).

    Rows are never updated or deleted (enforced by database triggers, see
    migration 0003). Each row's ``entry_hash`` covers its content plus the
    previous row's hash, so any later edit or removal breaks the chain and is
    detected by ``app.core.audit.verify_chain``.
    """

    __tablename__ = "audit_trail"

    id: Mapped[int]             = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[str]      = mapped_column(String(32), nullable=False, index=True)  # ISO-8601 UTC
    user_id: Mapped[Optional[int]]        = mapped_column(Integer, nullable=True)   # no FK: the trail outlives accounts
    username: Mapped[Optional[str]]       = mapped_column(String(50), nullable=True)
    action: Mapped[str]         = mapped_column(String(50), nullable=False)
    measurement_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    details: Mapped[Optional[str]]        = mapped_column(Text, nullable=True)      # JSON
    reason: Mapped[Optional[str]]         = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str]      = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str]     = mapped_column(String(64), nullable=False)

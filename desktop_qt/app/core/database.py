"""SQLAlchemy engine, session factory, and database initialisation."""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .paths import get_db_path

logger = logging.getLogger(__name__)

DATABASE_URL = f"sqlite:///{get_db_path()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_session():
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    return SessionLocal()


def init_db() -> None:
    """Migrate the schema to the current revision and seed development accounts.

    Raises if the migration fails (the database is backed up first and left at
    its previous revision); the caller must not start the app on a half-known
    schema.
    """
    from ..migrations import upgrade_database
    from ..models import db_models  # noqa: F401 — registers models

    applied = upgrade_database(get_db_path())
    if applied:
        logger.info("Database schema migrated: %s", ", ".join(applied))
    _mark_interrupted_runs()
    _seed_dev_accounts()
    logger.info("Database ready at %s", get_db_path())


def _mark_interrupted_runs() -> None:
    """Runs still 'running' at startup were cut off by a crash or forced exit.

    Their rows up to the last saved point are kept; only the status changes so
    History does not show them as live.
    """
    from ..models.db_models import Measurement

    db = SessionLocal()
    try:
        orphans = db.query(Measurement).filter(Measurement.status == "running").all()
        for m in orphans:
            m.status = "interrupted"
            m.end_reason = m.end_reason or (
                "Application closed or crashed during the run; "
                "data up to the last saved point is kept.")
        if orphans:
            db.commit()
            logger.warning("Marked %d unfinished run(s) as interrupted: %s",
                           len(orphans), [m.id for m in orphans])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Development seed (idempotent — checks per username before inserting)
# ⚠  Remove or rotate these accounts before any shared deployment.
# ---------------------------------------------------------------------------

_DEV_ACCOUNTS = [
    {"username": "superadmin", "password": "superadmin",
     "email": "superadmin@te-lab.local", "role": "super_admin", "lab": None},
    {"username": "labadmin",   "password": "labadmin",
     "email": "labadmin@te-lab.local",   "role": "lab_admin",   "lab": "Ikeda-Hamasaki Laboratory"},
    {"username": "researcher", "password": "researcher",
     "email": "researcher@te-lab.local", "role": "researcher",  "lab": "Ikeda-Hamasaki Laboratory"},
]


def _seed_dev_accounts() -> None:
    from ..models.db_models import Lab, User
    from .security import hash_password

    db = SessionLocal()
    try:
        lab = db.query(Lab).filter_by(name="Ikeda-Hamasaki Laboratory").first()
        if lab is None:
            lab = Lab(
                name="Ikeda-Hamasaki Laboratory",
                department="Materials Science & Engineering",
                contact_email="te-lab@university.ac.jp",
                active=True,
            )
            db.add(lab)
            db.flush()

        created = []
        for acct in _DEV_ACCOUNTS:
            if db.query(User).filter_by(username=acct["username"]).first():
                continue
            user = User(
                username=acct["username"],
                email=acct["email"],
                password_hash=hash_password(acct["password"]),
                role=acct["role"],
                lab_id=lab.id if acct["lab"] else None,
                active=True,
            )
            db.add(user)
            created.append(acct)

        db.commit()
        if created:
            logger.warning("DEV accounts seeded: %s",
                           [a["username"] for a in created])
    finally:
        db.close()

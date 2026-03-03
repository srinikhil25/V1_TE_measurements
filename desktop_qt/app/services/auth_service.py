"""Authentication service — login, logout, current-user state."""

import logging
from datetime import datetime
from typing import Optional

from ..core.database import SessionLocal
from ..core.security import verify_password
from ..models.db_models import User

logger = logging.getLogger(__name__)

# Module-level session state (single-user desktop app)
_current_user: Optional[User] = None


def get_current_user() -> Optional[User]:
    return _current_user


def authenticate(username: str, password: str) -> Optional[User]:
    """Verify credentials and set the session user. Returns the User or None."""
    global _current_user
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=username.strip(), active=True).first()
        if user and verify_password(password, user.password_hash):
            user.last_login = datetime.utcnow()
            db.commit()
            db.refresh(user)
            # Detach from session so the object can be used outside the session
            db.expunge(user)
            _current_user = user
            logger.info("Login: %s (%s)", user.username, user.role)
            return user
        logger.warning("Failed login attempt for username: %r", username)
        return None
    finally:
        db.close()


def logout() -> None:
    global _current_user
    if _current_user:
        logger.info("Logout: %s", _current_user.username)
    _current_user = None


def has_role(*roles: str) -> bool:
    """Return True if the current user has one of the given roles."""
    user = get_current_user()
    return user is not None and user.role in roles


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    from ..core.security import hash_password
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id, active=True).first()
        if not user or not verify_password(old_password, user.password_hash):
            return False
        user.password_hash = hash_password(new_password)
        db.commit()
        return True
    finally:
        db.close()

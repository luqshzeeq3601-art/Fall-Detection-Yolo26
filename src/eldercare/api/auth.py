"""Password hashing and cookie-session helpers for operator accounts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from eldercare.db.models import User, UserSession

SESSION_COOKIE = "ec_session"
SESSION_TTL = timedelta(hours=12)
REMEMBER_TTL = timedelta(days=14)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    """Hash with scrypt and a random salt; the parameters are stored with the hash."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "$".join(
        (
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a ``hash_password`` value."""
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc(ts: datetime) -> datetime:
    """SQLite drops tzinfo; stored values are UTC."""
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def create_session(db: Session, user: User, remember: bool) -> tuple[str, timedelta]:
    """Persist a new session and return (raw token, lifetime)."""
    ttl = REMEMBER_TTL if remember else SESSION_TTL
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id, expires_at=now + ttl))
    db.commit()
    return token, ttl


def user_for_token(db: Session, token: str | None) -> User | None:
    """Return the user owning an unexpired session token, else None."""
    if not token:
        return None
    row = db.get(UserSession, _token_hash(token))
    if row is None or _utc(row.expires_at) < datetime.now(timezone.utc):
        return None
    return db.get(User, row.user_id)


def revoke_session(db: Session, token: str | None) -> None:
    """Delete the session for ``token`` if present."""
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    db.commit()


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))

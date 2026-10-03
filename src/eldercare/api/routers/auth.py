"""Operator accounts: sign-up, sign-in, sign-out, profile, password change, team list."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eldercare.api.auth import (
    SESSION_COOKIE,
    create_session,
    find_user_by_email,
    hash_password,
    revoke_session,
    verify_password,
)
from eldercare.api.dependencies import get_current_user, get_db
from eldercare.db.models import User

router = APIRouter(prefix="/auth", tags=["Auth"])

_EMAIL_MAX = 254


class LoginRateLimiter:
    """In-memory sliding-window rate limiter for failed authentication attempts."""

    def __init__(self, max_failures: int = 5, window_seconds: float = 60.0) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _client_key(self, request: Request, email: str) -> str:
        client_ip = request.client.host if request.client else "unknown"
        return f"{client_ip}:{email.strip().lower()}"

    def check(self, request: Request, email: str) -> None:
        key = self._client_key(request, email)
        now = time.monotonic()
        with self._lock:
            timestamps = self._failures.get(key, [])
            timestamps = [t for t in timestamps if now - t < self.window_seconds]
            self._failures[key] = timestamps
            if len(timestamps) >= self.max_failures:
                retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
                msg = (
                    f"Too many failed login attempts. Please try again in {max(1, retry_after)}s."
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=msg,
                    headers={"Retry-After": str(max(1, retry_after))},
                )

    def record_failure(self, request: Request, email: str) -> None:
        key = self._client_key(request, email)
        now = time.monotonic()
        with self._lock:
            timestamps = self._failures.get(key, [])
            timestamps = [t for t in timestamps if now - t < self.window_seconds]
            timestamps.append(now)
            self._failures[key] = timestamps

    def reset(self, request: Request, email: str) -> None:
        key = self._client_key(request, email)
        with self._lock:
            self._failures.pop(key, None)


login_rate_limiter = LoginRateLimiter()


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    local, _, domain = value.partition("@")
    if not local or "." not in domain or " " in value or len(value) > _EMAIL_MAX:
        raise ValueError("Enter a valid email address.")
    return value


def _check_password(value: str) -> str:
    if len(value) < 8 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must be at least 8 characters with a letter and a number.")
    return value


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization: str | None
    care_setting: str | None
    job_role: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: str
    password: str = Field(..., max_length=256)
    organization: str | None = Field(default=None, max_length=255)
    care_setting: Literal["home", "facility"] | None = None
    job_role: Literal["caregiver", "facility-admin"] | None = None

    model_config = ConfigDict(extra="forbid")

    _email = field_validator("email")(_normalize_email)
    _password = field_validator("password")(_check_password)


class SignInRequest(BaseModel):
    email: str = Field(..., max_length=_EMAIL_MAX)
    password: str = Field(..., max_length=256)
    remember: bool = False

    model_config = ConfigDict(extra="forbid")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)

    model_config = ConfigDict(extra="forbid")

    _password = field_validator("new_password")(_check_password)


def _cookie_secure(request: Request | None = None) -> bool:
    if os.getenv("ELDERCARE_COOKIE_SECURE", "false").strip().lower() == "true":
        return True
    if request is not None:
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            return True
    return False


def _set_cookie(
    response: Response, token: str, max_age: int | None, request: Request | None = None
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        path="/",
    )


def _require(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    return user


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def sign_up(
    payload: SignUpRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Create an account and sign it in. The first account becomes the admin."""
    if os.getenv("ELDERCARE_ALLOW_SIGNUP", "true").strip().lower() == "false":
        existing = db.scalar(select(func.count(User.id))) or 0
        if existing > 0:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-up is disabled on this server.")
    if find_user_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    is_first = (db.scalar(select(func.count(User.id))) or 0) == 0
    user = User(
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="admin" if is_first else "operator",
        organization=(payload.organization or "").strip() or None,
        care_setting=payload.care_setting,
        job_role=payload.job_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token, _ = create_session(db, user, remember=False)
    _set_cookie(response, token, None, request=request)
    return user


@router.post("/login", response_model=UserRead)
def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Verify credentials and set the session cookie."""
    login_rate_limiter.check(request, payload.email)
    user = find_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        login_rate_limiter.record_failure(request, payload.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    login_rate_limiter.reset(request, payload.email)
    token, ttl = create_session(db, user, remember=payload.remember)
    _set_cookie(
        response,
        token,
        int(ttl.total_seconds()) if payload.remember else None,
        request=request,
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, db: Annotated[Session, Depends(get_db)]) -> Response:
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserRead)
def current_user(user: Annotated[User | None, Depends(get_current_user)]) -> User:
    return _require(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user)],
) -> Response:
    account = _require(user)
    if not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    account.password_hash = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users", response_model=list[UserRead])
def list_team(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user)],
) -> list[User]:
    """Accounts on this server (visible to any signed-in operator)."""
    _require(user)
    return list(db.scalars(select(User).order_by(User.created_at)).all())

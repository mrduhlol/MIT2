"""Shared dependencies: DB session, auth, and helpers."""

import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import SessionRecord, User, utcnow
from .security import decode_token

bearer_scheme_note = "Authorization: Bearer <access-token>"


def func_lower(column):
    """Case-insensitive helper (SQLAlchemy func.lower)."""
    return sa_func.lower(column)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_payload(request: Request) -> dict[str, Any] | None:
    """Extract and decode the bearer token from the request, or None."""
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    return decode_token(token)


def load_user_and_session(db: Session, payload: dict[str, Any]) -> tuple[User, SessionRecord]:
    """Resolve the JWT payload to a live (user, session) pair, or raise 401."""
    user_id_raw = payload.get("sub")
    jti = payload.get("jti")
    if user_id_raw is None or jti is None:
        raise _unauthorized()
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise _unauthorized()

    session = db.query(SessionRecord).filter(SessionRecord.token_jti == jti).first()
    if session is None or session.revoked_at is not None:
        raise _unauthorized("Session revoked or unknown")
    now = utcnow()
    if session.expires_at is not None and session.expires_at < now:
        raise _unauthorized("Session expired")
    if session.user_id != user_id:
        raise _unauthorized()

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _unauthorized()

    # Opportunistically purge other expired session rows for this user.
    db.query(SessionRecord).filter(
        SessionRecord.user_id == user.id,
        SessionRecord.revoked_at.is_(None),
        SessionRecord.expires_at < now,
    ).update({SessionRecord.revoked_at: now}, synchronize_session=False)
    db.commit()

    return user, session


def get_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[User, dict[str, Any]]:
    """Return (user, token_payload) for authenticated endpoints."""
    payload = get_token_payload(request)
    if payload is None:
        raise _unauthorized()
    user, session = load_user_and_session(db, payload)
    return user, payload


def get_current_user(
    auth: tuple = Depends(get_auth),
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated User for protected endpoints."""
    user, _payload = auth
    db.refresh(user)
    return user


def new_request_id() -> str:
    return uuid.uuid4().hex

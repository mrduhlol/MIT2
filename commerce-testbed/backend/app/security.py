"""Password hashing and JWT helpers.

Passwords are always stored as bcrypt hashes -- never plaintext.  Access
tokens are JWTs (HS256) embedding sub (user id), a unique jti (used to track
and revoke server-side sessions) and an expiry.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import bcrypt

from .config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        # Preserve the original bcrypt 72-byte semantics for existing accounts.
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("ascii"))
    except Exception:
        return False


def create_access_token(
    user_id: int,
    *,
    expires_minutes: int | None = None,
    token_type: str = "access",
) -> tuple[str, str, datetime]:
    """Create a signed JWT. Returns (token, jti, exp_utc_naive)."""
    settings = get_settings()
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=minutes)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti,
        "iat": now,
        "exp": exp,
        "type": token_type,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    # Naive UTC to match how datetimes are stored in the DB.
    return token, jti, exp.replace(tzinfo=None)


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT. Returns the payload, or None if invalid/expired."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload

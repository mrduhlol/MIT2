"""Per-user API key management: create, list, revoke, rotate.

These endpoints use the regular session-JWT auth (``get_current_user``).
The keys they mint authenticate the ``/api/security/*`` AI SOC endpoints
instead (see app/routers/security.py).

Secrets are returned exactly once (create / rotate), never stored in
plaintext, and never logged — audit events only reference ``key_id``.
"""

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..api_keys import (
    VISIBLE_PREFIX_LENGTH,
    generate_key_id,
    generate_secret,
    hash_secret,
    key_scopes,
    key_status,
    to_naive_utc,
)
from ..audit import log_event
from ..database import get_db
from ..deps import get_current_user
from ..models import ApiKey, User, utcnow
from ..schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreate,
    ApiKeyListResponse,
    ApiKeyOut,
)

router = APIRouter()

# Default rotation lifetime: 365 days, or the remaining original duration.
ROTATE_DEFAULT_DAYS = 365


def _key_out(key: ApiKey) -> ApiKeyOut:
    """List-item shape for a key (never includes the hashed secret)."""
    return ApiKeyOut(
        id=key.id,
        key_id=key.key_id,
        name=key.name,
        environment=key.environment,
        scopes=key_scopes(key),
        visible_prefix=key.visible_prefix,
        status=key_status(key),
        created_at=key.created_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
    )


def _get_own_key(db: Session, user: User, key_id: int) -> ApiKey:
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.get("", response_model=ApiKeyListResponse)
def list_api_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyListResponse:
    """List the authenticated user's own API keys (owner-scoped)."""
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.id).all()
    return ApiKeyListResponse(items=[_key_out(k) for k in keys])


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Create a key and return the one-time plaintext secret."""
    expires_at = None
    if body.expires_at is not None:
        expires_at = to_naive_utc(body.expires_at)
        if expires_at <= utcnow():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at must be in the future",
            )

    secret = generate_secret(body.environment)
    key = ApiKey(
        user_id=user.id,
        key_id=generate_key_id(),
        name=body.name,
        environment=body.environment,
        scopes=json.dumps(body.scopes),
        visible_prefix=secret[:VISIBLE_PREFIX_LENGTH],
        hashed_secret=hash_secret(secret),
        expires_at=expires_at,
    )
    db.add(key)
    db.commit()

    # Audit references key_id only — the secret is never logged.
    log_event(
        db, request, "api_key_created",
        severity="low", pseudo_user=user.pseudo_id,
        details={"key_id": key.key_id, "environment": key.environment, "scopes": body.scopes},
    )
    return ApiKeyCreatedResponse(key=_key_out(key), secret=secret)


@router.delete("/{key_id}")
def revoke_api_key(
    key_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Revoke one of the user's own keys now (idempotent)."""
    key = _get_own_key(db, user, key_id)
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        db.commit()
        log_event(
            db, request, "api_key_revoked",
            severity="medium", pseudo_user=user.pseudo_id,
            details={"key_id": key.key_id},
        )
    # Repeated revoke is idempotent and still returns ok.
    return {"ok": True}


@router.post("/{key_id}/rotate", response_model=ApiKeyCreatedResponse,
             status_code=status.HTTP_201_CREATED)
def rotate_api_key(
    key_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Atomically revoke a key and replace it with a fresh secret.

    The new key keeps the same name, environment, and scopes. Lifetime is
    365 days when the old key had no expiry (or had already expired),
    otherwise the remaining original duration.
    """
    old_key = _get_own_key(db, user, key_id)
    if old_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate a revoked key",
        )

    now = utcnow()
    if old_key.expires_at is None or old_key.expires_at <= now:
        expires_at = now + timedelta(days=ROTATE_DEFAULT_DAYS)
    else:
        expires_at = now + (old_key.expires_at - now)

    secret = generate_secret(old_key.environment)
    new_key = ApiKey(
        user_id=user.id,
        key_id=generate_key_id(),
        name=old_key.name,
        environment=old_key.environment,
        scopes=old_key.scopes,
        visible_prefix=secret[:VISIBLE_PREFIX_LENGTH],
        hashed_secret=hash_secret(secret),
        expires_at=expires_at,
    )
    # Single transaction: revoke the old key while inserting the new one.
    old_key.revoked_at = now
    db.add(new_key)
    db.commit()

    log_event(
        db, request, "api_key_rotated",
        severity="low", pseudo_user=user.pseudo_id,
        details={"old_key_id": old_key.key_id, "new_key_id": new_key.key_id},
    )
    return ApiKeyCreatedResponse(key=_key_out(new_key), secret=secret)

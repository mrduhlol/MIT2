"""API-key generation, authentication, and rate limiting for external AI SOC
integrations.

Design notes:
  * Secrets are high-entropy random tokens (``secrets.token_urlsafe(24)``)
    prefixed with ``sk_test_`` (development) or ``sk_live_`` (production) and
    shown to the owner exactly once, in the create / rotate responses.
  * Only the SHA-256 hex digest of the full secret is stored. Because the
    secret is high-entropy, an unsalted fast hash is acceptable, and it allows
    exact-match lookup by hashing the presented key.
  * Rate limiting is a simple in-process sliding window — adequate for this
    single-process testbed; a production deployment would use Redis (or
    similar) with a distributed counter per key.
"""

import hashlib
import json
import secrets
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .audit import log_event
from .database import get_db
from .models import ApiKey, User, utcnow

# Least privilege: only explicitly selected scopes are granted, no admin scope.
SCOPES = [
    "security_events:read",
    "security_events:write",
    "incidents:read",
    "users:read",
]

ENVIRONMENT_PREFIXES = {"development": "sk_test_", "production": "sk_live_"}

VISIBLE_PREFIX_LENGTH = 14

# Per-key rate limits (requests per sliding window). Module-level constants so
# tests (or a config-driven deployment) can adjust them via monkeypatch /
# environment. Read limit applies to GETs, write limit to mutating methods.
RATE_LIMIT_READ = 120
RATE_LIMIT_WRITE = 30
RATE_WINDOW_SECONDS = 60.0

# Successful API-key usage is audited at most once every 5 minutes per key.
API_KEY_USED_LOG_INTERVAL_SECONDS = 300.0

# In-process state (per worker process; see Redis note above).
_last_used_log: dict[str, float] = {}
_rate_windows: dict[tuple[str, str], deque[float]] = {}


class RateLimitExceeded(Exception):
    """Raised when an API key exceeds its rate limit (handled in main.py)."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Render 429 responses with both a Retry-After header and body field."""
    return JSONResponse(
        {"detail": "Rate limit exceeded", "retry_after": exc.retry_after},
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(exc.retry_after)},
    )


# ------------------------------------------------------------------ helpers

def generate_key_id() -> str:
    """Public, non-secret identifier safe to display and audit-log."""
    return "key_" + secrets.token_hex(8)


def generate_secret(environment: str) -> str:
    """One-time plaintext secret for the given environment."""
    return ENVIRONMENT_PREFIXES[environment] + secrets.token_urlsafe(24)


def hash_secret(secret: str) -> str:
    """SHA-256 hex digest of a full secret (what we persist, never the secret)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(presented: str, hashed_secret: str) -> bool:
    """Constant-time comparison of a presented secret against a stored digest."""
    import hmac

    return hmac.compare_digest(hash_secret(presented), hashed_secret)


def parse_iso_utc(value: str) -> datetime | None:
    """Parse an ISO-8601 string into a naive UTC datetime (None on failure)."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize a (possibly tz-aware) datetime to naive UTC for storage."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def key_scopes(key: ApiKey) -> list[str]:
    """Decode the JSON-encoded scope list of a key."""
    try:
        return list(json.loads(key.scopes or "[]"))
    except Exception:
        return []


def key_status(key: ApiKey, now: datetime | None = None) -> str:
    """Computed lifecycle status: revoked > expired > active."""
    now = now or utcnow()
    if key.revoked_at is not None:
        return "revoked"
    if key.expires_at is not None and key.expires_at < now:
        return "expired"
    return "active"


class ApiKeyContext:
    """Request-scoped API-key auth context.

    ``presented_secret`` lives in memory for the duration of the request only
    (used to reject detail payloads that echo the caller's own key); it is
    never persisted or logged.
    """

    def __init__(self, key: ApiKey, user: User, presented_secret: str) -> None:
        self.key = key
        self.user = user
        self.presented_secret = presented_secret


# ---------------------------------------------------------------- auth deps

def _api_key_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_presented_secret(request: Request) -> str:
    """Pull the API-key secret from the request, or raise 401.

    Authorization: Bearer <secret> is preferred; X-API-Key is accepted as a
    fallback for clients that cannot set Authorization headers.
    """
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    api_key_header = (request.headers.get("x-api-key") or "").strip()
    if api_key_header:
        return api_key_header
    raise _api_key_error("API key required")


def get_api_key_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> ApiKeyContext:
    """Authenticate a request via API key (Bearer secret or X-API-Key).

    Failure semantics (distinct details for SOC documentation):
      missing/malformed header -> 401 "API key required"
      unknown/invalid key      -> 401 "Invalid API key"
      revoked key              -> 401 "API key revoked"
      expired key              -> 401 "API key expired"
      inactive owner           -> 401 "API key owner inactive"
    """
    secret = _extract_presented_secret(request)

    key = db.query(ApiKey).filter(ApiKey.hashed_secret == hash_secret(secret)).first()
    if key is None or not verify_secret(secret, key.hashed_secret):
        raise _api_key_error("Invalid API key")
    now = utcnow()
    if key.revoked_at is not None:
        raise _api_key_error("API key revoked")
    if key.expires_at is not None and key.expires_at < now:
        raise _api_key_error("API key expired")
    user = db.query(User).filter(User.id == key.user_id).first()
    if user is None or not user.is_active:
        raise _api_key_error("API key owner inactive")

    # Record usage on every successful authentication.
    key.last_used_at = now
    key.last_used_ip = request.client.host if request.client else None
    db.commit()

    _check_rate_limit(db, request, key, user)
    _maybe_log_key_used(db, request, key, user)
    return ApiKeyContext(key, user, secret)


def _maybe_log_key_used(db: Session, request: Request, key: ApiKey, user: User) -> None:
    """Audit successful API-key usage at most once per 5 minutes per key."""
    now_mono = time.monotonic()
    last = _last_used_log.get(key.key_id, 0.0)
    if now_mono - last >= API_KEY_USED_LOG_INTERVAL_SECONDS:
        _last_used_log[key.key_id] = now_mono
        try:
            log_event(
                db, request, "api_key_used",
                severity="low", pseudo_user=user.pseudo_id,
                details={"key_id": key.key_id},
            )
        except Exception:
            pass


# ------------------------------------------------------------ rate limiting

def _method_bucket(method: str) -> str:
    return "read" if method in ("GET", "HEAD", "OPTIONS") else "write"


def _check_rate_limit(db: Session, request: Request, key: ApiKey, user: User) -> None:
    """Sliding-window rate limit per key.

    Reads (GET): RATE_LIMIT_READ/min; writes (POST/PUT/PATCH/DELETE):
    RATE_LIMIT_WRITE/min. Exceeding either raises 429 with a Retry-After
    header and audits rate_limit_triggered. In-process only — production
    would use a shared store such as Redis.
    """
    bucket = _method_bucket(request.method)
    limit = RATE_LIMIT_READ if bucket == "read" else RATE_LIMIT_WRITE

    now_mono = time.monotonic()
    window = _rate_windows.setdefault((key.key_id, bucket), deque())
    while window and window[0] <= now_mono - RATE_WINDOW_SECONDS:
        window.popleft()

    if len(window) >= limit:
        if window:
            retry_after = max(1, int(RATE_WINDOW_SECONDS - (now_mono - window[0])))
        else:
            retry_after = int(RATE_WINDOW_SECONDS)
        try:
            log_event(
                db, request, "rate_limit_triggered",
                severity="medium", pseudo_user=user.pseudo_id,
                details={"key_id": key.key_id, "limit": limit},
            )
        except Exception:
            pass
        raise RateLimitExceeded(retry_after=retry_after)

    window.append(now_mono)


# ------------------------------------------------------------------ scopes

def require_scope(scope: str):
    """Dependency factory: API-key auth plus a required scope.

    Returns the ApiKeyContext when the key carries ``scope``; otherwise logs
    an access_denied audit event and raises 403.
    """

    def dependency(
        request: Request,
        ctx: ApiKeyContext = Depends(get_api_key_auth),
        db: Session = Depends(get_db),
    ) -> ApiKeyContext:
        if scope not in key_scopes(ctx.key):
            try:
                log_event(
                    db, request, "access_denied",
                    severity="medium",
                    pseudo_user=ctx.user.pseudo_id,
                    details={
                        "path": request.url.path,
                        "required_scope": scope,
                        "key_id": ctx.key.key_id,
                    },
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires '{scope}'",
            )
        return ctx

    return dependency

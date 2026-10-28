"""Authentication endpoints: register, login, logout."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import email_hash, log_event
from ..database import get_db
from ..deps import func_lower, get_auth
from ..models import SessionRecord, SecurityEvent, User, utcnow
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter()

SESSION_RECORD_DAYS = 30


def _json_details(raw: str | None) -> dict | None:
    import json

    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _count_recent_login_failures(db: Session, ehash: str, ip: str | None, minutes: int = 10) -> int:
    """Count login_failure events for one email hash within the window."""
    cutoff = (utcnow() - timedelta(minutes=minutes)).isoformat()
    events = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.event_type == "login_failure")
        .order_by(SecurityEvent.id.desc())
        .limit(500)
        .all()
    )
    count = 0
    for ev in events:
        if not ev.details or ehash not in ev.details:
            continue
        details = _json_details(ev.details) or {}
        if details.get("email_hash") == ehash and ev.ip == ip and ev.ts and ev.ts >= cutoff:
            count += 1
    return count


def _suspicious_already_logged(db: Session, ehash: str, minutes: int = 10) -> bool:
    cutoff = (utcnow() - timedelta(minutes=minutes)).isoformat()
    events = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.event_type == "suspicious_login_activity")
        .order_by(SecurityEvent.id.desc())
        .limit(100)
        .all()
    )
    for ev in events:
        if ev.details and ehash in ev.details and ev.ts and ev.ts >= cutoff:
            return True
    return False


def _create_session(db: Session, user: User, request: Request) -> tuple[str, SessionRecord]:
    token, jti, _exp = create_access_token(user.id)
    session = SessionRecord(
        user_id=user.id,
        token_jti=jti,
        expires_at=utcnow() + timedelta(days=SESSION_RECORD_DAYS),
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:180] or None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Create an account. Returns an access token plus the new user."""
    existing = (
        db.query(User)
        .filter(func_lower(User.email) == str(body.email).lower())
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=str(body.email).lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        pseudo_id=uuid.uuid4().hex,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, _ = _create_session(db, user, request)

    log_event(
        db, request, "account_created",
        pseudo_user=user.pseudo_id,
        details={"registered": True},
    )
    # A session record was also created for the fresh account.
    log_event(
        db, request, "session_created",
        pseudo_user=user.pseudo_id,
        details={"reason": "registration"},
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Login with email + password. Returns an access token and user."""
    user = (
        db.query(User)
        .filter(func_lower(User.email) == str(body.email).lower())
        .first()
    )
    ehash = email_hash(str(body.email))

    if user is None or not verify_password(body.password, user.hashed_password):
        reason = "unknown_email" if user is None else "invalid_credentials"
        log_event(
            db, request, "login_failure",
            severity="low",
            pseudo_user=user.pseudo_id if user else None,
            details={"reason": reason, "email_hash": ehash},
        )

        # Credential-stuffing style detection: >= 5 failures for the same
        # email hash from the same IP within 10 minutes.
        ip = request.client.host if request.client else None
        if _count_recent_login_failures(db, ehash, ip) + 1 >= 5:
            if not _suspicious_already_logged(db, ehash):
                log_event(
                    db, request, "suspicious_login_activity",
                    severity="high",
                    pseudo_user=user.pseudo_id if user else None,
                    details={"email_hash": ehash, "ip": ip,
                             "window_minutes": 10, "failures": 5},
                )
        # Do not reveal whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        log_event(
            db, request, "login_failure",
            severity="medium",
            pseudo_user=user.pseudo_id,
            details={"reason": "account_disabled", "email_hash": ehash},
        )
        raise HTTPException(status_code=401, detail="Account is disabled")

    token, _ = _create_session(db, user, request)
    log_event(
        db, request, "login_success",
        pseudo_user=user.pseudo_id,
        details={"email_hash": ehash},
    )
    log_event(
        db, request, "session_created",
        pseudo_user=user.pseudo_id,
        details={"reason": "login"},
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(
    request: Request,
    auth: tuple = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Revoke the current session."""
    user, payload = auth
    jti = payload.get("jti")
    session = db.query(SessionRecord).filter(SessionRecord.token_jti == jti).first()
    if session and session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()
    log_event(
        db, request, "session_revoked",
        pseudo_user=user.pseudo_id,
        details={"reason": "logout"},
    )
    return {"ok": True}

"""User profile, addresses, sessions, and password management."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_event
from ..database import get_db
from ..deps import get_auth, get_current_user
from ..models import Address, SessionRecord, User, utcnow
from ..schemas import (
    AddressIn,
    AddressOut,
    PasswordChange,
    ProfileUpdate,
    SessionOut,
    UserOut,
)
from ..security import hash_password, verify_password

router = APIRouter()


# ---------- Profile ----------

@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


def _current_user_dep(auth: tuple = Depends(get_auth)) -> User:
    user, _payload = auth
    return user


@router.put("/me", response_model=UserOut)
def update_me(
    body: ProfileUpdate,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's profile (full_name and/or phone)."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided")
    for key, value in fields.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    log_event(db, request, "profile_updated", pseudo_user=user.pseudo_id)
    return user


@router.put("/me/password")
def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    """Change the password; requires the current password."""
    if not verify_password(body.current_password, user.hashed_password):
        log_event(
            db, request, "password_change_failed",
            severity="medium", pseudo_user=user.pseudo_id,
            details={"reason": "invalid_current_password"},
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    log_event(
        db, request, "password_changed",
        severity="medium", pseudo_user=user.pseudo_id,
    )
    return {"ok": True}


# ---------- Addresses ----------

def _unset_other_defaults(db: Session, user: User, keep_id: int | None = None) -> None:
    q = db.query(Address).filter(Address.user_id == user.id, Address.is_default.is_(True))
    if keep_id is not None:
        q = q.filter(Address.id != keep_id)
    for addr in q.all():
        addr.is_default = False


@router.get("/me/addresses", response_model=list[AddressOut])
def list_addresses(user: User = Depends(_current_user_dep), db: Session = Depends(get_db)):
    return (
        db.query(Address)
        .filter(Address.user_id == user.id)
        .order_by(Address.id)
        .all()
    )


def _apply_default_flag(db: Session, user: User, addr: Address, want_default: bool) -> None:
    has_any_default = db.query(Address).filter(
        Address.user_id == user.id, Address.is_default.is_(True)
    ).count() > 0
    if want_default or not has_any_default:
        _unset_other_defaults(db, user, keep_id=addr.id)
        addr.is_default = True


@router.post("/me/addresses", response_model=AddressOut, status_code=201)
def create_address(
    body: AddressIn,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    addr = Address(user_id=user.id, **body.model_dump())
    db.add(addr)
    db.flush()
    _apply_default_flag(db, user, addr, body.is_default)
    db.commit()
    db.refresh(addr)
    log_event(
        db, request, "address_changed",
        pseudo_user=user.pseudo_id,
        details={"action": "created", "address_id": addr.id},
    )
    return addr


def _get_owned_address(db: Session, user: User, address_id: int) -> Address:
    addr = (
        db.query(Address)
        .filter(Address.id == address_id, Address.user_id == user.id)
        .first()
    )
    if addr is None:
        raise HTTPException(status_code=404, detail="Address not found")
    return addr


@router.put("/me/addresses/{address_id}", response_model=AddressOut)
def update_address(
    address_id: int,
    body: AddressIn,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    addr = _get_owned_address(db, user, address_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(addr, key, value)
    if body.is_default:
        _unset_other_defaults(db, user, keep_id=addr.id)
        addr.is_default = True
    db.commit()
    db.refresh(addr)
    log_event(
        db, request, "address_changed",
        pseudo_user=user.pseudo_id,
        details={"action": "updated", "address_id": addr.id},
    )
    return addr


@router.delete("/me/addresses/{address_id}")
def delete_address(
    address_id: int,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    addr = _get_owned_address(db, user, address_id)
    was_default = addr.is_default
    db.delete(addr)
    db.commit()
    if was_default:
        remaining = (
            db.query(Address)
            .filter(Address.user_id == user.id)
            .order_by(Address.id)
            .first()
        )
        if remaining:
            remaining.is_default = True
            db.commit()
    log_event(
        db, request, "address_changed",
        pseudo_user=user.pseudo_id,
        details={"action": "deleted", "address_id": address_id},
    )
    return {"ok": True}


# ---------- Sessions ----------

def _session_out(s: SessionRecord) -> SessionOut:
    return SessionOut(
        id=s.id,
        created_at=s.created_at,
        expires_at=s.expires_at,
        revoked=s.revoked_at is not None,
        ip=s.ip,
        user_agent=s.user_agent,
    )


@router.get("/me/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(_current_user_dep), db: Session = Depends(get_db)):
    sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.user_id == user.id)
        .order_by(SessionRecord.id.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


@router.delete("/me/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    user: User = Depends(_current_user_dep),
    db: Session = Depends(get_db),
):
    session = (
        db.query(SessionRecord)
        .filter(SessionRecord.id == session_id, SessionRecord.user_id == user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()
    log_event(
        db, request, "session_revoked",
        pseudo_user=user.pseudo_id,
        details={"session_id": session.id},
    )
    return {"ok": True}

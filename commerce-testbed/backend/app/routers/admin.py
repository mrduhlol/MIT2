"""Role-protected operational dashboards. Secrets never enter these responses."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..audit import log_event
from ..database import get_db
from ..deps import get_current_user
from ..models import AdminRole, ApiKey, CartItem, Order, Product, SecurityEvent, SessionRecord, User, utcnow


def require_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if db.get(AdminRole, user.id) is None:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


router = APIRouter(dependencies=[Depends(require_admin)])

# Explicit response allowlists prevent accidental disclosure when models change.
RESOURCES = {
    "users": (User, ("id", "email", "full_name", "is_active", "is_admin", "created_at")),
    "products": (Product, ("id", "name", "category", "price_cents", "stock")),
    "orders": (Order, ("id", "user_id", "status", "total_cents", "created_at")),
    "sessions": (SessionRecord, ("id", "user_id", "created_at", "expires_at", "revoked_at")),
    "api-keys": (ApiKey, ("id", "user_id", "name", "environment", "visible_prefix", "created_at", "last_used_at", "expires_at", "revoked_at")),
    "events": (SecurityEvent, ("id", "ts", "event_type", "source", "severity", "pseudo_user", "request_id")),
}


@router.get("/overview")
def overview(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model))
    log_event(db, request, "admin_dashboard_viewed", pseudo_user=admin.pseudo_id)
    return {
        "updated_at": utcnow(),
        "users": count(User), "products": count(Product), "orders": count(Order),
        "cart_items": count(CartItem), "api_keys": count(ApiKey), "security_events": count(SecurityEvent),
        "active_sessions": db.scalar(select(func.count()).select_from(SessionRecord).where(
            SessionRecord.revoked_at.is_(None), SessionRecord.expires_at > utcnow())),
        "order_value_cents": db.scalar(select(func.coalesce(func.sum(Order.total_cents), 0))),
        "high_severity_events": db.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.severity == "high")),
        "database": db.get_bind().dialect.name,
        "service": "commerce-testbed", "status": "ok",
    }


@router.get("/records/{resource}")
def records(resource: str, request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
            q: str = Query("", max_length=100), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if resource not in RESOURCES:
        raise HTTPException(404, "Unknown dashboard")
    model, columns = RESOURCES[resource]
    query = db.query(model)
    if model is User:
        query = query.options(selectinload(User.admin_role))
    if q:
        searchable = [getattr(model, name) for name in ("email", "full_name", "name", "status", "event_type", "source", "severity", "pseudo_user") if hasattr(model, name)]
        searchable.extend(cast(getattr(model, name), String) for name in ("id", "user_id") if hasattr(model, name))
        if searchable:
            query = query.filter(or_(*(column.ilike(f"%{q}%") for column in searchable)))
    total = query.count()
    rows = query.order_by(model.id.desc()).offset(offset).limit(limit).all()
    items = [{name: getattr(row, name) for name in columns} for row in rows]
    log_event(db, request, "admin_records_viewed", pseudo_user=admin.pseudo_id, details={"resource": resource})
    return {"items": items, "total": total, "limit": limit, "offset": offset, "columns": columns}


class UserStatus(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserStatus, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if db.get(AdminRole, user_id) is not None:
        raise HTTPException(403, "Administrator accounts cannot be disabled here")
    target.is_active = body.is_active
    if not body.is_active:
        db.query(SessionRecord).filter(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None)).update({"revoked_at": utcnow()})
    db.commit()
    log_event(db, request, "admin_user_status_changed", pseudo_user=admin.pseudo_id,
              details={"target_pseudo": target.pseudo_id, "is_active": body.is_active})
    return {"ok": True}


@router.post("/sessions/{session_id}/revoke")
def revoke_session(session_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    session = db.get(SessionRecord, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()
    log_event(db, request, "admin_session_revoked", pseudo_user=admin.pseudo_id, details={"session_id": session_id})
    return {"ok": True}


@router.post("/api-keys/{key_id}/revoke")
def revoke_key(key_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(404, "API key not found")
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        db.commit()
    log_event(db, request, "admin_api_key_revoked", pseudo_user=admin.pseudo_id, details={"key_id": key.key_id})
    return {"ok": True}

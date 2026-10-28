"""AI SOC integration endpoints, authenticated with per-user API keys.

These endpoints coexist with the legacy shared-agent-key feed at
``GET /api/events/feed`` (X-Agent-Key), which remains untouched.

Unlike the shared agent key, API keys are issued per user and carry least-
privilege scopes. This testbed is a deployment the key owner controls, so a
key with ``security_events:read`` authorizes reading the app's full event
stream (app + synthetic + external rows).
"""

import hashlib
import json
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..api_keys import ApiKeyContext, get_api_key_auth, parse_iso_utc, require_scope
from ..audit import log_event
from ..database import get_db
from ..models import Order, SecurityEvent, SessionRecord, User, utcnow
from ..schemas import EventOut, SecurityEventIn, SecurityEventsResponse

router = APIRouter()

# detail keys that must never appear in externally submitted events
FORBIDDEN_DETAIL_KEYS = {
    "password", "token", "secret", "session_token", "authorization",
    "hashed_password", "hashed_secret", "api_key", "secret_key",
}

MAX_DETAIL_KEYS = 20
MAX_DETAIL_JSON_CHARS = 4096

# Credential stuffing synthesis: >= N login_failure events within the window
# for the same IP.
STUFFING_WINDOW = timedelta(minutes=10)
STUFFING_THRESHOLD = 5


def _event_out(row: SecurityEvent) -> EventOut:
    """Same event JSON shape as the feed's EventOut."""
    details: dict[str, Any] | str | None = None
    if row.details:
        try:
            details = json.loads(row.details)
        except Exception:
            details = row.details
    return EventOut(
        ts=row.ts,
        request_id=row.request_id,
        source=row.source,
        event_type=row.event_type,
        severity=row.severity,
        pseudo_user=row.pseudo_user,
        ip=row.ip,
        user_agent=row.user_agent,
        details=details,
    )


# ------------------------------------------------------------------- ping

@router.get("/ping")
def ping(ctx: ApiKeyContext = Depends(get_api_key_auth)) -> dict:
    """Connection-test endpoint: any valid API key, no scope required."""
    return {
        "authenticated": True,
        "key_name": ctx.key.name,
        "key_id": ctx.key.key_id,
        "environment": ctx.key.environment,
        "scopes": json.loads(ctx.key.scopes or "[]"),
        "user_pseudo": ctx.user.pseudo_id,
    }


# ----------------------------------------------------------------- events

@router.get("/events", response_model=SecurityEventsResponse)
def list_events(
    ctx: ApiKeyContext = Depends(require_scope("security_events:read")),
    db: Session = Depends(get_db),
    since: str | None = None,
    until: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    severity: str | None = Query(default=None, pattern="^(low|medium|high)$"),
    source: str = Query(default="all", pattern="^(app|synthetic|external|all)$"),
    event_type: str | None = None,
) -> SecurityEventsResponse:
    """Read the app's security event stream, newest first.

    This testbed is a deployment the key owner controls, so the key
    authorizes reading the full event stream (no per-source restrictions
    beyond the optional ``source`` filter).
    """
    since_dt = parse_iso_utc(since) if since else None
    until_dt = parse_iso_utc(until) if until else None

    query = db.query(SecurityEvent)
    if source and source != "all":
        query = query.filter(SecurityEvent.source == source)
    if severity:
        query = query.filter(SecurityEvent.severity == severity)
    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    rows = query.order_by(SecurityEvent.id.desc()).all()

    items: list[EventOut] = []
    for row in rows:
        row_dt = parse_iso_utc(row.ts)
        if since_dt is not None and (row_dt is None or row_dt < since_dt):
            continue
        if until_dt is not None and (row_dt is None or row_dt > until_dt):
            continue
        items.append(_event_out(row))

    total = len(items)
    return SecurityEventsResponse(
        items=items[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/events")
def ingest_event(
    body: SecurityEventIn,
    request: Request,
    ctx: ApiKeyContext = Depends(require_scope("security_events:write")),
    db: Session = Depends(get_db),
) -> dict:
    """Ingest an external security event (anti-spoofing enforced).

    ``source`` is always forced to ``"external"``; the stored ``ts`` is the
    server time. If the client supplies ``ts``, it is accepted and preserved
    under ``details["client_ts"]``. The presented key secret must never show
    up in (or anywhere near) the payload.
    """
    details: dict[str, Any] = dict(body.details or {})

    # Reject payloads echoing the presented secret or the raw header value.
    serialized = json.dumps(details, default=str)
    auth_header = request.headers.get("authorization") or ""
    if ctx.presented_secret and ctx.presented_secret in serialized:
        raise HTTPException(
            status_code=422,
            detail="Details must not contain the presented API key secret",
        )
    if auth_header and auth_header in serialized:
        raise HTTPException(
            status_code=422,
            detail="Details must not contain the raw Authorization header",
        )

    # Reject sensitive detail keys (case-insensitive).
    lowered = {str(k).lower() for k in details}
    hits = sorted(lowered & FORBIDDEN_DETAIL_KEYS)
    if hits:
        raise HTTPException(
            status_code=422,
            detail=f"Details must not contain sensitive keys: {', '.join(hits)}",
        )

    # Accept an optional client timestamp into metadata; server ts is now.
    if body.ts is not None:
        if parse_iso_utc(body.ts) is None:
            raise HTTPException(status_code=422, detail="Invalid ISO ts")
        details["client_ts"] = body.ts

    if len(details) > MAX_DETAIL_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Details must have at most {MAX_DETAIL_KEYS} keys",
        )
    serialized = json.dumps(details, default=str) if details else ""
    if len(serialized) > MAX_DETAIL_JSON_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Details JSON must be at most {MAX_DETAIL_JSON_CHARS} characters",
        )

    event = log_event(
        db, request, body.event_type,
        severity=body.severity,
        pseudo_user=body.pseudo_user,
        details=details or None,
        source="external",  # client-supplied source values are never trusted
    )
    return {
        "id": event.id,
        "ts": event.ts,
        "event_type": event.event_type,
        "source": event.source,
        "severity": event.severity,
        "status": "accepted",
    }


# -------------------------------------------------------------- incidents

def _incident_id(seed: str) -> str:
    return "inc_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


@router.get("/incidents")
def list_incidents(
    ctx: ApiKeyContext = Depends(require_scope("incidents:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Derived, read-only incident view (no new tables, no fabrication).

    Two simple heuristics over existing SecurityEvent rows:
      * every group of high-severity events sharing event_type + ip;
      * one "Possible credential stuffing" incident per IP with >= 5
        ``login_failure`` events inside a 10-minute window.
    """
    rows = db.query(SecurityEvent).order_by(SecurityEvent.id).all()

    incidents: list[dict[str, Any]] = []

    # High-severity groups by (event_type, ip).
    groups: dict[tuple[str, str | None], list[SecurityEvent]] = {}
    for row in rows:
        if row.severity == "high":
            groups.setdefault((row.event_type, row.ip), []).append(row)
    for (event_type, ip), group in groups.items():
        group.sort(key=lambda r: r.id)
        incidents.append({
            "id": _incident_id(f"{event_type}|{ip}"),
            "title": f"High-severity {event_type}" + (f" from {ip}" if ip else ""),
            "severity": "high",
            "first_seen": group[0].ts,
            "last_seen": group[-1].ts,
            "event_count": len(group),
            "sources": sorted({r.source for r in group}),
            "sample_events": [_event_out(r) for r in group[:5]],
        })

    # Credential stuffing synthesis per IP (simple O(n^2) sliding window).
    by_ip: dict[str, list[tuple[SecurityEvent, Any]]] = {}
    for row in rows:
        if row.event_type == "login_failure" and row.ip:
            row_dt = parse_iso_utc(row.ts)
            if row_dt is not None:
                by_ip.setdefault(row.ip, []).append((row, row_dt))
    for ip, parsed in by_ip.items():
        parsed.sort(key=lambda pair: pair[1])
        qualifying = None
        for i in range(len(parsed)):
            for j in range(i, len(parsed)):
                if parsed[j][1] - parsed[i][1] > STUFFING_WINDOW:
                    break
                if j - i + 1 >= STUFFING_THRESHOLD:
                    qualifying = (i, j)
                    break
            if qualifying:
                break
        if qualifying:
            i, j = qualifying
            window = parsed[i : j + 1]
            incidents.append({
                "id": _incident_id(f"stuffing|{ip}"),
                "title": "Possible credential stuffing",
                "severity": "high",
                "first_seen": window[0][0].ts,
                "last_seen": window[-1][0].ts,
                "event_count": len(window),
                "sources": sorted({r.source for r, _ in window}),
                "sample_events": [_event_out(r) for r, _ in window[:5]],
            })

    incidents.sort(key=lambda inc: inc["last_seen"], reverse=True)
    return incidents


# ------------------------------------------------------------------ users

@router.get("/users")
def list_users(
    ctx: ApiKeyContext = Depends(require_scope("users:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Pseudonymous account metadata only — NO PII.

    Never returns emails, phone numbers, names, or token material; accounts
    are referenced exclusively by their random ``pseudo_id``.
    """
    now = utcnow()
    users = db.query(User).order_by(User.created_at, User.id).all()
    out = []
    for u in users:
        order_count = (
            db.query(sa_func.count(Order.id)).filter(Order.user_id == u.id).scalar() or 0
        )
        session_count = (
            db.query(sa_func.count(SessionRecord.id))
            .filter(SessionRecord.user_id == u.id)
            .scalar() or 0
        )
        active_session_count = (
            db.query(sa_func.count(SessionRecord.id))
            .filter(
                SessionRecord.user_id == u.id,
                SessionRecord.revoked_at.is_(None),
                SessionRecord.expires_at > now,
            )
            .scalar() or 0
        )
        out.append({
            "pseudo_id": u.pseudo_id,
            "created_at": u.created_at,
            "account_status": "active" if u.is_active else "inactive",
            "order_count": int(order_count),
            "session_count": int(session_count),
            "active_session_count": int(active_session_count),
        })
    return out

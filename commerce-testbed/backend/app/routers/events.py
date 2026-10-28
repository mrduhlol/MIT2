"""Security event feed for the external AI cyber defense agent.

This is NOT regular-user auth: it uses a shared API key.

    GET /api/events/feed?since=<ISO-8601>&limit=<int>&source=<app|synthetic>&severity=<low|medium|high>

Auth via the X-Agent-Key header (matching AGENT_API_KEY) or, for
convenience, an ``api_key`` query parameter. Missing key -> 401,
wrong key -> 403.

Responses are ordered oldest -> newest, filtered to rows with ts >= since
(if given), and capped at ``limit`` (default 200, max 1000).
"""

import json
import time as _time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_event
from ..config import get_settings
from ..database import get_db
from ..models import SecurityEvent
from ..schemas import EventOut, FeedResponse

router = APIRouter()

# Simple per-process throttle so successful agent access is logged at most
# once every 5 minutes.
_last_event_feed_log: dict[str, float] = {"ts": 0.0}
EVENT_FEED_LOG_INTERVAL_SECONDS = 300


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_event_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    dt = _parse_iso(raw)
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return dt.astimezone(timezone.utc)


def _maybe_log_agent_access(db: Session, request: Request) -> None:
    now = _time.monotonic()
    if now - _last_event_feed_log["ts"] >= EVENT_FEED_LOG_INTERVAL_SECONDS:
        _last_event_feed_log["ts"] = now
        log_event(
            db, request, "event_feed_access",
            severity="low", pseudo_user=None,
            details={"agent": True},
        )


@router.get("/feed", response_model=FeedResponse)
def events_feed(
    request: Request,
    since: str | None = None,
    limit: int = 200,
    source: str | None = None,
    severity: str | None = None,
    api_key: str | None = None,
    db: Session = Depends(get_db),
):
    """Feed of security events for the AI defense agent (agent-key auth)."""
    settings = get_settings()
    key = request.headers.get("x-agent-key") or api_key
    if not key:
        raise HTTPException(status_code=401, detail="Agent key required")
    if key != settings.AGENT_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid agent key")

    _maybe_log_agent_access(db, request)

    limit = max(1, min(limit, 1000))

    since_dt = _parse_iso(since) if since else None

    query = db.query(SecurityEvent)
    if source:
        query = query.filter(SecurityEvent.source == source)
    if severity:
        query = query.filter(SecurityEvent.severity == severity)

    rows = query.order_by(SecurityEvent.id).all()

    events: list[EventOut] = []
    for row in rows:
        if since_dt is not None:
            row_dt = _parse_event_ts(row.ts)
            if row_dt is None or row_dt < since_dt:
                continue
        details: dict[str, Any] | str | None = None
        if row.details:
            try:
                details = json.loads(row.details)
            except Exception:
                details = row.details
        events.append(
            EventOut(
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
        )
        if len(events) >= limit:
            break

    return FeedResponse(events=events)

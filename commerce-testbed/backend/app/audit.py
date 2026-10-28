"""Audit / security event logging.

Rules:
  * NEVER log passwords, tokens, or raw emails.
  * Users are referenced by their pseudo_id (assigned at registration).
  * Failed logins for unknown accounts log a sha256 email hash prefix (first
    12 hex chars) under details["email_hash"] instead of the raw email.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import SecurityEvent

USER_AGENT_MAX = 180


def email_hash(email: str) -> str:
    import hashlib

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


def log_event(
    db: Session,
    request: Request | None,
    event_type: str,
    *,
    severity: str = "low",
    pseudo_user: str | None = None,
    details: dict[str, Any] | None = None,
    source: str = "app",
) -> SecurityEvent:
    """Persist a security event row and commit it."""
    request_id = getattr(getattr(request, "state", None), "request_id", None) or uuid.uuid4().hex

    ip = None
    user_agent = None
    if request is not None:
        if request.client is not None:
            ip = request.client.host
        user_agent = (request.headers.get("user-agent") or "")[:USER_AGENT_MAX] or None

    event = SecurityEvent(
        ts=datetime.now(timezone.utc).isoformat(),
        request_id=request_id,
        source=source,
        event_type=event_type,
        severity=severity,
        pseudo_user=pseudo_user,
        ip=ip,
        user_agent=user_agent,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(event)
    db.commit()
    return event

import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .audit import log_event
from .database import SessionLocal


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request_id to every request (available in request.state
    and echoed back in the X-Request-ID response header)."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


def log_access_denied(request: Request) -> None:
    """Log an access_denied event for a 401/403 response. Fails silently —
    logging must never break the API response."""
    try:
        db = SessionLocal()
        try:
            log_event(
                db,
                request,
                "access_denied",
                severity="medium",
                pseudo_user=None,
                details={"path": request.url.path},
            )
        finally:
            db.close()
    except Exception:
        pass


def access_denied_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI/Starlette HTTPException handler for the whole app: 401/403
    responses on protected endpoints are recorded as access_denied events."""
    if getattr(exc, "status_code", None) in (401, 403):
        log_access_denied(request)
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=headers,
    )

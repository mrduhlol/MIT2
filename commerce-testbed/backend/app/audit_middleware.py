import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .audit import log_event
from .database import SessionLocal


class RequestIDMiddleware:
    """Attach request IDs without creating background ASGI tasks."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


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

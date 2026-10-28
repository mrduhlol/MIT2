"""FastAPI application factory for the commerce-testbed backend."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api_keys import RateLimitExceeded, rate_limit_exception_handler
from .audit_middleware import RequestIDMiddleware, access_denied_exception_handler
from .config import Settings, get_settings, reset_request_settings, set_request_settings
from .database import (
    bind_hyperdrive,
    ensure_db_initialized,
    init_db,
    is_worker_mode,
    reset_hyperdrive,
)
from .routers import admin, auth, cart, events, orders, products, users
from .routers import api_keys as api_keys_router
from .routers import security as security_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not is_worker_mode():
        init_db()
    yield


app = FastAPI(
    title="commerce-testbed",
    description=(
        "Intentionally-instrumented fake e-commerce test environment for an "
        "AI Cyber Defense Agent hackathon. Synthetic activity can be "
        "generated with scripts/simulate.py."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)


if is_worker_mode():
    from starlette.types import ASGIApp, Receive, Scope, Send

    class WorkerBindingsMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            env = scope["env"]
            settings_token = set_request_settings(
                Settings(
                    SECRET_KEY=env.SECRET_KEY,
                    AGENT_API_KEY=env.AGENT_API_KEY,
                    DATABASE_URL="hyperdrive",
                    CORS_ORIGINS="",
                )
            )
            database_token = bind_hyperdrive(env.HYPERDRIVE)
            try:
                ensure_db_initialized()
                await self.app(scope, receive, send)
            finally:
                reset_hyperdrive(database_token)
                reset_request_settings(settings_token)

    app.add_middleware(WorkerBindingsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in get_settings().CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

exception_handlers = app.exception_handlers
exception_handlers[StarletteHTTPException] = access_denied_exception_handler
exception_handlers[RateLimitExceeded] = rate_limit_exception_handler

app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api", tags=["users"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(cart.router, prefix="/api/cart", tags=["cart"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(api_keys_router.router, prefix="/api/api-keys", tags=["api-keys"])
app.include_router(security_router.router, prefix="/api/security", tags=["security"])


def _health_payload() -> dict:
    return {
        "status": "ok",
        "service": "commerce-testbed",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/security/health", tags=["health"])
def security_health():
    return _health_payload()


@app.get("/health", tags=["health"])
def health():
    return _health_payload()

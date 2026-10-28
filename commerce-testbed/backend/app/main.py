"""FastAPI application factory for the commerce-testbed backend."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api_keys import RateLimitExceeded, rate_limit_exception_handler
from .audit_middleware import RequestIDMiddleware, access_denied_exception_handler
from .config import get_settings
from .database import init_db
from .routers import auth, cart, events, orders, products, users
from .routers import api_keys as api_keys_router
from .routers import security as security_router


@asynccontextmanager
async def lifespan(app: FastAPI):
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

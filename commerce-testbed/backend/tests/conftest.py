"""Shared test setup: temp SQLite DB + TestClient.

The DATABASE_URL environment variable MUST be set before the app is imported,
because the engine binds to it at import time.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEST_DIR = tempfile.mkdtemp(prefix="commerce_testbed_tests_")
_TEST_DB = os.path.join(_TEST_DIR, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789")
os.environ.setdefault("AGENT_API_KEY", "test-agent-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import SecurityEvent  # noqa: E402
from app.routers.events import EVENT_FEED_LOG_INTERVAL_SECONDS, _last_event_feed_log  # noqa: E402

init_db()


@pytest.fixture()
def client():
    # Reset the agent-access log throttle so feed-access logging behaves
    # consistently in tests.
    _last_event_feed_log["ts"] = -float(EVENT_FEED_LOG_INTERVAL_SECONDS)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def all_events(db):
    return db.query(SecurityEvent).order_by(SecurityEvent.id).all()

"""Tests for the API key management system and /api/security SOC endpoints."""

import hashlib
import json
import uuid
from datetime import timedelta

import app.api_keys as api_keys_module
from app.models import ApiKey, utcnow
from tests.conftest import all_events

API_KEYS_URL = "/api/api-keys"


def registered_user(client, password="S3cretpass!x", email=None):
    """Register + login via the public API; returns token and profile."""
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    user = response.json()["user"]
    return {
        "email": email,
        "password": password,
        "token": token,
        "user": user,
    }


def session_headers(token):
    return {"Authorization": f"Bearer {token}"}


def key_headers(secret):
    return {"Authorization": f"Bearer {secret}"}


def make_key(client, user, name="My key", environment="development", scopes=None, expires_at=None):
    body = {"name": name, "environment": environment, "scopes": scopes or ["security_events:read"]}
    if expires_at is not None:
        body["expires_at"] = expires_at
    response = client.post(API_KEYS_URL, json=body, headers=session_headers(user["token"]))
    assert response.status_code == 201, response.text
    return response.json()


def key_query(db, key_id):
    return db.query(ApiKey).filter(ApiKey.key_id == key_id).first()


# ---------------------------------------------------------------- create

def test_create_key_secret_prefixes_and_one_time_display(client, db):
    user = registered_user(client)

    dev = make_key(client, user, name="dev key", environment="development")
    assert dev["secret"].startswith("sk_test_")
    assert dev["key"]["visible_prefix"] == dev["secret"][:14]
    assert dev["key"]["environment"] == "development"
    assert dev["key"]["status"] == "active"
    assert dev["key"]["scopes"] == ["security_events:read"]

    prod = make_key(
        client,
        registered_user(client),
        name="prod key",
        environment="production",
        scopes=["security_events:read", "users:read"],
    )
    assert prod["secret"].startswith("sk_live_")

    # the secret appears exactly once: in the create response, never afterwards
    listing = client.get(API_KEYS_URL, headers=session_headers(user["token"]))
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    item = items[0]
    for field in ("id", "key_id", "name", "environment", "scopes", "visible_prefix",
                  "status", "created_at", "expires_at", "revoked_at", "last_used_at"):
        assert field in item
    assert dev["secret"] not in listing.text
    listing_again = client.get(API_KEYS_URL, headers=session_headers(user["token"]))
    assert dev["secret"] not in listing_again.text
    assert "hashed_secret" not in listing.text

    # no plaintext secret anywhere in the api_keys table
    rows = db.query(ApiKey).all()
    for row in rows:
        for column in ApiKey.__table__.columns:
            value = str(getattr(row, column.name))
            assert dev["secret"] not in value, f"plaintext secret in {column.name}"
    stored = key_query(db, dev["key"]["key_id"])
    assert stored.hashed_secret == hashlib.sha256(dev["secret"].encode()).hexdigest()
    assert stored.revoked_at is None


def test_create_key_validation(client, db):
    user = registered_user(client)
    headers = session_headers(user["token"])

    # unknown scope -> 422
    bad_scope = client.post(
        API_KEYS_URL,
        json={"name": "x", "scopes": ["security_events:read", "admin:all"]},
        headers=headers,
    )
    assert bad_scope.status_code == 422

    # empty scopes (least privilege: only explicitly selected) -> 422
    empty = client.post(API_KEYS_URL, json={"name": "x", "scopes": []}, headers=headers)
    assert empty.status_code == 422

    # name too long -> 422
    long_name = client.post(
        API_KEYS_URL,
        json={"name": "n" * 129, "scopes": ["users:read"]},
        headers=headers,
    )
    assert long_name.status_code == 422

    # bad environment -> 422; expires_at in the past -> 422
    assert client.post(
        API_KEYS_URL,
        json={"name": "x", "environment": "staging", "scopes": ["users:read"]},
        headers=headers,
    ).status_code == 422
    past = client.post(
        API_KEYS_URL,
        json={"name": "x", "scopes": ["users:read"],
              "expires_at": (utcnow() - timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert past.status_code == 422

    # audit trail without secrets
    created = [e for e in all_events(db) if e.event_type == "api_key_created"]
    assert created
    details = json.loads(created[-1].details)
    assert details["key_id"]
    assert isinstance(details["scopes"], list)
    assert not any(isinstance(v, str) and v.startswith("sk_") for v in details.values())


# -------------------------------------------------------- auth / ping

def test_api_key_auth_and_ping(client, db):
    user = registered_user(client)
    created = make_key(client, user, scopes=["security_events:read"])
    secret = created["secret"]

    ping = client.get("/api/security/ping", headers=key_headers(secret))
    assert ping.status_code == 200, ping.text
    body = ping.json()
    assert body["authenticated"] is True
    assert body["key_name"] == "My key"
    assert body["key_id"] == created["key"]["key_id"]
    assert body["environment"] == "development"
    assert body["scopes"] == ["security_events:read"]
    assert body["user_pseudo"] == user["user"]["pseudo_id"]

    # X-API-Key header is accepted as a fallback
    assert client.get(
        "/api/security/ping", headers={"X-API-Key": secret}
    ).status_code == 200

    # last_used tracking
    row = key_query(db, created["key"]["key_id"])
    db.expire_all()
    row = key_query(db, created["key"]["key_id"])
    assert row.last_used_at is not None
    assert row.last_used_ip

    # unknown/invalid key, missing header, garbage header
    wrong = client.get("/api/security/ping", headers=key_headers("sk_test_wrongwrongwrong"))
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid API key"

    missing = client.get("/api/security/ping")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "API key required"

    garbage = client.get("/api/security/ping", headers={"Authorization": "Basic abcdef"})
    assert garbage.status_code == 401

    # usage was audited (throttled to once per 5 min per key), never with a secret
    used = [e for e in all_events(db) if e.event_type == "api_key_used"]
    assert used
    assert json.loads(used[-1].details)["key_id"] == created["key"]["key_id"]
    assert secret not in (used[-1].details or "")


def test_expired_key_rejected(client, db):
    user = registered_user(client)
    created = make_key(
        client, user,
        expires_at=(utcnow() + timedelta(seconds=60)).isoformat() + "Z",
    )
    secret = created["secret"]
    row = key_query(db, created["key"]["key_id"])

    # force-expire directly in the DB
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    db.expire_all()

    response = client.get("/api/security/ping", headers=key_headers(secret))
    assert response.status_code == 401
    assert response.json()["detail"] == "API key expired"

    # the list view computes status too
    listing = client.get(API_KEYS_URL, headers=session_headers(user["token"])).json()
    statuses = {i["key_id"]: i["status"] for i in listing["items"]}
    assert statuses[created["key"]["key_id"]] == "expired"


# --------------------------------------------------------------- scopes

def test_events_read_scope_enforced(client, db):
    user = registered_user(client)
    no_read = make_key(client, user, name="no-read", scopes=["users:read"])
    response = client.get("/api/security/events", headers=key_headers(no_read["secret"]))
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Insufficient permissions: requires 'security_events:read'"
    )
    denied = [e for e in all_events(db) if e.event_type == "access_denied"]
    assert any(
        json.loads(e.details).get("required_scope") == "security_events:read"
        and json.loads(e.details).get("key_id") == no_read["key"]["key_id"]
        for e in denied
    )

    reader = make_key(client, user, name="reader", scopes=["security_events:read"])
    ok = client.get("/api/security/events", headers=key_headers(reader["secret"]))
    assert ok.status_code == 200, ok.text
    body = ok.json()
    for field in ("items", "total", "limit", "offset"):
        assert field in body
    assert body["limit"] == 100
    # event rows have the feed's shape
    if body["items"]:
        event = body["items"][0]
        assert set(event) >= {"ts", "source", "event_type", "severity", "details"}
        ts = [e["ts"] for e in body["items"]]
        assert ts == sorted(ts, reverse=True)  # newest first


def test_events_filters(client, db):
    user = registered_user(client)
    created = make_key(client, user, scopes=["security_events:read"])
    secret = created["secret"]

    rows = client.get(
        "/api/security/events", headers=key_headers(secret), params={"limit": 1000}
    ).json()
    assert rows["total"] >= len(rows["items"])
    assert rows["offset"] == 0

    filtered = client.get(
        "/api/security/events",
        headers=key_headers(secret),
        params={"source": "app", "limit": 1000},
    ).json()
    assert all(e["source"] == "app" for e in filtered["items"])

    limited = client.get(
        "/api/security/events", headers=key_headers(secret), params={"limit": 2, "offset": 1}
    ).json()
    assert len(limited["items"]) <= 2
    assert limited["offset"] == 1


# ---------------------------------------------------------- write scope

def test_event_ingestion_anti_spoofing(client, db):
    user = registered_user(client)
    writer = make_key(client, user, name="writer", scopes=["security_events:write"])
    secret = writer["secret"]
    key_headers_value = key_headers(secret)

    # no write scope -> 403
    reader = make_key(client, user, name="reader2", scopes=["security_events:read"])
    assert client.post(
        "/api/security/events",
        json={"event_type": "brute_force_attempt"},
        headers=key_headers(reader["secret"]),
    ).status_code == 403

    # client may not spoof the source field
    spoof = client.post(
        "/api/security/events",
        json={"event_type": "brute_force_attempt", "source": "app"},
        headers=key_headers_value,
    )
    assert spoof.status_code == 422

    # sensitive detail keys rejected
    pw = client.post(
        "/api/security/events",
        json={"event_type": "brute_force_attempt", "details": {"password": "hunter2"}},
        headers=key_headers_value,
    )
    assert pw.status_code == 422

    # the presented secret itself must not appear in details (nor raw header)
    leak = client.post(
        "/api/security/events",
        json={"event_type": "brute_force_attempt", "details": {"note": f"sent {secret}"}},
        headers=key_headers_value,
    )
    assert leak.status_code == 422

    # valid ingestion: source forced to external, server ts, optional client ts
    ok = client.post(
        "/api/security/events",
        json={
            "event_type": "brute_force_attempt",
            "severity": "medium",
            "pseudo_user": "victim-pseudo-123",
            "details": {"ip_reputation": "bad"},
            "ts": "2026-01-01T00:00:00+00:00",
        },
        headers=key_headers_value,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["source"] == "external"
    assert body["status"] == "accepted"
    assert body["event_type"] == "brute_force_attempt"
    assert body["severity"] == "medium"

    db.expire_all()
    from app.models import SecurityEvent

    row = db.query(SecurityEvent).filter(SecurityEvent.id == body["id"]).first()
    assert row is not None
    assert row.source == "external"
    assert json.loads(row.details)["client_ts"] == "2026-01-01T00:00:00+00:00"
    assert row.pseudo_user == "victim-pseudo-123"
    assert row.ip  # recorded from the request
    # the raw secret never landed in any stored event
    for e in all_events(db):
        assert secret not in (e.details or "")


# ------------------------------------------------------------ revocation

def test_revocation(client, db):
    user = registered_user(client)
    created = make_key(client, user, scopes=["security_events:read"])
    secret = created["secret"]
    assert client.get(
        "/api/security/ping", headers=key_headers(secret)
    ).status_code == 200

    revoke = client.delete(
        f"{API_KEYS_URL}/{created['key']['id']}", headers=session_headers(user["token"])
    )
    assert revoke.status_code == 200
    assert revoke.json() == {"ok": True}

    response = client.get("/api/security/ping", headers=key_headers(secret))
    assert response.status_code == 401
    assert response.json()["detail"] == "API key revoked"

    # repeated revoke is idempotent
    again = client.delete(
        f"{API_KEYS_URL}/{created['key']['id']}", headers=session_headers(user["token"])
    )
    assert again.status_code == 200
    assert again.json() == {"ok": True}

    # audit + list status
    assert [e for e in all_events(db) if e.event_type == "api_key_revoked"]
    listing = client.get(API_KEYS_URL, headers=session_headers(user["token"])).json()
    assert listing["items"][0]["status"] == "revoked"
    assert listing["items"][0]["revoked_at"] is not None

    # unknown id -> 404
    assert client.delete(
        f"{API_KEYS_URL}/999999999", headers=session_headers(user["token"])
    ).status_code == 404


# -------------------------------------------------------------- rotation

def test_rotation(client, db):
    user = registered_user(client)
    created = make_key(
        client, user,
        name="rotate-me",
        environment="production",
        scopes=["security_events:read", "users:read"],
    )
    old_secret = created["secret"]

    rotated = client.post(
        f"{API_KEYS_URL}/{created['key']['id']}/rotate",
        headers=session_headers(user["token"]),
    )
    assert rotated.status_code == 201, rotated.text
    body = rotated.json()
    new_secret = body["secret"]
    assert new_secret != old_secret
    assert new_secret.startswith("sk_live_")

    # old secret is dead, new secret works with same metadata
    assert client.get(
        "/api/security/ping", headers=key_headers(old_secret)
    ).status_code == 401
    assert client.get(
        "/api/security/ping", headers=key_headers(old_secret)
    ).json()["detail"] == "API key revoked"
    ping = client.get("/api/security/ping", headers=key_headers(new_secret))
    assert ping.status_code == 200
    assert ping.json()["key_id"] != created["key"]["key_id"]

    old_row = key_query(db, created["key"]["key_id"])
    new_row = key_query(db, body["key"]["key_id"])
    assert old_row.revoked_at is not None
    assert old_row.name == new_row.name == "rotate-me"
    assert old_row.environment == new_row.environment == "production"
    assert old_row.scopes == new_row.scopes

    # rotate response never leaks the secret afterwards
    listing = client.get(API_KEYS_URL, headers=session_headers(user["token"]))
    assert old_secret not in listing.text
    assert new_secret not in listing.text

    rotated_events = [e for e in all_events(db) if e.event_type == "api_key_rotated"]
    assert rotated_events
    details = json.loads(rotated_events[-1].details)
    assert set(details) == {"old_key_id", "new_key_id"}

    # default rotation expiry is ~365 days out
    assert new_row.expires_at is not None
    delta = new_row.expires_at - utcnow()
    assert timedelta(days=360) < delta <= timedelta(days=366)


# ----------------------------------------------------- cross-user isolation

def test_cross_user_isolation(client, db):
    user1 = registered_user(client)
    user2 = registered_user(client)
    created = make_key(client, user1, name="user1 key", scopes=["security_events:read"])

    # user2 sees only own (empty) listing, never user1's keys
    listing2 = client.get(API_KEYS_URL, headers=session_headers(user2["token"]))
    assert listing2.status_code == 200
    assert listing2.json()["items"] == []
    assert created["key"]["key_id"] not in listing2.text

    # user2 cannot revoke or rotate user1's key
    assert client.delete(
        f"{API_KEYS_URL}/{created['key']['id']}",
        headers=session_headers(user2["token"]),
    ).status_code == 404
    assert client.post(
        f"{API_KEYS_URL}/{created['key']['id']}/rotate",
        headers=session_headers(user2["token"]),
    ).status_code == 404

    # user1's key still active; user2 can mint and use their own key
    assert client.get(
        "/api/security/ping", headers=key_headers(created["secret"])
    ).status_code == 200
    own2 = make_key(client, user2, name="user2 key", scopes=["security_events:read"])
    events2 = client.get("/api/security/events", headers=key_headers(own2["secret"]))
    assert events2.status_code == 200


# ------------------------------------------------------------ rate limit

def test_rate_limit_on_writes(client, db, monkeypatch):
    monkeypatch.setattr(api_keys_module, "RATE_LIMIT_WRITE", 5)
    user = registered_user(client)
    created = make_key(client, user, scopes=["security_events:write"])
    secret = created["secret"]
    body = {"event_type": "rate_test_event"}

    statuses = []
    for _ in range(6):
        response = client.post(
            "/api/security/events", json=body, headers=key_headers(secret)
        )
        statuses.append(response.status_code)
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429

    throttled = client.post(
        "/api/security/events", json=body, headers=key_headers(secret)
    )
    assert throttled.status_code == 429
    assert throttled.json()["detail"] == "Rate limit exceeded"
    assert throttled.json()["retry_after"] >= 1
    assert int(throttled.headers["Retry-After"]) >= 1

    triggered = [e for e in all_events(db) if e.event_type == "rate_limit_triggered"]
    assert triggered
    assert json.loads(triggered[-1].details)["key_id"] == created["key"]["key_id"]

    # a different key has its own window
    other = make_key(client, user, name="other", scopes=["security_events:write"])
    assert client.post(
        "/api/security/events", json=body, headers=key_headers(other["secret"])
    ).status_code == 200

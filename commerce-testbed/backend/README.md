# commerce-testbed — Fake E-commerce Backend (AI Cyber Defense Agent Hackathon)

An intentionally-instrumented fake e-commerce "test environment" built with
FastAPI + SQLAlchemy 2.0 + SQLite. It produces a stream of realistic security
audit events (real app events + synthetic incidents) that an external AI cyber
defense agent can monitor and analyze via `/api/events/feed`.

**No real payments, no real users, no real PII.** Passwords are bcrypt-hashed,
audit events reference users by a random `pseudo_id`, and attempted emails in
failed logins are recorded only as a SHA-256 hash prefix.

## Stack

- FastAPI (sync endpoints), SQLAlchemy 2.0 ORM, SQLite (`backend/data/app.db`)
- Pydantic v2 + pydantic-settings, PyJWT (HS256 access tokens), bcrypt
- uvicorn, pytest + httpx for tests

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install ".[local]"
```

On first start the app creates `data/app.db` and seeds ~40 demo products.

## Run the API

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health: `GET /api/security/health` (also `GET /health`)

## Deploy on Cloudflare Workers

`worker.py` exposes this FastAPI app through Cloudflare's Python Workers ASGI adapter. Cloudflare serves
the React assets directly, and the app uses the `HYPERDRIVE` binding for
persistent PostgreSQL. Do not deploy the local SQLite database file to Workers.

Create a PostgreSQL database and a Hyperdrive configuration in Cloudflare, then replace the
placeholder Hyperdrive ID in `wrangler.jsonc`. Set the two runtime secrets with `pywrangler
secret put` and deploy from this directory; the root README has the full command sequence.
Tables and the product catalog initialize on the first request. Local development still uses
SQLite and the usual `uvicorn` command above.

## Environment variables (optional; dev defaults exist but MUST be changed for real use)

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me-not-for-production` | JWT signing secret (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `AGENT_API_KEY` | `agent-dev-key-change-me` | Key for `/api/events/feed` |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy DB URL |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated exact browser origins allowed to call the API |

For a hosted frontend, set `CORS_ORIGINS` to its HTTPS origin (for example,
`https://your-worker.workers.dev`). Do not include a path or trailing slash. For multiple
frontends, separate exact origins with commas. Set `VITE_API_BASE_URL` in the frontend build to
the API's HTTPS origin (for example, `https://api.example.com`); leave it unset for local Vite
development, which proxies `/api` to `localhost:8000`.

## Generate synthetic data & incidents

```bash
source .venv/bin/activate
python -m scripts.simulate          # run from backend/ (or: python scripts/simulate.py)
python scripts/simulate.py --db ./data/app.db   # optional explicit DB path
```

The simulator runs in seconds and writes directly to the DB:

## Demo account (seeded via the real API — nothing mocked)

A ready-to-log-in demo user exists in the local database:

| Field | Value |
|---|---|
| Email | `demo@amezon.com` |
| Password | `AmezonDemo2026!` |

It was created through the public register/login endpoints, so its password is stored as a bcrypt
hash like every other account, and it already has a default address (Bengaluru 560001) and three
placed orders. Log in on the website, or via API:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@amezon.com","password":"AmezonDemo2026!"}'
```

```

The simulator runs in seconds and writes directly to the DB:

- ~8 synthetic users with normal login/browsing/order activity over the past 7 days
- **Credential stuffing incident**: one IP, ~150 `login_failure` events across
  many different attempted email hashes within a 10-minute window (severity medium)
- **Account takeover attempt**: repeated `login_failure` events for one account
  from an unusual IP, then a `login_success` → `session_created` →
  `password_changed` → `address_changed` chain (chain severity high)

Prints a summary of everything it wrote.

## Run tests

```bash
source .venv/bin/activate
python -m pytest
```

## Security event feed (for the AI agent)

Only agent-key auth — not regular user tokens:

```bash
curl -H "X-Agent-Key: $AGENT_API_KEY" "http://localhost:8000/api/events/feed?limit=10"
# or via query param:
curl "http://localhost:8000/api/events/feed?limit=10&api_key=$AGENT_API_KEY&severity=high&source=synthetic"
```

Query parameters: `since` (ISO-8601 timestamp, only rows with `ts >= since`),
`limit` (default 200, max 1000), `source` (`app` | `synthetic`), `severity`
(`low` | `medium` | `high`). Results are ordered oldest → newest. Missing key →
401; wrong key → 403. Successful agent access is logged at most once per 5
minutes as an `event_feed_access` event.

## AI SOC / API Key Integration

Per-user API keys let an external AI SOC agent authenticate against
`/api/security/*` endpoints. Keys are managed with the regular session JWT
(`Authorization: Bearer <access-token>`), are strictly owner-scoped, and
coexist with the legacy shared-agent-key feed above (which stays).

### Scopes

| Scope                  | Grants                                                                 |
|------------------------|------------------------------------------------------------------------|
| `security_events:read` | `GET /api/security/events`, `GET /api/security/incidents` needs `incidents:read` |
| `security_events:write`| `POST /api/security/events`                                            |
| `incidents:read`       | `GET /api/security/incidents`                                          |
| `users:read`           | `GET /api/security/users` (pseudonymous metadata only, no PII)         |

Keys carry **no admin scope**; least privilege applies — only explicitly
selected scopes are granted, unknown scopes are rejected, and an empty scope
list is rejected.

### Key lifecycle (create → one-time display)

`POST /api/api-keys` returns the full plaintext secret **exactly once**. Only
the SHA-256 hash of the secret is stored; a secret can never be retrieved,
listed, or logged again. Losing it means rotating or creating a new key.

```bash
curl -X POST "http://localhost:8000/api/api-keys" \
  -H "Authorization: Bearer <session-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "SOC agent", "environment": "development",
       "scopes": ["security_events:read", "security_events:write"]}'
```

```json
{
  "key": {
    "id": 1, "key_id": "key_ab12cd34ef56", "name": "SOC agent",
    "environment": "development", "scopes": ["security_events:read", "security_events:write"],
    "visible_prefix": "sk_test_xYz12ab", "status": "active",
    "created_at": "...", "expires_at": null, "revoked_at": null, "last_used_at": null
  },
  "secret": "sk_test_xYz12ab000000000000000000000000000000"
}
```

Development keys use the `sk_test_` prefix, production keys `sk_live_`.
`GET /api/api-keys` lists only the caller's own keys (same shape as `key`
above — never the secret). `DELETE /api/api-keys/{id}` revokes (idempotent,
`{"ok": true}`); `POST /api/api-keys/{id}/rotate` atomically revokes the old
key and returns a replacement with the same name/environment/scopes and a
fresh one-time secret (expiry: 365 days, or the remaining original duration).

### Authenticating SOC endpoints

Pass the key secret itself (never the JWT):

```bash
curl -H "Authorization: Bearer sk_test_..." "http://localhost:8000/api/security/ping"
# or:
curl -H "X-API-Key: sk_test_..." "http://localhost:8000/api/security/ping"
```

### Endpoints

| Endpoint | Scope | Description |
|---|---|---|
| `GET /api/security/ping` | none | Connection test: verifies key validity, returns key metadata |
| `GET /api/security/events` | `security_events:read` | Event stream, newest first; params `since`, `until`, `limit` (default 100, max 1000), `offset`, `severity`, `source` (`app`/`synthetic`/`external`/default `all`), `event_type` |
| `POST /api/security/events` | `security_events:write` | Ingest an external event; `source` is forced to `external`, server records its own timestamp |
| `GET /api/security/incidents` | `incidents:read` | Derived, read-only incident view (no new tables): high-severity event groups + synthesized "Possible credential stuffing" per IP |
| `GET /api/security/users` | `users:read` | Pseudonymous account metadata only — **no PII** (no emails/phones/names) |

Connection test:

```bash
curl -H "Authorization: Bearer sk_test_..." "http://localhost:8000/api/security/ping"
# → {"authenticated": true, "key_id": "key_ab12cd34ef56", "key_name": "SOC agent",
#    "environment": "development", "scopes": [...], "user_pseudo": "..."}
```

Ingest an event (client-supplied `source` fields are rejected 422; details
must not contain sensitive keys such as `password`/`token`/`secret` and must
never echo the API key secret itself):

```json
POST /api/security/events
{"event_type": "brute_force_attempt", "severity": "medium",
 "pseudo_user": "victim-pseudo-123", "details": {"ip_reputation": "bad"}}
→ {"id": 42, "ts": "2026-...", "event_type": "brute_force_attempt",
   "source": "external", "severity": "medium", "status": "accepted"}
```

### Error responses

| Status | Detail | Meaning |
|---|---|---|
| 401 | `API key required` | Missing or malformed auth header |
| 401 | `Invalid API key` | Unknown key / wrong secret |
| 401 | `API key revoked` | Key was revoked by its owner |
| 401 | `API key expired` | Key past `expires_at` |
| 401 | `API key owner inactive` | Owning account deactivated |
| 403 | `Insufficient permissions: requires '<scope>'` | Key lacks the required scope |
| 429 | `Rate limit exceeded` + `Retry-After` header/body | Per-key limit: 120 reads/min, 30 writes/min |

Rate limiting is a simple in-process sliding window in this single-process
testbed; production deployments should use a shared store (e.g. Redis).

### TLS

In production terminate TLS at the reverse proxy (uvicorn behind nginx), or
for direct TLS:

```bash
uvicorn app.main:app --port 443 --ssl-keyfile ./key.pem --ssl-certfile ./cert.pem
```

API-key secrets must never travel over plain HTTP.

## Event types

`account_created`, `login_success`, `login_failure`, `session_created`,
`session_revoked`, `suspicious_login_activity`, `profile_updated`,
`password_changed`, `password_change_failed`, `address_changed`, `cart_updated`,
`order_placed`, `access_denied`, `event_feed_access`, plus API-key activity:
`api_key_created`, `api_key_rotated`, `api_key_revoked`, `api_key_used`,
`rate_limit_triggered`, and externally ingested events (source `external`).

## API overview (all under `/api`)

- `POST /api/auth/register` `{email, password(min 8), full_name}` → `{access_token, user}`
- `POST /api/auth/login` `{email, password}` → `{access_token, user}`
- `POST /api/auth/logout` — revokes the current session
- `GET/PUT /api/me`, `PUT /api/me/password`
- `GET/POST /api/me/addresses`, `PUT/DELETE /api/me/addresses/{id}`
- `GET /api/me/sessions`, `DELETE /api/me/sessions/{id}`
- `GET /api/products?q=&category=&page=&page_size=`, `GET /api/products/categories`, `GET /api/products/{id}`
- `GET /api/cart`, `POST /api/cart/items`, `PATCH/DELETE /api/cart/items/{item_id}`
- `POST /api/cart/checkout` `{shipping_address_id, payment_method_display}`
- `GET /api/orders`, `GET /api/orders/{id}`
- `GET /api/events/feed` (agent key only)
- `GET/POST /api/api-keys`, `DELETE /api/api-keys/{id}`, `POST /api/api-keys/{id}/rotate` (session JWT)
- `GET /api/security/ping|events|incidents|users`, `POST /api/security/events` (API key)
- `GET /api/security/health`, `GET /health`

Protected endpoints use `Authorization: Bearer <access-token>`.

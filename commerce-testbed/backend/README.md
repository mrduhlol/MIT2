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
- Pydantic v2 + pydantic-settings, PyJWT (HS256 access tokens), passlib/bcrypt
- uvicorn, pytest + httpx for tests

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On first start the app creates `data/app.db` and seeds ~40 demo products.

## Run the API

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health: `GET /api/security/health` (also `GET /health`)

## Environment variables (optional; dev defaults exist but MUST be changed for real use)

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me-not-for-production` | JWT signing secret (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `AGENT_API_KEY` | `agent-dev-key-change-me` | Key for `/api/events/feed` |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy DB URL |

## Generate synthetic data & incidents

```bash
source .venv/bin/activate
python -m scripts.simulate          # run from backend/ (or: python scripts/simulate.py)
python scripts/simulate.py --db ./data/app.db   # optional explicit DB path
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

## Event types

`account_created`, `login_success`, `login_failure`, `session_created`,
`session_revoked`, `suspicious_login_activity`, `profile_updated`,
`password_changed`, `password_change_failed`, `address_changed`, `cart_updated`,
`order_placed`, `access_denied`, `event_feed_access`.

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
- `GET /api/security/health`, `GET /health`

Protected endpoints use `Authorization: Bearer <access-token>`.

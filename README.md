# MIT2 — Hackathon Workspace

This repo hosts the **commerce-testbed**: a full-stack e-commerce application used as a controlled
target/test environment for an AI Cyber Defense Agent project. It is intentionally kept separate
from any SOC dashboard.

➡️ See [`commerce-testbed/backend/README.md`](./commerce-testbed/backend/README.md) for the full overview,
architecture, and setup instructions.

## Quick start (two terminals)

```bash
# 1) Backend (FastAPI + SQLite) on http://localhost:8000
cd commerce-testbed/backend
python -m venv .venv && source .venv/bin/activate
pip install ".[local]"
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs

# 2) Frontend (React + TypeScript + Tailwind) on http://localhost:5173
cd commerce-testbed/frontend
npm install
npm run dev
```

## Neon PostgreSQL setup

The workspace is linked locally to Neon project `shy-term-30624525`, branch `production`.
`neon.ts` declares Postgres only; the existing FastAPI login and session system is retained.

```bash
npm install
neon init -y --org-id org-lingering-union-88719333 --project-id shy-term-30624525 --branch production --services postgres
neon deploy
npm run build
```

Complete browser sign-in when prompted. `neon deploy` pulls `DATABASE_URL`,
`DATABASE_URL_UNPOOLED`, and `NEON_BRANCH` into `.env.local` (or an existing `.env`).
These files and `.neon` are git-ignored. Never expose database URLs through `VITE_*` variables.

FastAPI reads workspace `.env.local` / `.env`, then backend `.env.local` / `.env`;
process environment variables override file values. SQLAlchemy uses psycopg 3 with the pooled
URL for application queries and the direct URL for schema initialization. SQLite remains the
fallback when no database URL is configured. Existing SQLite users are not automatically migrated.

Run the Neon-backed application in two terminals:

```bash
npm run dev:api  # http://127.0.0.1:8001
npm run dev:web  # Vite UI; /api proxies to port 8001
```

Validate a running API, or the Vite frontend's API proxy:

```bash
cd commerce-testbed/backend
.venv/bin/python -m scripts.smoke_test --base-url http://127.0.0.1:8001
```

The smoke test creates a synthetic account and order, checks login, saved addresses,
products, cart/checkout, order persistence, event-feed permission checks, API-key revocation,
and session revocation. It keeps the audit trail and does not print credentials.

## Deploy the full app to Cloudflare

For Cloudflare Workers Builds, use these settings:

- **Root directory:** repository root (`/`)
- **Build command:** leave blank (the Worker custom build prepares everything)
- **Deploy command:** `npx wrangler deploy` (or `npm run deploy`)
- **Worker name:** `frontend`

The root `wrangler.jsonc` runs `scripts/prepare-deploy.mjs`: installs locked frontend/backend
Node dependencies, bootstraps pinned uv without changing shell profiles, installs Python
build tools, vendors Worker-compatible Python packages, builds React, and stages FastAPI.
Only generated runtime packages and app sources are uploaded. Runtime secrets `SECRET_KEY`
and `AGENT_API_KEY` must remain configured on the Worker; Neon credentials are accessed through
its existing Hyperdrive binding. No Neon login or `.env.local` is needed during CI builds.

To reproduce the same deployment from the repository root:

```bash
npm ci
npm run deploy:dry-run
npm run deploy
```


The React assets and FastAPI API share <https://frontend.abhishek-a2534.workers.dev>.

Current verification: the build, all 31 automated tests, and the complete Neon-backed local
API/frontend-proxy smoke tests pass. Public storefront/docs and individual API flows work,
but the complete public smoke test has intermittently failed with HTTP 503 on login/logout.
Runtime logs also captured Cloudflare Python `NoGilError`; public reliability is not yet verified.
See [Cloudflare runtime issue #6624](https://github.com/cloudflare/workerd/issues/6624).
The backend's Hyperdrive binding connects to the Neon production database's direct endpoint;
Hyperdrive pools connections, with query caching disabled. The Worker uses the pure-Python pg8000 driver and opens request-scoped connections without
a client pool; local FastAPI uses psycopg 3.

```bash
npm run build
cd commerce-testbed/backend
npm ci
uv sync --group dev
uv run pywrangler deploy --dry-run
uv run pywrangler secret put SECRET_KEY
uv run pywrangler secret put AGENT_API_KEY
uv run pywrangler deploy
```

The secret commands prompt privately. Use distinct random secrets; never commit them.
Worker authentication uses Cloudflare runtime secrets, not the local Neon environment file.
Only application sources are staged into `.worker-build`; virtual environments, local
configuration, and test files are excluded from deployment. API docs are at `/docs`, and
health is at `/api/security/health` or `/health`.

After deployment, run the smoke test against the public HTTPS URL too. To attach your domain,
open **Workers & Pages → frontend → Settings → Domains & Routes → Add → Custom Domain**.
The domain's DNS zone must be active in the same Cloudflare account.

## Generate synthetic activity & incidents

```bash
cd commerce-testbed/backend
.venv/bin/python -m scripts.simulate    # realistic normal usage + credential-stuffing & ATO attempts
```

## Consume the event feed (AI Cyber Defense Agent)

All security events are exposed at `GET /api/events/feed` with a fixed API key header:

```bash
curl -H "X-Agent-Key: agent-dev-key-change-me" "http://localhost:8000/api/events/feed?limit=50"
```

Events carry `source: "app"` (real application activity) or `"source": "synthetic"` (generated by
the simulator) so the two are always distinguishable. See the testbed README for the full event
taxonomy.

## AI SOC integration via per-user API keys

Instead of the shared agent key above, each user can mint **scoped API keys** (`sk_test_` / `sk_live_`)
in the website under **Account → Developer**. Secrets are shown exactly once, hashes are stored
(`sha256`, `hmac.compare_digest` verified), and every request is permission-checked:

```bash
# 1) In the UI: Account → Developer → Create API Key (copy the one-time secret)
# 2) Test the connection
curl -H "Authorization: Bearer sk_test_..." http://localhost:8000/api/security/ping
# 3) Pull security events (needs security_events:read)
curl -H "Authorization: Bearer sk_test_..." "http://localhost:8000/api/security/events?limit=50&severity=high"
# 4) Submit external events (needs security_events:write; source is forced to "external")
curl -X POST -H "Authorization: Bearer sk_test_..." -H "Content-Type: application/json" \
  -d '{"event_type":"scanner_detected","severity":"medium","details":{"src":"my_agent"}}' \
  http://localhost:8000/api/security/events
```

Scopes: `security_events:read`, `security_events:write`, `incidents:read`, `users:read` (the latter
returns pseudonymous-only metadata — no PII). Rotation revokes the old key immediately; expired and
revoked keys get distinct 401 responses; per-key rate limits (120 reads/min, 30 writes/min) return
429 with `Retry-After`. Full endpoint docs: `commerce-testbed/backend/README.md` and `/docs`.

## Administrator portal

Administrators sign in through `/login` and are sent to `/admin`. The portal includes live
overview, users, products, orders, sessions, API keys, and security-event dashboards, with
search, pagination, account enable/disable, and session/key revocation. Privileges are checked
against the `admin_roles` table on every admin API request. Registration and profile updates
cannot grant admin access. Responses exclude password hashes, session identifiers, and secret
API-key material. Admin views and actions are audit-logged.

Provision or reset an administrator explicitly (the password is prompted privately):

```bash
cd commerce-testbed/backend
.venv/bin/python -m scripts.create_admin --email owner@example.com
.venv/bin/python -m scripts.check_admin --base-url http://127.0.0.1:8001 --email owner@example.com
```

The setup command creates the additive admin-role table, stores only a bcrypt password hash,
and revokes existing sessions when resetting an account. There are no built-in admin passwords
or email-based privilege bypasses. Credentials are not stored in repository files.

## Currency

All storefront, cart, checkout, order-history, and admin amounts display in Indian rupees
(INR / ₹) with Indian digit grouping. Monetary database/API fields keep their legacy
`*_cents` names for compatibility; their integer values represent paise (100 paise = ₹1).
Existing numeric prices and order amounts are retained; this is not an exchange-rate conversion.

## Public synthetic credentials for hackathon demos

Admin → Users includes a **Demo password** column only for explicitly provisioned synthetic
shopper accounts. Run `python -m scripts.create_demo_accounts` from the backend directory to
create three `demo-shopper-N@example.com` accounts with the intentionally public sample
password in `app/demo_data.py`. These are marked Synthetic and their provisioning events
are tagged `source: synthetic`. Existing accounts are never reset or reclassified.

Normal registration/password-change flows store only bcrypt hashes and do not capture
plaintext passwords. Public profile responses exclude demo credentials. If a demo account's
password changes or it becomes an administrator, its demo password is no longer displayed.

## Product imagery

Each of the 40 seeded products has a stable image in
`commerce-testbed/frontend/public/images/products/`, mapped by product name in
`backend/app/product_images.py`. Photos illustrate the named product type; the six book
covers are original title-matched demo artwork. Photographer/license attribution is
available from the footer's Product image credits link and `credits.json` beside the images.
Startup atomically replaces legacy Picsum URLs without modifying product IDs, prices, stock,
or orders. Custom image URLs are preserved. Images are served by the site's static assets,
so browsers do not depend on third-party photo services.

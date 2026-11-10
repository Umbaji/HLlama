# HLlama Backend API

REST API for the **HLlama** connected-health platform — the sexual and reproductive
health assistant built by **Umbaji**, serving women and girls in West Africa
(Benin, Togo).

The backend powers:

- the **admin dashboard** (`admin/`, Next.js): statistics, user management, question
  moderation, documentary-base review, activity logs, CSV exports;
- the **WhatsApp bot** (`bot/`, Flask): exchange storage, history, full-text
  search and feedback;
- **external clients**: authentication and nearby healthcare place lookup.

## Features

- **Users**: create, paginated listing, lookup, update, active/inactive status,
  soft delete (`deleted_at`).
- **Administrators**: creation (admins only), listing, promote/demote a user,
  TOTP-based MFA (enrollment, verification, recovery codes).
- **JWT authentication**: `POST /api/login`, tokens signed with `PyJWT`,
  passwords hashed with `bcrypt`, configurable token lifetime.
- **Questions & exchanges**: questions asked from a phone number, bot exchanges
  (`request_type`: `question`, `translation`, `agent_action`, `health_fact`, …),
  full-text search over the history.
- **Statistics** (admin): overview counts for the dashboard.
- **Management** (admin): activate/deactivate, soft delete, promote, question
  moderation, activity log (`activity_logs`), CSV exports (users, questions).
- **Health / proximity**: nearest healthcare place lookup (pharmacy, hospital,
  clinic) via the Google Maps API plus place geocoding.
- **Documentary knowledge base**: ingestion, semantic search over WHO/health
  fact sheets, a review workflow (scan, diff, apply, supervise) for admins.
- **Health facts**: facts she declares about her own health, stored
  pseudonymously and removable on request.
- **Consent**: web consent page opened from a tokenised link; the bot asks the
  status and the link with the number in the request body, never in the URL.
- **Feedback**: answers stored pseudonymously and aggregated per question for
  admins.
- **Service misses**: formulations the bot could not route to a known service,
  logged for review (bot) and listed for admins.

## Tech Stack

| Layer | Technology |
| --- | --- |
| API | FastAPI (Python 3.12) |
| ORM / migrations | SQLAlchemy 2 + Alembic |
| Database | PostgreSQL 16 (+ pgvector for the knowledge base) |
| Auth | JWT (`PyJWT`), `passlib[bcrypt]`, TOTP (MFA) |
| Geolocation | `googlemaps` + `haversine` |
| API docs | Swagger UI (`/docs`) and ReDoc (`/redoc`) |
| Deployment | Docker, `docker-compose` at project root |

## Repository Structure

Every directory holds one kind of thing, and the dependency runs one way:
`routes` parse and answer, `services` decide, `models` and `schemas` describe,
`helpers` and `clients` reach outside. A route never talks to an external API
and a service never builds an HTTP response.

```text
backend/
|-- main.py                       # FastAPI app: CORS, error handlers, routers,
|                                 #   static mount, lifespan
|-- config.py                     # Every setting, typed, via pydantic-settings.
|                                 #   PSEUDO_ID_SECRET and CONSENT_TOKEN_SECRET
|                                 #   have no default: the API refuses to start
|-- database.py                   # Engine, SyncSession, declarative Base
|-- api_tester.py                 # Manual end-to-end script against a running API
|-- Dockerfile                    # Production image: alembic upgrade head, then uvicorn
|-- docker-compose.yml            # Local stack: API + PostgreSQL
|
|-- routes/                       # HTTP only: parse, authorise, answer. No logic.
|   |-- auth.py, auth_mfa*.py     #   POST /api/login and TOTP MFA
|   |-- users.py, admins.py       #   User and administrator CRUD
|   |-- questions.py              #   Questions of a number (bot)
|   |-- bot.py                    #   Exchanges, history, knowledge search,
|   |                             #   profile, feedback (bot)
|   |-- health.py                 #   /api/nearest/{category}, /api/geocode
|   |-- health_fact.py            #   Health facts she declares (bot)
|   |-- knowledge.py              #   Documentary base review (admin)
|   |-- service_miss.py           #   Unrouted requests, logged and listed
|   |-- consent.py                #   The consent/policy pages and the consent API
|   |-- management.py             #   Admin actions and CSV exports
|   |-- stats.py                  #   Overview aggregate for the dashboard
|   `-- monitoring.py             #   Health probes and their history
|
|-- services/                     # The decisions. Everything testable lives here.
|   |-- auth_service.py           #   Tokens, current_user dependency
|   |-- admin_mfa*.py             #   TOTP enrollment, verification, recovery
|   |-- login_throttle.py         #   Shared PostgreSQL login budgets
|   |-- user_service.py           #   Users, bot users, encrypted numbers
|   |-- question_service.py       #   Exchanges and history
|   |-- consent_service.py        #   Tokens (single use), decisions, fail-closed ties
|   |-- consent_page.py           #   Renders the page: language, strings, states
|   |-- policy_page.py            #   Renders the policy page
|   |-- knowledge.py, knowledge_corpus.py, knowledge_ingestion.py
|   |                             #   Documentary base: search, scan, diff, apply
|   |-- health_fact.py            #   Declared health facts
|   |-- health_lookup_limit.py    #   Shared budgets for nearest-place lookups
|   |-- service_miss.py           #   Unrouted-request logging
|   |-- feedback_service.py       #   Satisfaction answers
|   |-- stats_service.py          #   Statistics queries
|   |-- admin_service.py          #   Admin actions and their activity log
|   |-- bot_auth.py               #   X-Bot-Api-Key verification
|   `-- retention.py              #   Data retention / right-to-be-forgotten
|
|-- models/                       # SQLAlchemy tables, one file per domain
|   |-- user.py                   #   users (encrypted number, last_inbound_at)
|   |-- question.py               #   questions (the exchanges)
|   |-- consent.py                #   consent_records (decision, token_jti unique)
|   |-- feedback.py               #   feedback_responses
|   |-- health_fact.py            #   health_facts
|   |-- knowledge.py              #   knowledge_documents, knowledge_chunks (pgvector)
|   |-- service_miss.py           #   service_misses
|   |-- admin_mfa.py              #   admin TOTP secrets, recovery codes
|   |-- login_attempt.py          #   login_attempts (throttling)
|   |-- health_lookup_bucket.py   #   nearest-place lookup budgets
|   `-- activity_log.py           #   activity_logs
|
|-- schemas/                      # Pydantic: what crosses a boundary, bounded
|-- helpers/
|   |-- anonymity.py              #   pseudo_id, number encryption, masking
|   |-- health.py                 #   Google Places and geocoding
|   |-- server_message.py         #   The {error,status,message,data,meta} envelope
|   `-- email.py                  #   Outbound notification email
|-- clients/
|   `-- embeddings.py             #   Embedding calls for the knowledge base
|
|-- templates/                    # consent.html, policy.html shells, $placeholders only
|-- static/consent/               # Its stylesheet, its three scripts, its mark
|-- content/
|   |-- consent/                  #   Legal text and interface strings, fr and en
|   `-- knowledge/                #   Example knowledge-base documents
|
|-- monitoring/                   # Probes, alerts, contract checks, history
|-- alembic/versions/             # Migrations
|-- scripts/                      # fetch_who_fact_sheets.py, ingest_knowledge.py, and friends
|-- tests/                        # pytest suite
`-- docs/
    `-- *.md                      #   Bot conversation profile, localisation
```

### Where to start reading

| To understand | Read |
| --- | --- |
| How a request is answered | `main.py`, then the route, then its service |
| What the bot may call | `routes/bot.py` and `routes/consent.py` |
| Why a consent decision counts | `services/consent_service.py` |
| How the knowledge base is reviewed | `routes/knowledge.py`, then `services/knowledge_ingestion.py` |
| What the answer looks like | `helpers/server_message.py` |

## Requirements

- Python 3.12+
- PostgreSQL 16 (or `docker compose up db`)
- Google Maps API key (proximity/geocoding endpoints)
- (Optional) Docker to run the full stack

## Installation

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate   |  Linux/macOS: source .venv/bin/activate
pip install --require-hashes -r requirements-tools.txt
```

`requirements.txt`, `requirements-dev.txt`, and `requirements-tools.txt` are
generated from their matching `.in` files with pinned `pip-tools` 7.6.1. To
refresh them with Python 3.12, install the pinned lock generator and run:

```bash
python -m pip install pip-tools==7.6.1
pip-compile --generate-hashes --strip-extras --resolver=backtracking --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --strip-extras --resolver=backtracking --output-file=requirements-dev.txt requirements-dev.in
pip-compile --generate-hashes --strip-extras --resolver=backtracking --output-file=requirements-tools.txt requirements-tools.in
```

Create your `.env` file (see `.env.example`):

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/hllama_dev
SECRET_KEY=a-strong-jwt-secret
GOOGLE_API_KEY=your_google_api_key_here
BOT_API_KEY=your_shared_bot_key
ALLOWED_ORIGINS=http://localhost:3000
DEBUG=false
# Interactive docs are local-only; set both explicitly for local development.
ENVIRONMENT=development
API_DOCS_ENABLED=true
# Required, no default: the API refuses to start without them.
PSEUDO_ID_SECRET=same-value-as-the-bot
CONSENT_TOKEN_SECRET=a-strong-random-secret
CONSENT_PAGE_BASE_URL=https://api.example.org
# Required for /api/login throttling: 32 random bytes encoded as 64 hex chars.
ADMIN_LOGIN_BUCKET_KEY=replace-with-a-random-64-character-hex-value
# Keep at zero locally; set to one only behind a reverse-proxy ingress.
LOGIN_TRUSTED_PROXY_HOPS=0
```

Login protection uses PostgreSQL-backed identity and IP counters shared by all
backend replicas. Never commit `ADMIN_LOGIN_BUCKET_KEY` into a checked-in
values file or print it in logs. If the key is missing or the counter store is
unavailable, login fails closed with `LOGIN_THROTTLE_UNAVAILABLE`.

Health lookup authentication is staged off by default. The bot sends
`X-Bot-Api-Key` for nearest-place and geocoding requests. Keep
`HEALTH_LOOKUP_AUTH_REQUIRED=false` until the deployed bot has been verified;
then enable it to require the header and activate the shared PostgreSQL budgets.
Defaults are 120 nearest lookups/minute and 30 geocoding calls/minute, with
bounded configuration ranges. Database limiter failures return 503 without
calling Google. Never place `BOT_API_KEY` in URLs or logs.

Admin MFA is staged off by default. `ADMIN_MFA_ENROLLMENT_ENABLED=true` permits
enrollment challenges; `ADMIN_MFA_REQUIRED=true` rejects admin access tokens
without a verified MFA claim. Before enabling enrollment, provision an
independent `ADMIN_MFA_ENCRYPTION_KEY` containing 32 random bytes encoded as 64
hex characters in the runtime secret manager. Never reuse
`ADMIN_LOGIN_BUCKET_KEY`, derive the key from `SECRET_KEY`, or log the value.
MFA enforcement must remain disabled until every active admin has enrolled and
recovery has been tested.

## Never commit a secret

Run this once per clone, from the repository root (the guard is shared by
the bot, the API and the back office):

```bash
sh scripts/install-hooks.sh
```

It points git at `.githooks/`, which refuses a commit or a push carrying a
`.env`, a private key, or a line shaped like a real credential.
`scripts/check_secrets.py` at the root holds the rules; the same script runs in
CI, so the two can never disagree.

**Why hooks are not enough, and what to rely on.** `.gitignore` already lists
`.env`, and it works — until someone runs `git add -f`. Hooks close that door,
but they live on your machine: a fresh clone has none until the command above,
and `--no-verify` skips them. A secret-guard CI job can run on every push and
every pull request so nobody can skip it in review, but it only reports;
making it block a merge needs branch protection.

**If a secret has already left**, rewriting history does not take it back: the
blob stays reachable through pull request refs and through every fork of the
repository. Rotate it, then ask your Git host's support to purge the objects.

## Migrate and run

```bash
alembic upgrade head          # Apply migrations
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000
- Interactive Swagger docs: http://localhost:8000/docs (only with
  `ENVIRONMENT=development` and `API_DOCS_ENABLED=true`)
- ReDoc docs: http://localhost:8000/redoc (same local-only setting)
- Raw OpenAPI: http://localhost:8000/openapi.json (same local-only setting)

## Tests

```bash
pip install --require-hashes -r requirements-dev.txt
python -m pytest tests/ -q
```

No `.env` is needed: `tests/conftest.py` supplies the settings that have no
default, and each test builds its own in-memory SQLite engine.

**Install from `requirements-dev.txt`, in a virtual environment.** The versions
are pinned for a reason — `bcrypt` is held at 4.0.1 because passlib 1.7.4 probes
its backend with a long test string, which bcrypt 5 refuses instead of
truncating. With a newer bcrypt installed, every test that creates a user fails
inside `hash_password` and the failure looks like a bug in the code under
review. Use the Python the Dockerfile ships, 3.12.

## Endpoint authentication

| Audience | Method |
| --- | --- |
| Administration (stats, management, knowledge) | `Authorization: Bearer <JWT>` (from `POST /api/login`) |
| WhatsApp bot (questions, exchanges, knowledge search) | `X-Bot-Api-Key: <BOT_API_KEY>` header |
| Current user | `GET /api/users/me/` with JWT |

## Response contract

All JSON API responses use the following envelope. HTML consent/policy pages and
CSV downloads use their documented media types instead:

```json
{
  "status": 200,
  "error": false,
  "message": "USERS_FETCHED",
  "data": [],
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "served_at": "2026-10-29T12:00:00Z"
  }
}
```

| Field | Type | Description |
| --- | --- | --- |
| `status` | number | HTTP status code mirrored in the body |
| `error` | boolean | `true` when `status >= 400` |
| `message` | string | Stable application key (e.g. `USER_CREATED`, `CONSENT_TOKEN_INVALID`) |
| `data` | object / array / null | Main payload |
| `meta` | object | Always includes `request_id` and UTC `served_at`, with optional typed context |

Error example:

```json
{
  "status": 404,
  "error": true,
  "message": "USER_NOT_FOUND",
  "data": null,
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "served_at": "2026-10-29T12:00:00Z"
  }
}
```

Framework and validation errors use registered message codes. Validation
metadata contains at most 50 `{ "field": "body", "reason": "..." }`
violations and never echoes submitted values or exception text.

## Endpoint summary

| Method | Path | Description | Access |
| --- | --- | --- | --- |
| GET | `/` | API health | public |
| POST | `/api/login` | Authenticate → JWT token | public |
| POST | `/api/login/mfa/setup` | Start TOTP enrollment | admin (JWT) |
| POST | `/api/login/mfa/enroll` | Confirm enrollment with a TOTP code | admin (JWT, challenge token) |
| POST | `/api/login/mfa/verify` | Verify a TOTP code at login | challenge token |
| POST | `/api/login/mfa/recover` | Use a recovery code | challenge token |
| GET | `/api/users` | Paginated user listing | admin (JWT) |
| POST | `/api/users` | Create a user | admin (JWT) |
| GET | `/api/users/me/` | Current user | JWT |
| GET | `/api/users/{user_id}` | User detail | admin |
| PUT | `/api/users/{user_id}` | Update a user | self or admin (JWT) |
| GET | `/api/admins` | List admins | admin |
| POST | `/api/admins` | Create an admin | admin |
| GET | `/api/admins/{user_id}` | Admin detail | admin |
| POST | `/api/users/{pseudo_id}/questions` | Add a question | bot key |
| GET | `/api/users/{pseudo_id}/questions` | Questions for a pseudonymous user | bot key |
| GET | `/api/nearest/{category}` | Nearest healthcare place (`pharmacy`/`hospital`/`clinic`) | bot key when staged enforcement is enabled |
| GET | `/api/geocode` | Geocode a place name | bot key when staged enforcement is enabled |
| GET | `/api/stats/overview` | Overview | admin |
| POST | `/api/manage/users/{id}/deactivate` | Deactivate a user | admin |
| POST | `/api/manage/users/{id}/activate` | Activate a user | admin |
| DELETE | `/api/manage/users/{id}` | Soft delete | admin |
| POST | `/api/manage/users/{id}/promote` | Promote to admin | admin |
| POST | `/api/manage/users/{id}/demote` | Demote an admin | admin |
| GET | `/api/manage/questions` | All questions (paginated) | admin |
| DELETE | `/api/manage/questions/{id}` | Delete a question | admin |
| GET | `/api/manage/logs` | Activity log | admin |
| GET | `/api/manage/feedback` | Feedback answers + per-question aggregates | admin |
| GET | `/api/manage/export/users` | Users CSV export | admin |
| GET | `/api/manage/export/questions` | Questions CSV export | admin |
| GET | `/api/service-misses` | Unrouted requests (paginated) | admin |
| POST | `/api/bot/exchanges` | Store a bot exchange | bot |
| GET | `/api/bot/users/{pseudo_id}/history` | Recent history | bot |
| GET | `/api/bot/users/{pseudo_id}/search` | Full-text search | bot |
| GET | `/api/bot/knowledge/search` | Semantic search over the documentary base | bot |
| GET | `/api/bot/users/{pseudo_id}/profile` | Read the encrypted conversation profile | bot |
| PUT | `/api/bot/users/{pseudo_id}/profile` | Update the encrypted preferred name | bot |
| GET | `/api/bot/users/{pseudo_id}/health-facts` | Declared health facts | bot |
| POST | `/api/bot/health-facts` | Declare a health fact | bot |
| POST | `/api/bot/health-facts/{fact_id}/remove` | Remove a declared health fact | bot |
| POST | `/api/bot/service-misses` | Log an unrouted request | bot |
| POST | `/api/bot/consent/status` | Consent status, body `{pseudo_id, telnumber}` | bot |
| POST | `/api/bot/consent/link` | Tokenised consent page link, same body | bot |
| POST | `/api/bot/feedback` | Store a feedback answer | bot |
| GET | `/consent` | Consent web page | public (token) |
| GET | `/policy` | Policy web page | public |
| POST | `/api/consent` | Record the consent decision | public (token) |
| GET | `/api/knowledge/documents` | List ingested documents | admin |
| POST | `/api/knowledge/documents` | Ingest a document | admin |
| GET | `/api/knowledge/documents/{document_id}` | Document detail | admin |
| GET | `/api/knowledge/corpus` | List the source corpus | admin |
| POST | `/api/knowledge/corpus/scan` | Scan the corpus for differences | admin |
| GET | `/api/knowledge/corpus/{slug}` | A corpus entry's diff | admin |
| POST | `/api/knowledge/corpus/{slug}/apply` | Apply a corpus entry | admin |
| GET | `/api/monitoring/health` | Service and dependency health | monitoring key |
| GET | `/api/monitoring/history` | Recorded health history | monitoring key |

## Docker

```bash
docker build -t hllama-backend .
docker run --env-file .env -p 8000:8000 hllama-backend
```

Or run the local stack from `backend/`:

```bash
docker compose up --build
```

This starts `db` and `backend` (the API on `http://localhost:8000`). The
`backend/` directory is bind-mounted, so `uvicorn --reload` picks up code
changes without a rebuild. The bot and the back office have their own compose
files; each connects to this API through `NEAREST_API_URL` /
`NEXT_PUBLIC_API_URL`.

The backend image runs `alembic upgrade head` at startup, then `uvicorn main:app`.

## Deployment

A deployer builds the Docker image, applies the Alembic migrations, and runs
it behind their own reverse proxy or container platform; `backend/deploy/`
holds a generic Helm chart and a `values-dev.yaml` with placeholder values as
a starting point. The repository's CI runs the test suite on every push and
pull request; it does not deploy anywhere on its own.

## Additional documentation

- [Bot conversation profile](docs/BOT_CONVERSATION_PROFILE.md)

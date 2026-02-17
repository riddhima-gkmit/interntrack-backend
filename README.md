# InternTrack

**Multi-tenant internship task tracking platform** — a FastAPI backend for managing organizations (tenants), users, tasks, leave requests, and team collaboration with role-based access control.

---

## Features

- **Multi-tenancy** — Organizations (tenants) with isolated data; tenant self-registration and admin management.
- **Authentication** — JWT access/refresh tokens, email verification, OTP (Redis), forgot-password, invite-based registration.
- **Roles** — `INTERN`, `MENTOR`, `TENANT_ADMIN`, `SUPER_ADMIN` with scoped permissions (own, team, tenant, or platform).
- **Tasks** — Create, assign, track status (`pending` / `in_progress` / `completed`) and priority; task history and comments.
- **Leaves** — Leave requests (sick, vacation, personal, other) with approval workflow.
- **Invitations** — Mentors/admins invite users by email with a role; token-based acceptance and optional email notifications.
- **Dashboard** — User-scoped stats (e.g. tasks, leaves) for the current tenant.
- **API** — REST under `/api/v1`, unified error responses, CORS, request logging, health check at `/health`.

---

## Tech stack

| Layer        | Technology |
|-------------|------------|
| Runtime     | Python 3.13+ |
| Framework   | FastAPI |
| Database    | PostgreSQL (async via **asyncpg**) |
| Migrations  | Alembic |
| Cache / OTP | Redis |
| Auth        | JWT (python-jose), bcrypt |
| Email       | Optional SMTP (aiosmtplib) |
| Package mgr | **uv** (pyproject.toml) |

---

## Prerequisites

- **Python 3.13+**
- **uv** — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **PostgreSQL** — running and a database created (e.g. `interntrack_db`)
- **Redis** — required at startup (OTP and rate limiting)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/InternTrack.git
cd InternTrack
uv sync
```

### 2. Environment variables

Copy the example env and fill in values:

```bash
cp .env.example .env
```

Edit `.env`. Required:

- **DATABASE_URL** — `postgresql+asyncpg://user:password@localhost:5432/interntrack_db`
- **SECRET_KEY** — Min 32 characters; use a strong secret in production.
- **REDIS_URL** — e.g. `redis://localhost:6379/0`
- **CORS_ORIGINS** — e.g. `["*"]` or your frontend origin.
- **FRONTEND_URL** — Used in email links (e.g. `http://localhost:3000`).

Optional (email): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAILS_FROM_EMAIL`, `EMAILS_FROM_NAME`. If not set, verification/invite/forgot-password emails are skipped.

### 3. Database

Create the database (if needed), then run migrations:

```bash
uv run alembic upgrade head
```

### 4. Run the API

```bash
uv run uvicorn app.main:app --reload
```

- API: **http://127.0.0.1:8000**
- Interactive docs: **http://127.0.0.1:8000/docs**
- Health: **http://127.0.0.1:8000/health**

---

## API overview

| Prefix / path | Description |
|---------------|-------------|
| `GET /health` | Health check (no auth) |
| `/api/v1/auth` | Register, login, OTP verify, email verify, forgot-password, refresh, logout |
| `/api/v1/tenants` | Tenant register, list, get, create, update, delete (admin) |
| `/api/v1/users` | Profile (`/me`), list/get/create/update/delete users, invite, restore |
| `/api/v1/tasks` | Tasks CRUD, list filters (status, priority, assignee, owner), task history |
| `/api/v1/tasks/{task_id}/comments` | Comments on a task |
| `/api/v1/users/{user_id}/dashboard` | Dashboard data for a user (tenant-scoped) |
| `/api/v1/leaves` | Leave requests CRUD, filters (type, status, user) |

All `/api/v1` routes (except auth endpoints that are documented as public) require a valid **JWT** in the `Authorization: Bearer <access_token>` header. Tenant context is derived from the token for scoping data.

---

## Project structure

```
InternTrack/
├── app/
│   ├── config/          # Settings, logging
│   ├── constants/       # Auth TTL, limits, messages
│   ├── crud/            # DB access layer
│   ├── database/        # Session, engine, get_db
│   ├── dependencies/    # Auth, tenant, permissions
│   ├── enums/           # Roles, task status/priority, leave type/status, invitation role
│   ├── middleware/      # Request logging
│   ├── models/          # SQLAlchemy models (User, Tenant, Task, Leave, Comment, Invitation, etc.)
│   ├── routers/        # auth, tenants, users, tasks, comments, leaves, dashboard
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # Business logic
│   ├── utils/           # JWT, password, OTP, Redis, exception handlers
│   └── main.py          # FastAPI app, lifespan, routes
├── alembic/             # Migrations
├── .env.example         # Env template
├── pyproject.toml       # Dependencies (uv)
├── GIT_WORKFLOW.md      # Branching and PR workflow
└── TERMINAL_GUIDE.md    # Copy-paste Git commands
```

---

## Environment variables reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL URL; use `postgresql+asyncpg://...` for the app |
| `SECRET_KEY` | Yes | JWT signing key (min 32 chars) |
| `ALGORITHM` | Yes | e.g. `HS256` |
| `ACCESS_EXPIRE_MIN` | Yes | Access token TTL (minutes) |
| `REFRESH_EXPIRE_DAYS` | Yes | Refresh token TTL (days) |
| `REDIS_URL` | Yes | Redis URL (e.g. `redis://localhost:6379/0`) |
| `CORS_ORIGINS` | Yes | JSON list of allowed origins |
| `FRONTEND_URL` | Yes | Frontend base URL (e.g. for email links) |
| `DEBUG` | Yes | Enable SQL echo and extra debug behavior |
| `LOG_LEVEL` | No | e.g. `INFO`, `DEBUG` (default `INFO`) |
| `SMTP_*`, `EMAILS_*` | No | Optional; omit to disable sending emails |

See `.env.example` for the full list and format.

---

## Git and workflow

- **Branching:** `main` (production) ← `dev` ← `feature/*`. See [GIT_WORKFLOW.md](GIT_WORKFLOW.md) for the full workflow.
- **Copy-paste commands:** See [TERMINAL_GUIDE.md](TERMINAL_GUIDE.md) for step-by-step terminal commands (initial push, creating `dev`, feature flow, releases).

---


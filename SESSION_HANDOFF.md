# 🤝 Session Handoff — photos_backend

> **Repo-level handoff.** Only written when a session is focused heavily on this repo.  
> Always read `photos_infra/SESSION_HANDOFF.md` first for project-wide context.
>
> **To resume:** *"Read `photos_backend/SESSION_HANDOFF.md` and the project-level handoff. State the next backend task and the exact file to open."*  
> **To write:** Say *"write handoff"* at end of session.

---

## 🔄 CURRENT STATE
> Overwritten each session. Do not manually edit.

**Last Updated:** 2026-04-18  
**Sprint:** Pre-Sprint 1 (no code written yet)

---

### ⏭️ Resume Here

**Next task:** `S1-001` — Scaffold FastAPI application  
**Depends on:** `photos_infra S1-001` (Docker Compose must be running first)  
**First file to create:** `app/main.py`

**Scaffold order for S1-001:**
1. `requirements.txt` — add fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, pydantic-settings, alembic, python-jose[cryptography], passlib[bcrypt], httpx (test client)
2. `Dockerfile` — python:3.12-slim, non-root user, copy requirements, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
3. `app/config.py` — Pydantic `Settings` class reading all env vars
4. `app/database.py` — SQLAlchemy 2.0 async engine + `AsyncSession` factory
5. `app/main.py` — app factory, CORS, exception handlers, router registration, `/health` endpoint
6. `app/api/deps.py` — `get_db`, `get_current_user`, `get_admin_user` dependencies
7. `tests/conftest.py` — pytest fixtures for async DB session

---

### ✅ Completed This Repo

*No code written yet.*

---

### 🔄 In Progress

*Nothing in progress.*

---

### ⚠️ Backend-Specific Decisions

| Decision | Detail |
|---|---|
| Email service | Stub to `print()` / logging for MVP — no real SMTP. Class exists, just doesn't send. |
| GPS parsing | Store `NULL` for lat/lng if `piexif` GPS edge cases are complex. Parse retroactively later. |
| Error envelope | All errors: `{"error": {"code": "SNAKE_CASE_CODE", "message": "Human string"}}` |
| Exception location | Raise domain exceptions in domain/service layer. `exception_handler` in `main.py` converts to HTTP |
| Async everywhere | All route handlers and service methods that touch DB or I/O must use `async def` |

---

### 🚧 Backend Gotchas

- **Alembic async env**: `env.py` must use `run_sync()` pattern for async engines. Don't use the default Alembic template — it's sync-only. Check Alembic docs for async setup.
- **`asyncpg` vs `psycopg2`**: We use `asyncpg` as the async driver. Connection string uses `postgresql+asyncpg://` prefix.
- **Test DB**: pytest tests use a separate test PostgreSQL database (`TEST_DATABASE_URL` env var). Never run tests against the dev DB.
- **Import order**: Domain models must never import from `app/infrastructure` or `app/api`. Violating this breaks Clean Architecture.

---

### 🗂️ Backend Directory Structure (target layout)

```
app/
  main.py               ← app factory
  config.py             ← Pydantic Settings
  database.py           ← async engine + session
  api/
    deps.py             ← shared FastAPI dependencies
    v1/
      auth.py           ← auth endpoints
      media.py          ← media endpoints
      albums.py         ← album endpoints
      shares.py         ← sharing endpoints
      admin.py          ← admin endpoints
  domain/
    models/             ← SQLAlchemy ORM models (also domain aggregates)
    schemas/            ← Pydantic request/response schemas
    events.py           ← domain events
  services/             ← use case / application layer
  infrastructure/
    repositories/       ← SQLAlchemy repo implementations
    storage/            ← StorageBackend ABC + LocalStorageBackend
    email/              ← EmailService stub
  middleware/           ← CORS, quota enforcement
migrations/             ← Alembic migration versions
tests/
  conftest.py
  api/
  services/
  infrastructure/
```

---

## 📋 SESSION LOG

| # | Date | Summary | Files Modified | Next Up |
|---|---|---|---|---|
| 1 | 2026-04-18 | Repo-level handoff template created. No code yet. | `SESSION_HANDOFF.md` (created) | S1-001 FastAPI scaffold (unblock: infra S1-001 first) |

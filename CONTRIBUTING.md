# Contributing — photos_backend

> FastAPI backend — API, auth, database schema, business logic, and services for Pixel Vault.

---

## Branch Naming

```
<type>/<task-id>-<short-description>
```

**Examples:**
```
feat/S1-001-fastapi-app-scaffold
feat/S1-002-alembic-initial-migration
feat/S1-003-jwt-auth-endpoints
feat/S2-001-admin-user-approval
feat/S2-002-storage-backend-local
feat/S2-003-media-upload-exif-thumbnail
fix/S2-004-timeline-pagination-off-by-one
test/S2-005-album-service-unit-tests
```

**Types:** `feat` | `fix` | `test` | `chore` | `docs` | `refactor`

---

## Commit Convention

```
feat: add FastAPI app factory and Pydantic config (S1-001)
feat: add Alembic initial migration — users, email_tokens, refresh_tokens (S1-002)
feat: implement JWT auth — register, login, verify-email, refresh, logout (S1-003)
feat: add admin user approval endpoints with role guard (S2-001)
feat: implement LocalStorageBackend with StorageBackend ABC (S2-002)
feat: add photo upload with EXIF parsing and Pillow thumbnail generation (S2-003)
fix: resolve quota race condition on concurrent uploads (S2-003)
test: add unit tests for GpsCoordinates value object (S2-003)
chore: add piexif and Pillow to requirements.txt
docs: add API auth guide to docs/
chore: daily sprint update Apr-XX
```

| Prefix | When to use |
|---|---|
| `feat:` | New endpoint, service, model, or domain feature |
| `fix:` | Bug fix in logic, query, or constraint |
| `test:` | Adding or updating tests |
| `chore:` | Dependencies, tooling, config changes |
| `docs:` | Docstrings, README, inline comments |
| `refactor:` | Internal rework with no behaviour change |

---

## Solo Dev Workflow

1. Pick next task from `TASKS.md` (respect dependency order — `S1-002` before `S1-003`)
2. Create branch:
   ```bash
   git checkout -b feat/S1-003-jwt-auth-endpoints
   ```
3. Write code following Clean Architecture layers (Domain → Infrastructure → Service → API)
4. Write tests alongside implementation (not after)
5. Run tests locally:
   ```bash
   pytest tests/ -v --tb=short
   ```
6. Run linter:
   ```bash
   ruff check app/ tests/
   ```
7. Self-review against TASKS.md acceptance criteria
8. Mark task `✅` in `TASKS.md` (move to Done section with date)
9. Commit:
   ```bash
   git add .
   git commit -m "feat: implement JWT auth — register, login, verify-email, refresh, logout (S1-003)"
   ```
10. Update `photos_infra/SPRINT.md` status table
11. Push and open PR:
    ```bash
    git push origin feat/S1-003-jwt-auth-endpoints
    gh pr create --title "feat: implement auth endpoints (S1-003)" --body "Closes task S1-003. All 8 auth endpoints implemented. pytest: 12 passed."
    ```
12. Merge → delete branch

---

## Self-Review Checklist (before merge)

- [ ] All acceptance criteria from `TASKS.md` task verified with manual test or test output
- [ ] `pytest` passes with no failures (`pytest tests/ -v`)
- [ ] `ruff check app/ tests/` passes with no errors
- [ ] No `print()` or `console.log` debug statements left in code
- [ ] No hardcoded secrets, passwords, or connection strings — all via `config.py` / env vars
- [ ] New endpoints are visible in `GET /docs` (Swagger UI)
- [ ] Error responses use the standard envelope: `{"error": {"code": "...", "message": "..."}}`
- [ ] New env vars added to `.env.example` in `photos_infra/`
- [ ] SQLAlchemy models have correct indexes matching LLD §3 Key Indexes
- [ ] Domain invariants enforced in domain layer (not in service or API layer)
- [ ] `TASKS.md` task marked ✅ with completion date
- [ ] `photos_infra/SPRINT.md` status table updated

---

## Architecture Rules

Follow Clean Architecture strictly — outer layers depend on inner layers, never reversed:

```
API Layer (app/api/)         → Service Layer only
Service Layer (app/services/)  → Domain Layer + Repositories (interfaces)
Domain Layer (app/domain/)    → NO external dependencies (no DB, no HTTP)
Infrastructure (app/infrastructure/) → Implements domain interfaces
```

- **Never** import SQLAlchemy models directly in API routers — go through service
- **Never** put business logic in routers — routers call services, services call domain
- **Never** raise `HTTPException` in service or domain layers — raise domain exceptions, let `exception_handler` convert
- **Always** use `async def` for route handlers and service methods that touch DB or I/O
- **Always** inject dependencies via FastAPI `Depends()` — never instantiate services or repos directly in routers

---

## Daily Habit (2 min)

```
1. Open photos_infra/SPRINT.md
2. Update the status table row for photos_backend
3. git add TASKS.md
4. git commit -m "chore: daily sprint update Apr-XX"
5. git push origin main
```

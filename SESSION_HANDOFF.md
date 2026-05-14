# 🤝 Session Handoff — photos_backend

> **Repo-level handoff.** Only written when a session is focused heavily on this repo.  
> Always read `photos_infra/SESSION_HANDOFF.md` first for project-wide context.
>
> **To resume:** _"Read `photos_backend/SESSION_HANDOFF.md` and the project-level handoff. State the next backend task and the exact file to open."_  
> **To write:** Say _"write handoff"_ at end of session.

---

## 🔄 CURRENT STATE

> Overwritten each session. Do not manually edit.

**Last Updated:** 2026-05-14  
**Sprint:** Security Hardening — ALL BACKEND SEC + N-CATEGORY TASKS COMPLETE ✅  
**Tests:** 115/115 passing (was 108 before N-category fixes)

---

### ⏭️ Resume Here

**`photos_backend` security hardening is complete.** 115/115 tests passing.

**Applied this session (2026-05-14) — N-Category Fixes (from Pixel_Vault_Security_Pitfalls_Report_New.md):**

- **N-01** (`main.py`) — Startup validation: rejects default `SECRET_KEY` and keys shorter than 32 chars in production
- **N-02** (`api/deps.py`) — `get_current_user` now does live DB lookup per request; suspended user's access token rejected immediately (closes 15-minute staleness window)
- **N-06** (`docker-compose.yml`, `.env.example`) — Redis `requirepass` wired via `$REDIS_PASSWORD`; backend `REDIS_URL` embeds password
- **N-08** (`domain/models/user.py`, `user_repo.py`, `auth_service.py`, `migrations/0005_hash_email_tokens.py`) — `EmailToken.token` renamed to `token_hash`; all create/lookup sites now use `_hash_token()` SHA-256; Alembic migration 0005 created
- **N-12** (`services/sharing_service.py`) — `create_share()` rejects non-ACTIVE target users with `InvalidStateError`
- **N-13** (`domain/models/user.py`) — `approve()` enforces `email_verified=True`; raises `InvalidStateError("unverified email")` otherwise
- **Tests** (`tests/test_security.py`, `tests/test_admin.py`) — 7 new security tests; `test_approve_pending_user_returns_active` updated to set `email_verified=True`

**Applied previous session (2026-05-13) — Security Hardening:**

All SEC-001 through SEC-017 backend tasks are done per `Pixel Vault Security Pitfalls Report` and `Pixel Vault Security Remediation Plan` (both dated 2026-05-13).

- **SEC-001** — Created `app/services/access_policy.py`: `MediaAccessPolicy` with `can_view_media / can_delete_media / can_view_album / can_modify_album`. `media_service.get_media()` now checks owner OR direct user share.
- **SEC-002** — `LocalStorageBackend._safe_path()`: rejects null bytes, absolute paths, `..` traversal, root escape via `.relative_to()`
- **SEC-003** — `_detect_mime_from_bytes()` pure magic-byte detection (JPEG/PNG/GIF/WebP/HEIC). Canonical MIME taken from bytes, not declared header. MIME spoof rejected.
- **SEC-004** — `Image.MAX_IMAGE_PIXELS = 100_000_000`, dimension guard (12000×12000), `DecompressionBombError` caught in `_generate_thumbnail()`
- **SEC-006** — Quota now reserves `original + 5MB thumbnail estimate` before upload; deducts `original + actual_thumbnail` after success; original cleaned up on failure
- **SEC-007** — CORS restricted to explicit methods/headers; refresh token rotation (old revoked, new issued on every `/auth/refresh`); reuse detection → revoke all sessions for user
- **SEC-010** — `app/infrastructure/logging/security_log.py`: JSON security event logger (`pixelvault.security`) covering auth/media/admin/share events. Integrated into all 4 services.
- **SEC-011** — `app/infrastructure/rate_limiter.py`: `AbstractRateLimiter` / `NoOpRateLimiter` / `InMemoryRateLimiter` / `get_rate_limiter()` FastAPI dep. Redis wiring ready.
- **SEC-012** — Public share links default to 7-day expiry; 30-day max enforced at creation time
- **SEC-015** — `tests/test_security.py`: 13 security regression tests (all passing)
- **SEC-016** — `revoke_all_for_user()` called in `suspend_user()` and `delete_user()`
- **SEC-017** — `AuditLog` model + `AuditLogRepository` + Alembic migration `0004_add_audit_logs`
- **SEC-005/008/009/013/014/018** — N/A for backend (FFmpeg not in MVP; Cloudflare/Nginx/CI handled in infra)

**Before applying migration 0004 locally:**
```bash
docker compose exec backend alembic upgrade head
```

**Next security work:**
- `photos_frontend` — SEC tasks for frontend (XSS, CSP, token handling, etc.)
- `photos_infra` — SEC-008 (Cloudflare Zero Trust admin), SEC-009 (backup restore), SEC-013 (Nginx secure headers)
- `photos_admin_ui` — SEC tasks for admin panel

---

### ✅ Completed This Repo (all tasks)

#### S1-001 — FastAPI Scaffold ✅

- `app/main.py` — app factory, CORS, 7 global exception handlers, router registration, `/health`
- `app/config.py` — Pydantic Settings (all env vars from `.env.example`)
- `app/database.py` — SQLAlchemy 2.0 async engine + `AsyncSession` factory + `get_db` generator
- `app/api/deps.py` — `get_current_user`, `get_admin_user`, `get_storage`, `DB`/`CurrentUser`/`AdminUser`/`Storage` type aliases
- `app/exceptions.py` — full exception hierarchy (Domain → Application → Infrastructure)
- `app/middleware/cors.py` — CORS middleware wired from `allowed_origins_list`
- `requirements.txt`, `Dockerfile`, `.env.example`, `pytest.ini`, `ruff.toml`

#### S1-002 — Alembic + DB Migration ✅

- `migrations/env.py` — async Alembic config; reads `DATABASE_URL` from env; imports all models for autogenerate
- `migrations/versions/0001_initial_users.py` — creates `users`, `email_tokens`, `refresh_tokens` + all indexes
- `app/domain/models/user.py` — `User`, `EmailToken`, `RefreshToken` ORM models + `UserRole`, `UserStatus` (pending/active/suspended/deleted), `EmailTokenType` enums + domain methods (`approve()`, `suspend()`, `activate()`, `soft_delete()`, `can_upload()`)
- `app/domain/schemas/user.py` — `UserResponse`, `AdminStats`, `StorageStats`

#### S1-003 — Auth Endpoints ✅ (9/9 tests)

- `app/api/v1/auth.py` — 8 endpoints: register, login, verify-email, resend-verification, refresh, logout, forgot-password, reset-password
- `app/services/auth_service.py` — `AuthService` with all auth use cases; bcrypt hashing; `_as_utc()` helper for SQLite/PostgreSQL datetime compatibility
- `app/domain/schemas/auth.py` — all auth request/response schemas
- `app/domain/events.py` — domain event dataclasses
- `app/infrastructure/repositories/user_repo.py` — `SQLUserRepository`, `EmailTokenRepository`, `RefreshTokenRepository`
- `app/infrastructure/email/email_service.py` — stdout stub
- `tests/conftest.py` — SQLite in-memory DB, `client` fixture with `get_db` + `get_storage` overrides
- `tests/test_auth.py` — 9 tests

#### S2-001 — Admin Approval Routes ✅ (9/9 tests, extended to 15/15)

- `app/services/admin_service.py` — `AdminService` with `get_pending_users()`, `approve_user()`, `suspend_user()`, `get_stats()`, `activate_user()`, `delete_user()`
- `app/api/v1/admin.py` — endpoints: `GET /admin/users/pending`, `POST /admin/users/{id}/approve`, `POST /admin/users/{id}/suspend`, `GET /admin/stats`, `GET /admin/users`, `GET /admin/users/{id}`, `PUT /admin/users/{id}/quota`, `GET /admin/media`, `DELETE /admin/media/{id}`, `POST /admin/users/{id}/activate`, `DELETE /admin/users/{id}`
- `tests/test_admin.py` — 15 tests (9 original + 6 state machine tests added 2026-04-30)

#### S2-002 — StorageBackend ✅ (12/12 tests)

- `app/infrastructure/storage/base.py` — `StorageBackend` ABC: `save()`, `read()` (async generator), `delete()`, `get_url()`, `exists()`
- `app/infrastructure/storage/local.py` — `LocalStorageBackend` using `asyncio.to_thread`, 64KB chunks
- `tests/infrastructure/test_local_storage.py` — 12 tests

#### S2-003 — Media Upload ✅ (9/9 tests)

- `app/domain/models/media.py` — `Media` ORM model, `MediaType` + `MediaStatus` enums
- `app/domain/schemas/media.py` — `MediaResponse`, `PaginatedMediaResponse`, `TimelineGroupResponse`
- `app/infrastructure/repositories/media_repo.py` — `SQLMediaRepository` with filters + timeline
- `app/middleware/quota.py` — `check_quota()` raises `QuotaExceededError`
- `app/services/media_service.py` — `MediaService` with `handle_upload()` (EXIF parse, Pillow thumbnail, status=ready)
- `app/api/v1/media.py` — `POST /media/upload`
- `migrations/versions/0002_media_albums_shares.py` — creates `media`, `albums`, `album_media`, `shares` tables

#### S2-004 — Media Read Endpoints ✅ (9/9 tests)

- `app/api/v1/media.py` (updated) — `GET /media`, `GET /media/timeline`, `GET /media/{id}/thumbnail`, `GET /media/{id}/stream` (HTTP Range → 206)
- `tests/test_media.py` — 18 tests total

#### S2-005 — Album CRUD ✅ (22/22 tests)

- `app/domain/models/album.py` — `Album` + `AlbumMedia` ORM models; `check_can_add_media()` domain method
- `app/domain/schemas/album.py` — `AlbumCreate`, `AlbumUpdate`, `AddMediaRequest`, `AlbumResponse`, `AlbumDetailResponse`
- `app/infrastructure/repositories/album_repo.py` — `SQLAlbumRepository`; explicit AlbumMedia delete before album delete (SQLite FK compatibility)
- `app/services/album_service.py` — `AlbumService`
- `app/api/v1/albums.py` — 7 endpoints
- `tests/test_albums.py` — 22 tests

#### S2-006 — Sharing Endpoints ✅ (20/20 tests)

- `app/domain/models/share.py` — `Share` ORM model, `ShareType` enum, `is_valid()` (handles naive/aware datetime for SQLite+PostgreSQL)
- `app/domain/schemas/share.py` — `ShareCreate` (model_validator enforces XOR target + user-type recipient), `ShareResponse`, `PublicMediaResponse`, `PublicAlbumResponse`, `PublicShareResponse`
- `app/infrastructure/repositories/share_repo.py` — `SQLShareRepository`
- `app/services/sharing_service.py` — `SharingService`
- `app/api/v1/shares.py` — 4 authed endpoints (`/shares`) + 1 unauthenticated (`/public/{token}`)
- `tests/test_shares.py` — 20 tests

---

### 🔄 In Progress

_Nothing in progress. All backend tasks complete._

---

### ⚠️ Backend-Specific Decisions (for future reference)

| Decision | Detail |
|---|---|
| **bcrypt over passlib** | Switched from `passlib[bcrypt]` to `bcrypt==4.2.1` directly. passlib 1.7.4 is incompatible with bcrypt 4.x on Python 3.13. |
| **`secure=False` in dev** | Refresh cookie sets `secure=settings.app_env != "development"`. In dev/test, `secure=False` so httpOnly cookie works over HTTP. In production always secure. |
| **`_as_utc()` helper** | `auth_service.py` has `_as_utc(dt)` that adds UTC tzinfo to naive datetimes. Needed because SQLite returns naive datetimes; PostgreSQL returns timezone-aware. Same pattern used in `Share.is_valid()`. |
| **`asyncio.to_thread`** | LocalStorageBackend uses `asyncio.to_thread` for file I/O — no `aiofiles` dependency needed. |
| **Enum values_callable** | All ORM Enum columns use `values_callable=lambda e: [x.value for x in e]` to store string values rather than enum names. Matches migration enum definitions. |
| **SQLite FK cascades** | SQLite doesn't enforce FK constraints by default. `album_repo.delete()` and `share_repo.delete()` explicitly delete child rows first. |
| **Route ordering in media.py** | `/upload`, `""`, `/timeline` defined before `/{media_id}/...` to prevent path parameter from capturing static segments. |
| **Storage in tests** | `conftest.py` overrides `get_storage` with `LocalStorageBackend(storage_root=str(tmp_path), ...)` so file I/O uses a temp directory. |

---

### 🚧 Backend Gotchas

- **Alembic needs PostgreSQL running**: `alembic upgrade head` requires the database. Depends on `photos_infra S1-001` (Docker Compose). Test suite runs independently via SQLite.
- **`asyncpg` vs `psycopg2`**: Connection string uses `postgresql+asyncpg://` prefix. Never use `psycopg2` format.
- **Import order / Clean Architecture**: Domain models must never import from `app/infrastructure` or `app/api`.
- **`get_settings()` is cached**: Uses `@lru_cache`. In tests, set env vars before any app import or the cached value won't pick them up.
- **piexif integer keys**: piexif uses integer constant keys (e.g. `piexif.ExifIFD.DateTimeOriginal`), not string keys. `piexif.insert(exif_bytes, img_bytes, output_bytesio)` requires a third `BytesIO` argument when passing bytes.
- **User state machine**: Strict one-way: pending→active (`activate`), active→suspended (`suspend`), suspended→active (`activate`), suspended→deleted (`soft_delete`). Admins cannot be deleted. `deleted` rows stay in DB but are excluded from all admin list views via `.where(User.status != UserStatus.DELETED)` in `get_all_users()`.
- **Soft delete + PG enum**: `deleted` added to `user_status` PostgreSQL enum in migration 0003. PostgreSQL cannot remove enum values — downgrade is a documented no-op.
- **`.gitignore` `/storage/`**: Pattern is anchored to repo root (`/storage/`) not unanchored (`storage/`). Unanchored pattern matched `app/infrastructure/storage/` causing CI `ModuleNotFoundError`.
- **CI job name `backend-ci`**: Job `name:` in `ci-backend.yml` is `backend-ci`. GitHub branch protection check name becomes `backend-ci (Python 3.12)` after matrix expansion.

---

### 🗂️ Backend Directory Structure (final state)

```
app/
  main.py               ✅ app factory, 7 exception handlers, /health
  config.py             ✅ Pydantic Settings
  database.py           ✅ async engine + session
  exceptions.py         ✅ full exception hierarchy
  api/
    deps.py             ✅ get_current_user, get_admin_user, get_storage, type aliases
    v1/
      auth.py           ✅ 8 auth endpoints
      admin.py          ✅ 4 admin endpoints
      media.py          ✅ 5 media endpoints (upload, list, timeline, thumbnail, stream)
      albums.py         ✅ 7 album endpoints
      shares.py         ✅ 4 share endpoints + public router (1 unauthenticated endpoint)
  domain/
    models/
      user.py           ✅ User, EmailToken, RefreshToken + enums
      media.py          ✅ Media + MediaType/MediaStatus enums
      album.py          ✅ Album + AlbumMedia
      share.py          ✅ Share + ShareType enum
    schemas/
      auth.py           ✅
      user.py           ✅
      media.py          ✅
      album.py          ✅
      share.py          ✅
    events.py           ✅
  services/
    auth_service.py     ✅ (SEC-007: refresh rotation + reuse detection; SEC-010: security logging)
    admin_service.py    ✅ (SEC-016: revoke_all_for_user on suspend/delete; SEC-010: logging)
    media_service.py    ✅ (SEC-003: magic bytes; SEC-004: bomb protection; SEC-006: quota fix; SEC-001: policy)
    album_service.py    ✅
    sharing_service.py  ✅ (SEC-012: public share default expiry; SEC-010: logging)
    access_policy.py    ✅ NEW — SEC-001: MediaAccessPolicy (owner + shared-with access)
  infrastructure/
    repositories/
      user_repo.py      ✅ (SEC-007/016: get_by_hash_any, revoke_all_for_user added)
      media_repo.py     ✅
      album_repo.py     ✅
      share_repo.py     ✅
      audit_repo.py     ✅ NEW — SEC-017: AuditLogRepository
    storage/
      base.py           ✅ StorageBackend ABC
      local.py          ✅ SEC-002: _safe_path() path traversal protection
    email/
      email_service.py  ✅ stdout stub
    logging/
      __init__.py       ✅ NEW — package init
      security_log.py   ✅ NEW — SEC-010: structured JSON security event logger
  domain/
    models/
      audit.py          ✅ NEW — SEC-017: AuditLog model + AuditEventType enum
  middleware/
    cors.py             ✅ SEC-007: restricted allow_methods + allow_headers
    quota.py            ✅
  rate_limiter.py       ✅ NEW — SEC-011: AbstractRateLimiter / NoOpRateLimiter / InMemoryRateLimiter
migrations/
  env.py                ✅ async Alembic config
  versions/
    0001_initial_users.py              ✅
    0002_media_albums_shares.py        ✅
    0003_add_deleted_user_status.py    ✅
    0004_add_audit_logs.py             ✅ NEW — SEC-017: audit_logs table
tests/
  conftest.py                          ✅ SQLite in-memory, client + storage fixtures
  test_auth.py                         ✅ 9 tests
  test_admin.py                        ✅ 15 tests
  test_media.py                        ✅ 18 tests (test_upload_updates_user_storage_used updated for SEC-006)
  test_albums.py                       ✅ 22 tests
  test_shares.py                       ✅ 20 tests
  test_security.py                     ✅ NEW — SEC-015: 13 security regression tests
  infrastructure/
    test_local_storage.py              ✅ 12 tests
```

---

## 📋 SESSION LOG

| # | Date | Summary | Files Modified | Next Up |
|---|---|---|---|---|
| 1 | 2026-04-18 | Repo-level handoff template created. No code yet. | `SESSION_HANDOFF.md` (created) | S1-001 FastAPI scaffold |
| 2 | 2026-04-18 | Sprint 1 complete: S1-001 scaffold, S1-002 Alembic+migration, S1-003 auth endpoints. 9/9 tests passing. Fixed .gitignore. | 30+ files created | S2-001 Admin approval routes |
| 3 | 2026-04-23 | S2-001 complete: AdminService, 4 admin endpoints, stats. 18/18 tests. | admin_service.py, admin.py, user_repo.py, user.py (schemas), main.py, test_admin.py | S2-002 Storage |
| 4 | 2026-04-23 | Sprint 2 complete: S2-002 through S2-006 all implemented. StorageBackend, media upload+EXIF+thumbnails, media read/stream/range, album CRUD, sharing with public links. 89/89 tests passing. | 25+ files created/updated | photos_infra S1-001 |
| 5 | 2026-04-27 | Full E2E testing (37 steps via Postman). Fixed [EMAIL STUB] logging by adding explicit StreamHandler to app logger in main.py. Confirmed: auth flow, admin routes, media upload+EXIF+thumbnail, HTTP Range 206, album CRUD, share + public link all working. Wiped test data after session. | main.py, DEPLOYMENT_TESTING.md | photos_infra S2-001–S2-004 + photos_frontend S1-001 + photos_admin_ui S1-001 |
| 6 | 2026-04-28 | No backend changes. Session focused on photos_frontend Sprint 1 (all 6 tasks complete). Backend remains 89/89 tests passing and ready for frontend integration. | — | No further backend work needed for MVP |
| 7 | 2026-04-30 | User state machine: activate (pending/suspended→active) + soft delete (suspended→deleted). New routes POST /activate + DELETE /{id} (204). Migration 0003 (ALTER TYPE user_status ADD VALUE 'deleted'). get_all_users() excludes deleted. 6 new tests → 95/95. Fixed .gitignore /storage/ anchor (CI ModuleNotFoundError). Renamed CI job to backend-ci. All ruff lint+format+type-check clean. | user.py (DELETED enum + activate/soft_delete), admin_service.py, admin.py, user_repo.py, 0003_add_deleted_user_status.py, test_admin.py, .gitignore, ci-backend.yml, ruff.toml | Apply migration 0003 locally: docker compose exec backend alembic upgrade head |
| 8 | 2026-05-13 | Security hardening complete — all backend SEC tasks done before first deployment. SEC-001: MediaAccessPolicy (IDOR prevention). SEC-002: _safe_path() path traversal. SEC-003: magic-byte MIME detection. SEC-004: decompression bomb protection. SEC-006: quota pre-reserve + actual deduct. SEC-007: CORS hardening + refresh token rotation + reuse-detection (revoke all sessions). SEC-010: structured JSON security logger (pixelvault.security). SEC-011: AbstractRateLimiter / InMemoryRateLimiter / NoOpRateLimiter. SEC-012: public share 7-day default + 30-day max. SEC-015: 13 security regression tests. SEC-016: revoke_all_for_user on suspend + delete. SEC-017: AuditLog model + AuditLogRepository + migration 0004. Tests: 95→108/108 passing. | app/services/access_policy.py (NEW), app/infrastructure/storage/local.py, app/services/media_service.py, app/exceptions.py, app/middleware/cors.py, app/main.py, app/infrastructure/repositories/user_repo.py, app/services/auth_service.py, app/api/v1/auth.py, app/services/admin_service.py, app/services/sharing_service.py, app/infrastructure/logging/security_log.py (NEW), app/infrastructure/logging/__init__.py (NEW), app/infrastructure/rate_limiter.py (NEW), app/domain/models/audit.py (NEW), app/infrastructure/repositories/audit_repo.py (NEW), migrations/versions/0004_add_audit_logs.py (NEW), tests/test_security.py (NEW), tests/test_media.py | Apply migration 0004 before first deploy. Next: photos_frontend SEC tasks (XSS, CSP, token handling) |
| 9 | 2026-05-14 | N-category fixes from expanded security report. N-01: startup secret key validation. N-02: live DB check in get_current_user (closes 15-min suspended-user window). N-06: Redis requirepass. N-08: EmailToken column token→token_hash + migration 0005. N-12: create_share rejects non-ACTIVE targets. N-13: approve() enforces email_verified. 7 new tests (20 security tests total). test_admin.py updated for N-13. Tests: 108→115/115 passing. | app/main.py, app/api/deps.py, photos_infra/docker-compose.yml, photos_infra/.env.example, app/domain/models/user.py, app/infrastructure/repositories/user_repo.py, app/services/auth_service.py, migrations/versions/0005_hash_email_tokens.py (NEW), app/services/sharing_service.py, tests/test_security.py, tests/test_admin.py | Apply migration 0005 before deploy. Deploy when ready. |

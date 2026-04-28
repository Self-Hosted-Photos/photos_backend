# photos_backend — Sprint Task Board

> Last updated: 2026-04-23  
> Sprint 1: Apr 21–27 | Sprint 2: Apr 28–May 4 | MVP: May 4

---

## 🏃 Sprint 1 (Apr 21–27) — Auth + User system fully working with JWT and admin approval flow

### Done ✅

- [x] **[S1-001]** `Scaffold FastAPI application (app factory, config, database, deps)` · `size: M` · `~8h`
  - **What**: Create the full FastAPI application skeleton following the Clean Architecture layout from LLD.md §2. Includes: `app/main.py` (app factory, CORS middleware, exception handlers, router registration), `app/config.py` (Pydantic Settings reading from `.env`), `app/database.py` (SQLAlchemy 2.0 async engine + `AsyncSession` factory), `app/api/deps.py` (shared `get_db`, `get_current_user`, `get_admin_user` dependencies), `requirements.txt`, and `Dockerfile` using Python 3.12-slim base.
  - **Files**: `app/main.py`, `app/config.py`, `app/database.py`, `app/api/deps.py`, `requirements.txt`, `Dockerfile`, `.env.example`
  - **LLD ref**: Backend Module Structure (LLD.md §2), Clean Architecture (LLD.md §1)
  - **Done when**: `uvicorn app.main:app --reload` starts without error; `GET /docs` returns Swagger UI (200); CORS headers present on requests from `localhost:5173`; `pytest` discovers test directory and runs (0 tests, no errors)
  - **Depends on**: photos_infra S1-001 (Docker Compose running PostgreSQL)

- [x] **[S1-002]** `Alembic setup + initial DB migration (users, email_tokens, refresh_tokens)` · `size: M` · `~8h`
  - **What**: Configure Alembic for async SQLAlchemy, create the first migration creating three tables: `users` (all fields per LLD §3 including `storage_used_bytes`, `storage_quota_bytes`, `status`, `role`), `email_tokens`, and `refresh_tokens`. Add all indexes from LLD §3 Key Indexes (`idx_users_email`, `idx_users_oauth`, `idx_users_status`, `idx_refresh_tokens_hash`). Write the SQLAlchemy ORM model for `User` with domain-level invariant comments.
  - **Files**: `migrations/env.py`, `migrations/versions/0001_initial_users.py`, `app/domain/models/user.py`, `app/domain/schemas/user.py`
  - **LLD ref**: Data Models (LLD.md §3), Key Indexes (LLD.md §3), User Aggregate (LLD.md §4)
  - **Done when**: `alembic upgrade head` runs without error; `\dt` in psql shows `users`, `email_tokens`, `refresh_tokens`; `alembic downgrade -1` cleanly drops tables
  - **Depends on**: S1-001

- [x] **[S1-003]** `Implement Auth endpoints (register, login, JWT issue, email verify, refresh, logout)` · `size: L` · `~16h`
  - **What**: Implement the full authentication flow per LLD §5 and ADR-003. Includes: `AuthService` with all use cases, `app/api/v1/auth.py` router with all 8 endpoints. Key behaviours: (1) register creates user with `status=pending`, `email_verified=false`, dispatches verification email; (2) login validates credentials, checks user is `active`, issues 15-min access JWT (HS256, `user_id`+`role`+`email` claims) + stores 7-day refresh token hash in DB, sets httpOnly refresh cookie; (3) verify-email activates `email_verified=true`; (4) refresh validates token hash in DB + not-revoked → issues new access token; (5) logout deletes refresh token from DB. Add `EmailService` stub (log to stdout for MVP). Add global exception handlers for `QuotaExceededError`, `AuthorizationError`, `ResourceNotFoundError`.
  - **Files**: `app/api/v1/auth.py`, `app/services/auth_service.py`, `app/domain/schemas/auth.py`, `app/infrastructure/repositories/user_repo.py`, `app/infrastructure/email/email_service.py`, `app/middleware/cors.py`, `app/domain/events.py`
  - **LLD ref**: Auth Endpoints (LLD.md §5), JWT lifecycle (ADR-003), Exception Hierarchy (LLD.md §6), Flow 3 (LLD.md §7)
  - **Depends on**: S1-001, S1-002

---

## 🏃 Sprint 2 (Apr 28–May 4) — Media upload, photo thumbnails, albums, and sharing delivered end-to-end

### Done ✅

- [x] **[S2-001]** `Implement Admin user approval routes` · `size: S` · `~4h`
  - **What**: Create `app/api/v1/admin.py` with the admin approval endpoints and `app/services/admin_service.py`. Implement: `GET /admin/users/pending`, `POST /admin/users/{id}/approve` (calls `user.approve()` domain method → saves → emails user), `POST /admin/users/{id}/suspend`, `GET /admin/stats`. All routes protected by `get_admin_user` dependency from `deps.py`. Emit `UserApprovedEvent` on approval.
  - **Files**: `app/api/v1/admin.py`, `app/services/admin_service.py`
  - **LLD ref**: Admin Endpoints (LLD.md §5), Admin Approval Flow (LLD.md §7 Flow 3), User Aggregate (LLD.md §4)
  - **Depends on**: S1-001, S1-002, S1-003

- [x] **[S2-002]** `Implement StorageBackend ABC + LocalStorageBackend` · `size: M` · `~8h`
  - **What**: Implement the storage abstraction layer per ADR-004. `StorageBackend` ABC defines `save()`, `read()` (async generator), `delete()`, `get_url()`, `exists()`. `LocalStorageBackend` implements all methods using `asyncio.to_thread` for non-blocking I/O. Wire into `app/api/deps.py` as `Storage` type alias. Write unit tests with temp directory fixtures.
  - **Files**: `app/infrastructure/storage/base.py`, `app/infrastructure/storage/local.py`, `tests/infrastructure/test_local_storage.py`
  - **LLD ref**: StorageBackend ABC (ADR-004)
  - **Depends on**: S1-001

- [x] **[S2-003]** `Implement Media upload (photos) + EXIF parsing + Pillow thumbnail generation` · `size: M` · `~8h`
  - **What**: Full photo upload flow. `MediaService.handle_upload()`: validate MIME type, check quota, save to storage, insert media row, parse EXIF (piexif) for `captured_at` + GPS coordinates, generate 320×320 JPEG thumbnail with Pillow (centre-crop), set `status=ready`. Migration for `media`, `albums`, `album_media`, `shares` tables.
  - **Files**: `app/api/v1/media.py`, `app/services/media_service.py`, `app/domain/models/media.py`, `app/domain/schemas/media.py`, `app/infrastructure/repositories/media_repo.py`, `app/middleware/quota.py`, `migrations/versions/0002_media_albums_shares.py`
  - **LLD ref**: Media upload flow (LLD.md §7 Flow 1), Media Aggregate (LLD.md §4)
  - **Depends on**: S2-001, S2-002

- [x] **[S2-004]** `Implement Media listing, timeline grouping, and thumbnail/stream endpoints` · `size: S` · `~4h`
  - **What**: `GET /media` (paginated, date + location-bounds filters), `GET /media/timeline` (grouped by month/year), `GET /media/{id}/thumbnail` (stream JPEG), `GET /media/{id}/stream` (stream original with HTTP Range support, returns 206).
  - **Files**: `app/api/v1/media.py` (updated), `app/infrastructure/repositories/media_repo.py` (updated)
  - **LLD ref**: MediaRepository (LLD.md §4), Media Endpoints (LLD.md §5)
  - **Depends on**: S2-003

- [x] **[S2-005]** `Implement Album CRUD endpoints` · `size: S` · `~4h`
  - **What**: All 7 album endpoints. `AlbumService` enforces ownership invariants. `SQLAlbumRepository` with explicit AlbumMedia delete before album delete (SQLite FK compatibility). `GET /albums/{id}` returns full media list.
  - **Files**: `app/api/v1/albums.py`, `app/services/album_service.py`, `app/domain/models/album.py`, `app/domain/schemas/album.py`, `app/infrastructure/repositories/album_repo.py`
  - **LLD ref**: Album Aggregate (LLD.md §4), Album Endpoints (LLD.md §5)
  - **Depends on**: S2-003

- [x] **[S2-006]** `Implement Sharing endpoints (user-to-user + public link resolution)` · `size: S` · `~4h`
  - **What**: All 5 share endpoints + unauthenticated `GET /public/{token}`. `SharingService` enforces: exactly one target (media XOR album), cannot share with yourself, public token is UUID4. Expired shares return 404. `PublicShareResponse` wraps media or album data without owner fields.
  - **Files**: `app/api/v1/shares.py`, `app/services/sharing_service.py`, `app/domain/models/share.py`, `app/domain/schemas/share.py`, `app/infrastructure/repositories/share_repo.py`
  - **LLD ref**: Share Aggregate (LLD.md §4), Share Endpoints (LLD.md §5), Public Share Flow (LLD.md §7 Flow 2)
  - **Depends on**: S2-004, S2-005

---

## 📦 Post-MVP Backlog

- [ ] **[BACKLOG-001]** `FFmpeg + Celery worker for video transcoding` · reason: Photos are MVP; video transcoding adds server complexity (ADR-007) — defer to post-MVP sprint
- [ ] **[BACKLOG-002]** `OAuth2 login (Google/GitHub)` · reason: Email/password auth is sufficient for admin-gated MVP; OAuth reduces friction but isn't a blocker (ADR-003)
- [ ] **[BACKLOG-003]** `Password reset flow (forgot/reset endpoints)` · reason: Admin can manually reset during MVP; full self-serve reset is post-MVP
- [ ] **[BACKLOG-004]** `User profile update + avatar upload (PUT /users/me)` · reason: Read-only profile sufficient for MVP; update is a day-2 feature
- [ ] **[BACKLOG-005]** `GET /media/map endpoint` · reason: Map view is a Phase 2 UI feature; GPS data is captured at upload already, so map endpoint can be added without schema changes
- [ ] **[BACKLOG-006]** `Full admin moderation routes (GET /admin/media, DELETE /admin/media/{id})` · reason: Basic user approval covers MVP admin needs; content moderation added in post-MVP sprint
- [ ] **[BACKLOG-007]** `EXIF metadata strip for public shares` · reason: Functional photos MVP doesn't require privacy-stripping; add before enabling public sharing widely

---

## 📊 Capacity Summary

| Sprint | Tasks | Est. Hours | Capacity | Status |
|---|---|---|---|---|
| Sprint 1 | 3 tasks | 32h | 32h | ✅ Done |
| Sprint 2 | 6 tasks | 32h | 32h | ✅ Done |

---

## 🔗 Cross-Repo Dependencies

| This Task | Depends On | Repo |
|---|---|---|
| S1-001 (scaffold) | photos_infra S1-001 (Docker Compose + PostgreSQL running) | photos_infra |
| S2-002 (storage) | photos_infra S1-006 (init-storage.sh has created /storage dirs) | photos_infra |
| photos_frontend S1-003 (API client) | S1-001, S1-003 (auth endpoints live) | photos_backend |
| photos_frontend S2-001 (upload) | S2-003 (upload endpoint live) | photos_backend |
| photos_admin_ui S1-004 (pending users) | S2-001 (admin approval routes live) | photos_backend |

# photos_backend — Sprint Task Board

> Last updated: April 18, 2026  
> Sprint 1: Apr 21–27 | Sprint 2: Apr 28–May 4 | MVP: May 4

---

## 🏃 Sprint 1 (Apr 21–27) — Auth + User system fully working with JWT and admin approval flow

### In Progress
<!-- Move tasks here when you start them -->

### Todo

- [ ] **[S1-001]** `Scaffold FastAPI application (app factory, config, database, deps)` · `size: M` · `~8h`
  - **What**: Create the full FastAPI application skeleton following the Clean Architecture layout from LLD.md §2. Includes: `app/main.py` (app factory, CORS middleware, exception handlers, router registration), `app/config.py` (Pydantic Settings reading from `.env`), `app/database.py` (SQLAlchemy 2.0 async engine + `AsyncSession` factory), `app/api/deps.py` (shared `get_db`, `get_current_user`, `get_admin_user` dependencies), `requirements.txt`, and `Dockerfile` using Python 3.12-slim base.
  - **Files**: `app/main.py`, `app/config.py`, `app/database.py`, `app/api/deps.py`, `requirements.txt`, `Dockerfile`, `.env.example`
  - **LLD ref**: Backend Module Structure (LLD.md §2), Clean Architecture (LLD.md §1)
  - **Done when**: `uvicorn app.main:app --reload` starts without error; `GET /docs` returns Swagger UI (200); CORS headers present on requests from `localhost:5173`; `pytest` discovers test directory and runs (0 tests, no errors)
  - **Depends on**: photos_infra S1-001 (Docker Compose running PostgreSQL)

- [ ] **[S1-002]** `Alembic setup + initial DB migration (users, email_tokens, refresh_tokens)` · `size: M` · `~8h`
  - **What**: Configure Alembic for async SQLAlchemy, create the first migration creating three tables: `users` (all fields per LLD §3 including `storage_used_bytes`, `storage_quota_bytes`, `status`, `role`), `email_tokens`, and `refresh_tokens`. Add all indexes from LLD §3 Key Indexes (`idx_users_email`, `idx_users_oauth`, `idx_users_status`, `idx_refresh_tokens_hash`). Write the SQLAlchemy ORM model for `User` with domain-level invariant comments.
  - **Files**: `migrations/env.py`, `migrations/versions/0001_initial_users.py`, `app/domain/models/user.py`, `app/domain/schemas/user.py`
  - **LLD ref**: Data Models (LLD.md §3), Key Indexes (LLD.md §3), User Aggregate (LLD.md §4)
  - **Done when**: `alembic upgrade head` runs without error; `\dt` in psql shows `users`, `email_tokens`, `refresh_tokens`; `\d users` shows all columns including `latitude`, `longitude` fields (added early to avoid future migration churn); `alembic downgrade -1` cleanly drops tables
  - **Depends on**: S1-001

- [ ] **[S1-003]** `Implement Auth endpoints (register, login, JWT issue, email verify, refresh, logout)` · `size: L` · `~16h`
  - **What**: Implement the full authentication flow per LLD §5 and ADR-003. Includes: `AuthService` with all use cases, `app/api/v1/auth.py` router with all 8 endpoints. Key behaviours: (1) register creates user with `status=pending`, `email_verified=false`, dispatches verification email; (2) login validates credentials, checks user is `active`, issues 15-min access JWT (HS256, `user_id`+`role`+`email` claims) + stores 7-day refresh token hash in DB, sets httpOnly refresh cookie; (3) verify-email activates `email_verified=true`; (4) refresh validates token hash in DB + not-revoked → issues new access token; (5) logout deletes refresh token from DB. Add `EmailService` stub (log to stdout for MVP). Add global exception handlers for `QuotaExceededError`, `AuthorizationError`, `ResourceNotFoundError`.
  - **Files**: `app/api/v1/auth.py`, `app/services/auth_service.py`, `app/domain/schemas/auth.py`, `app/infrastructure/repositories/user_repo.py`, `app/infrastructure/email/email_service.py`, `app/middleware/cors.py`, `app/domain/events.py`
  - **LLD ref**: Auth Endpoints (LLD.md §5), JWT lifecycle (ADR-003), Exception Hierarchy (LLD.md §6), Flow 3 (LLD.md §7)
  - **Done when**: `POST /auth/register` returns 201 with `status=pending`; `POST /auth/login` with valid active user returns `access_token` + sets `refresh_token` cookie; `GET /auth/verify-email?token=X` returns 200 and user.email_verified=true; `POST /auth/refresh` with valid cookie returns new access token; `POST /auth/logout` removes refresh token from DB; all 8 endpoints visible in `/docs`; pytest tests cover all happy paths and key error cases (wrong password, pending user login, expired token)
  - **Depends on**: S1-001, S1-002

### Done ✅
<!-- Move completed tasks here with completion date -->

---

## 🏃 Sprint 2 (Apr 28–May 4) — Media upload, photo thumbnails, albums, and sharing delivered end-to-end

### Todo

- [ ] **[S2-001]** `Implement Admin user approval routes` · `size: S` · `~4h`
  - **What**: Create `app/api/v1/admin.py` with the admin approval endpoints and `app/services/admin_service.py`. Implement: `GET /admin/users/pending`, `POST /admin/users/{id}/approve` (calls `user.approve()` domain method → saves → emails user), `POST /admin/users/{id}/suspend`, `GET /admin/stats`. All routes protected by `get_admin_user` dependency from `deps.py`. Emit `UserApprovedEvent` on approval.
  - **Files**: `app/api/v1/admin.py`, `app/services/admin_service.py`
  - **LLD ref**: Admin Endpoints (LLD.md §5), Admin Approval Flow (LLD.md §7 Flow 3), User Aggregate (LLD.md §4)
  - **Done when**: Non-admin JWT gets 403 on all `/admin/*` routes; admin JWT can list pending users, approve one (status changes to `active`), suspend one (returns 422 if target is admin); `GET /admin/stats` returns user counts and storage totals
  - **Depends on**: S1-001, S1-002, S1-003

- [ ] **[S2-002]** `Implement StorageBackend ABC + LocalStorageBackend` · `size: M` · `~8h`
  - **What**: Implement the storage abstraction layer per ADR-004. `StorageBackend` ABC defines `save()`, `read()` (async generator), `delete()`, `get_url()`. `LocalStorageBackend` implements all methods using the `/storage/originals/`, `/transcoded/`, `/thumbnails/` directory structure. Store files as `{user_id}/{media_id}.{ext}`. Inject via FastAPI dependency. Wire into `app/config.py` with `STORAGE_BACKEND=local` env var (future: `s3`). Write unit tests with temp directory fixtures.
  - **Files**: `app/infrastructure/storage/base.py`, `app/infrastructure/storage/local.py`, `tests/infrastructure/test_local_storage.py`
  - **LLD ref**: StorageBackend ABC (ADR-004), Directory Structure (ADR-004 §Directory Structure)
  - **Done when**: Unit tests pass for save/read/delete/get_url with a temp directory; `LocalStorageBackend.save()` writes a file; `read()` streams bytes back correctly; `delete()` removes file and returns None; `get_url()` returns correct relative path
  - **Depends on**: S1-001

- [ ] **[S2-003]** `Implement Media upload (photos) + EXIF parsing + Pillow thumbnail generation` · `size: M` · `~8h`
  - **What**: Implement the full photo upload flow per LLD §7 Flow 1. Create `MediaService.handle_upload()`: validate MIME type, check quota (`can_upload()`), generate UUID4 media_id, save to `LocalStorageBackend`, insert media row with `status=uploading`, parse EXIF with `piexif` to extract `captured_at` (DateTimeOriginal) and GPS coordinates using `GpsCoordinates.from_exif()` value object, generate 320×320 JPEG thumbnail with Pillow (maintain aspect ratio, centre-crop), update media `status=ready`. Create all DB migration for `media`, `album_media`, `shares` tables. Add quota enforcement middleware.
  - **Files**: `app/api/v1/media.py`, `app/services/media_service.py`, `app/domain/models/media.py`, `app/domain/schemas/media.py`, `app/infrastructure/repositories/media_repo.py`, `app/middleware/quota.py`, `migrations/versions/0002_media_albums_shares.py`
  - **LLD ref**: Media upload flow (LLD.md §7 Flow 1), Media Aggregate (LLD.md §4), GpsCoordinates VO (LLD.md §4), Media Endpoints (LLD.md §5)
  - **Done when**: `POST /media/upload` with a JPEG returns 202; media row in DB has `status=ready`; thumbnail file exists at `storage/thumbnails/{user_id}/{media_id}.jpg`; EXIF datetime parsed into `captured_at`; GPS parsed if present; uploading a file that would exceed quota returns 422 `QUOTA_EXCEEDED`
  - **Depends on**: S2-001, S2-002

- [ ] **[S2-004]** `Implement Media listing, timeline grouping, and thumbnail/stream endpoints` · `size: S` · `~4h`
  - **What**: Add remaining media read endpoints. `GET /media`: paginated list with optional date and bounding-box location filters (backed by `idx_media_owner_date` and `idx_media_owner_location` indexes). `GET /media/timeline`: grouped by month/year using `MediaRepository.get_timeline_groups()`. `GET /media/{id}/thumbnail`: stream thumbnail file with correct MIME type. `GET /media/{id}/stream`: stream original file using HTTP range request support (`StreamingResponse` with `Range` header handling).
  - **Files**: `app/api/v1/media.py` (update), `app/infrastructure/repositories/media_repo.py` (update)
  - **LLD ref**: MediaRepository.get_timeline_groups (LLD.md §4), Media Endpoints (LLD.md §5), get_by_location_bounds (LLD.md §4)
  - **Done when**: `GET /media` returns paginated JSON with `meta.total`; `GET /media/timeline` returns month-grouped array; `GET /media/{id}/thumbnail` streams JPEG with `Content-Type: image/jpeg`; providing partial location bounds (e.g. only `lat_min`) returns 400; range requests return 206 Partial Content
  - **Depends on**: S2-003

- [ ] **[S2-005]** `Implement Album CRUD endpoints` · `size: S` · `~4h`
  - **What**: Implement all 7 album endpoints. `AlbumService` enforces ownership invariants from the `Album` aggregate (cannot add another user's media, cannot add media in non-ready status). Include `AlbumRepository` with paginated media fetch. Wire database migration for `albums` and `album_media` tables (included in S2-003 migration or separate).
  - **Files**: `app/api/v1/albums.py`, `app/services/album_service.py`, `app/domain/models/album.py`, `app/domain/schemas/album.py`, `app/infrastructure/repositories/album_repo.py`
  - **LLD ref**: Album Aggregate (LLD.md §4), Album Endpoints (LLD.md §5)
  - **Done when**: All 7 album endpoints return correct status codes; adding another user's media returns 403; adding unprocessed media returns 422; deleting an album removes the album row but not the media rows; GET /albums/{id} returns album with its media list
  - **Depends on**: S2-003

- [ ] **[S2-006]** `Implement Sharing endpoints (user-to-user + public link resolution)` · `size: S` · `~4h`
  - **What**: Implement all 5 share endpoints + public link resolution. `ShareService` enforces `Share` aggregate invariants (target must be media OR album not both; cannot share with yourself; public token is UUID4). `GET /public/{token}` is unauthenticated — resolves share, checks validity (not expired), returns `PublicMediaResponse` or `PublicAlbumResponse` (strips owner data). Expired shares return 404 (no info leak per LLD §7 Flow 2).
  - **Files**: `app/api/v1/shares.py`, `app/services/sharing_service.py`, `app/domain/models/share.py`, `app/domain/schemas/share.py`, `app/infrastructure/repositories/share_repo.py`
  - **LLD ref**: Share Aggregate (LLD.md §4), Share Endpoints (LLD.md §5), Public Share Flow (LLD.md §7 Flow 2)
  - **Done when**: `POST /shares` with `share_type=public_link` creates share with UUID token; `GET /public/{token}` without auth returns media data; expired share returns 404; sharing with yourself returns 422; revoking share via DELETE removes DB row; `GET /shares/with-me` lists shares received by current user
  - **Depends on**: S2-004, S2-005

### Done ✅

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
| Sprint 1 | 3 tasks | 32h | 32h | 🟢 OK |
| Sprint 2 | 6 tasks | 32h | 32h | 🟢 OK |

---

## 🔗 Cross-Repo Dependencies

| This Task | Depends On | Repo |
|---|---|---|
| S1-001 (scaffold) | photos_infra S1-001 (Docker Compose + PostgreSQL running) | photos_infra |
| S2-002 (storage) | photos_infra S1-006 (init-storage.sh has created /storage dirs) | photos_infra |
| photos_frontend S1-003 (API client) | S1-001, S1-003 (auth endpoints live) | photos_backend |
| photos_frontend S2-001 (upload) | S2-003 (upload endpoint live) | photos_backend |
| photos_admin_ui S1-004 (pending users) | S2-001 (admin approval routes live) | photos_backend |

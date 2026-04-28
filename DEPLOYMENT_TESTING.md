# Pixel Vault — E2E Testing Guide

> **Canonical copy lives in `photos_infra/DEPLOYMENT_TESTING.md`.**
> This copy is kept here so the guide is accessible when working inside the backend repo.
> **Last synced:** 2026-04-27

---

## Current State (as of 2026-04-27)

| Item | Status |
|---|---|
| Docker stack (nginx, backend, postgres, redis) | ✅ Running |
| `photos_infra/.env` | ✅ Configured |
| `photos_backend/.venv` | ✅ Installed (Python 3.12) |
| Migration 0001 — users, email_tokens, refresh_tokens | ✅ Applied |
| Migration 0002 — media, albums, album_media, shares | ❌ Not applied — **do this first** |
| `/storage/originals`, `/storage/thumbnails` | ❌ Not created — **do this second** |

---

## Postman Environment Setup

Create a Postman environment called **Pixel Vault Local** with these variables before starting:

| Variable | Value | Updated when |
|---|---|---|
| `base_url` | `http://localhost` | Never changes |
| `admin_token` | _(empty)_ | After admin login |
| `access_token` | _(empty)_ | After user login |
| `media_id` | _(empty)_ | After photo upload |
| `album_id` | _(empty)_ | After create album |
| `share_id` | _(empty)_ | After create share |
| `share_token` | _(empty)_ | After create public share |

All authenticated requests need this header:
```
Authorization: Bearer {{access_token}}
```
(swap `access_token` for `admin_token` on admin routes)

---

## Part 1 — Pre-flight Checks

### Step 1 — Confirm all containers are running

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Expected — all four showing `Up`:**
```
photos_infra-nginx-1     Up    0.0.0.0:80->80/tcp
photos_infra-backend-1   Up    0.0.0.0:8000->8000/tcp
photos_infra-postgres-1  Up    0.0.0.0:5432->5432/tcp
photos_infra-redis-1     Up    0.0.0.0:6379->6379/tcp
```

If any container is not running:
```bash
cd /path/to/photos_infra
docker compose up -d
```

---

### Step 2 — Run the full test suite

```bash
cd /path/to/photos_backend
source .venv/bin/activate
pytest --tb=short -q
```

**Expected:** `89 passed` — if any fail, stop and fix before continuing.

---

### Step 3 — Run the linter

```bash
# Still inside photos_backend with venv active
ruff check .
ruff format --check .
```

**Expected:** no output, both exit 0.

---

## Part 2 — Apply Migration 0002

Migration 0001 (users/email_tokens/refresh_tokens) is already applied.
Migration 0002 (media, albums, album_media, shares) has not been applied yet.

> Alembic must run inside the backend container — the hostname `postgres` only resolves on the Docker internal network, not from your Mac.

### Step 4 — Apply migration 0002

```bash
docker exec photos_infra-backend-1 alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, media albums shares
```

### Step 5 — Verify all 8 tables exist

```bash
docker exec photos_infra-postgres-1 psql -U pixelvault -d pixelvault -c "\dt"
```

**Expected:**
```
 public | alembic_version | table | pixelvault
 public | album_media     | table | pixelvault
 public | albums          | table | pixelvault
 public | email_tokens    | table | pixelvault
 public | media           | table | pixelvault
 public | refresh_tokens  | table | pixelvault
 public | shares          | table | pixelvault
 public | users           | table | pixelvault
```

---

## Part 3 — Initialise Storage Directories

The `/storage` volume exists but its subdirectories have not been created yet.

> **macOS note:** `storage:` is a Docker **named volume**, not a bind mount to a host path.
> On macOS, named volumes live inside Docker Desktop's Linux VM — the macOS filesystem
> cannot reach them. Running `sudo bash scripts/init-storage.sh` will fail with
> `mkdir: /storage: Read-only file system`.
>
> `init-storage.sh` is only for Linux servers where `/storage` is a real host directory.
> On macOS, create the subdirectories from inside the running container instead (Step 6 below).

### Step 6 — Create storage subdirectories (macOS)

```bash
docker exec -u root photos_infra-backend-1 mkdir -p /storage/originals /storage/transcoded /storage/thumbnails
docker exec -u root photos_infra-backend-1 chown -R 1001:1001 /storage
docker exec -u root photos_infra-backend-1 chmod 750 /storage
```

### Step 6 (Linux server alternative) — Run init-storage.sh

```bash
cd /path/to/photos_infra
sudo bash scripts/init-storage.sh
```

### Step 7 — Verify inside the container

```bash
docker exec photos_infra-backend-1 find /storage -type d
```

**Expected:**
```
/storage
/storage/originals
/storage/transcoded
/storage/thumbnails
```

---

## Part 4 — Health Check

### Step 8 — Hit the health endpoint through nginx

```bash
curl -i http://localhost/health
```

**Expected:**
```
HTTP/1.1 200 OK
{"status":"ok"}
```

You can also open `http://localhost/docs` in your browser to see the full Swagger UI.

---

## Part 5 — Create the Admin Account

Admin accounts are provisioned manually (no public register endpoint for admins).

### Step 9 — Generate a bcrypt hash for the admin password

```bash
cd /path/to/photos_backend
source .venv/bin/activate
python3 -c "import bcrypt; print(bcrypt.hashpw(b'AdminPass123!', bcrypt.gensalt()).decode())"
```

Copy the full output (starts with `$2b$12$...`).

### Step 10 — Insert the admin user

Replace `<HASH>` with the output from Step 9:

```bash
docker exec photos_infra-postgres-1 psql -U pixelvault -d pixelvault -c "
INSERT INTO users (
  id, email, password_hash, full_name, role, status, email_verified,
  storage_used_bytes, storage_quota_bytes, created_at, updated_at
) VALUES (
  gen_random_uuid(),
  'admin@pixelvault.dev',
  '<HASH>',
  'Admin User',
  'admin',
  'active',
  true,
  0,
  107374182400,
  now(),
  now()
);"
```

**Expected:** `INSERT 0 1`

---

## Part 6 — Auth Flow

### Step 11 — Log in as admin

**Postman:**
- POST `{{base_url}}/api/v1/auth/login`
- Body (JSON): `{"email":"admin@pixelvault.dev","password":"AdminPass123!"}`

```bash
curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pixelvault.dev","password":"AdminPass123!"}' | jq .
```

→ Copy `access_token` → paste into Postman `admin_token` variable.

---

### Step 12 — Register a regular test user

**Postman:**
- POST `{{base_url}}/api/v1/auth/register`
- Body (JSON): `{"email":"user@test.com","password":"UserPass123!","full_name":"Test User"}`

```bash
curl -s -X POST http://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","password":"UserPass123!","full_name":"Test User"}' | jq .
```

**Expected:** 201 Created, `status: "pending"`.

---

### Step 13 — Get the email verification token from backend logs

```bash
docker logs photos_infra-backend-1 2>&1 | grep "EMAIL STUB" | tail -3
```

Copy the `token=` value from the link in the log output.

---

### Step 14 — Verify the user's email

**Postman:** GET `{{base_url}}/api/v1/auth/verify-email?token=<TOKEN>`

```bash
curl -s "http://localhost/api/v1/auth/verify-email?token=<TOKEN>" | jq .
```

**Expected:** `email_verified: true`, `status` still `"pending"`.

---

### Step 15 — Confirm pending user cannot log in yet

```bash
curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","password":"UserPass123!"}' | jq .
```

**Expected:** `403 Forbidden`, `"code":"account_not_active"`.

---

## Part 7 — Admin Routes

### Step 16 — List pending users

**Postman:** GET `{{base_url}}/api/v1/admin/users/pending` + `Authorization: Bearer {{admin_token}}`

```bash
curl -s http://localhost/api/v1/admin/users/pending \
  -H "Authorization: Bearer <ADMIN_TOKEN>" | jq .
```

**Expected:** array with one user, `status: "pending"`. Copy the user's `id`.

---

### Step 17 — Approve the user via admin API

**Postman:** POST `{{base_url}}/api/v1/admin/users/{{user_id}}/approve` + admin token

```bash
curl -s -X POST http://localhost/api/v1/admin/users/<USER_ID>/approve \
  -H "Authorization: Bearer <ADMIN_TOKEN>" | jq .
```

**Expected:** `status: "active"`.

---

### Step 18 — Check admin stats

**Postman:** GET `{{base_url}}/api/v1/admin/stats` + admin token

```bash
curl -s http://localhost/api/v1/admin/stats \
  -H "Authorization: Bearer <ADMIN_TOKEN>" | jq .
```

**Expected:**
```json
{
  "total_users": 2,
  "active_users": 2,
  "pending_users": 0,
  "total_media_items": 0,
  "total_storage_used_bytes": 0
}
```

---

## Part 8 — User Login + Token Lifecycle

### Step 19 — Log in as the approved user

**Postman:** POST `{{base_url}}/api/v1/auth/login`
Body: `{"email":"user@test.com","password":"UserPass123!"}`

```bash
curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","password":"UserPass123!"}' \
  -c /tmp/pv_cookies.txt | jq .
```

→ Copy `access_token` → paste into Postman `access_token` variable.

---

### Step 20 — Test the refresh token

```bash
curl -s -X POST http://localhost/api/v1/auth/refresh \
  -b /tmp/pv_cookies.txt | jq .
```

**Expected:** new `access_token` issued from the httpOnly cookie alone.

---

### Step 21 — Test logout + token invalidation

```bash
curl -s -X POST http://localhost/api/v1/auth/logout \
  -b /tmp/pv_cookies.txt | jq .
```

**Expected:** `{"message":"Logged out"}`

Try refresh again — should fail:
```bash
curl -s -X POST http://localhost/api/v1/auth/refresh \
  -b /tmp/pv_cookies.txt | jq .
```

**Expected:** `401 Unauthorized`.

Log back in before continuing, update `access_token` in Postman.

---

## Part 9 — Photo Upload + Storage Verification

### Step 22 — Upload a JPEG photo

**Postman:**
- POST `{{base_url}}/api/v1/media/upload`
- Header: `Authorization: Bearer {{access_token}}`
- Body: `form-data` → key `file`, type **File** → select a JPEG from your Mac

```bash
curl -s -X POST http://localhost/api/v1/media/upload \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "file=@/path/to/photo.jpg" | jq .
```

**Expected — 202 Accepted:**
```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "media_type": "photo",
  "mime_type": "image/jpeg",
  "original_path": "originals/<user_id>/<uuid>.jpg",
  "thumbnail_path": "thumbnails/<user_id>/<uuid>_thumb.jpg",
  "file_size_bytes": 123456,
  "captured_at": "2024-06-15",
  "status": "ready"
}
```

→ Copy `id` → paste into Postman `media_id` variable.

> `captured_at` is `null` if the photo has no EXIF data. Use a real phone photo for best results.

---

### Step 23 — Verify files are on disk

```bash
docker exec photos_infra-backend-1 find /storage -type f
```

**Expected — two files:**
```
/storage/originals/<user_id>/<uuid>.jpg
/storage/thumbnails/<user_id>/<uuid>_thumb.jpg
```

Verify the DB row:
```bash
docker exec photos_infra-postgres-1 psql -U pixelvault -d pixelvault \
  -c "SELECT id, original_path, thumbnail_path, file_size_bytes, status FROM media;"
```

**Expected:** one row, `status = ready`.

---

## Part 10 — Media Listing + Timeline + Streaming

### Step 24 — List media (paginated)

**Postman:** GET `{{base_url}}/api/v1/media`

```bash
curl -s http://localhost/api/v1/media \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | jq .
```

**Expected:** `data[]` with one item, `meta.total: 1`.

---

### Step 25 — Timeline view

**Postman:** GET `{{base_url}}/api/v1/media/timeline`

```bash
curl -s http://localhost/api/v1/media/timeline \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | jq .
```

**Expected:** array of groups with `year`, `month`, `count`, `items[]`.

---

### Step 26 — Stream thumbnail

**Postman:** GET `{{base_url}}/api/v1/media/{{media_id}}/thumbnail`

```bash
curl -s "http://localhost/api/v1/media/<MEDIA_ID>/thumbnail" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  --output /tmp/thumb_check.jpg && open /tmp/thumb_check.jpg
```

**Expected:** `200 OK`, `Content-Type: image/jpeg`, viewable 320×320 image.

---

### Step 27 — Stream original + HTTP Range

Full file:
```bash
curl -s "http://localhost/api/v1/media/<MEDIA_ID>/stream" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  --output /tmp/original_check.jpg && open /tmp/original_check.jpg
```

Ranged request:
```bash
curl -si "http://localhost/api/v1/media/<MEDIA_ID>/stream" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Range: bytes=0-1023" | head -6
```

**Expected:** `HTTP/1.1 206 Partial Content`, `Content-Range: bytes 0-1023/<total>`.

---

## Part 11 — Album CRUD

### Step 28 — Create an album

**Postman:** POST `{{base_url}}/api/v1/albums`
Body: `{"title":"Summer 2024","description":"Holiday photos"}`

```bash
curl -s -X POST http://localhost/api/v1/albums \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Summer 2024","description":"Holiday photos"}' | jq .
```

**Expected:** 201 Created, `media_count: 0`. → Copy `id` → `album_id`.

---

### Step 29 — Add photo to album

**Postman:** POST `{{base_url}}/api/v1/albums/{{album_id}}/media`
Body: `{"media_ids":["{{media_id}}"]}`

```bash
curl -s -X POST "http://localhost/api/v1/albums/<ALBUM_ID>/media" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"media_ids":["<MEDIA_ID>"]}' | jq .
```

**Expected:** `media_count: 1`, photo in `items[]`.

---

### Step 30 — Get album detail

**Postman:** GET `{{base_url}}/api/v1/albums/{{album_id}}`

```bash
curl -s "http://localhost/api/v1/albums/<ALBUM_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | jq .
```

---

### Step 31 — List all albums

**Postman:** GET `{{base_url}}/api/v1/albums`

```bash
curl -s http://localhost/api/v1/albums \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | jq .
```

---

### Step 32 — Remove photo from album

```bash
curl -si -X DELETE "http://localhost/api/v1/albums/<ALBUM_ID>/media/<MEDIA_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | head -1
```

**Expected:** `HTTP/1.1 204 No Content`

---

### Step 33 — Delete the album

```bash
curl -si -X DELETE "http://localhost/api/v1/albums/<ALBUM_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | head -1
```

**Expected:** `HTTP/1.1 204 No Content`

---

## Part 12 — Sharing

### Step 34 — Create a public link share

**Postman:** POST `{{base_url}}/api/v1/shares`
Body: `{"share_type":"public_link","target_media_id":"{{media_id}}"}`

```bash
curl -s -X POST http://localhost/api/v1/shares \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"share_type":"public_link","target_media_id":"<MEDIA_ID>"}' | jq .
```

**Expected:** 201 Created with `public_token` UUID4.
→ Copy `id` → `share_id`. Copy `public_token` → `share_token`.

---

### Step 35 — Resolve the public link with no auth

**Postman:** GET `{{base_url}}/api/v1/public/{{share_token}}` — **no Authorization header**

```bash
curl -s "http://localhost/api/v1/public/<SHARE_TOKEN>" | jq .
```

**Expected — 200 OK, no credentials needed:**
```json
{
  "share_type": "media",
  "media": { "id": "...", "media_type": "photo", ... },
  "album": null
}
```

---

### Step 36 — User-to-user share (requires a second user)

Register + verify + approve `user2@test.com` (repeat Steps 12–17), then:

```bash
curl -s -X POST http://localhost/api/v1/shares \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "share_type": "user",
    "target_media_id": "<MEDIA_ID>",
    "shared_with_user_id": "<USER2_ID>"
  }' | jq .
```

Log in as user 2 and check their inbox:
```bash
curl -s http://localhost/api/v1/shares/with-me \
  -H "Authorization: Bearer <USER2_TOKEN>" | jq .
```

**Expected:** share appears in user 2's list.

---

### Step 37 — Revoke + confirm dead

```bash
curl -si -X DELETE "http://localhost/api/v1/shares/<SHARE_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" | head -1
```

**Expected:** `HTTP/1.1 204 No Content`

```bash
curl -s "http://localhost/api/v1/public/<SHARE_TOKEN>" | jq .
```

**Expected:** `404 NOT_FOUND`.

---

## Part 13 — Full Database Audit

```bash
docker exec photos_infra-postgres-1 psql -U pixelvault -d pixelvault
```

```sql
\dt

SELECT id, email, role, status, storage_used_bytes FROM users;
SELECT id, original_path, thumbnail_path, status, file_size_bytes FROM media;
SELECT id, title, owner_id FROM albums;
SELECT * FROM album_media;
SELECT id, share_type, public_token, target_media_id FROM shares;
SELECT id, user_id, revoked FROM refresh_tokens;

\q
```

---

## Quick Reference — All 24 Endpoints

| # | Method | Path | Auth |
|---|---|---|---|
| 1 | GET | `/health` | None |
| 2 | POST | `/api/v1/auth/register` | None |
| 3 | GET | `/api/v1/auth/verify-email?token=` | None |
| 4 | POST | `/api/v1/auth/login` | None |
| 5 | POST | `/api/v1/auth/refresh` | Cookie |
| 6 | POST | `/api/v1/auth/logout` | Cookie |
| 7 | GET | `/api/v1/admin/users/pending` | Admin JWT |
| 8 | POST | `/api/v1/admin/users/{id}/approve` | Admin JWT |
| 9 | GET | `/api/v1/admin/stats` | Admin JWT |
| 10 | POST | `/api/v1/media/upload` | User JWT |
| 11 | GET | `/api/v1/media` | User JWT |
| 12 | GET | `/api/v1/media/timeline` | User JWT |
| 13 | GET | `/api/v1/media/{id}/thumbnail` | User JWT |
| 14 | GET | `/api/v1/media/{id}/stream` | User JWT |
| 15 | POST | `/api/v1/albums` | User JWT |
| 16 | GET | `/api/v1/albums` | User JWT |
| 17 | GET | `/api/v1/albums/{id}` | User JWT |
| 18 | POST | `/api/v1/albums/{id}/media` | User JWT |
| 19 | DELETE | `/api/v1/albums/{id}/media/{media_id}` | User JWT |
| 20 | DELETE | `/api/v1/albums/{id}` | User JWT |
| 21 | POST | `/api/v1/shares` | User JWT |
| 22 | GET | `/api/v1/shares/with-me` | User JWT |
| 23 | DELETE | `/api/v1/shares/{id}` | User JWT |
| 24 | GET | `/api/v1/public/{token}` | None |

---

## Resetting the Database (Dev Only)

```bash
docker exec photos_infra-postgres-1 psql -U pixelvault -d pixelvault \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO pixelvault;"

docker exec photos_infra-backend-1 alembic upgrade head
```

## Stopping / Restarting the Stack

```bash
cd /path/to/photos_infra
docker compose down       # stop, data preserved
docker compose up -d      # start again
docker compose down -v    # stop + delete all data
```

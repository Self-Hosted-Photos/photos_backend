# Pixel Vault — Deployment & Testing Guide

> **Canonical copy lives in `photos_infra/DEPLOYMENT_TESTING.md`.**
> This copy is kept here so the guide is accessible when working inside the backend repo.
> If you update one, update both.

This document covers the full process of bringing up the Pixel Vault stack for the
first time, whether locally or on a fresh server. Follow it in order.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker Desktop (macOS/Windows) or Docker Engine (Linux) | 24+ | Must be running before Step 3 |
| Python | 3.12 | For running local tests and alembic |
| curl | any | For smoke-testing endpoints |

---

## Part 1 — Run the Test Suite (No Docker Required)

These tests run against an in-memory SQLite database. No PostgreSQL needed.

### Step 1 — Create a virtualenv and install dependencies

```bash
cd photos_backend
python3.12 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt aiosqlite
```

`aiosqlite` is the test-only driver that lets pytest use SQLite instead of PostgreSQL.

### Step 2 — Run the test suite

```bash
pytest --tb=short -q
```

**Expected output:**
```
.........
9 passed in Xs
```

All 9 tests must be green before proceeding. If any fail, do not continue — fix them first.

### Step 3 — Run the linter

```bash
ruff check .
ruff format --check .
```

**Expected output:** no output (zero issues). Both commands exit with code 0.

---

## Part 2 — Configure the Environment

All commands from here run from `photos_infra/` unless stated otherwise.

### Step 4 — Copy and edit `.env`

```bash
cd photos_infra
cp .env.example .env
```

Open `.env` and make these changes:

**Generate a SECRET_KEY** (run this, copy the output):
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Replace the `SECRET_KEY` placeholder in `.env` with the 64-character hex string.

For a local test you can leave all other values at their defaults. For a production
server, also change `POSTGRES_PASSWORD` to a strong random value and update the
`DATABASE_URL` to match.

> `.env` is git-ignored and must never be committed.

---

## Part 3 — Initialise Storage Directories

The backend container runs as UID 1001 (non-root). The host storage directories must
be pre-created with the correct ownership before the container tries to write files.

### Step 5 — Run init-storage.sh

```bash
sudo bash scripts/init-storage.sh
```

**Expected output:**
```
[init-storage] Storage root : /storage
[init-storage] Creating /storage
[init-storage] Creating /storage/originals
[init-storage] Creating /storage/transcoded
[init-storage] Creating /storage/thumbnails
[init-storage] Setting ownership to 1001:1001 on /storage
[init-storage] Setting permissions (750) on /storage
[init-storage] Write test passed.
[init-storage] Done. Directory tree:
...
[init-storage] Next step: docker compose up -d
```

> This step only needs to be run once on first deployment. If you change `STORAGE_ROOT`
> in `.env`, re-run with: `sudo bash scripts/init-storage.sh /your/custom/path`

---

## Part 4 — Build and Start the Stack

### Step 6 — Build images and start all containers

```bash
docker compose up -d --build
```

This pulls `postgres:16-alpine` and `redis:7.2-alpine`, builds the backend and nginx
images, then starts all four containers. The first build takes 2–5 minutes.

### Step 7 — Verify all containers are running

```bash
docker compose ps
```

**Expected output (all STATUS = running):**
```
NAME                        STATUS
photos_infra-postgres-1     running
photos_infra-redis-1        running
photos_infra-backend-1      running
photos_infra-nginx-1        running
```

If `backend` shows `restarting`, check its logs:
```bash
docker compose logs backend --tail=40
```

Common causes: missing `SECRET_KEY` in `.env`, or PostgreSQL not yet ready (wait 5s and retry).

---

## Part 5 — Run the Database Migration

> **Important:** always run alembic from **inside** the backend container.
> Running it from the host fails because the `postgres` hostname only resolves
> inside the Docker network.

### Step 8 — Apply migrations

```bash
docker compose exec backend alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial users, email_tokens, refresh_tokens
```

No traceback. The migration creates four tables: `alembic_version`, `users`,
`email_tokens`, `refresh_tokens`.

### Step 9 — Verify the tables exist

```bash
docker compose exec postgres psql -U pixelvault -d pixelvault -c "\dt"
```

**Expected output:**
```
           List of relations
 Schema |      Name       | Type  |   Owner
--------+-----------------+-------+------------
 public | alembic_version | table | pixelvault
 public | email_tokens    | table | pixelvault
 public | refresh_tokens  | table | pixelvault
 public | users           | table | pixelvault
```

---

## Part 6 — Smoke Test the Endpoints

### Step 10 — Health check (nginx → backend chain)

```bash
curl -i http://localhost/health
```

**Expected:**
```
HTTP/1.1 200 OK
{"status":"ok"}
```

This confirms: nginx is up, the proxy to backend:8000 works, and the backend
connected to PostgreSQL successfully.

---

### Step 11 — Register a new user

```bash
curl -i -X POST http://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!","full_name":"Test User"}'
```

**Expected:**
```
HTTP/1.1 201 Created

{
  "id": "...",
  "email": "test@example.com",
  "full_name": "Test User",
  "role": "user",
  "status": "pending",
  ...
}
```

> `status: "pending"` is correct — every new user must be approved by an admin
> before they can log in. This is the admin-gating feature (ADR-001).

Check the backend logs to see the email verification stub:
```bash
docker compose logs backend 2>&1 | grep "EMAIL STUB"
```

You will see a line like:
```
[EMAIL STUB] Verification email → test@example.com | link: http://localhost:8000/verify-email?token=<token>
```

---

### Step 12 — Confirm pending users cannot log in

```bash
curl -i -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}'
```

**Expected:**
```
HTTP/1.1 403 Forbidden
{"detail":"Account is not active","code":"account_not_active"}
```

The admin gate is working correctly.

---

### Step 13 — Manually approve the user (admin routes not built yet)

Until Sprint 2 admin routes are complete, approve users directly in the database:

```bash
docker compose exec postgres psql -U pixelvault -d pixelvault \
  -c "UPDATE users SET status='active' WHERE email='test@example.com';"
```

**Expected:** `UPDATE 1`

---

### Step 14 — Log in as the active user

```bash
curl -i -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}' \
  -c /tmp/pv_cookies.txt
```

**Expected:**
```
HTTP/1.1 200 OK
Set-Cookie: refresh_token=...; Path=/api/v1/auth; HttpOnly; SameSite=Lax

{"access_token":"eyJ...","token_type":"bearer","user":{...}}
```

Two things returned:
- `access_token` in the body — a 15-minute JWT, used in `Authorization: Bearer` headers
- `refresh_token` httpOnly cookie — a 7-day token stored only in the browser, saved to `/tmp/pv_cookies.txt`

---

### Step 15 — Use the refresh token to get a new access token

```bash
curl -i -X POST http://localhost/api/v1/auth/refresh \
  -b /tmp/pv_cookies.txt
```

**Expected:**
```
HTTP/1.1 200 OK
{"access_token":"eyJ...","token_type":"bearer"}
```

New access token issued from the cookie alone — no password needed.

---

### Step 16 — Log out

```bash
curl -i -X POST http://localhost/api/v1/auth/logout \
  -b /tmp/pv_cookies.txt
```

**Expected:**
```
HTTP/1.1 200 OK
{"message":"Logged out"}
```

The refresh token is deleted from the database and the cookie is cleared.

---

### Step 17 — Confirm refresh no longer works after logout

```bash
curl -i -X POST http://localhost/api/v1/auth/refresh \
  -b /tmp/pv_cookies.txt
```

**Expected:**
```
HTTP/1.1 401 Unauthorized
```

Token invalidation confirmed.

---

## Part 7 — Inspect the Database (Optional)

```bash
docker compose exec postgres psql -U pixelvault -d pixelvault
```

Inside psql:

```sql
-- See all registered users
SELECT id, email, status, role, created_at FROM users;

-- See refresh tokens (empty after logout)
SELECT id, user_id, revoked, created_at FROM refresh_tokens;

-- See email verification tokens
SELECT id, user_id, type, used, expires_at FROM email_tokens;

-- Exit
\q
```

---

## Resetting the Database (Dev Only)

If the database gets into a bad state during development (e.g. a partial migration),
wipe and re-run:

```bash
docker compose exec postgres psql -U pixelvault -d pixelvault \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO pixelvault;"

docker compose exec backend alembic upgrade head
```

> Never run this on a production database. It destroys all data.

---

## Stopping the Stack

```bash
docker compose down          # stops containers, keeps volumes (data preserved)
docker compose down -v       # stops containers AND deletes volumes (data destroyed)
```

---

## What Each Step Validates

| Step | What it proves |
|---|---|
| 1–3 | Auth service logic, bcrypt hashing, SQLite compat, all 9 tests |
| 4 | Environment is correctly configured |
| 5 | Storage directory tree exists with correct UID ownership |
| 6–7 | All 4 Docker images build and all containers start |
| 8–9 | Alembic connects to PostgreSQL and all 3 tables + indexes are created |
| 10 | nginx → backend proxy chain is alive |
| 11 | Registration, bcrypt hash stored, email verification token created |
| 12 | Admin-gating works — pending users cannot log in |
| 13 | Direct DB access works (useful for admin tasks pre-Sprint 2) |
| 14 | Login, JWT access token issued, refresh cookie set |
| 15 | Refresh token rotation |
| 16–17 | Logout + server-side token invalidation |

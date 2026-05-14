import uuid

import pytest

from app.domain.models.user import UserRole, UserStatus
from app.infrastructure.repositories.user_repo import SQLUserRepository

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_admin(
    client, db, email: str = "admin@test.com", password: str = "adminpass123"
) -> str:
    """Register a user, promote to admin+active, return access token."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Admin User",
            "password": password,
        },
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    user.role = UserRole.ADMIN
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.flush()

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


async def _create_pending_user(client, email: str = "pending@test.com") -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Pending User",
            "password": "userpass123",
        },
    )
    return r.json()


# ── GET /admin/users/pending ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pending_users_returns_list(client, db):
    token = await _create_admin(client, db, "admin_p1@test.com")
    await _create_pending_user(client, "pend_a@test.com")
    await _create_pending_user(client, "pend_b@test.com")

    r = await client.get(
        "/api/v1/admin/users/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 2
    assert all(u["status"] == "pending" for u in body)


@pytest.mark.asyncio
async def test_non_admin_gets_403_on_pending_users(client, db):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "regular_p@test.com",
            "full_name": "Regular",
            "password": "userpass123",
        },
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("regular_p@test.com")
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.flush()

    r = await client.post(
        "/api/v1/auth/login", json={"email": "regular_p@test.com", "password": "userpass123"}
    )
    token = r.json()["access_token"]

    r = await client.get(
        "/api/v1/admin/users/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_gets_401_on_pending_users(client, db):
    r = await client.get("/api/v1/admin/users/pending")
    assert r.status_code == 401


# ── POST /admin/users/{id}/approve ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_pending_user_returns_active(client, db):
    token = await _create_admin(client, db, "admin_ap1@test.com")
    await _create_pending_user(client, "approve_me@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("approve_me@test.com")
    user.email_verified = True  # N-13: approval requires verified email
    await db.flush()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_approve_already_active_user_returns_422(client, db):
    token = await _create_admin(client, db, "admin_ap2@test.com")
    await _create_pending_user(client, "already_active@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("already_active@test.com")
    user.status = UserStatus.ACTIVE
    await db.flush()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_approve_nonexistent_user_returns_404(client, db):
    token = await _create_admin(client, db, "admin_ap3@test.com")

    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


# ── POST /admin/users/{id}/suspend ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suspend_active_user_returns_suspended(client, db):
    token = await _create_admin(client, db, "admin_sp1@test.com")
    await _create_pending_user(client, "suspend_me@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("suspend_me@test.com")
    user.status = UserStatus.ACTIVE
    await db.flush()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/suspend",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"


@pytest.mark.asyncio
async def test_suspend_nonexistent_user_returns_404(client, db):
    token = await _create_admin(client, db, "admin_sp2@test.com")

    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/suspend",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


# ── GET /admin/stats ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_stats_returns_correct_shape(client, db):
    token = await _create_admin(client, db, "admin_st1@test.com")
    await _create_pending_user(client, "stat_pend1@test.com")
    await _create_pending_user(client, "stat_pend2@test.com")

    r = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pending_users"] >= 2
    assert body["active_users"] >= 1  # admin itself is active
    assert (
        body["total_users"]
        == body["pending_users"] + body["active_users"] + body["suspended_users"]
    )
    assert "total_storage_used_bytes" in body
    assert "total_storage_used_gb" in body


# ── POST /admin/users/{id}/activate ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_pending_user_returns_active(client, db):
    token = await _create_admin(client, db, "admin_act1@test.com")
    await _create_pending_user(client, "activate_pending@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("activate_pending@test.com")

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_activate_suspended_user_returns_active(client, db):
    token = await _create_admin(client, db, "admin_act2@test.com")
    await _create_pending_user(client, "activate_suspended@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("activate_suspended@test.com")
    user.status = UserStatus.SUSPENDED
    await db.flush()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_activate_already_active_user_returns_422(client, db):
    token = await _create_admin(client, db, "admin_act3@test.com")
    await _create_pending_user(client, "activate_active@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("activate_active@test.com")
    user.status = UserStatus.ACTIVE
    await db.flush()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_activate_nonexistent_user_returns_404(client, db):
    token = await _create_admin(client, db, "admin_act4@test.com")

    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


# ── DELETE /admin/users/{id} ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_suspended_user_returns_204_and_excluded_from_list(client, db):
    token = await _create_admin(client, db, "admin_del1@test.com")
    await _create_pending_user(client, "delete_me@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("delete_me@test.com")
    user.status = UserStatus.SUSPENDED
    await db.flush()

    r = await client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Confirm excluded from GET /admin/users
    r = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    ids = [u["id"] for u in r.json()]
    assert str(user.id) not in ids


@pytest.mark.asyncio
async def test_delete_non_suspended_user_returns_422(client, db):
    token = await _create_admin(client, db, "admin_del2@test.com")
    await _create_pending_user(client, "delete_active@test.com")

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("delete_active@test.com")
    user.status = UserStatus.ACTIVE
    await db.flush()

    r = await client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422

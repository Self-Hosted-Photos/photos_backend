import pytest

from app.domain.models.user import UserStatus


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_register_returns_201_with_pending_status(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Smith",
            "password": "securepass123",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["status"] == "pending"
    assert body["email_verified"] is False


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client):
    payload = {"email": "bob@example.com", "full_name": "Bob", "password": "securepass123"}
    await client.post("/api/v1/auth/register", json=payload)
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_login_pending_user_returns_403(client):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "charlie@example.com",
            "full_name": "Charlie",
            "password": "securepass123",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "charlie@example.com",
            "password": "securepass123",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ACCOUNT_PENDING"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, db):
    from app.domain.models.user import UserStatus
    from app.infrastructure.repositories.user_repo import SQLUserRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dave@example.com",
            "full_name": "Dave",
            "password": "securepass123",
        },
    )
    # Manually activate
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("dave@example.com")
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "dave@example.com",
            "password": "wrongpassword",
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_active_user_returns_access_token(client, db):
    from app.infrastructure.repositories.user_repo import SQLUserRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "eve@example.com",
            "full_name": "Eve",
            "password": "securepass123",
        },
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("eve@example.com")
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "eve@example.com",
            "password": "securepass123",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "refresh_token" in r.cookies


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(client, db):
    from app.infrastructure.repositories.user_repo import SQLUserRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "frank@example.com",
            "full_name": "Frank",
            "password": "securepass123",
        },
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("frank@example.com")
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.commit()

    login_r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "frank@example.com",
            "password": "securepass123",
        },
    )
    assert login_r.status_code == 200

    refresh_r = await client.post("/api/v1/auth/refresh")
    assert refresh_r.status_code == 200
    assert "access_token" in refresh_r.json()


@pytest.mark.asyncio
async def test_logout_removes_refresh_token(client, db):
    from app.infrastructure.repositories.user_repo import SQLUserRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "grace@example.com",
            "full_name": "Grace",
            "password": "securepass123",
        },
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("grace@example.com")
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.commit()

    await client.post(
        "/api/v1/auth/login",
        json={
            "email": "grace@example.com",
            "password": "securepass123",
        },
    )
    logout_r = await client.post("/api/v1/auth/logout")
    assert logout_r.status_code == 200

    # Refresh should now fail
    refresh_r = await client.post("/api/v1/auth/refresh")
    assert refresh_r.status_code == 401


@pytest.mark.asyncio
async def test_verify_email_invalid_token_returns_400(client):
    r = await client.get("/api/v1/auth/verify-email?token=invalid-token-xyz")
    assert r.status_code == 400

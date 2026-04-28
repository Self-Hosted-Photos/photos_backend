import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app.domain.models.user import UserStatus
from app.infrastructure.repositories.user_repo import SQLUserRepository


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jpeg() -> bytes:
    img = Image.new("RGB", (100, 100), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _create_active_user(
    client, db, email: str = "user@test.com", password: str = "pass1234"
) -> str:
    """Register user, activate, return access token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": password},
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.flush()

    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return r.json()["access_token"]


async def _upload_photo(client, token: str) -> str:
    """Upload a photo and return its media_id."""
    jpeg = _make_jpeg()
    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    return r.json()["id"]


async def _create_album(client, token: str, title: str = "Test Album") -> str:
    """Create an album and return its album_id."""
    r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": title},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _get_user_id(db, email: str) -> str:
    """Return the UUID string for a user by email."""
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    return str(user.id)


# ── POST /shares ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_public_link_for_media_returns_201_with_token(client, db):
    token = await _create_active_user(client, db, "shr_pl1@test.com")
    media_id = await _upload_photo(client, token)

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["share_type"] == "public_link"
    assert body["public_token"] is not None
    assert body["target_media_id"] == media_id
    assert body["shared_with_user_id"] is None


@pytest.mark.asyncio
async def test_create_user_share_for_media_returns_201(client, db):
    token_a = await _create_active_user(client, db, "shr_usr_a@test.com")
    token_b = await _create_active_user(client, db, "shr_usr_b@test.com")
    media_id = await _upload_photo(client, token_a)
    user_b_id = await _get_user_id(db, "shr_usr_b@test.com")

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "share_type": "user",
            "target_media_id": media_id,
            "shared_with_user_id": user_b_id,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["share_type"] == "user"
    assert body["public_token"] is None
    assert body["shared_with_user_id"] == user_b_id


@pytest.mark.asyncio
async def test_create_public_link_for_album_returns_201(client, db):
    token = await _create_active_user(client, db, "shr_alb1@test.com")
    album_id = await _create_album(client, token)

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_album_id": album_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["target_album_id"] == album_id
    assert body["public_token"] is not None


@pytest.mark.asyncio
async def test_create_share_no_target_returns_422(client, db):
    token = await _create_active_user(client, db, "shr_notgt@test.com")

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_share_both_targets_returns_422(client, db):
    token = await _create_active_user(client, db, "shr_both@test.com")
    media_id = await _upload_photo(client, token)
    album_id = await _create_album(client, token)

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "share_type": "public_link",
            "target_media_id": media_id,
            "target_album_id": album_id,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_user_share_without_recipient_returns_422(client, db):
    token = await _create_active_user(client, db, "shr_norecip@test.com")
    media_id = await _upload_photo(client, token)

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "user", "target_media_id": media_id},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_share_with_self_returns_422(client, db):
    token = await _create_active_user(client, db, "shr_self@test.com")
    media_id = await _upload_photo(client, token)
    own_id = await _get_user_id(db, "shr_self@test.com")

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "share_type": "user",
            "target_media_id": media_id,
            "shared_with_user_id": own_id,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_share_unowned_media_returns_403(client, db):
    token_a = await _create_active_user(client, db, "shr_unown_a@test.com")
    token_b = await _create_active_user(client, db, "shr_unown_b@test.com")
    media_id = await _upload_photo(client, token_a)

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_share_nonexistent_media_returns_404(client, db):
    token = await _create_active_user(client, db, "shr_nomedia@test.com")

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_media_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_share_unauthenticated_returns_401(client, db):
    r = await client.post(
        "/api/v1/shares",
        json={"share_type": "public_link", "target_media_id": str(uuid.uuid4())},
    )
    assert r.status_code == 401


# ── GET /shares ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_my_shares_returns_owned_shares(client, db):
    token = await _create_active_user(client, db, "shr_lst1@test.com")
    media_id = await _upload_photo(client, token)

    await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )

    r = await client.get("/api/v1/shares", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    shares = r.json()
    assert len(shares) == 1
    assert shares[0]["target_media_id"] == media_id


@pytest.mark.asyncio
async def test_list_my_shares_returns_empty_for_new_user(client, db):
    token = await _create_active_user(client, db, "shr_lst_empty@test.com")

    r = await client.get("/api/v1/shares", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


# ── GET /shares/with-me ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_shares_with_me(client, db):
    token_a = await _create_active_user(client, db, "shr_wm_a@test.com")
    token_b = await _create_active_user(client, db, "shr_wm_b@test.com")
    media_id = await _upload_photo(client, token_a)
    user_b_id = await _get_user_id(db, "shr_wm_b@test.com")

    await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "share_type": "user",
            "target_media_id": media_id,
            "shared_with_user_id": user_b_id,
        },
    )

    r = await client.get(
        "/api/v1/shares/with-me", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert r.status_code == 200
    shares = r.json()
    assert len(shares) == 1
    assert shares[0]["target_media_id"] == media_id


# ── DELETE /shares/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_share_returns_204(client, db):
    token = await _create_active_user(client, db, "shr_rev1@test.com")
    media_id = await _upload_photo(client, token)

    create_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )
    share_id = create_r.json()["id"]

    r = await client.delete(
        f"/api/v1/shares/{share_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Share should no longer be listed
    list_r = await client.get(
        "/api/v1/shares", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_r.json() == []


@pytest.mark.asyncio
async def test_revoke_share_wrong_owner_returns_403(client, db):
    token_a = await _create_active_user(client, db, "shr_rev_a@test.com")
    token_b = await _create_active_user(client, db, "shr_rev_b@test.com")
    media_id = await _upload_photo(client, token_a)

    create_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )
    share_id = create_r.json()["id"]

    r = await client.delete(
        f"/api/v1/shares/{share_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_revoke_nonexistent_share_returns_404(client, db):
    token = await _create_active_user(client, db, "shr_rev_none@test.com")

    r = await client.delete(
        f"/api/v1/shares/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


# ── GET /public/{token} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_public_share_for_media_returns_200(client, db):
    token = await _create_active_user(client, db, "shr_pub1@test.com")
    media_id = await _upload_photo(client, token)

    create_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_media_id": media_id},
    )
    public_token = create_r.json()["public_token"]

    # No auth header
    r = await client.get(f"/api/v1/public/{public_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["share_type"] == "media"
    assert body["media"]["id"] == media_id
    assert "owner_id" not in body["media"]
    assert body["album"] is None


@pytest.mark.asyncio
async def test_resolve_public_share_for_album_returns_200(client, db):
    token = await _create_active_user(client, db, "shr_pub2@test.com")
    album_id = await _create_album(client, token, "Public Album")

    create_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={"share_type": "public_link", "target_album_id": album_id},
    )
    public_token = create_r.json()["public_token"]

    r = await client.get(f"/api/v1/public/{public_token}")
    assert r.status_code == 200
    body = r.json()
    assert body["share_type"] == "album"
    assert body["album"]["id"] == album_id
    assert body["album"]["title"] == "Public Album"
    assert "owner_id" not in body["album"]
    assert body["media"] is None


@pytest.mark.asyncio
async def test_resolve_invalid_token_returns_404(client, db):
    r = await client.get(f"/api/v1/public/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_resolve_expired_share_returns_404(client, db):
    token = await _create_active_user(client, db, "shr_exp@test.com")
    media_id = await _upload_photo(client, token)

    # Create share with an expiry in the past
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    create_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "share_type": "public_link",
            "target_media_id": media_id,
            "expires_at": past,
        },
    )
    public_token = create_r.json()["public_token"]

    r = await client.get(f"/api/v1/public/{public_token}")
    assert r.status_code == 404

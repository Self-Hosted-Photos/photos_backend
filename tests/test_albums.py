import io
import uuid

import pytest
from PIL import Image

from app.domain.models.media import MediaStatus
from app.domain.models.user import UserStatus
from app.infrastructure.repositories.media_repo import SQLMediaRepository
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

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


async def _upload_photo(client, token: str) -> dict:
    """Upload a JPEG and return the response body."""
    jpeg = _make_jpeg()
    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    return r.json()


# ── POST /albums ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_album_returns_201(client, db):
    token = await _create_active_user(client, db, "alb_create1@test.com")

    r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Summer 2024"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Summer 2024"
    assert body["media_count"] == 0
    assert body["description"] is None
    assert "id" in body
    assert "owner_id" in body


@pytest.mark.asyncio
async def test_create_album_with_description(client, db):
    token = await _create_active_user(client, db, "alb_create2@test.com")

    r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Holidays", "description": "Best moments"},
    )
    assert r.status_code == 201
    assert r.json()["description"] == "Best moments"


@pytest.mark.asyncio
async def test_create_album_empty_title_returns_422(client, db):
    token = await _create_active_user(client, db, "alb_create3@test.com")

    r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": ""},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_album_unauthenticated_returns_401(client, db):
    r = await client.post("/api/v1/albums", json={"title": "Test"})
    assert r.status_code == 401


# ── GET /albums ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_albums_returns_empty_for_new_user(client, db):
    token = await _create_active_user(client, db, "alb_list1@test.com")

    r = await client.get("/api/v1/albums", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_albums_returns_owned_albums_with_count(client, db):
    token = await _create_active_user(client, db, "alb_list2@test.com")

    # Create 2 albums
    await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Album A"},
    )
    await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Album B"},
    )

    r = await client.get("/api/v1/albums", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    albums = r.json()
    assert len(albums) == 2
    titles = {a["title"] for a in albums}
    assert titles == {"Album A", "Album B"}
    for a in albums:
        assert "media_count" in a


@pytest.mark.asyncio
async def test_list_albums_isolates_between_users(client, db):
    token_a = await _create_active_user(client, db, "alb_iso_a@test.com")
    token_b = await _create_active_user(client, db, "alb_iso_b@test.com")

    await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "User A album"},
    )

    r = await client.get("/api/v1/albums", headers={"Authorization": f"Bearer {token_b}"})
    assert r.json() == []


# ── GET /albums/{id} ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_album_returns_detail_with_items(client, db):
    token = await _create_active_user(client, db, "alb_get1@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Detail Test"},
    )
    album_id = create_r.json()["id"]

    r = await client.get(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == album_id
    assert body["title"] == "Detail Test"
    assert body["items"] == []
    assert body["media_count"] == 0


@pytest.mark.asyncio
async def test_get_album_not_found_returns_404(client, db):
    token = await _create_active_user(client, db, "alb_get2@test.com")
    fake_id = str(uuid.uuid4())

    r = await client.get(
        f"/api/v1/albums/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_album_wrong_owner_returns_403(client, db):
    token_a = await _create_active_user(client, db, "alb_own_a@test.com")
    token_b = await _create_active_user(client, db, "alb_own_b@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Private"},
    )
    album_id = create_r.json()["id"]

    r = await client.get(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


# ── PUT /albums/{id} ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_album_title(client, db):
    token = await _create_active_user(client, db, "alb_upd1@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Old Title"},
    )
    album_id = create_r.json()["id"]

    r = await client.put(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "New Title"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_update_album_not_found_returns_404(client, db):
    token = await _create_active_user(client, db, "alb_upd2@test.com")
    fake_id = str(uuid.uuid4())

    r = await client.put(
        f"/api/v1/albums/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Whatever"},
    )
    assert r.status_code == 404


# ── DELETE /albums/{id} ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_album_returns_204(client, db):
    token = await _create_active_user(client, db, "alb_del1@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "To Delete"},
    )
    album_id = create_r.json()["id"]

    r = await client.delete(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Confirm gone
    r2 = await client.get(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_album_media_records_survive(client, db):
    """Deleting an album must not delete the underlying media rows."""
    token = await _create_active_user(client, db, "alb_del2@test.com")

    media_body = await _upload_photo(client, token)
    media_id = media_body["id"]

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Temp Album"},
    )
    album_id = create_r.json()["id"]

    await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )

    await client.delete(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Media row should still exist in the DB
    repo = SQLMediaRepository(db)
    media = await repo.get_by_id(uuid.UUID(media_id))
    assert media is not None


# ── POST /albums/{id}/media ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_media_to_album_returns_detail(client, db):
    token = await _create_active_user(client, db, "alb_add1@test.com")

    media_body = await _upload_photo(client, token)
    media_id = media_body["id"]

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "With Media"},
    )
    album_id = create_r.json()["id"]

    r = await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["media_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == media_id


@pytest.mark.asyncio
async def test_add_media_idempotent(client, db):
    """Adding the same media twice should not duplicate it."""
    token = await _create_active_user(client, db, "alb_add2@test.com")

    media_body = await _upload_photo(client, token)
    media_id = media_body["id"]

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Idempotent"},
    )
    album_id = create_r.json()["id"]

    await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )
    r = await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )
    assert r.status_code == 200
    assert r.json()["media_count"] == 1


@pytest.mark.asyncio
async def test_add_another_users_media_returns_403(client, db):
    token_a = await _create_active_user(client, db, "alb_cross_a@test.com")
    token_b = await _create_active_user(client, db, "alb_cross_b@test.com")

    # User A uploads a photo
    media_body = await _upload_photo(client, token_a)
    media_id = media_body["id"]

    # User B creates an album
    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"title": "B Album"},
    )
    album_id = create_r.json()["id"]

    # User B tries to add User A's media
    r = await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"media_ids": [media_id]},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_add_unprocessed_media_returns_422(client, db):
    """Media with status != READY cannot be added to an album."""
    token = await _create_active_user(client, db, "alb_unproc@test.com")

    media_body = await _upload_photo(client, token)
    media_id = media_body["id"]

    # Force media back to processing status
    repo = SQLMediaRepository(db)
    media = await repo.get_by_id(uuid.UUID(media_id))
    media.status = MediaStatus.PROCESSING
    await db.flush()

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Unprocessed"},
    )
    album_id = create_r.json()["id"]

    r = await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_STATE"


@pytest.mark.asyncio
async def test_add_nonexistent_media_returns_404(client, db):
    token = await _create_active_user(client, db, "alb_nomedia@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Empty"},
    )
    album_id = create_r.json()["id"]

    r = await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 404


# ── DELETE /albums/{id}/media/{media_id} ─────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_media_from_album_returns_204(client, db):
    token = await _create_active_user(client, db, "alb_rm1@test.com")

    media_body = await _upload_photo(client, token)
    media_id = media_body["id"]

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Remove Test"},
    )
    album_id = create_r.json()["id"]

    await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        json={"media_ids": [media_id]},
    )

    r = await client.delete(
        f"/api/v1/albums/{album_id}/media/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Verify album is now empty
    detail = await client.get(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.json()["media_count"] == 0
    assert detail.json()["items"] == []


@pytest.mark.asyncio
async def test_remove_media_wrong_owner_returns_403(client, db):
    token_a = await _create_active_user(client, db, "alb_rmown_a@test.com")
    token_b = await _create_active_user(client, db, "alb_rmown_b@test.com")

    media_body = await _upload_photo(client, token_a)
    media_id = media_body["id"]

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "A Album"},
    )
    album_id = create_r.json()["id"]

    await client.post(
        f"/api/v1/albums/{album_id}/media",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"media_ids": [media_id]},
    )

    r = await client.delete(
        f"/api/v1/albums/{album_id}/media/{media_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403

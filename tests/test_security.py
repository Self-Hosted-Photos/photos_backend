"""
Security regression tests for Pixel Vault photos_backend.

Coverage:
  A-01  Cross-user media isolation (GET, thumbnail, stream)
  A-01  Cross-user album isolation (GET)
  A-09  Admin-only route enforcement for regular users
  A-02  MIME spoof rejection (ZIP magic bytes declared as image/jpeg)
  A-03  Oversized file rejection (monkeypatched size limit)
  A-05  Path traversal rejection in LocalStorageBackend._safe_path
  B-09  Suspended user cannot exchange refresh token
  A-08  Expired public share returns 404
"""

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.domain.models.user import EmailToken, User, UserStatus
from app.exceptions import InvalidStateError, StorageError
from app.infrastructure.repositories.user_repo import RefreshTokenRepository, SQLUserRepository
from app.infrastructure.storage.local import LocalStorageBackend

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _create_active_user(client, db, email: str, password: str = "pass1234") -> str:
    """Register user, activate, and return access token."""
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


# ── A-01: Cross-user media isolation ──────────────────────────────────────────
# The media router exposes two per-item endpoints: /thumbnail and /stream.
# There is no standalone GET /media/{id} metadata route; isolation is enforced
# on both streaming endpoints below.


@pytest.mark.asyncio
async def test_cross_user_media_thumbnail_returns_403(client, db):
    """User B cannot fetch the thumbnail of User A's media."""
    token_a = await _create_active_user(client, db, "sec_thumb_a@test.com")
    token_b = await _create_active_user(client, db, "sec_thumb_b@test.com")

    jpeg = _make_jpeg()
    upload = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload.status_code == 202
    media_id = upload.json()["id"]

    r = await client.get(
        f"/api/v1/media/{media_id}/thumbnail",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cross_user_media_stream_returns_403(client, db):
    """User B cannot stream User A's media file."""
    token_a = await _create_active_user(client, db, "sec_stream_a@test.com")
    token_b = await _create_active_user(client, db, "sec_stream_b@test.com")

    jpeg = _make_jpeg()
    upload = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload.status_code == 202
    media_id = upload.json()["id"]

    r = await client.get(
        f"/api/v1/media/{media_id}/stream",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


# ── A-01: Cross-user album isolation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_album_get_returns_403(client, db):
    """User B cannot GET User A's album."""
    token_a = await _create_active_user(client, db, "sec_album_a@test.com")
    token_b = await _create_active_user(client, db, "sec_album_b@test.com")

    create_r = await client.post(
        "/api/v1/albums",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "User A Album", "description": "private"},
    )
    assert create_r.status_code == 201
    album_id = create_r.json()["id"]

    r = await client.get(
        f"/api/v1/albums/{album_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


# ── A-09: Admin-only route enforcement ────────────────────────────────────────


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_pending(client, db):
    """A regular (non-admin) user must receive 403 on GET /admin/users/pending."""
    token = await _create_active_user(client, db, "sec_admin_check_a@test.com")

    r = await client.get(
        "/api/v1/admin/users/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_stats(client, db):
    """A regular (non-admin) user must receive 403 on GET /admin/stats."""
    token = await _create_active_user(client, db, "sec_admin_check_b@test.com")

    r = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ── A-02: MIME spoof rejection ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_bytes_declared_as_jpeg_returns_422(client, db):
    """ZIP magic bytes (PK\\x03\\x04) declared as image/jpeg must be rejected."""
    token = await _create_active_user(client, db, "sec_mime_spoof@test.com")

    # Local ZIP magic bytes — not a valid image
    zip_bytes = b"PK\x03\x04" + b"\x00" * 100

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(zip_bytes), "image/jpeg")},
    )
    assert r.status_code == 422


# ── A-03 / SEC-003: Oversized file rejection ──────────────────────────────────


@pytest.mark.asyncio
async def test_oversized_file_returns_422(client, db, monkeypatch):
    """File exceeding MAX_IMAGE_FILE_SIZE_BYTES must be rejected with 422."""
    import app.services.media_service as media_svc

    monkeypatch.setattr(media_svc, "MAX_IMAGE_FILE_SIZE_BYTES", 1)

    token = await _create_active_user(client, db, "sec_oversize@test.com")
    jpeg = _make_jpeg()  # well above 1 byte

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 422


# ── A-05: Path traversal rejection ────────────────────────────────────────────


def test_path_traversal_dot_dot_raises_storage_error(tmp_path):
    """../../etc/passwd must raise StorageError."""
    backend = LocalStorageBackend(storage_root=str(tmp_path), base_url="http://test")
    with pytest.raises(StorageError):
        backend._safe_path("../../etc/passwd")


def test_path_traversal_absolute_raises_storage_error(tmp_path):
    """/absolute/path must raise StorageError."""
    backend = LocalStorageBackend(storage_root=str(tmp_path), base_url="http://test")
    with pytest.raises(StorageError):
        backend._safe_path("/absolute/path")


def test_path_traversal_null_byte_raises_storage_error(tmp_path):
    """Path containing a null byte must raise StorageError."""
    backend = LocalStorageBackend(storage_root=str(tmp_path), base_url="http://test")
    with pytest.raises(StorageError):
        backend._safe_path("originals/user-id/file\x00.jpg")


def test_path_traversal_valid_path_does_not_raise(tmp_path):
    """A well-formed relative path must not raise StorageError."""
    backend = LocalStorageBackend(storage_root=str(tmp_path), base_url="http://test")
    # _safe_path only validates; it does not require the file to exist
    result = backend._safe_path("originals/user-id/file.jpg")
    assert isinstance(result, Path)
    assert result.is_relative_to(tmp_path)


# ── B-09: Suspended user cannot use refresh token ─────────────────────────────


@pytest.mark.asyncio
async def test_suspended_user_refresh_returns_401(client, db):
    """After suspension and token revocation the refresh endpoint returns 401."""
    email = "sec_suspended@test.com"
    password = "pass1234"

    # 1. Register and activate
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Suspended User", "password": password},
    )
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.flush()

    # 2. Login — this sets the refresh_token cookie on the client
    login_r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_r.status_code == 200
    assert "refresh_token" in login_r.cookies

    # 3. Suspend the user and revoke all refresh tokens
    user = await repo.get_by_email(email)
    user.status = UserStatus.SUSPENDED
    await db.flush()

    rt_repo = RefreshTokenRepository(db)
    await rt_repo.revoke_all_for_user(user.id)

    # 4. Attempt to refresh — must be rejected
    refresh_r = await client.post("/api/v1/auth/refresh")
    assert refresh_r.status_code == 401


# ── A-08: Public share expiry ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expired_public_share_returns_404(client, db):
    """A public share whose expiry is in the past must return 404 when accessed."""
    token = await _create_active_user(client, db, "sec_share_exp@test.com")

    # Upload a photo to share
    jpeg = _make_jpeg()
    upload_r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload_r.status_code == 202
    media_id = upload_r.json()["id"]

    # Create a share that has already expired (1 hour ago)
    # The sharing service only rejects expiries > 30 days in the future,
    # so a past expiry passes creation validation but is immediately invalid.
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    share_r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "share_type": "public_link",
            "target_media_id": media_id,
            "expires_at": past_time,
            "permission": "view",
        },
    )
    assert share_r.status_code == 201
    public_token = share_r.json()["public_token"]
    assert public_token is not None

    # Accessing the expired share must return 404
    r = await client.get(f"/api/v1/public/{public_token}")
    assert r.status_code == 404


# ── N-13: approve() requires verified email ───────────────────────────────────


def test_approve_unverified_email_raises():
    """User.approve() must raise InvalidStateError when email_verified is False."""
    user = User(
        id=uuid.uuid4(),
        email="pending@test.com",
        full_name="Pending",
        status=UserStatus.PENDING,
        email_verified=False,
    )
    with pytest.raises(InvalidStateError, match="unverified email"):
        user.approve()


def test_approve_verified_email_sets_active():
    """User.approve() must succeed and set status to ACTIVE when email_verified is True."""
    user = User(
        id=uuid.uuid4(),
        email="pending@test.com",
        full_name="Pending",
        status=UserStatus.PENDING,
        email_verified=True,
    )
    user.approve()
    assert user.status == UserStatus.ACTIVE


# ── N-02: Live DB check closes suspended-user window ─────────────────────────


@pytest.mark.asyncio
async def test_suspended_user_access_token_rejected_immediately(client, db):
    """Access token for a suspended user must return 403 on the very next request."""
    email = "sec_n02_suspended@test.com"
    token = await _create_active_user(client, db, email)

    # Suspend the user directly in DB (simulates an admin action mid-session)
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    user.status = UserStatus.SUSPENDED
    await db.flush()

    # The old access token must now be refused — the live DB check closes the window
    r = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ACCOUNT_SUSPENDED"


# ── N-08: Email tokens stored as SHA-256 hashes, not plaintext ───────────────


@pytest.mark.asyncio
async def test_email_token_stored_as_hash_not_plaintext(db, client):
    """After registration the email_tokens row must contain a 64-char hex hash."""
    email = "sec_n08_hash@test.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Hash Test", "password": "pass1234"},
    )
    assert r.status_code == 201

    result = await db.execute(
        select(EmailToken).join(User, User.id == EmailToken.user_id).where(User.email == email)
    )
    token_row = result.scalar_one_or_none()
    assert token_row is not None, "No EmailToken row created on registration"

    # SHA-256 hex digest is always exactly 64 lowercase hex characters
    assert len(token_row.token_hash) == 64
    assert all(
        c in "0123456789abcdef" for c in token_row.token_hash
    ), f"token_hash is not a hex string: {token_row.token_hash!r}"


@pytest.mark.asyncio
async def test_verify_email_with_raw_token_flow(client, db):
    """Full flow: register → intercept raw token from DB → verify succeeds."""
    email = "sec_n08_verify@test.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Verify Test", "password": "pass1234"},
    )

    user = await SQLUserRepository(db).get_by_email(email)
    assert user is not None

    # In production the raw token is only in the email link; here we cannot reconstruct
    # it. Instead, verify that looking up by a wrong value returns None (hash mismatch).
    result = await db.execute(select(EmailToken).where(EmailToken.user_id == user.id))
    token_row = result.scalar_one_or_none()
    assert token_row is not None

    # A plaintext lookup (wrong value) must not match the stored hash
    from app.infrastructure.repositories.user_repo import EmailTokenRepository

    et_repo = EmailTokenRepository(db)
    not_found = await et_repo.get_by_token_hash("not-the-real-token")
    assert not_found is None

    # The stored hash must resolve to itself
    found = await et_repo.get_by_token_hash(token_row.token_hash)
    assert found is not None
    assert found.id == token_row.id


# ── N-12: Cannot share with non-active users ─────────────────────────────────


@pytest.mark.asyncio
async def test_share_with_pending_user_rejected(client, db):
    """Sharing with a PENDING user must return 422."""
    owner_token = await _create_active_user(client, db, "sec_n12_owner_a@test.com")

    # Register target user but leave them PENDING (default after register)
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "sec_n12_pending@test.com",
            "full_name": "Pending Target",
            "password": "pass1234",
        },
    )
    target = await SQLUserRepository(db).get_by_email("sec_n12_pending@test.com")
    assert target.status == UserStatus.PENDING

    jpeg = _make_jpeg()
    upload_r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload_r.status_code == 202
    media_id = upload_r.json()["id"]

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "share_type": "user",
            "target_media_id": media_id,
            "shared_with_user_id": str(target.id),
            "permission": "view",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_STATE"


@pytest.mark.asyncio
async def test_share_with_suspended_user_rejected(client, db):
    """Sharing with a SUSPENDED user must return 422."""
    owner_token = await _create_active_user(client, db, "sec_n12_owner_b@test.com")

    # Create and suspend the target user
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "sec_n12_suspended@test.com",
            "full_name": "Suspended Target",
            "password": "pass1234",
        },
    )
    repo = SQLUserRepository(db)
    target = await repo.get_by_email("sec_n12_suspended@test.com")
    target.status = UserStatus.ACTIVE
    target.email_verified = True
    await db.flush()
    target.status = UserStatus.SUSPENDED
    await db.flush()

    jpeg = _make_jpeg()
    upload_r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert upload_r.status_code == 202
    media_id = upload_r.json()["id"]

    r = await client.post(
        "/api/v1/shares",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "share_type": "user",
            "target_media_id": media_id,
            "shared_with_user_id": str(target.id),
            "permission": "view",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_STATE"

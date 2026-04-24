import io

import piexif
import pytest
from PIL import Image

from app.domain.models.user import UserRole, UserStatus
from app.infrastructure.repositories.user_repo import SQLUserRepository


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jpeg(width: int = 100, height: int = 150) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_jpeg_with_exif(capture_date: str = "2024:03:15 10:30:00") -> bytes:
    """Return a JPEG with DateTimeOriginal EXIF tag embedded."""
    jpeg_bytes = _make_jpeg()
    exif_dict = {
        "0th": {},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: capture_date.encode("ascii")},
        "GPS": {},
        "1st": {},
    }
    exif_bytes = piexif.dump(exif_dict)
    output = io.BytesIO()
    piexif.insert(exif_bytes, jpeg_bytes, output)
    return output.getvalue()


def _make_jpeg_with_gps() -> bytes:
    """Return a JPEG with GPS coordinates (Sydney, Australia) in EXIF."""
    jpeg_bytes = _make_jpeg()
    # Sydney: -33.8688, 151.2093
    def _to_rational(val: float) -> tuple:
        d = int(val)
        m = int((val - d) * 60)
        s = int(((val - d) * 60 - m) * 60 * 100)
        return ((d, 1), (m, 1), (s, 100))

    lat = abs(-33.8688)
    lng = 151.2093
    exif_dict = {
        "0th": {},
        "Exif": {},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"S",
            piexif.GPSIFD.GPSLatitude: _to_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: _to_rational(lng),
        },
        "1st": {},
    }
    exif_bytes = piexif.dump(exif_dict)
    output = io.BytesIO()
    piexif.insert(exif_bytes, jpeg_bytes, output)
    return output.getvalue()


async def _create_active_user(client, db, email: str = "user@test.com", password: str = "pass1234") -> str:
    """Register user, activate, return access token."""
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "full_name": "Test User",
        "password": password,
    })
    repo = SQLUserRepository(db)
    user = await repo.get_by_email(email)
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    await db.flush()

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ── POST /media/upload ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_jpeg_returns_202_with_ready_status(client, db):
    token = await _create_active_user(client, db, "upload1@test.com")
    jpeg = _make_jpeg()

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "ready"
    assert body["media_type"] == "photo"
    assert body["mime_type"] == "image/jpeg"
    assert body["thumbnail_path"] is not None
    assert body["file_size_bytes"] == len(jpeg)


@pytest.mark.asyncio
async def test_upload_sets_thumbnail_path(client, db, tmp_path):
    token = await _create_active_user(client, db, "upload2@test.com")
    jpeg = _make_jpeg()

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    thumbnail_path = r.json()["thumbnail_path"]
    assert thumbnail_path.startswith("thumbnails/")
    assert thumbnail_path.endswith(".jpg")
    # Thumbnail file must exist on disk
    assert (tmp_path / thumbnail_path).exists()


@pytest.mark.asyncio
async def test_upload_parses_exif_datetime(client, db):
    token = await _create_active_user(client, db, "upload3@test.com")
    jpeg = _make_jpeg_with_exif("2024:03:15 10:30:00")

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    assert r.json()["captured_at"] == "2024-03-15"


@pytest.mark.asyncio
async def test_upload_parses_gps_coordinates(client, db):
    token = await _create_active_user(client, db, "upload4@test.com")
    jpeg = _make_jpeg_with_gps()

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["latitude"] is not None
    assert body["longitude"] is not None
    # Sydney latitude should be negative (south)
    assert body["latitude"] < 0
    assert body["longitude"] > 0


@pytest.mark.asyncio
async def test_upload_no_exif_returns_null_captured_at(client, db):
    token = await _create_active_user(client, db, "upload5@test.com")
    jpeg = _make_jpeg()  # no EXIF

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 202
    assert r.json()["captured_at"] is None
    assert r.json()["latitude"] is None


@pytest.mark.asyncio
async def test_upload_unsupported_mime_returns_422(client, db):
    token = await _create_active_user(client, db, "upload6@test.com")

    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_quota_exceeded_returns_422(client, db):
    token = await _create_active_user(client, db, "upload7@test.com")

    # Set quota to 1 byte so any upload exceeds it
    repo = SQLUserRepository(db)
    user = await repo.get_by_email("upload7@test.com")
    user.storage_quota_bytes = 1
    await db.flush()

    jpeg = _make_jpeg()
    r = await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_upload_unauthenticated_returns_401(client, db):
    jpeg = _make_jpeg()
    r = await client.post(
        "/api/v1/media/upload",
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_upload_updates_user_storage_used(client, db):
    token = await _create_active_user(client, db, "upload8@test.com")
    jpeg = _make_jpeg()

    await client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )

    repo = SQLUserRepository(db)
    user = await repo.get_by_email("upload8@test.com")
    assert user.storage_used_bytes == len(jpeg)

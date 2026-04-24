import io
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import piexif
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.events import MediaUploadedEvent
from app.domain.models.media import Media, MediaStatus, MediaType
from app.exceptions import InvalidStateError, ResourceNotFoundError
from app.infrastructure.repositories.media_repo import SQLMediaRepository
from app.infrastructure.repositories.user_repo import SQLUserRepository
from app.infrastructure.storage.base import StorageBackend
from app.middleware.quota import check_quota

_ALLOWED_PHOTO_MIMES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "image/webp",
    "image/gif",
})

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/heif": "heic",
    "image/webp": "webp",
    "image/gif": "gif",
}

_THUMBNAIL_SIZE = 320


@dataclass(frozen=True)
class GpsCoordinates:
    latitude: float   # decimal degrees, -90.0 (S) to +90.0 (N)
    longitude: float  # decimal degrees, -180.0 (W) to +180.0 (E)

    def __post_init__(self) -> None:
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"Invalid latitude {self.latitude}: must be in [-90, 90]")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"Invalid longitude {self.longitude}: must be in [-180, 180]")


def _parse_exif(file_bytes: bytes) -> tuple[date | None, GpsCoordinates | None]:
    """Extract capture date and GPS from EXIF. Returns (None, None) on missing/invalid EXIF."""
    try:
        exif_dict = piexif.load(file_bytes)
    except Exception:
        return None, None

    captured_at: date | None = None
    gps: GpsCoordinates | None = None

    # DateTimeOriginal → piexif.ExifIFD.DateTimeOriginal (tag 36867)
    exif_ifd = exif_dict.get("Exif", {})
    dt_raw = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
    if dt_raw:
        try:
            captured_at = datetime.strptime(
                dt_raw.decode("ascii"), "%Y:%m:%d %H:%M:%S"
            ).date()
        except (ValueError, UnicodeDecodeError):
            pass

    # GPS IFD — piexif uses integer keys
    gps_ifd = exif_dict.get("GPS", {})
    if gps_ifd:
        try:
            lat_dms = gps_ifd.get(piexif.GPSIFD.GPSLatitude)
            lat_ref = gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b"N")
            lng_dms = gps_ifd.get(piexif.GPSIFD.GPSLongitude)
            lng_ref = gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef, b"E")

            if lat_dms and lng_dms:
                def _dms_to_decimal(dms: tuple, ref: bytes) -> float:
                    d = dms[0][0] / dms[0][1]
                    m = dms[1][0] / dms[1][1]
                    s = dms[2][0] / dms[2][1]
                    val = d + m / 60 + s / 3600
                    return -val if ref.decode("ascii").strip() in ("S", "W") else val

                gps = GpsCoordinates(
                    latitude=_dms_to_decimal(lat_dms, lat_ref),
                    longitude=_dms_to_decimal(lng_dms, lng_ref),
                )
        except (KeyError, ZeroDivisionError, ValueError, UnicodeDecodeError):
            pass

    return captured_at, gps


def _generate_thumbnail(file_bytes: bytes, size: int = _THUMBNAIL_SIZE) -> bytes:
    """Return a square JPEG thumbnail (centre-cropped, resized to size×size)."""
    img = Image.open(io.BytesIO(file_bytes))

    if img.mode != "RGB":
        img = img.convert("RGB")

    # Centre-crop to square
    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    img = img.crop((left, top, left + min_dim, top + min_dim))

    img = img.resize((size, size), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


class MediaService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        storage: StorageBackend,
    ) -> None:
        self._db = db
        self._settings = settings
        self._storage = storage
        self._media = SQLMediaRepository(db)
        self._users = SQLUserRepository(db)

    async def handle_upload(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        user_id: uuid.UUID,
    ) -> Media:
        mime = content_type.lower().split(";")[0].strip()

        # 1. Validate MIME type — photos only for MVP
        if mime not in _ALLOWED_PHOTO_MIMES:
            raise InvalidStateError(
                f"Unsupported file type: {mime!r}. Supported: {sorted(_ALLOWED_PHOTO_MIMES)}"
            )

        ext = _MIME_TO_EXT[mime]
        file_size = len(file_bytes)

        # 2. Load user + quota check
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User not found")
        check_quota(user, file_size)

        # 3. Paths
        media_id = uuid.uuid4()
        filename_stored = f"{media_id}.{ext}"
        original_path = f"originals/{user_id}/{filename_stored}"
        thumbnail_path = f"thumbnails/{user_id}/{media_id}.jpg"

        # 4. Save original
        await self._storage.save(original_path, io.BytesIO(file_bytes), mime)

        # 5. Parse EXIF
        captured_at, gps = _parse_exif(file_bytes)

        # 6. Generate + save thumbnail
        thumb_bytes = _generate_thumbnail(file_bytes)
        await self._storage.save(thumbnail_path, io.BytesIO(thumb_bytes), "image/jpeg")

        # 7. Persist media row (status=ready — synchronous MVP flow, no Celery)
        media = Media(
            id=media_id,
            owner_id=user_id,
            filename_original=filename,
            filename_stored=filename_stored,
            media_type=MediaType.PHOTO,
            mime_type=mime,
            file_size_bytes=file_size,
            status=MediaStatus.READY,
            original_path=original_path,
            thumbnail_path=thumbnail_path,
            captured_at=captured_at,
            latitude=gps.latitude if gps else None,
            longitude=gps.longitude if gps else None,
        )
        media = await self._media.save(media)

        # 8. Deduct from user quota
        user.storage_used_bytes += file_size
        await self._users.save(user)

        # Domain event (future event bus)
        _event = MediaUploadedEvent(
            media_id=media.id,
            owner_id=user_id,
            file_size=file_size,
            media_type="photo",
            timestamp=datetime.now(UTC),
        )

        return media

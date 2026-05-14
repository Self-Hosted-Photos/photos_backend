import contextlib
import io
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import piexif
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.events import MediaUploadedEvent
from app.domain.models.media import Media, MediaStatus, MediaType
from app.exceptions import AuthorizationError, InvalidStateError, ResourceNotFoundError
from app.infrastructure.logging import security_log
from app.infrastructure.repositories.media_repo import SQLMediaRepository
from app.infrastructure.repositories.user_repo import SQLUserRepository
from app.infrastructure.storage.base import StorageBackend
from app.middleware.quota import check_quota

_ALLOWED_PHOTO_MIMES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
        "image/gif",
    }
)

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/heif": "heic",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _detect_mime_from_bytes(data: bytes) -> str | None:
    """Detect MIME type from magic bytes. Returns None if not recognised."""
    if len(data) < 12:
        return None
    h = data[:12]
    if h[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF: ftyp box — offset 4 is "ftyp", offset 8 is the brand
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        heic_brands = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
        if brand in heic_brands:
            return "image/heic"
    return None


_THUMBNAIL_SIZE = 320

MAX_IMAGE_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_IMAGE_WIDTH = 12_000
MAX_IMAGE_HEIGHT = 12_000
MAX_IMAGE_PIXELS = 100_000_000  # 100 MP
_THUMBNAIL_QUOTA_RESERVE = 5 * 1024 * 1024  # 5 MB estimate for thumbnail + overhead

# Set Pillow's decompression bomb threshold at module load time
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@dataclass
class PaginatedResult:
    items: list[Media]
    total: int
    page: int
    per_page: int

    @property
    def has_next(self) -> bool:
        return (self.page * self.per_page) < self.total


@dataclass
class TimelineGroup:
    year: int
    month: int
    items: list[Media] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class GpsCoordinates:
    latitude: float  # decimal degrees, -90.0 (S) to +90.0 (N)
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
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            captured_at = datetime.strptime(dt_raw.decode("ascii"), "%Y:%m:%d %H:%M:%S").date()

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
    """Return a square JPEG thumbnail. Raises InvalidStateError for malformed/oversized images."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
    except Image.DecompressionBombError:
        raise InvalidStateError(
            "Image exceeds maximum allowed pixel count (decompression bomb)"
        ) from None
    except Exception as exc:
        raise InvalidStateError(f"Cannot open image for thumbnail generation: {exc}") from exc

    w, h = img.size
    if w > MAX_IMAGE_WIDTH or h > MAX_IMAGE_HEIGHT:
        raise InvalidStateError(
            f"Image dimensions {w}×{h} exceed the maximum {MAX_IMAGE_WIDTH}×{MAX_IMAGE_HEIGHT}"
        )

    if img.mode != "RGB":
        img = img.convert("RGB")

    # Centre-crop to square
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
        # 1. File size guard (before any heavy work)
        file_size = len(file_bytes)
        if file_size > MAX_IMAGE_FILE_SIZE_BYTES:
            security_log.log_upload_rejected(
                user_id=user_id, filename=filename, reason="file_too_large"
            )
            raise InvalidStateError(f"File size {file_size:,} bytes exceeds the 25 MB limit")

        # 2. Validate declared MIME against allowlist
        declared_mime = content_type.lower().split(";")[0].strip()
        if declared_mime not in _ALLOWED_PHOTO_MIMES:
            security_log.log_upload_rejected(
                user_id=user_id, filename=filename, reason="invalid_declared_mime"
            )
            raise InvalidStateError(
                f"Unsupported file type: {declared_mime!r}. Allowed: {sorted(_ALLOWED_PHOTO_MIMES)}"
            )

        # 3. Magic-byte detection — reject if actual content doesn't match an allowed type
        detected_mime = _detect_mime_from_bytes(file_bytes)
        if detected_mime is None or detected_mime not in _ALLOWED_PHOTO_MIMES:
            security_log.log_upload_rejected(
                user_id=user_id, filename=filename, reason="mime_spoof_detected"
            )
            raise InvalidStateError(
                f"File content does not match a supported image format "
                f"(declared: {declared_mime!r}, detected: {detected_mime!r})"
            )

        # 4. Use magic-byte-detected MIME as canonical type
        mime = detected_mime
        ext = _MIME_TO_EXT.get(mime, "bin")

        # 5. Load user + quota check (reserve original + thumbnail estimate)
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User not found")
        check_quota(user, file_size + _THUMBNAIL_QUOTA_RESERVE)

        # 6. Build paths
        media_id = uuid.uuid4()
        filename_stored = f"{media_id}.{ext}"
        original_path = f"originals/{user_id}/{filename_stored}"
        thumbnail_path = f"thumbnails/{user_id}/{media_id}.jpg"

        # 7. Save original + generate thumbnail (clean up on any failure)
        original_saved = False
        try:
            await self._storage.save(original_path, io.BytesIO(file_bytes), mime)
            original_saved = True

            # 8. Parse EXIF
            captured_at, gps = _parse_exif(file_bytes)

            # 9. Generate thumbnail (raises InvalidStateError for malformed/oversized images)
            thumb_bytes = _generate_thumbnail(file_bytes)
            await self._storage.save(thumbnail_path, io.BytesIO(thumb_bytes), "image/jpeg")

        except Exception:
            if original_saved:
                with contextlib.suppress(Exception):
                    await self._storage.delete(original_path)
            raise

        # 10. Persist media row (status=ready — synchronous MVP flow)
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
        security_log.log_upload_accepted(
            user_id=user_id, media_id=media.id, filename=filename, file_size=file_size
        )

        # 11. Deduct actual usage from quota (original + thumbnail)
        user.storage_used_bytes += file_size + len(thumb_bytes)
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

    # ── Read operations ───────────────────────────────────────────────────────

    async def list_media(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
        date_from: date | None = None,
        date_to: date | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lng_min: float | None = None,
        lng_max: float | None = None,
    ) -> PaginatedResult:
        offset = (page - 1) * per_page
        items = await self._media.get_by_owner(
            owner_id=user_id,
            limit=per_page,
            offset=offset,
            date_from=date_from,
            date_to=date_to,
            lat_min=lat_min,
            lat_max=lat_max,
            lng_min=lng_min,
            lng_max=lng_max,
        )
        total = await self._media.count_by_owner(
            owner_id=user_id,
            date_from=date_from,
            date_to=date_to,
            lat_min=lat_min,
            lat_max=lat_max,
            lng_min=lng_min,
            lng_max=lng_max,
        )
        return PaginatedResult(items=items, total=total, page=page, per_page=per_page)

    async def get_timeline(self, user_id: uuid.UUID) -> list[TimelineGroup]:
        all_media = await self._media.get_all_for_timeline(user_id)

        groups: dict[tuple[int, int], TimelineGroup] = {}
        for item in all_media:
            if item.captured_at:
                key = (item.captured_at.year, item.captured_at.month)
            else:
                key = (item.uploaded_at.year, item.uploaded_at.month)
            if key not in groups:
                groups[key] = TimelineGroup(year=key[0], month=key[1])
            groups[key].items.append(item)

        return [g for _, g in sorted(groups.items(), reverse=True)]

    async def get_media(self, media_id: uuid.UUID, user_id: uuid.UUID) -> Media:
        from app.services.access_policy import MediaAccessPolicy

        media = await self._media.get_by_id(media_id)
        if not media:
            raise ResourceNotFoundError("Media not found")
        policy = MediaAccessPolicy(self._db)
        if not await policy.can_view_media(user_id, media_id, media=media):
            raise AuthorizationError("Not allowed to access this media")
        return media

    async def read_file_bytes(self, path: str) -> bytes:
        try:
            chunks = []
            async for chunk in self._storage.read(path):
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception as exc:
            raise ResourceNotFoundError(f"File not found: {path}") from exc

    def read_stream(self, path: str):
        """Return the async iterator from storage (for StreamingResponse)."""
        return self._storage.read(path)

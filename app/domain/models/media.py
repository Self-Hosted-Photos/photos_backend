import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MediaType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"


class MediaStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Media(Base):
    __tablename__ = "media"

    # Invariants:
    # - Owner cannot be changed after creation
    # - Status transitions: uploading → ready | failed (Celery worker: uploading → processing → ready)
    # - Original file path is immutable after set
    # - file_size must be positive

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename_original: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename_stored: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name="media_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="media_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=MediaStatus.UPLOADING,
    )
    original_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    transcoded_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    exif_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_media_owner_date", "owner_id", "captured_at"),
        Index("idx_media_status", "status"),
        # idx_media_owner_location partial index is defined in the Alembic migration only
        # (SQLite test DB creates a non-partial version via create_all)
    )

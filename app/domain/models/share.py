import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ShareType(str, enum.Enum):
    USER = "user"
    ALBUM = "album"
    PUBLIC_LINK = "public_link"


class Share(Base):
    __tablename__ = "shares"

    # Invariants:
    # - Must target either media OR album (not both, not neither)
    # - public_token is UUID4 (set only for public_link type)
    # - Cannot share with yourself (enforced in SharingService)
    # - Expired shares are invalid (is_valid() returns False)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    share_type: Mapped[ShareType] = mapped_column(
        Enum(ShareType, name="share_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    target_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media.id", ondelete="CASCADE"), nullable=True
    )
    target_album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="CASCADE"), nullable=True
    )
    shared_with_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # public_token uniqueness on non-NULL values enforced by
    # idx_shares_public_token partial index in the Alembic migration.
    public_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission: Mapped[str] = mapped_column(String(50), nullable=False, default="view")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def is_valid(self) -> bool:
        if self.expires_at:
            now = datetime.now(UTC)
            exp = self.expires_at
            # SQLite stores datetimes without timezone; assume UTC if naive
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if now > exp:
                return False
        return True

    __table_args__ = (
        Index("idx_shares_shared_with", "shared_with_user_id"),
    )

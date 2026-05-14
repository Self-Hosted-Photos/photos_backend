import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditEventType(str, enum.Enum):
    # Auth
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    REFRESH_FAILURE = "auth.refresh.failure"
    TOKEN_REUSE = "auth.token_reuse_detected"
    # Media
    MEDIA_UPLOAD_ACCEPTED = "media.upload.accepted"
    MEDIA_UPLOAD_REJECTED = "media.upload.rejected"
    MEDIA_DELETED = "media.deleted"
    # Shares
    SHARE_CREATED = "share.created"
    SHARE_REVOKED = "share.revoked"
    PUBLIC_SHARE_ACCESSED = "share.public_access"
    # Admin
    USER_APPROVED = "admin.user.approved"
    USER_SUSPENDED = "admin.user.suspended"
    USER_DELETED = "admin.user.deleted"
    QUOTA_CHANGED = "admin.quota.changed"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_actor_id", "actor_id"),
        Index("idx_audit_created_at", "created_at"),
    )

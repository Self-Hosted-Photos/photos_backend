import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

_logger = logging.getLogger("pixelvault.security")


def _emit(event_type: str, **kwargs: Any) -> None:
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event_type,
    }
    for k, v in kwargs.items():
        if v is None:
            continue
        record[k] = str(v) if isinstance(v, uuid.UUID) else v
    _logger.info(json.dumps(record))


# ── Auth events ───────────────────────────────────────────────────────────────


def log_login_success(user_id: uuid.UUID, email: str, ip_address: str | None = None) -> None:
    _emit("auth.login.success", user_id=user_id, email=email, ip_address=ip_address)


def log_login_failure(email: str, reason: str, ip_address: str | None = None) -> None:
    _emit("auth.login.failure", email=email, reason=reason, ip_address=ip_address)


def log_logout(user_id: uuid.UUID) -> None:
    _emit("auth.logout", user_id=user_id)


def log_refresh_failure(reason: str, ip_address: str | None = None) -> None:
    _emit("auth.refresh.failure", reason=reason, ip_address=ip_address)


def log_token_reuse_detected(user_id: uuid.UUID) -> None:
    _emit("auth.token_reuse_detected", user_id=user_id)


# ── Media events ──────────────────────────────────────────────────────────────


def log_upload_accepted(
    user_id: uuid.UUID, media_id: uuid.UUID, filename: str, file_size: int
) -> None:
    _emit(
        "media.upload.accepted",
        user_id=user_id,
        media_id=media_id,
        filename=filename,
        file_size=file_size,
    )


def log_upload_rejected(user_id: uuid.UUID, filename: str, reason: str) -> None:
    _emit("media.upload.rejected", user_id=user_id, filename=filename, reason=reason)


def log_media_deleted(actor_id: uuid.UUID, media_id: uuid.UUID) -> None:
    _emit("media.deleted", actor_id=actor_id, media_id=media_id)


# ── Share events ──────────────────────────────────────────────────────────────


def log_share_created(
    owner_id: uuid.UUID, share_id: uuid.UUID, share_type: str, target_id: uuid.UUID | None = None
) -> None:
    _emit(
        "share.created",
        owner_id=owner_id,
        share_id=share_id,
        share_type=share_type,
        target_id=target_id,
    )


def log_share_revoked(owner_id: uuid.UUID, share_id: uuid.UUID) -> None:
    _emit("share.revoked", owner_id=owner_id, share_id=share_id)


def log_public_share_accessed(share_id: uuid.UUID, ip_address: str | None = None) -> None:
    _emit("share.public_access", share_id=share_id, ip_address=ip_address)


# ── Admin events ──────────────────────────────────────────────────────────────


def log_user_approved(admin_id: uuid.UUID, user_id: uuid.UUID) -> None:
    _emit("admin.user.approved", admin_id=admin_id, user_id=user_id)


def log_user_suspended(admin_id: uuid.UUID | None, user_id: uuid.UUID) -> None:
    _emit("admin.user.suspended", admin_id=admin_id, user_id=user_id)


def log_user_deleted(admin_id: uuid.UUID | None, user_id: uuid.UUID) -> None:
    _emit("admin.user.deleted", admin_id=admin_id, user_id=user_id)


def log_quota_changed(admin_id: uuid.UUID, user_id: uuid.UUID, new_quota_bytes: int) -> None:
    _emit("admin.quota.changed", admin_id=admin_id, user_id=user_id, new_quota_bytes=new_quota_bytes)


# ── Rate limit events ─────────────────────────────────────────────────────────


def log_rate_limit_triggered(
    limit_name: str, user_id: uuid.UUID | None = None, ip_address: str | None = None
) -> None:
    _emit(
        "rate_limit.triggered",
        limit_name=limit_name,
        user_id=user_id,
        ip_address=ip_address,
    )

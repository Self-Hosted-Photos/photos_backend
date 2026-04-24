from app.domain.models.user import User
from app.exceptions import QuotaExceededError


def check_quota(user: User, file_size: int) -> None:
    """Raise QuotaExceededError if uploading file_size bytes would exceed the user's quota."""
    if not user.can_upload(file_size):
        used_gb = user.storage_used_bytes / (1024 ** 3)
        quota_gb = user.storage_quota_bytes / (1024 ** 3)
        raise QuotaExceededError(
            f"Storage quota exceeded. Used {used_gb:.1f} GB of {quota_gb:.1f} GB."
        )

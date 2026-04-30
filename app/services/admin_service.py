import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.events import UserApprovedEvent
from app.domain.models.media import Media
from app.domain.models.user import User, UserStatus
from app.domain.schemas.user import AdminStats
from app.exceptions import ResourceNotFoundError
from app.infrastructure.email.email_service import EmailService
from app.infrastructure.repositories.media_repo import SQLMediaRepository
from app.infrastructure.repositories.user_repo import SQLUserRepository


class AdminService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        email_service: EmailService,
    ) -> None:
        self._db = db
        self._settings = settings
        self._email = email_service
        self._users = SQLUserRepository(db)
        self._media = SQLMediaRepository(db)

    async def get_pending_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        return await self._users.get_pending_users(limit=limit, offset=offset)

    async def approve_user(self, user_id: uuid.UUID, admin_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")

        user.approve()  # raises InvalidStateError if not pending
        user = await self._users.save(user)
        await self._email.send_approval_notification(user.email, user.full_name)

        # Domain event — will be published to event bus when implemented
        _event = UserApprovedEvent(
            user_id=user.id,
            approved_by=admin_id,
            timestamp=datetime.now(UTC),
        )

        return user

    async def activate_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")
        user.activate()
        return await self._users.save(user)

    async def suspend_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")

        user.suspend()  # raises InvalidStateError if role is admin
        user = await self._users.save(user)
        return user

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")
        user.soft_delete()
        await self._users.save(user)

    async def get_all_users(
        self, status: UserStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[User]:
        return await self._users.get_all_users(status=status, limit=limit, offset=offset)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")
        return user

    async def update_user_quota(self, user_id: uuid.UUID, storage_quota_bytes: int) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")
        user.storage_quota_bytes = storage_quota_bytes
        return await self._users.save(user)

    async def get_all_media(self, limit: int = 50, offset: int = 0) -> tuple[list[Media], int]:
        items = await self._media.get_all(limit=limit, offset=offset)
        total = await self._media.count_all()
        return items, total

    async def delete_media(self, media_id: uuid.UUID) -> None:
        media = await self._media.get_by_id(media_id)
        if not media:
            raise ResourceNotFoundError(f"Media {media_id} not found")
        await self._media.delete(media_id)

    async def get_stats(self) -> AdminStats:
        pending = await self._users.count_by_status(UserStatus.PENDING)
        active = await self._users.count_by_status(UserStatus.ACTIVE)
        suspended = await self._users.count_by_status(UserStatus.SUSPENDED)
        total_storage = await self._users.get_total_storage_used()

        return AdminStats(
            total_users=pending + active + suspended,
            pending_users=pending,
            active_users=active,
            suspended_users=suspended,
            total_storage_used_bytes=total_storage,
            total_storage_used_gb=round(total_storage / (1024**3), 2),
        )

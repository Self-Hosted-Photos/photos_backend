import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.events import UserApprovedEvent
from app.domain.models.user import User, UserStatus
from app.domain.schemas.user import AdminStats
from app.exceptions import ResourceNotFoundError
from app.infrastructure.email.email_service import EmailService
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

    async def suspend_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")

        user.suspend()  # raises InvalidStateError if role is admin
        user = await self._users.save(user)
        return user

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
            total_storage_used_gb=round(total_storage / (1024 ** 3), 2),
        )

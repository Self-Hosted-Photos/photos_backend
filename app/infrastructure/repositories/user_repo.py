import uuid
from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.user import EmailToken, RefreshToken, User, UserStatus


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get_pending_users(self, limit: int, offset: int) -> list[User]: ...

    @abstractmethod
    async def get_all_users(self, status: UserStatus | None, limit: int, offset: int) -> list[User]: ...

    @abstractmethod
    async def count_by_status(self, status: UserStatus) -> int: ...

    @abstractmethod
    async def get_total_storage_used(self) -> int: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, id: uuid.UUID) -> None: ...


class SQLUserRepository(UserRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: uuid.UUID) -> User | None:
        result = await self._db.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_pending_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.status == UserStatus.PENDING)
            .order_by(User.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_all_users(
        self, status: UserStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[User]:
        q = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        if status is not None:
            q = q.where(User.status == status)
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def save(self, user: User) -> User:
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def count_by_status(self, status: UserStatus) -> int:
        result = await self._db.execute(
            select(func.count()).select_from(User).where(User.status == status)
        )
        return result.scalar_one()

    async def get_total_storage_used(self) -> int:
        result = await self._db.execute(
            select(func.sum(User.storage_used_bytes))
        )
        return result.scalar_one_or_none() or 0

    async def delete(self, id: uuid.UUID) -> None:
        user = await self.get_by_id(id)
        if user:
            await self._db.delete(user)
            await self._db.flush()


class EmailTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_token(self, token: str) -> EmailToken | None:
        result = await self._db.execute(
            select(EmailToken).where(EmailToken.token == token)
        )
        return result.scalar_one_or_none()

    async def save(self, token: EmailToken) -> EmailToken:
        self._db.add(token)
        await self._db.flush()
        await self._db.refresh(token)
        return token


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, token: RefreshToken) -> RefreshToken:
        self._db.add(token)
        await self._db.flush()
        await self._db.refresh(token)
        return token

    async def revoke(self, token_hash: str) -> None:
        token = await self.get_by_hash(token_hash)
        if token:
            token.revoked = True
            await self._db.flush()

    async def delete_by_hash(self, token_hash: str) -> None:
        token = await self.get_by_hash(token_hash)
        if token:
            await self._db.delete(token)
            await self._db.flush()

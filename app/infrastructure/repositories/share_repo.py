import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.share import Share


class SQLShareRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: uuid.UUID) -> Share | None:
        result = await self._db.execute(select(Share).where(Share.id == id))
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> Share | None:
        result = await self._db.execute(select(Share).where(Share.public_token == token))
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: uuid.UUID) -> list[Share]:
        result = await self._db.execute(
            select(Share).where(Share.owner_id == owner_id).order_by(Share.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_shared_with(self, user_id: uuid.UUID) -> list[Share]:
        result = await self._db.execute(
            select(Share)
            .where(Share.shared_with_user_id == user_id)
            .order_by(Share.created_at.desc())
        )
        return list(result.scalars().all())

    async def save(self, share: Share) -> Share:
        self._db.add(share)
        await self._db.flush()
        await self._db.refresh(share)
        return share

    async def delete(self, id: uuid.UUID) -> None:
        share = await self.get_by_id(id)
        if share:
            await self._db.delete(share)
            await self._db.flush()

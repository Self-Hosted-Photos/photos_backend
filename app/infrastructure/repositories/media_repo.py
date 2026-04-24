import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.media import Media


class MediaRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> Media | None: ...

    @abstractmethod
    async def save(self, media: Media) -> Media: ...

    @abstractmethod
    async def delete(self, id: uuid.UUID) -> None: ...


class SQLMediaRepository(MediaRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: uuid.UUID) -> Media | None:
        result = await self._db.execute(select(Media).where(Media.id == id))
        return result.scalar_one_or_none()

    async def save(self, media: Media) -> Media:
        self._db.add(media)
        await self._db.flush()
        await self._db.refresh(media)
        return media

    async def delete(self, id: uuid.UUID) -> None:
        media = await self.get_by_id(id)
        if media:
            await self._db.delete(media)
            await self._db.flush()

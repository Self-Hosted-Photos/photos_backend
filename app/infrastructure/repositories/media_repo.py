import uuid
from abc import ABC, abstractmethod
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.media import Media, MediaStatus


class MediaRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> Media | None: ...

    @abstractmethod
    async def get_by_owner(
        self,
        owner_id: uuid.UUID,
        limit: int,
        offset: int,
        date_from: date | None = None,
        date_to: date | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lng_min: float | None = None,
        lng_max: float | None = None,
    ) -> list[Media]: ...

    @abstractmethod
    async def count_by_owner(
        self,
        owner_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lng_min: float | None = None,
        lng_max: float | None = None,
    ) -> int: ...

    @abstractmethod
    async def get_all_for_timeline(self, owner_id: uuid.UUID) -> list[Media]: ...

    @abstractmethod
    async def get_all(self, limit: int, offset: int) -> list[Media]: ...

    @abstractmethod
    async def count_all(self) -> int: ...

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

    async def get_by_owner(
        self,
        owner_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        date_from: date | None = None,
        date_to: date | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lng_min: float | None = None,
        lng_max: float | None = None,
    ) -> list[Media]:
        q = (
            select(Media)
            .where(Media.owner_id == owner_id, Media.status == MediaStatus.READY)
            .order_by(Media.uploaded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        q = self._apply_filters(q, date_from, date_to, lat_min, lat_max, lng_min, lng_max)
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def count_by_owner(
        self,
        owner_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        lat_min: float | None = None,
        lat_max: float | None = None,
        lng_min: float | None = None,
        lng_max: float | None = None,
    ) -> int:
        q = (
            select(func.count())
            .select_from(Media)
            .where(Media.owner_id == owner_id, Media.status == MediaStatus.READY)
        )
        q = self._apply_filters(q, date_from, date_to, lat_min, lat_max, lng_min, lng_max)
        result = await self._db.execute(q)
        return result.scalar_one()

    async def get_all_for_timeline(self, owner_id: uuid.UUID) -> list[Media]:
        result = await self._db.execute(
            select(Media)
            .where(Media.owner_id == owner_id, Media.status == MediaStatus.READY)
            .order_by(Media.uploaded_at.desc())
        )
        return list(result.scalars().all())

    async def get_all(self, limit: int = 50, offset: int = 0) -> list[Media]:
        result = await self._db.execute(
            select(Media).order_by(Media.uploaded_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        result = await self._db.execute(select(func.count()).select_from(Media))
        return result.scalar_one()

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

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _apply_filters(q, date_from, date_to, lat_min, lat_max, lng_min, lng_max):
        if date_from is not None:
            q = q.where(Media.captured_at >= date_from)
        if date_to is not None:
            q = q.where(Media.captured_at <= date_to)
        if lat_min is not None:
            q = q.where(Media.latitude >= lat_min)
        if lat_max is not None:
            q = q.where(Media.latitude <= lat_max)
        if lng_min is not None:
            q = q.where(Media.longitude >= lng_min)
        if lng_max is not None:
            q = q.where(Media.longitude <= lng_max)
        return q

import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.album import Album, AlbumMedia
from app.domain.models.media import Media


class SQLAlbumRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: uuid.UUID) -> Album | None:
        result = await self._db.execute(select(Album).where(Album.id == id))
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_id: uuid.UUID) -> list[tuple[Album, int]]:
        """Returns list of (album, media_count) ordered by created_at desc."""
        result = await self._db.execute(
            select(Album, func.count(AlbumMedia.media_id).label("cnt"))
            .outerjoin(AlbumMedia, AlbumMedia.album_id == Album.id)
            .where(Album.owner_id == owner_id)
            .group_by(Album.id)
            .order_by(Album.created_at.desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def save(self, album: Album) -> Album:
        self._db.add(album)
        await self._db.flush()
        await self._db.refresh(album)
        return album

    async def delete(self, id: uuid.UUID) -> None:
        # Explicitly delete album_media rows first — SQLite doesn't enforce FK cascades by default
        await self._db.execute(sa.delete(AlbumMedia).where(AlbumMedia.album_id == id))
        album = await self.get_by_id(id)
        if album:
            await self._db.delete(album)
            await self._db.flush()

    async def media_in_album(self, album_id: uuid.UUID, media_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(AlbumMedia).where(
                AlbumMedia.album_id == album_id,
                AlbumMedia.media_id == media_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def add_media(
        self, album_id: uuid.UUID, media_id: uuid.UUID, sort_order: int = 0
    ) -> None:
        entry = AlbumMedia(album_id=album_id, media_id=media_id, sort_order=sort_order)
        self._db.add(entry)
        await self._db.flush()

    async def remove_media(self, album_id: uuid.UUID, media_id: uuid.UUID) -> None:
        await self._db.execute(
            sa.delete(AlbumMedia).where(
                AlbumMedia.album_id == album_id,
                AlbumMedia.media_id == media_id,
            )
        )
        await self._db.flush()

    async def get_media_for_album(self, album_id: uuid.UUID) -> list[Media]:
        result = await self._db.execute(
            select(Media)
            .join(AlbumMedia, AlbumMedia.media_id == Media.id)
            .where(AlbumMedia.album_id == album_id)
            .order_by(AlbumMedia.sort_order.asc(), AlbumMedia.added_at.asc())
        )
        return list(result.scalars().all())

    async def count_media_for_album(self, album_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.count()).select_from(AlbumMedia).where(AlbumMedia.album_id == album_id)
        )
        return result.scalar_one()

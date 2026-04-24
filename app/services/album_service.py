import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.album import Album
from app.domain.models.media import Media
from app.exceptions import AuthorizationError, ResourceNotFoundError
from app.infrastructure.repositories.album_repo import SQLAlbumRepository
from app.infrastructure.repositories.media_repo import SQLMediaRepository


class AlbumService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._albums = SQLAlbumRepository(db)
        self._media = SQLMediaRepository(db)

    async def create_album(
        self,
        user_id: uuid.UUID,
        title: str,
        description: str | None = None,
    ) -> tuple[Album, int]:
        album = Album(id=uuid.uuid4(), owner_id=user_id, title=title, description=description)
        album = await self._albums.save(album)
        return album, 0

    async def list_albums(self, user_id: uuid.UUID) -> list[tuple[Album, int]]:
        return await self._albums.get_by_owner(user_id)

    async def get_album(
        self, album_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Album, int, list[Media]]:
        album = await self._albums.get_by_id(album_id)
        if not album:
            raise ResourceNotFoundError("Album not found")
        if album.owner_id != user_id:
            raise AuthorizationError("Not allowed to access this album")

        items = await self._albums.get_media_for_album(album_id)
        return album, len(items), items

    async def update_album(
        self,
        album_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        cover_media_id: uuid.UUID | None = None,
    ) -> tuple[Album, int]:
        album = await self._albums.get_by_id(album_id)
        if not album:
            raise ResourceNotFoundError("Album not found")
        if album.owner_id != user_id:
            raise AuthorizationError("Not allowed to modify this album")

        if title is not None:
            album.title = title
        if description is not None:
            album.description = description
        if cover_media_id is not None:
            album.cover_media_id = cover_media_id

        album = await self._albums.save(album)
        count = await self._albums.count_media_for_album(album_id)
        return album, count

    async def delete_album(self, album_id: uuid.UUID, user_id: uuid.UUID) -> None:
        album = await self._albums.get_by_id(album_id)
        if not album:
            raise ResourceNotFoundError("Album not found")
        if album.owner_id != user_id:
            raise AuthorizationError("Not allowed to delete this album")

        await self._albums.delete(album_id)

    async def add_media_to_album(
        self,
        album_id: uuid.UUID,
        user_id: uuid.UUID,
        media_ids: list[uuid.UUID],
    ) -> tuple[Album, int, list[Media]]:
        album = await self._albums.get_by_id(album_id)
        if not album:
            raise ResourceNotFoundError("Album not found")
        if album.owner_id != user_id:
            raise AuthorizationError("Not allowed to modify this album")

        for media_id in media_ids:
            media = await self._media.get_by_id(media_id)
            if not media:
                raise ResourceNotFoundError(f"Media {media_id} not found")
            album.check_can_add_media(media)  # raises on wrong owner or non-ready status

            already_in = await self._albums.media_in_album(album_id, media_id)
            if not already_in:
                await self._albums.add_media(album_id, media_id)

        items = await self._albums.get_media_for_album(album_id)
        return album, len(items), items

    async def remove_media_from_album(
        self,
        album_id: uuid.UUID,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
    ) -> None:
        album = await self._albums.get_by_id(album_id)
        if not album:
            raise ResourceNotFoundError("Album not found")
        if album.owner_id != user_id:
            raise AuthorizationError("Not allowed to modify this album")

        await self._albums.remove_media(album_id, media_id)

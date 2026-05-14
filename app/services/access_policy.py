import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.album import Album
from app.domain.models.media import Media
from app.infrastructure.repositories.album_repo import SQLAlbumRepository
from app.infrastructure.repositories.media_repo import SQLMediaRepository
from app.infrastructure.repositories.share_repo import SQLShareRepository


class MediaAccessPolicy:
    """Centralised authorization checks for media, album, and share resources."""

    def __init__(self, db: AsyncSession) -> None:
        self._media = SQLMediaRepository(db)
        self._shares = SQLShareRepository(db)
        self._albums = SQLAlbumRepository(db)

    async def can_view_media(
        self,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        media: Media | None = None,
    ) -> bool:
        """True if user owns the media or has a valid direct share."""
        if media is None:
            media = await self._media.get_by_id(media_id)
        if media is None:
            return False
        if media.owner_id == user_id:
            return True
        # Check direct user shares
        shares = await self._shares.get_by_shared_with(user_id)
        return any(
            s.target_media_id == media_id and s.is_valid()
            for s in shares
        )

    async def can_delete_media(
        self,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        media: Media | None = None,
    ) -> bool:
        """True only if user owns the media."""
        if media is None:
            media = await self._media.get_by_id(media_id)
        if media is None:
            return False
        return media.owner_id == user_id

    async def can_view_album(
        self,
        user_id: uuid.UUID,
        album_id: uuid.UUID,
        album: Album | None = None,
    ) -> bool:
        """True if user owns the album or has a valid direct share."""
        if album is None:
            album = await self._albums.get_by_id(album_id)
        if album is None:
            return False
        if album.owner_id == user_id:
            return True
        shares = await self._shares.get_by_shared_with(user_id)
        return any(
            s.target_album_id == album_id and s.is_valid()
            for s in shares
        )

    async def can_modify_album(
        self,
        user_id: uuid.UUID,
        album_id: uuid.UUID,
        album: Album | None = None,
    ) -> bool:
        """True only if user owns the album."""
        if album is None:
            album = await self._albums.get_by_id(album_id)
        if album is None:
            return False
        return album.owner_id == user_id

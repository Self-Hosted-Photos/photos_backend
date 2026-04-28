import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.share import Share, ShareType
from app.domain.schemas.share import PublicAlbumResponse, PublicMediaResponse, PublicShareResponse
from app.exceptions import AuthorizationError, InvalidStateError, ResourceNotFoundError
from app.infrastructure.repositories.album_repo import SQLAlbumRepository
from app.infrastructure.repositories.media_repo import SQLMediaRepository
from app.infrastructure.repositories.share_repo import SQLShareRepository


class SharingService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._shares = SQLShareRepository(db)
        self._media = SQLMediaRepository(db)
        self._albums = SQLAlbumRepository(db)

    async def create_share(
        self,
        owner_id: uuid.UUID,
        share_type: str,
        target_media_id: uuid.UUID | None,
        target_album_id: uuid.UUID | None,
        shared_with_user_id: uuid.UUID | None,
        expires_at: datetime | None,
        permission: str,
    ) -> Share:
        # Validate target ownership
        if target_media_id is not None:
            media = await self._media.get_by_id(target_media_id)
            if not media:
                raise ResourceNotFoundError("Media not found")
            if media.owner_id != owner_id:
                raise AuthorizationError("Cannot share media you do not own")

        if target_album_id is not None:
            album = await self._albums.get_by_id(target_album_id)
            if not album:
                raise ResourceNotFoundError("Album not found")
            if album.owner_id != owner_id:
                raise AuthorizationError("Cannot share album you do not own")

        # Cannot share with yourself
        if shared_with_user_id is not None and shared_with_user_id == owner_id:
            raise InvalidStateError("Cannot share with yourself")

        public_token: str | None = None
        if share_type == "public_link":
            public_token = str(uuid.uuid4())

        share = Share(
            id=uuid.uuid4(),
            owner_id=owner_id,
            share_type=ShareType(share_type),
            target_media_id=target_media_id,
            target_album_id=target_album_id,
            shared_with_user_id=shared_with_user_id,
            public_token=public_token,
            permission=permission,
            expires_at=expires_at,
        )
        return await self._shares.save(share)

    async def list_my_shares(self, owner_id: uuid.UUID) -> list[Share]:
        return await self._shares.get_by_owner(owner_id)

    async def list_shares_with_me(self, user_id: uuid.UUID) -> list[Share]:
        return await self._shares.get_by_shared_with(user_id)

    async def revoke_share(self, share_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        share = await self._shares.get_by_id(share_id)
        if not share:
            raise ResourceNotFoundError("Share not found")
        if share.owner_id != owner_id:
            raise AuthorizationError("Not allowed to revoke this share")
        await self._shares.delete(share_id)

    async def resolve_public_share(self, token: str) -> PublicShareResponse:
        share = await self._shares.get_by_token(token)
        if not share or not share.is_valid():
            raise ResourceNotFoundError("Share not found")

        if share.target_media_id is not None:
            media = await self._media.get_by_id(share.target_media_id)
            if not media:
                raise ResourceNotFoundError("Share not found")
            return PublicShareResponse(
                share_type="media",
                media=PublicMediaResponse.model_validate(media),
            )

        # target_album_id
        album = await self._albums.get_by_id(share.target_album_id)
        if not album:
            raise ResourceNotFoundError("Share not found")
        items = await self._albums.get_media_for_album(share.target_album_id)
        return PublicShareResponse(
            share_type="album",
            album=PublicAlbumResponse(
                id=album.id,
                title=album.title,
                description=album.description,
                cover_media_id=album.cover_media_id,
                media_count=len(items),
                items=[PublicMediaResponse.model_validate(m) for m in items],
            ),
        )

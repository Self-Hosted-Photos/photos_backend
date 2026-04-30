import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DB, CurrentUser
from app.domain.schemas.album import (
    AddMediaRequest,
    AlbumCreate,
    AlbumDetailResponse,
    AlbumResponse,
    AlbumUpdate,
)
from app.domain.schemas.media import MediaResponse
from app.services.album_service import AlbumService

router = APIRouter(prefix="/albums", tags=["albums"])


def _get_album_service(db: DB) -> AlbumService:
    return AlbumService(db=db)


# ── POST /albums ──────────────────────────────────────────────────────────────


@router.post("", response_model=AlbumResponse, status_code=status.HTTP_201_CREATED)
async def create_album(
    body: AlbumCreate,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> AlbumResponse:
    album, count = await service.create_album(
        user_id=uuid.UUID(current_user["sub"]),
        title=body.title,
        description=body.description,
    )
    return AlbumResponse(**album.__dict__, media_count=count)


# ── GET /albums ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[AlbumResponse])
async def list_albums(
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> list[AlbumResponse]:
    rows = await service.list_albums(uuid.UUID(current_user["sub"]))
    return [AlbumResponse(**album.__dict__, media_count=count) for album, count in rows]


# ── GET /albums/{id} ──────────────────────────────────────────────────────────


@router.get("/{album_id}", response_model=AlbumDetailResponse)
async def get_album(
    album_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> AlbumDetailResponse:
    album, count, items = await service.get_album(
        album_id=album_id,
        user_id=uuid.UUID(current_user["sub"]),
    )
    return AlbumDetailResponse(
        **album.__dict__,
        media_count=count,
        items=[MediaResponse.model_validate(m) for m in items],
    )


# ── PUT /albums/{id} ──────────────────────────────────────────────────────────


@router.put("/{album_id}", response_model=AlbumResponse)
async def update_album(
    album_id: uuid.UUID,
    body: AlbumUpdate,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> AlbumResponse:
    album, count = await service.update_album(
        album_id=album_id,
        user_id=uuid.UUID(current_user["sub"]),
        title=body.title,
        description=body.description,
        cover_media_id=body.cover_media_id,
    )
    return AlbumResponse(**album.__dict__, media_count=count)


# ── DELETE /albums/{id} ───────────────────────────────────────────────────────


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album(
    album_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> None:
    await service.delete_album(
        album_id=album_id,
        user_id=uuid.UUID(current_user["sub"]),
    )


# ── POST /albums/{id}/media ───────────────────────────────────────────────────


@router.post("/{album_id}/media", response_model=AlbumDetailResponse)
async def add_media_to_album(
    album_id: uuid.UUID,
    body: AddMediaRequest,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> AlbumDetailResponse:
    album, count, items = await service.add_media_to_album(
        album_id=album_id,
        user_id=uuid.UUID(current_user["sub"]),
        media_ids=body.media_ids,
    )
    return AlbumDetailResponse(
        **album.__dict__,
        media_count=count,
        items=[MediaResponse.model_validate(m) for m in items],
    )


# ── DELETE /albums/{id}/media/{media_id} ──────────────────────────────────────


@router.delete("/{album_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_media_from_album(
    album_id: uuid.UUID,
    media_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[AlbumService, Depends(_get_album_service)],
) -> None:
    await service.remove_media_from_album(
        album_id=album_id,
        user_id=uuid.UUID(current_user["sub"]),
        media_id=media_id,
    )

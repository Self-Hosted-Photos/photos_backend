import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DB, CurrentUser
from app.domain.schemas.share import (
    PublicShareResponse,
    ShareCreate,
    ShareResponse,
)
from app.services.sharing_service import SharingService

router = APIRouter(prefix="/shares", tags=["shares"])
public_router = APIRouter(prefix="/public", tags=["public"])


def _get_sharing_service(db: DB) -> SharingService:
    return SharingService(db=db)


# ── POST /shares ──────────────────────────────────────────────────────────────


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share(
    body: ShareCreate,
    current_user: CurrentUser,
    service: Annotated[SharingService, Depends(_get_sharing_service)],
) -> ShareResponse:
    share = await service.create_share(
        owner_id=uuid.UUID(current_user["sub"]),
        share_type=body.share_type,
        target_media_id=body.target_media_id,
        target_album_id=body.target_album_id,
        shared_with_user_id=body.shared_with_user_id,
        expires_at=body.expires_at,
        permission=body.permission,
    )
    return ShareResponse.model_validate(share)


# ── GET /shares ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[ShareResponse])
async def list_my_shares(
    current_user: CurrentUser,
    service: Annotated[SharingService, Depends(_get_sharing_service)],
) -> list[ShareResponse]:
    shares = await service.list_my_shares(uuid.UUID(current_user["sub"]))
    return [ShareResponse.model_validate(s) for s in shares]


# ── GET /shares/with-me ───────────────────────────────────────────────────────


@router.get("/with-me", response_model=list[ShareResponse])
async def list_shares_with_me(
    current_user: CurrentUser,
    service: Annotated[SharingService, Depends(_get_sharing_service)],
) -> list[ShareResponse]:
    shares = await service.list_shares_with_me(uuid.UUID(current_user["sub"]))
    return [ShareResponse.model_validate(s) for s in shares]


# ── DELETE /shares/{id} ───────────────────────────────────────────────────────


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    share_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[SharingService, Depends(_get_sharing_service)],
) -> None:
    await service.revoke_share(
        share_id=share_id,
        owner_id=uuid.UUID(current_user["sub"]),
    )


# ── GET /public/{token} ───────────────────────────────────────────────────────


@public_router.get("/{token}", response_model=PublicShareResponse)
async def resolve_public_share(
    token: str,
    service: Annotated[SharingService, Depends(_get_sharing_service)],
) -> PublicShareResponse:
    return await service.resolve_public_share(token)

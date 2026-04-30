import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, AdminUser
from app.config import Settings, get_settings
from app.domain.models.user import User, UserStatus
from app.domain.schemas.media import MediaResponse, PaginatedMediaResponse, PaginationMeta
from app.domain.schemas.user import AdminStats, QuotaUpdateRequest, UserResponse
from app.infrastructure.email.email_service import EmailService
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_admin_service(
    db: DB,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminService:
    email = EmailService(smtp_enabled=settings.smtp_enabled, base_url=settings.base_url)
    return AdminService(db=db, settings=settings, email_service=email)


@router.get("/users/pending", response_model=list[UserResponse])
async def get_pending_users(
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[User]:
    return await service.get_pending_users(limit=limit, offset=offset)


@router.get("/users", response_model=list[UserResponse])
async def get_all_users(
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[User]:
    status_enum: UserStatus | None = None
    if status is not None:
        with contextlib.suppress(ValueError):
            status_enum = UserStatus(status)
    return await service.get_all_users(status=status_enum, limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> User:
    return await service.get_user_by_id(user_id)


@router.post("/users/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> User:
    admin_id = uuid.UUID(str(admin["sub"]))
    return await service.approve_user(user_id=user_id, admin_id=admin_id)


@router.post("/users/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> User:
    return await service.activate_user(user_id=user_id)


@router.post("/users/{user_id}/suspend", response_model=UserResponse)
async def suspend_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> User:
    return await service.suspend_user(user_id=user_id)


@router.put("/users/{user_id}/quota", response_model=UserResponse)
async def update_user_quota(
    user_id: uuid.UUID,
    body: QuotaUpdateRequest,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> User:
    return await service.update_user_quota(
        user_id=user_id, storage_quota_bytes=body.storage_quota_bytes
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> None:
    await service.delete_user(user_id=user_id)


@router.get("/stats", response_model=AdminStats)
async def get_stats(
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> AdminStats:
    return await service.get_stats()


@router.get("/media", response_model=PaginatedMediaResponse)
async def get_all_media(
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
) -> PaginatedMediaResponse:
    offset = (page - 1) * per_page
    items, total = await service.get_all_media(limit=per_page, offset=offset)
    return PaginatedMediaResponse(
        data=[MediaResponse.model_validate(m) for m in items],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            has_next=(offset + len(items)) < total,
        ),
    )


@router.delete("/media/{media_id}", status_code=204)
async def delete_media(
    media_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> None:
    await service.delete_media(media_id)

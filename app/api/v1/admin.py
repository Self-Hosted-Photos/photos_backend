import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminUser, DB
from app.config import Settings, get_settings
from app.domain.schemas.user import AdminStats, UserResponse
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
) -> list[UserResponse]:
    return await service.get_pending_users(limit=limit, offset=offset)


@router.post("/users/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> UserResponse:
    admin_id = uuid.UUID(admin["sub"])
    return await service.approve_user(user_id=user_id, admin_id=admin_id)


@router.post("/users/{user_id}/suspend", response_model=UserResponse)
async def suspend_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> UserResponse:
    return await service.suspend_user(user_id=user_id)


@router.get("/stats", response_model=AdminStats)
async def get_stats(
    _admin: AdminUser,
    service: Annotated[AdminService, Depends(_get_admin_service)],
) -> AdminStats:
    return await service.get_stats()

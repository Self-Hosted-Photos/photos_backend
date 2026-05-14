import uuid
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.domain.models.user import UserStatus
from app.infrastructure.repositories.user_repo import SQLUserRepository
from app.infrastructure.storage.base import StorageBackend
from app.infrastructure.storage.local import LocalStorageBackend

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(
    token: str,
    settings: Settings,
) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials, settings)

    # Live DB check — closes the 15-minute suspended-user window (N-02).
    # The JWT payload status is stale; the DB is authoritative.
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await SQLUserRepository(db).get_by_id(uuid.UUID(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "User not found"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status == UserStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_PENDING", "message": "Account awaiting admin approval"},
        )
    if user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_SUSPENDED", "message": "Account has been suspended"},
        )

    return payload


async def get_admin_user(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )
    return current_user


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorageBackend(
            storage_root=settings.storage_root,
            base_url=settings.base_url,
        )
    raise ValueError(f"Unknown storage backend: {settings.storage_backend!r}")


# Convenience type aliases
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
AdminUser = Annotated[dict[str, Any], Depends(get_admin_user)]
DB = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[StorageBackend, Depends(get_storage)]

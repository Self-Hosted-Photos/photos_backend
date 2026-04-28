import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.models.user import UserRole, UserStatus


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: UserRole
    status: UserStatus
    storage_used_bytes: int
    storage_quota_bytes: int
    email_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublicProfile(BaseModel):
    id: uuid.UUID
    full_name: str
    avatar_url: str | None

    model_config = {"from_attributes": True}


class StorageStats(BaseModel):
    storage_used_bytes: int
    storage_quota_bytes: int
    storage_used_gb: float
    storage_quota_gb: float
    percent_used: float


class AdminStats(BaseModel):
    total_users: int
    pending_users: int
    active_users: int
    suspended_users: int
    total_storage_used_bytes: int
    total_storage_used_gb: float

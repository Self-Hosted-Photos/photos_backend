import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.domain.models.media import MediaStatus, MediaType


class MediaResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    filename_original: str
    media_type: MediaType
    mime_type: str
    file_size_bytes: int
    status: MediaStatus
    original_path: str
    thumbnail_path: str | None
    captured_at: date | None
    latitude: float | None
    longitude: float | None
    uploaded_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    has_next: bool


class PaginatedMediaResponse(BaseModel):
    data: list[MediaResponse]
    meta: PaginationMeta


class TimelineGroupResponse(BaseModel):
    year: int
    month: int
    count: int
    items: list[MediaResponse]

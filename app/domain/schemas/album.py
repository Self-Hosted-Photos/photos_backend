import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.schemas.media import MediaResponse


class AlbumCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)


class AlbumUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    cover_media_id: uuid.UUID | None = None


class AddMediaRequest(BaseModel):
    media_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class AlbumResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: str | None
    cover_media_id: uuid.UUID | None
    media_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlbumDetailResponse(AlbumResponse):
    items: list[MediaResponse]

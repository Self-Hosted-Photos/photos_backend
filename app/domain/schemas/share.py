import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ShareCreate(BaseModel):
    share_type: Literal["user", "public_link"]
    target_media_id: uuid.UUID | None = None
    target_album_id: uuid.UUID | None = None
    shared_with_user_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    permission: str = Field(default="view", max_length=50)

    @model_validator(mode="after")
    def validate_target_and_recipient(self) -> "ShareCreate":
        has_media = self.target_media_id is not None
        has_album = self.target_album_id is not None
        if has_media == has_album:
            raise ValueError("Specify exactly one of target_media_id or target_album_id")
        if self.share_type == "user" and self.shared_with_user_id is None:
            raise ValueError("shared_with_user_id is required for user share type")
        return self


class ShareResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    share_type: str
    target_media_id: uuid.UUID | None
    target_album_id: uuid.UUID | None
    shared_with_user_id: uuid.UUID | None
    public_token: str | None
    permission: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicMediaResponse(BaseModel):
    id: uuid.UUID
    media_type: str
    mime_type: str
    file_size_bytes: int
    original_path: str
    thumbnail_path: str | None
    captured_at: date | None

    model_config = {"from_attributes": True}


class PublicAlbumResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    cover_media_id: uuid.UUID | None
    media_count: int
    items: list[PublicMediaResponse]


class PublicShareResponse(BaseModel):
    share_type: Literal["media", "album"]
    media: PublicMediaResponse | None = None
    album: PublicAlbumResponse | None = None

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserRegisteredEvent:
    user_id: uuid.UUID
    email: str
    timestamp: datetime


@dataclass
class UserApprovedEvent:
    user_id: uuid.UUID
    approved_by: uuid.UUID
    timestamp: datetime


@dataclass
class MediaUploadedEvent:
    media_id: uuid.UUID
    owner_id: uuid.UUID
    file_size: int
    media_type: str
    timestamp: datetime


@dataclass
class MediaProcessingCompletedEvent:
    media_id: uuid.UUID
    success: bool
    timestamp: datetime


@dataclass
class ShareCreatedEvent:
    share_id: uuid.UUID
    owner_id: uuid.UUID
    share_type: str
    timestamp: datetime

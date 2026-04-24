import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import CurrentUser, DB, Storage
from app.config import Settings, get_settings
from app.domain.schemas.media import MediaResponse
from app.services.media_service import MediaService

router = APIRouter(prefix="/media", tags=["media"])


def _get_media_service(
    db: DB,
    storage: Storage,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MediaService:
    return MediaService(db=db, settings=settings, storage=storage)


@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_media(
    current_user: CurrentUser,
    service: Annotated[MediaService, Depends(_get_media_service)],
    file: UploadFile = File(...),
) -> MediaResponse:
    file_bytes = await file.read()
    user_id = uuid.UUID(current_user["sub"])

    return await service.handle_upload(
        file_bytes=file_bytes,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        user_id=user_id,
    )

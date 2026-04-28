import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import CurrentUser, DB, Storage
from app.config import Settings, get_settings
from app.domain.schemas.media import (
    MediaResponse,
    PaginatedMediaResponse,
    PaginationMeta,
    TimelineGroupResponse,
)
from app.services.media_service import MediaService

router = APIRouter(prefix="/media", tags=["media"])


def _get_media_service(
    db: DB,
    storage: Storage,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MediaService:
    return MediaService(db=db, settings=settings, storage=storage)


def _parse_range_header(range_header: str, total: int) -> tuple[int, int]:
    """Parse 'bytes=start-end'. Returns (start, end), both inclusive."""
    try:
        range_val = range_header.split("=", 1)[1]
        start_str, end_str = range_val.split("-", 1)
        start = int(start_str)
        end = int(end_str) if end_str.strip() else total - 1
        return max(0, start), min(end, total - 1)
    except (IndexError, ValueError):
        return 0, total - 1


# ── POST /media/upload ────────────────────────────────────────────────────────

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


# ── GET /media ────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedMediaResponse)
async def list_media(
    current_user: CurrentUser,
    service: Annotated[MediaService, Depends(_get_media_service)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    lat_min: float | None = Query(default=None),
    lat_max: float | None = Query(default=None),
    lng_min: float | None = Query(default=None),
    lng_max: float | None = Query(default=None),
) -> PaginatedMediaResponse:
    # All four location bounds must be supplied together or not at all
    loc_params = [lat_min, lat_max, lng_min, lng_max]
    if any(p is not None for p in loc_params) and not all(p is not None for p in loc_params):
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "All four location bounds (lat_min, lat_max, lng_min, lng_max) must be provided together"},
        )

    result = await service.list_media(
        user_id=uuid.UUID(current_user["sub"]),
        page=page,
        per_page=per_page,
        date_from=date_from,
        date_to=date_to,
        lat_min=lat_min,
        lat_max=lat_max,
        lng_min=lng_min,
        lng_max=lng_max,
    )
    return PaginatedMediaResponse(
        data=[MediaResponse.model_validate(m) for m in result.items],
        meta=PaginationMeta(
            page=result.page,
            per_page=result.per_page,
            total=result.total,
            has_next=result.has_next,
        ),
    )


# ── GET /media/timeline ───────────────────────────────────────────────────────

@router.get("/timeline", response_model=list[TimelineGroupResponse])
async def get_timeline(
    current_user: CurrentUser,
    service: Annotated[MediaService, Depends(_get_media_service)],
) -> list[TimelineGroupResponse]:
    groups = await service.get_timeline(uuid.UUID(current_user["sub"]))
    return [
        TimelineGroupResponse(
            year=g.year,
            month=g.month,
            count=g.count,
            items=[MediaResponse.model_validate(m) for m in g.items],
        )
        for g in groups
    ]


# ── GET /media/{id}/thumbnail ─────────────────────────────────────────────────

@router.get("/{media_id}/thumbnail")
async def stream_thumbnail(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[MediaService, Depends(_get_media_service)],
) -> StreamingResponse:
    media = await service.get_media(media_id, uuid.UUID(current_user["sub"]))

    if not media.thumbnail_path:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Thumbnail not available"},
        )

    return StreamingResponse(
        service.read_stream(media.thumbnail_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


# ── GET /media/{id}/stream ────────────────────────────────────────────────────

@router.get("/{media_id}/stream")
async def stream_media(
    media_id: uuid.UUID,
    current_user: CurrentUser,
    service: Annotated[MediaService, Depends(_get_media_service)],
    request: Request,
) -> Response:
    media = await service.get_media(media_id, uuid.UUID(current_user["sub"]))
    raw = await service.read_file_bytes(media.original_path)
    total = len(raw)

    range_header = request.headers.get("range")
    if range_header:
        start, end = _parse_range_header(range_header, total)
        chunk = raw[start : end + 1]
        return Response(
            content=chunk,
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(chunk)),
                "Content-Type": media.mime_type,
            },
        )

    return Response(
        content=raw,
        status_code=200,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(total),
            "Content-Type": media.mime_type,
        },
    )

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser
from app.infrastructure.rate_limiter import AbstractRateLimiter, get_rate_limiter

router = APIRouter(tags=["logging"])

_logger = logging.getLogger("pixelvault.frontend")

_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


class ClientLogPayload(BaseModel):
    level: Literal["debug", "info", "warn", "error"]
    message: str = Field(max_length=500)
    path: str = Field(max_length=200)
    component: str = Field(max_length=100)
    error_stack: str | None = Field(default=None, max_length=2000)
    metadata: dict | None = Field(default=None)

    @field_validator("metadata")
    @classmethod
    def limit_metadata_keys(cls, v: dict | None) -> dict | None:
        if v is not None and len(v) > 10:
            raise ValueError("metadata may not have more than 10 keys")
        return v


@router.post("/client-logs", status_code=204)
async def receive_client_log(
    request: Request,
    payload: ClientLogPayload,
    current_user: CurrentUser,
    rate_limiter: Annotated[AbstractRateLimiter, Depends(get_rate_limiter)],
) -> None:
    ip = request.client.host if request.client else "unknown"
    await rate_limiter.check(
        key=f"client_log:{ip}",
        limit=10,
        window_seconds=60,
        action="client_log",
    )

    _logger.log(
        _LEVEL_MAP[payload.level],
        payload.message,
        extra={
            "user_id": current_user.get("sub"),
            "client_path": payload.path,
            "component": payload.component,
            "error_stack": payload.error_stack,
            "metadata": payload.metadata,
        },
    )

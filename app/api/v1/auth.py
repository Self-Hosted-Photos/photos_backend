from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.domain.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.domain.schemas.user import UserResponse
from app.exceptions import (
    AccountNotActiveError,
    ConflictError,
    InvalidCredentialsError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.infrastructure.email.email_service import EmailService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _get_email_service(settings: Annotated[Settings, Depends(get_settings)]) -> EmailService:
    return EmailService(smtp_enabled=settings.smtp_enabled, base_url=settings.base_url)


def _get_auth_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    email_service: Annotated[EmailService, Depends(_get_email_service)],
) -> AuthService:
    return AuthService(db=db, settings=settings, email_service=email_service)


def _set_refresh_cookie(
    response: Response, token: str, expire_days: int, secure: bool = True
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=expire_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


# ── POST /auth/register ───────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(
    data: RegisterRequest,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    try:
        user = await auth.register(data)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_ALREADY_EXISTS", "message": str(exc)},
        ) from exc
    return user


# ── POST /auth/login ──────────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    try:
        access_token, refresh_token_raw = await auth.login(
            data,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": str(exc)},
        ) from exc
    except AccountNotActiveError as exc:
        code = "ACCOUNT_PENDING" if "approval" in str(exc) else "ACCOUNT_SUSPENDED"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": str(exc)},
        ) from exc

    _set_refresh_cookie(
        response,
        refresh_token_raw,
        settings.refresh_token_expire_days,
        secure=settings.app_env != "development",
    )
    return TokenResponse(access_token=access_token)


# ── GET /auth/verify-email ────────────────────────────────────────────────────


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(
    token: str,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    try:
        await auth.verify_email(token)
    except (ResourceNotFoundError, InvalidStateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    return MessageResponse(message="Email verified successfully. Awaiting admin approval.")


# ── POST /auth/resend-verification ────────────────────────────────────────────


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerificationRequest,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    await auth.resend_verification(data.email)
    return MessageResponse(
        message="If that email exists and is unverified, a new link has been sent."
    )


# ── POST /auth/refresh ────────────────────────────────────────────────────────


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    refresh_token_raw = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Refresh token missing"},
        )
    try:
        access_token = await auth.refresh_access_token(refresh_token_raw)
    except (InvalidCredentialsError, AccountNotActiveError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": str(exc)},
        ) from exc
    return RefreshResponse(access_token=access_token)


# ── POST /auth/logout ─────────────────────────────────────────────────────────


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    refresh_token_raw = request.cookies.get(REFRESH_COOKIE)
    if refresh_token_raw:
        await auth.logout(refresh_token_raw)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully")


# ── POST /auth/forgot-password ────────────────────────────────────────────────


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    await auth.forgot_password(data.email)
    return MessageResponse(message="If that email exists, a password reset link has been sent.")


# ── POST /auth/reset-password ─────────────────────────────────────────────────


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    auth: Annotated[AuthService, Depends(_get_auth_service)],
):
    try:
        await auth.reset_password(data.token, data.new_password)
    except (ResourceNotFoundError, InvalidStateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    return MessageResponse(message="Password reset successfully. You can now log in.")

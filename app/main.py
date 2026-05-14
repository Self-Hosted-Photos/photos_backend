import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import (
    AccountNotActiveError,
    AuthorizationError,
    ConflictError,
    InvalidCredentialsError,
    InvalidStateError,
    QuotaExceededError,
    ResourceNotFoundError,
    TooManyRequestsError,
)
from app.middleware.cors import add_cors

# Attach an explicit stdout handler so all app.* loggers are visible in docker
# logs regardless of uvicorn's logging configuration.
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    _app_logger.addHandler(_handler)
    _app_logger.propagate = False

_security_logger = logging.getLogger("pixelvault.security")
_security_logger.setLevel(logging.INFO)
if not _security_logger.handlers:
    _sec_handler = logging.StreamHandler(sys.stdout)
    _sec_handler.setLevel(logging.INFO)
    _sec_handler.setFormatter(logging.Formatter("%(message)s"))
    _security_logger.addHandler(_sec_handler)
    _security_logger.propagate = False


_DEFAULT_SECRET = "dev-secret-key-change-in-production"
_MIN_SECRET_LEN = 32  # 256 bits minimum for HS256


@asynccontextmanager
async def lifespan(app: FastAPI):
    # N-01: Guard against a weak or default SECRET_KEY in production.
    from app.config import get_settings
    _s = get_settings()
    if _s.app_env == "production":
        if _s.secret_key == _DEFAULT_SECRET:
            raise RuntimeError(
                "SECRET_KEY is set to the default placeholder. "
                "Generate a strong key with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(_s.secret_key) < _MIN_SECRET_LEN:
            raise RuntimeError(
                f"SECRET_KEY must be at least {_MIN_SECRET_LEN} characters. "
                "Use secrets.token_hex(32) to generate a 64-char hex string."
            )
    yield
    # Shutdown: dispose engine
    from app.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pixel Vault API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    add_cors(app)
    _register_exception_handlers(app)
    _register_routers(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded_handler(request: Request, exc: QuotaExceededError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "QUOTA_EXCEEDED", "message": str(exc)}},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_handler(request: Request, exc: AuthorizationError):
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "FORBIDDEN", "message": str(exc)}},
        )

    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(request: Request, exc: ResourceNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": str(exc)}},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "CONFLICT", "message": str(exc)}},
        )

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "UNAUTHORIZED", "message": str(exc)}},
        )

    @app.exception_handler(AccountNotActiveError)
    async def account_not_active_handler(request: Request, exc: AccountNotActiveError):
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "ACCOUNT_PENDING", "message": str(exc)}},
        )

    @app.exception_handler(InvalidStateError)
    async def invalid_state_handler(request: Request, exc: InvalidStateError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_STATE", "message": str(exc)}},
        )

    @app.exception_handler(TooManyRequestsError)
    async def too_many_requests_handler(request: Request, exc: TooManyRequestsError):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": str(exc)}},
        )


def _register_routers(app: FastAPI) -> None:
    from app.api.v1 import admin, albums, auth, media, shares

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")
    app.include_router(albums.router, prefix="/api/v1")
    app.include_router(shares.router, prefix="/api/v1")
    app.include_router(shares.public_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}


app = create_app()

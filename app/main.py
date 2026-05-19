import logging
import logging.handlers
import os
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
from app.infrastructure.logging.json_formatter import JsonFormatter
from app.middleware.cors import add_cors

_DEFAULT_SECRET = "dev-secret-key-change-in-production"
_MIN_SECRET_LEN = 32


def _configure_logging() -> None:
    json_fmt = JsonFormatter()
    app_env = os.getenv("APP_ENV", "development")

    def _stdout_handler() -> logging.StreamHandler:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(json_fmt)
        return h

    # pixelvault.request — one JSON line per HTTP request (middleware writes here)
    _req = logging.getLogger("pixelvault.request")
    _req.setLevel(logging.INFO)
    if not _req.handlers:
        _req.addHandler(_stdout_handler())
        _req.propagate = False

    # pixelvault.security — pre-encoded JSON from security_log._emit()
    # JsonFormatter detects and flattens pre-encoded JSON messages.
    _sec = logging.getLogger("pixelvault.security")
    _sec.setLevel(logging.INFO)
    if not _sec.handlers:
        _sec.addHandler(_stdout_handler())
        _sec.propagate = False

    # pixelvault.frontend — client-side errors posted via /api/v1/client-logs
    # In production, writes to a file tailed by the CloudWatch Agent.
    # In development, writes to stdout so docker compose logs shows it.
    _fe = logging.getLogger("pixelvault.frontend")
    _fe.setLevel(logging.DEBUG)
    if not _fe.handlers:
        if app_env == "production":
            log_dir = "/var/log/pixelvault"
            os.makedirs(log_dir, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                f"{log_dir}/frontend-client.log",
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=3,
                encoding="utf-8",
            )
            fh.setFormatter(json_fmt)
            _fe.addHandler(fh)
        else:
            _fe.addHandler(_stdout_handler())
        _fe.propagate = False

    # uvicorn.error — startup/shutdown messages and unhandled exceptions
    _uv_err = logging.getLogger("uvicorn.error")
    _uv_err.setLevel(logging.INFO)
    if not _uv_err.handlers:
        _uv_err.addHandler(_stdout_handler())
        _uv_err.propagate = False

    # uvicorn.access — suppressed: RequestLoggingMiddleware replaces it with
    # richer structured output. Keeping both would double-log every request.
    _uv_acc = logging.getLogger("uvicorn.access")
    _uv_acc.setLevel(logging.CRITICAL)
    _uv_acc.propagate = False


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # N-01: Guard against a weak or default SECRET_KEY in production.
    from app.config import get_settings

    _s = get_settings()
    if _s.app_env == "production":
        if _s.secret_key == _DEFAULT_SECRET:
            raise RuntimeError(
                "SECRET_KEY is set to the default placeholder. "
                'Generate a strong key with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if len(_s.secret_key) < _MIN_SECRET_LEN:
            raise RuntimeError(
                f"SECRET_KEY must be at least {_MIN_SECRET_LEN} characters. "
                "Use secrets.token_hex(32) to generate a 64-char hex string."
            )
    yield
    from app.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    from app.middleware.request_logging import RequestLoggingMiddleware

    app = FastAPI(
        title="Pixel Vault API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # RequestLoggingMiddleware must be added before CORS so it captures the
    # final status code after all middleware has run.
    app.add_middleware(RequestLoggingMiddleware)
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
    from app.api.v1 import admin, albums, auth, client_logs, media, shares

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")
    app.include_router(albums.router, prefix="/api/v1")
    app.include_router(shares.router, prefix="/api/v1")
    app.include_router(shares.public_router, prefix="/api/v1")
    app.include_router(client_logs.router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}


app = create_app()

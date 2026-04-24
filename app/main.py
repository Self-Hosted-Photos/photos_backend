from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.exceptions import (
    AccountNotActiveError,
    AuthorizationError,
    ConflictError,
    InvalidCredentialsError,
    InvalidStateError,
    QuotaExceededError,
    ResourceNotFoundError,
)
from app.middleware.cors import add_cors


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing needed yet (DB connections are per-request via deps)
    yield
    # Shutdown: dispose engine
    from app.database import engine
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

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

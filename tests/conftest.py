import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must be set before app imports so Settings picks it up
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

from app.api.deps import get_storage  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.infrastructure.storage.local import LocalStorageBackend  # noqa: E402
from app.main import app  # noqa: E402

# In-memory SQLite for tests (no PostgreSQL needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def engine():
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest.fixture
async def db(engine):
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db, tmp_path):
    async def override_get_db():
        yield db

    def override_get_storage():
        return LocalStorageBackend(storage_root=str(tmp_path), base_url="http://test")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

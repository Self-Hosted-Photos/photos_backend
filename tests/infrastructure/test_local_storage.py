import io

import pytest

from app.exceptions import StorageError
from app.infrastructure.storage.local import LocalStorageBackend


@pytest.fixture
def storage(tmp_path) -> LocalStorageBackend:
    return LocalStorageBackend(storage_root=str(tmp_path), base_url="http://localhost:8000")


# ── save ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_writes_file_and_returns_path(storage, tmp_path):
    data = io.BytesIO(b"hello world")
    returned = await storage.save("originals/user1/photo.jpg", data, "image/jpeg")

    assert returned == "originals/user1/photo.jpg"
    assert (tmp_path / "originals/user1/photo.jpg").read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_save_creates_parent_directories(storage, tmp_path):
    await storage.save("originals/a/b/c/file.jpg", io.BytesIO(b"x"), "image/jpeg")
    assert (tmp_path / "originals/a/b/c/file.jpg").exists()


@pytest.mark.asyncio
async def test_save_overwrites_existing_file(storage, tmp_path):
    await storage.save("originals/u/f.jpg", io.BytesIO(b"old"), "image/jpeg")
    await storage.save("originals/u/f.jpg", io.BytesIO(b"new"), "image/jpeg")
    assert (tmp_path / "originals/u/f.jpg").read_bytes() == b"new"


# ── read ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_streams_correct_content(storage):
    await storage.save("originals/u/r.jpg", io.BytesIO(b"stream me"), "image/jpeg")

    chunks = [chunk async for chunk in storage.read("originals/u/r.jpg")]
    assert b"".join(chunks) == b"stream me"


@pytest.mark.asyncio
async def test_read_raises_storage_error_for_missing_file(storage):
    with pytest.raises(StorageError):
        async for _ in storage.read("originals/u/nonexistent.jpg"):
            pass


@pytest.mark.asyncio
async def test_read_large_file_yields_multiple_chunks(storage, tmp_path):
    # Write a file larger than _CHUNK_SIZE (64 KB) to verify chunking
    big = b"x" * (64 * 1024 + 1)
    await storage.save("originals/u/big.jpg", io.BytesIO(big), "image/jpeg")

    chunks = [chunk async for chunk in storage.read("originals/u/big.jpg")]
    assert len(chunks) == 2
    assert b"".join(chunks) == big


# ── delete ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_removes_file(storage, tmp_path):
    await storage.save("originals/u/del.jpg", io.BytesIO(b"bye"), "image/jpeg")
    await storage.delete("originals/u/del.jpg")
    assert not (tmp_path / "originals/u/del.jpg").exists()


@pytest.mark.asyncio
async def test_delete_is_idempotent_for_missing_file(storage):
    await storage.delete("originals/u/never_existed.jpg")  # must not raise


# ── get_url ───────────────────────────────────────────────────────────────────

def test_get_url_returns_correct_url(storage):
    url = storage.get_url("originals/user1/photo.jpg")
    assert url == "http://localhost:8000/storage/originals/user1/photo.jpg"


def test_get_url_strips_trailing_slash_from_base():
    s = LocalStorageBackend(storage_root="/tmp", base_url="http://localhost:8000/")
    assert s.get_url("thumbnails/u/t.jpg") == "http://localhost:8000/storage/thumbnails/u/t.jpg"


# ── exists ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exists_returns_true_for_saved_file(storage):
    await storage.save("thumbnails/u/e.jpg", io.BytesIO(b"y"), "image/jpeg")
    assert await storage.exists("thumbnails/u/e.jpg") is True


@pytest.mark.asyncio
async def test_exists_returns_false_for_missing_file(storage):
    assert await storage.exists("thumbnails/u/missing.jpg") is False

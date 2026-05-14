import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

from app.exceptions import StorageError
from app.infrastructure.storage.base import StorageBackend

_CHUNK_SIZE = 64 * 1024  # 64 KB


class LocalStorageBackend(StorageBackend):
    """
    Stores files on the local filesystem under storage_root.

    Directory layout (mirrors ADR-004):
        {storage_root}/originals/{user_id}/{media_id}.{ext}
        {storage_root}/transcoded/{user_id}/{media_id}.mp4
        {storage_root}/thumbnails/{user_id}/{media_id}.jpg
    """

    def __init__(self, storage_root: str, base_url: str) -> None:
        self._root = Path(storage_root).resolve()
        self._base_url = base_url.rstrip("/")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _safe_path(self, relative_path: str) -> Path:
        """Resolve relative_path under storage root, rejecting traversal attempts."""
        if "\x00" in relative_path:
            raise StorageError("Invalid path: null bytes not allowed")
        rel = Path(relative_path)
        if rel.is_absolute():
            raise StorageError("Absolute paths are not allowed")
        for part in rel.parts:
            if part == "..":
                raise StorageError("Path traversal is not allowed")
        resolved = (self._root / relative_path).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise StorageError("Path escapes storage root")
        return resolved

    # ── StorageBackend interface ──────────────────────────────────────────────

    async def save(self, path: str, data: BinaryIO, content_type: str) -> str:
        full = self._safe_path(path)

        def _write() -> None:
            full.parent.mkdir(parents=True, exist_ok=True)
            with open(full, "wb") as f:
                while chunk := data.read(_CHUNK_SIZE):
                    f.write(chunk)

        try:
            await asyncio.to_thread(_write)
        except OSError as exc:
            raise StorageError(f"Failed to write {path}: {exc}") from exc

        return path

    async def read(self, path: str) -> AsyncIterator[bytes]:
        full = self._safe_path(path)
        if not full.exists():
            raise StorageError(f"File not found: {path}")

        try:
            raw = await asyncio.to_thread(full.read_bytes)
        except OSError as exc:
            raise StorageError(f"Failed to read {path}: {exc}") from exc

        for i in range(0, len(raw), _CHUNK_SIZE):
            yield raw[i : i + _CHUNK_SIZE]

    async def delete(self, path: str) -> None:
        full = self._safe_path(path)
        try:
            await asyncio.to_thread(full.unlink, True)  # missing_ok=True
        except OSError as exc:
            raise StorageError(f"Failed to delete {path}: {exc}") from exc

    def get_url(self, path: str) -> str:
        return f"{self._base_url}/storage/{path}"

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(self._safe_path(path).exists)

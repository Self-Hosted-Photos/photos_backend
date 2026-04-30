from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import BinaryIO


class StorageBackend(ABC):
    """
    Abstract storage interface. Implementations: LocalStorageBackend (MVP), S3StorageBackend (future).
    All paths are relative (e.g. "originals/{user_id}/{media_id}.jpg").
    """

    @abstractmethod
    async def save(self, path: str, data: BinaryIO, content_type: str) -> str:
        """Write data to path. Returns the path on success."""
        ...

    @abstractmethod
    def read(self, path: str) -> AsyncIterator[bytes]:
        """Yield file contents in chunks. Raises StorageError if path does not exist."""
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Remove file at path. No-op if file does not exist."""
        ...

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Return the URL at which path can be served."""
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Return True if a file exists at path."""
        ...

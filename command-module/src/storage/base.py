from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    async def save_clip(self, data: bytes, relative_path: str) -> str:
        """Persist clip bytes and return the canonical path/key."""

    @abstractmethod
    async def get_clip_url(self, path: str) -> str:
        """Return a URL (local file path or presigned S3 URL) for playback."""

    @abstractmethod
    async def delete_clip(self, path: str) -> None:
        """Delete a clip by its canonical path/key."""

    @abstractmethod
    async def free_bytes(self) -> int:
        """Return available storage in bytes (-1 if unknown)."""

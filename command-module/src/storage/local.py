import asyncio
import shutil
from pathlib import Path

from config import settings
from storage.base import StorageBackend


class LocalDiskBackend(StorageBackend):
    def __init__(self):
        self.root = Path(settings.recordings_path)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_clip(self, data: bytes, relative_path: str) -> str:
        full = self.root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, full.write_bytes, data)
        return relative_path

    async def get_clip_url(self, path: str) -> str:
        return f"/recordings/{path}"

    async def delete_clip(self, path: str) -> None:
        full = self.root / path
        if full.exists():
            full.unlink()

    async def free_bytes(self) -> int:
        usage = shutil.disk_usage(self.root)
        return usage.free

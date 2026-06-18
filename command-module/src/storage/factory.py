from config import settings
from storage.base import StorageBackend


def get_storage_backend() -> StorageBackend:
    backend = settings.storage_backend.lower()
    if backend == "s3":
        from storage.s3 import S3Backend
        return S3Backend()
    from storage.local import LocalDiskBackend
    return LocalDiskBackend()

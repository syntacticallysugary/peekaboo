import asyncio

import boto3
from botocore.exceptions import ClientError

from config import settings
from storage.base import StorageBackend


class S3Backend(StorageBackend):
    def __init__(self):
        self._client = boto3.client("s3", region_name=settings.aws_region)
        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix.rstrip("/")

    def _key(self, path: str) -> str:
        return f"{self._prefix}/{path}"

    async def save_clip(self, data: bytes, relative_path: str) -> str:
        key = self._key(relative_path)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType="video/mp4"),
        )
        return relative_path

    async def get_clip_url(self, path: str) -> str:
        key = self._key(path)
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            lambda: self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=3600
            ),
        )
        return url

    async def delete_clip(self, path: str) -> None:
        key = self._key(path)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_object(Bucket=self._bucket, Key=key),
        )

    async def free_bytes(self) -> int:
        return -1

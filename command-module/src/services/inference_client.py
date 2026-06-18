import logging
from datetime import datetime, timezone

import httpx

from config import settings

logger = logging.getLogger(__name__)


class InferenceClient:
    """Async HTTP client for the Jetson Inference Node."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.inference_node_url,
            timeout=settings.inference_timeout_s,
        )
        self.online: bool = True
        self.last_success: datetime | None = None

    async def detect(self, frame_b64: str) -> dict:
        """
        Call POST /detect on the Inference Node.
        Returns the raw JSON dict on success.
        Raises httpx.HTTPError on failure.
        """
        resp = await self._client.post("/detect", json={"frame": frame_b64})
        resp.raise_for_status()
        self.online = True
        self.last_success = datetime.now(timezone.utc)
        return resp.json()

    async def recognize(self, embedding: list[float], candidates: list[dict]) -> dict:
        """Call POST /recognize on the Inference Node."""
        resp = await self._client.post(
            "/recognize",
            json={"embedding": embedding, "candidates": candidates},
        )
        resp.raise_for_status()
        self.online = True
        self.last_success = datetime.now(timezone.utc)
        return resp.json()

    async def set_armed(self, armed: bool) -> bool:
        """Push armed/disarmed state to the Jetson — disarming stops it from recording."""
        try:
            resp = await self._client.post("/system/armed", json={"armed": armed})
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Failed to push armed=%s to Jetson: %s", armed, exc)
            return False

    async def arm_capture(self) -> dict:
        resp = await self._client.post("/capture")
        resp.raise_for_status()
        return resp.json()

    async def get_capture_result(self) -> list[float] | None:
        try:
            resp = await self._client.get("/capture/result")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("embedding")
        except httpx.HTTPStatusError:
            return None

    async def health(self) -> dict | None:
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            self.online = True
            return resp.json()
        except Exception as exc:
            logger.warning("Inference Node health check failed: %s", exc)
            self.online = False
            return None

    async def close(self):
        await self._client.aclose()


inference_client = InferenceClient()

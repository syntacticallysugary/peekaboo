"""Deliver detection events to all registered active webhooks."""
import hashlib
import hmac
import json
import logging

import httpx

from google.cloud.firestore_v1 import FieldFilter

from config import settings
from db.firestore import WEBHOOKS, get_db
from services.event_queue import DetectionEvent, event_bus

logger = logging.getLogger(__name__)


async def _dispatch(event: DetectionEvent) -> None:
    payload = json.dumps(event.to_dict()).encode()
    db = get_db()

    async for doc in db.collection(WEBHOOKS).where(filter=FieldFilter("active", "==", True)).stream():
        wh = doc.to_dict()
        headers = {"Content-Type": "application/json"}
        secret = wh.get("secret")
        if secret:
            sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            headers["X-Peekaboo-Signature"] = f"sha256={sig}"
        url = wh.get("url", "")
        try:
            async with httpx.AsyncClient(timeout=settings.webhook_timeout_s) as client:
                resp = await client.post(url, content=payload, headers=headers)
            if not resp.is_success:
                logger.warning("Webhook %s returned %d", url, resp.status_code)
        except Exception as exc:
            logger.error("Webhook delivery to %s failed: %s", url, exc)


def register() -> None:
    event_bus.subscribe(_dispatch)

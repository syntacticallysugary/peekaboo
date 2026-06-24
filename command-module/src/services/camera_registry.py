"""
Background task that monitors camera node heartbeats and updates status.
Runs as an asyncio task alongside the FastAPI server.
"""
import asyncio
import logging
from datetime import datetime, timezone

from google.cloud.firestore_v1 import FieldFilter

from config import settings
from db.postgres import CAMERAS, get_db
from db.models import Camera
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)

_stop_event = asyncio.Event()


async def register_camera(
    camera_id: str, camera_type: str, ip: str | None, stream_url: str | None
) -> Camera:
    db = get_db()
    now = datetime.now(timezone.utc)
    data = {
        "type": camera_type,
        "ip": ip,
        "stream_url": stream_url,
        "last_seen": now,
        "status": "connected",
    }
    await db.collection(CAMERAS).document(camera_id).set(data)

    await ws_manager.broadcast({"type": "camera_status", "camera_id": camera_id, "status": "connected"})
    logger.info("Camera registered: %s (%s)", camera_id, camera_type)

    return Camera(
        camera_id=camera_id,
        type=camera_type,
        ip=ip,
        stream_url=stream_url,
        status="connected",
        last_seen=now,
    )


async def heartbeat(camera_id: str) -> None:
    db = get_db()
    await db.collection(CAMERAS).document(camera_id).update({
        "last_seen": datetime.now(timezone.utc),
        "status": "connected",
    })


async def _health_loop() -> None:
    timeout = settings.camera_heartbeat_timeout_s
    while not _stop_event.is_set():
        await asyncio.sleep(10)
        now = datetime.now(timezone.utc)
        db = get_db()
        async for doc in db.collection(CAMERAS).where(filter=FieldFilter("status", "==", "connected")).stream():
            data = doc.to_dict()
            last_seen = data.get("last_seen")
            if last_seen is None:
                continue
            # Firestore returns datetime objects with tzinfo
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age = (now - last_seen).total_seconds()
            if age > timeout:
                await doc.reference.update({"status": "disconnected"})
                logger.warning("Camera %s timed out (last seen %.0fs ago)", doc.id, age)
                await ws_manager.broadcast({
                    "type": "camera_status",
                    "camera_id": doc.id,
                    "status": "disconnected",
                })


def start() -> asyncio.Task:
    return asyncio.create_task(_health_loop())


def stop() -> None:
    _stop_event.set()

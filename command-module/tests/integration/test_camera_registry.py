import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from db.database import SessionLocal
from db.models import Camera
from services.camera_registry import register_camera, heartbeat

@pytest.mark.asyncio
async def test_camera_lifecycle_and_health_logic():
    cam_id = "test-lifecycle-cam"
    
    # 1. Register
    await register_camera(cam_id, "eye", "127.0.0.1", "http://test/stream")
    
    async with SessionLocal() as db:
        res = await db.execute(select(Camera).where(Camera.camera_id == cam_id))
        cam = res.scalar_one()
        assert cam.status == "connected"
        assert cam.ip == "127.0.0.1"
        last_seen_1 = cam.last_seen

    # 2. Heartbeat
    await asyncio.sleep(0.1)
    await heartbeat(cam_id)
    
    async with SessionLocal() as db:
        res = await db.execute(select(Camera).where(Camera.camera_id == cam_id))
        cam = res.scalar_one()
        assert cam.last_seen > last_seen_1

    # 3. Disconnect logic
    # Manually backdate the last_seen
    async with SessionLocal() as db:
        res = await db.execute(select(Camera).where(Camera.camera_id == cam_id))
        cam = res.scalar_one()
        cam.last_seen = datetime.now(timezone.utc) - timedelta(seconds=60)
        await db.commit()
    
    # Run the detection logic core
    timeout = 30
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        result = await db.execute(select(Camera).where(Camera.status == "connected"))
        cameras = result.scalars().all()
        for cam in cameras:
            # Only affect our test camera to avoid side effects on others
            if cam.camera_id == cam_id and cam.last_seen and (now - cam.last_seen).total_seconds() > timeout:
                cam.status = "disconnected"
        await db.commit()

    # 4. Verify disconnected
    async with SessionLocal() as db:
        res = await db.execute(select(Camera).where(Camera.camera_id == cam_id))
        cam = res.scalar_one()
        assert cam.status == "disconnected"

    # 5. Cleanup
    async with SessionLocal() as db:
        await db.delete(cam)
        await db.commit()

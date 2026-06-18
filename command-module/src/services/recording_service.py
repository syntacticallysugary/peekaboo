"""
Pulls the MJPEG stream from a camera node for a fixed duration and saves it as MP4.
Uses ffmpeg via subprocess to avoid OpenCV threading issues with multiple streams.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from storage.factory import get_storage_backend

logger = logging.getLogger(__name__)

_storage = get_storage_backend()


async def record_clip(
    camera_id: str,
    stream_url: str,
    classification: str,
    duration_s: int = 30,
) -> str | None:
    """
    Stream `duration_s` seconds of video from `stream_url` and persist it.
    Returns the canonical storage path, or None on failure.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    ts_str = now.strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts_str}_{classification}.mp4"
    relative_path = f"{date_str}/{camera_id}/{filename}"

    tmp = Path(f"/tmp/pfig_{uuid.uuid4().hex}.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-t", str(duration_s),
        "-i", stream_url,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-an",
        str(tmp),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=duration_s + 15)
        if proc.returncode != 0:
            logger.error("ffmpeg exited %d for camera %s", proc.returncode, camera_id)
            return None

        data = tmp.read_bytes()
        path = await _storage.save_clip(data, relative_path)
        logger.info("Clip saved: %s (%d bytes)", path, len(data))
        return path

    except asyncio.TimeoutError:
        logger.error("ffmpeg timed out for camera %s", camera_id)
        return None
    except Exception as exc:
        logger.error("Recording failed for camera %s: %s", camera_id, exc)
        return None
    finally:
        if tmp.exists():
            tmp.unlink()


async def check_storage_health() -> bool:
    """Returns False if free space is below the configured minimum."""
    free = await _storage.free_bytes()
    if free == -1:
        return True
    min_bytes = settings.recording_min_free_gb * 1024 ** 3
    return free >= min_bytes

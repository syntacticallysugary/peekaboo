"""Frame persistence, mp4 encoding, and retention cleanup."""
import logging
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def save_frame(frame_bytes: bytes, frames_dir: Path, frame_index: int) -> None:
    path = frames_dir / f"frame_{frame_index:06d}.jpg"
    path.write_bytes(frame_bytes)


def encode_mp4(frames_dir: Path, output_path: Path, fps: int = 10) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.jpg"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            logger.error("ffmpeg encode failed: %s", result.stderr.decode(errors="replace"))
            return False
        for f in frames_dir.glob("frame_*.jpg"):
            f.unlink()
        frames_dir.rmdir()
        return True
    except Exception as exc:
        logger.error("encode_mp4 error: %s", exc)
        return False


def purge_old_recordings(recordings_dir: Path, max_age_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    if not recordings_dir.is_dir():
        return
    for session_dir in recordings_dir.iterdir():
        if not session_dir.is_dir():
            continue
        mtime = datetime.fromtimestamp(session_dir.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.info("Purged old recording: %s", session_dir.name)

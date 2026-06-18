"""Firmware binary storage and OTA distribution for camera devices."""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/firmware", tags=["firmware"])

_FIRMWARE_DIR = Path("/data/firmware")

# Channels known to the camera build (platformio.ini FIRMWARE_CHANNEL values).
_KNOWN_CHANNELS = ["s3eye", "xiao", "esp32cam"]


def _ensure_dir() -> None:
    _FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
async def list_firmware():
    """Current stored firmware per known channel, for the Settings UI."""
    _ensure_dir()
    result = []
    for channel in _KNOWN_CHANNELS:
        ver_path = _FIRMWARE_DIR / f"{channel}.version"
        bin_path = _FIRMWARE_DIR / f"{channel}.bin"
        if ver_path.exists() and bin_path.exists():
            result.append({
                "channel": channel,
                "version": ver_path.read_text().strip(),
                "size": bin_path.stat().st_size,
                "updated_at": datetime.fromtimestamp(
                    bin_path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
        else:
            result.append({"channel": channel, "version": None, "size": None, "updated_at": None})
    return result


@router.post("/{channel}")
async def upload_firmware(channel: str, request: Request):
    """
    Store a firmware binary for a camera channel (e.g. 's3eye', 'xiao').

    Send the raw .bin as the request body with X-Firmware-Version header.
    Example:
        curl -X POST http://localhost:8081/api/firmware/s3eye \\
             -H 'X-Firmware-Version: 1.1.0' \\
             -H 'Content-Type: application/octet-stream' \\
             --data-binary @.pio/build/esp32s3eye/firmware.bin
    """
    _ensure_dir()
    version = request.headers.get("X-Firmware-Version", "").strip()
    if not version:
        raise HTTPException(400, "X-Firmware-Version header required")

    body = await request.body()
    if len(body) < 1024:
        raise HTTPException(400, "Firmware binary too small — upload the full .bin file")

    (_FIRMWARE_DIR / f"{channel}.bin").write_bytes(body)
    (_FIRMWARE_DIR / f"{channel}.version").write_text(version)

    return {"channel": channel, "version": version, "size": len(body)}


@router.get("/{channel}/check")
async def check_firmware(channel: str, version: str = Query(...)):
    """
    Called by cameras on boot and periodically to check for updates.

    Returns update_available=true when the stored version differs from the
    device's current version string.
    """
    ver_path = _FIRMWARE_DIR / f"{channel}.version"
    if not ver_path.exists():
        return {"update_available": False, "version": None}

    stored = ver_path.read_text().strip()
    return {"update_available": stored != version, "version": stored}


@router.get("/{channel}/binary")
async def get_firmware_binary(channel: str):
    """Serve the stored firmware binary for OTA download."""
    bin_path = _FIRMWARE_DIR / f"{channel}.bin"
    if not bin_path.exists():
        raise HTTPException(404, f"No firmware stored for channel '{channel}'")

    return FileResponse(
        bin_path,
        media_type="application/octet-stream",
        filename=f"{channel}-firmware.bin",
    )

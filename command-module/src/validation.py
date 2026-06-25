"""Input validation helpers for API endpoints."""

import re
from urllib.parse import urlparse

from fastapi import HTTPException

# Format validation patterns
CAMERA_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,48}[a-z0-9]$", re.IGNORECASE)
CHANNEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,19}$", re.IGNORECASE)
PERSON_ID_PATTERN = re.compile(r"^[a-z0-9]{8,}$", re.IGNORECASE)

# Size limits (bytes)
MAX_JPEG_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_FIRMWARE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FRAME_B64_SIZE = 6 * 1024 * 1024  # 6 MB (base64 is ~1.33x larger than binary)

# Allowed MIME types
ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png")
ALLOWED_FIRMWARE_TYPES = ("application/octet-stream", "application/x-binary")


def validate_camera_id(camera_id: str) -> str:
    """Validate camera ID format.

    Raises:
        HTTPException: 400 if invalid format.

    Returns:
        The validated camera_id.
    """
    if not camera_id:
        raise HTTPException(400, "camera_id cannot be empty")
    if len(camera_id) > 50:
        raise HTTPException(400, "camera_id too long (max 50 chars)")
    if not CAMERA_ID_PATTERN.match(camera_id):
        raise HTTPException(400, "camera_id format invalid (alphanumeric, hyphen, underscore only)")
    return camera_id


def validate_channel(channel: str) -> str:
    """Validate firmware channel name.

    Raises:
        HTTPException: 400 if invalid format.

    Returns:
        The validated channel.
    """
    if not channel:
        raise HTTPException(400, "channel cannot be empty")
    if len(channel) > 20:
        raise HTTPException(400, "channel too long (max 20 chars)")
    if not CHANNEL_PATTERN.match(channel):
        raise HTTPException(400, "channel format invalid (lowercase alphanumeric, underscore only)")
    return channel


def validate_person_id(person_id: str) -> str:
    """Validate person ID format.

    Raises:
        HTTPException: 400 if invalid format.

    Returns:
        The validated person_id.
    """
    if not person_id:
        raise HTTPException(400, "person_id cannot be empty")
    if len(person_id) > 1024:
        raise HTTPException(400, "person_id too long")
    if not PERSON_ID_PATTERN.match(person_id):
        raise HTTPException(400, "person_id format invalid")
    return person_id


def validate_image_size(data: bytes) -> bytes:
    """Validate image file size.

    Raises:
        HTTPException: 413 if too large.

    Returns:
        The validated data.
    """
    if len(data) > MAX_JPEG_SIZE:
        raise HTTPException(413, f"Image exceeds {MAX_JPEG_SIZE // (1024*1024)} MB limit")
    return data


def validate_image_mime_type(mime_type: str | None) -> str:
    """Validate image MIME type.

    Raises:
        HTTPException: 400 if invalid.

    Returns:
        The validated mime_type.
    """
    if not mime_type:
        raise HTTPException(400, "Content-Type header required")
    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Only {ALLOWED_IMAGE_TYPES} allowed")
    return mime_type


def validate_firmware_mime_type(mime_type: str | None) -> str:
    """Validate firmware binary MIME type.

    Raises:
        HTTPException: 400 if invalid.

    Returns:
        The validated mime_type.
    """
    if not mime_type:
        raise HTTPException(400, "Content-Type header required")
    if mime_type not in ALLOWED_FIRMWARE_TYPES:
        raise HTTPException(400, f"Only {ALLOWED_FIRMWARE_TYPES} allowed")
    return mime_type


def validate_b64_frame_size(b64_data: str) -> str:
    """Validate base64-encoded frame size.

    Base64 is ~33% larger than binary, so we check the encoded size.

    Raises:
        HTTPException: 413 if too large.

    Returns:
        The validated b64_data.
    """
    if len(b64_data) > MAX_FRAME_B64_SIZE:
        raise HTTPException(413, f"Frame exceeds size limit")
    return b64_data


def validate_webhook_url(url_str: str) -> str:
    """Validate webhook URL for SSRF safety.

    Blocks:
    - Private IP ranges (127.0.0.1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local and multicast ranges
    - Non-HTTP(S) schemes
    - Localhost and shorthand hostnames

    Raises:
        HTTPException: 400 if unsafe.

    Returns:
        The validated URL string.
    """
    try:
        parsed = urlparse(url_str)
    except Exception:
        raise HTTPException(400, "Invalid URL format")

    # Check scheme (only HTTP/HTTPS allowed)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http/https schemes allowed for webhooks")

    # Extract hostname
    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(400, "Webhook URL must include a hostname")

    # Require https for external webhooks
    if parsed.scheme == "http":
        raise HTTPException(400, "Webhook URLs must use HTTPS (not HTTP)")

    # Block localhost variants
    localhost_variants = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "[::]", "127.0.0.2")  # nosec B104
    if hostname.lower() in localhost_variants or hostname.startswith("127."):
        raise HTTPException(400, "Localhost URLs not allowed for webhooks")

    # Block private IPv4 ranges using simple prefix checks
    # (not comprehensive CIDR checking, but sufficient for SSRF blocking)
    blocked_prefixes = (
        "10.",           # 10.0.0.0/8
        "172.16.",       # 172.16.0.0/12 (start of range)
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",       # 172.31.255.255/12 (end of range)
        "192.168.",      # 192.168.0.0/16
        "169.254.",      # 169.254.0.0/16 (link-local)
        "224.",          # 224.0.0.0/4 (multicast)
        "255.255.",      # 255.255.x.x (broadcast)
    )

    for prefix in blocked_prefixes:
        if hostname.startswith(prefix):
            raise HTTPException(400, f"Private network URLs not allowed for webhooks (blocked: {prefix}*)")

    # Block IPv6 private ranges (basic check)
    if hostname.startswith("fc") or hostname.startswith("fd"):
        raise HTTPException(400, "IPv6 private ranges not allowed for webhooks")

    # Require HTTPS for external URLs as defense in depth
    if parsed.scheme != "https":
        raise HTTPException(400, "Only HTTPS webhooks supported (HTTP not secure)")

    return url_str

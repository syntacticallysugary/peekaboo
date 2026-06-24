"""Audit logging for security events and state changes.

Logs are written to Firestore collection 'audit_logs' with:
- Timestamp (UTC)
- Event type (enum)
- Actor (API key, service name)
- Resource (camera_id, person_id, webhook_id, etc.)
- Action details (what changed, old/new values)
- Result (success, failure reason)
"""

import logging
from datetime import datetime, timezone
from enum import Enum

from db.firestore import get_db

logger = logging.getLogger(__name__)

AUDIT_COLLECTION = "audit_logs"


class AuditEventType(str, Enum):
    """Audit event categories."""

    # Camera management
    CAMERA_REGISTERED = "camera_registered"
    CAMERA_DELETED = "camera_deleted"
    CAMERA_REBOOT = "camera_reboot"
    CAMERA_OTA_CHECK = "camera_ota_check"
    CAMERA_DIAG_REQUESTED = "camera_diag_requested"

    # Person/face management
    PERSON_CREATED = "person_created"
    PERSON_DELETED = "person_deleted"
    PERSON_UPDATED = "person_updated"
    FACE_ENROLLED = "face_enrolled"

    # Firmware management
    FIRMWARE_UPLOADED = "firmware_uploaded"
    FIRMWARE_DOWNLOADED = "firmware_downloaded"

    # System control
    SYSTEM_ARMED = "system_armed"
    SYSTEM_DISARMED = "system_disarmed"

    # Webhook management
    WEBHOOK_CREATED = "webhook_created"
    WEBHOOK_DELETED = "webhook_deleted"
    WEBHOOK_DELIVERY_FAILED = "webhook_delivery_failed"

    # Authentication/Security
    AUTH_FAILED = "auth_failed"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


async def log_audit_event(
    event_type: AuditEventType,
    actor: str | None = None,
    resource: str | None = None,
    resource_type: str | None = None,
    details: dict | None = None,
    success: bool = True,
    error_reason: str | None = None,
) -> None:
    """Log an audit event to Firestore.

    Args:
        event_type: Type of event (from AuditEventType enum)
        actor: Who performed the action (e.g. "api_key:...", "system")
        resource: ID of affected resource (camera_id, person_id, etc.)
        resource_type: Type of resource ("camera", "person", "firmware", "webhook")
        details: Additional context (JSON-serializable dict)
        success: Whether the action succeeded
        error_reason: If success=False, reason for failure

    Returns:
        None (errors are logged but don't raise)
    """
    try:
        db = get_db()
        doc_data = {
            "timestamp": datetime.now(timezone.utc),
            "event_type": event_type.value,
            "actor": actor or "unknown",
            "resource": resource,
            "resource_type": resource_type,
            "success": success,
            "error_reason": error_reason,
            "details": details or {},
        }

        # Add to Firestore (auto-generates document ID)
        await db.collection(AUDIT_COLLECTION).add(doc_data)

    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc, exc_info=True)
        # Don't raise; audit logging failures shouldn't break the application


async def log_camera_registered(actor: str, camera_id: str, camera_type: str, ip: str | None) -> None:
    """Log camera registration."""
    await log_audit_event(
        AuditEventType.CAMERA_REGISTERED,
        actor=actor,
        resource=camera_id,
        resource_type="camera",
        details={"type": camera_type, "ip": ip},
    )


async def log_camera_deleted(actor: str, camera_id: str) -> None:
    """Log camera deletion."""
    await log_audit_event(
        AuditEventType.CAMERA_DELETED,
        actor=actor,
        resource=camera_id,
        resource_type="camera",
    )


async def log_person_created(actor: str, person_id: str, name: str) -> None:
    """Log person enrollment."""
    await log_audit_event(
        AuditEventType.PERSON_CREATED,
        actor=actor,
        resource=person_id,
        resource_type="person",
        details={"name": name},
    )


async def log_person_deleted(actor: str, person_id: str, name: str | None = None) -> None:
    """Log person deletion."""
    await log_audit_event(
        AuditEventType.PERSON_DELETED,
        actor=actor,
        resource=person_id,
        resource_type="person",
        details={"name": name},
    )


async def log_face_enrolled(actor: str, person_id: str, face_count: int) -> None:
    """Log face enrollment for a person."""
    await log_audit_event(
        AuditEventType.FACE_ENROLLED,
        actor=actor,
        resource=person_id,
        resource_type="person",
        details={"face_count": face_count},
    )


async def log_firmware_uploaded(actor: str, channel: str, version: str, size_bytes: int) -> None:
    """Log firmware upload."""
    await log_audit_event(
        AuditEventType.FIRMWARE_UPLOADED,
        actor=actor,
        resource=channel,
        resource_type="firmware",
        details={"version": version, "size_bytes": size_bytes},
    )


async def log_firmware_downloaded(actor: str, channel: str, camera_id: str | None = None) -> None:
    """Log firmware download (camera OTA)."""
    await log_audit_event(
        AuditEventType.FIRMWARE_DOWNLOADED,
        actor=actor,
        resource=channel,
        resource_type="firmware",
        details={"camera_id": camera_id},
    )


async def log_system_armed(actor: str) -> None:
    """Log system arm."""
    await log_audit_event(
        AuditEventType.SYSTEM_ARMED,
        actor=actor,
    )


async def log_system_disarmed(actor: str, reason: str | None = None) -> None:
    """Log system disarm."""
    await log_audit_event(
        AuditEventType.SYSTEM_DISARMED,
        actor=actor,
        details={"reason": reason},
    )


async def log_webhook_created(actor: str, webhook_id: str, url: str) -> None:
    """Log webhook creation."""
    await log_audit_event(
        AuditEventType.WEBHOOK_CREATED,
        actor=actor,
        resource=webhook_id,
        resource_type="webhook",
        details={"url": url},
    )


async def log_webhook_deleted(actor: str, webhook_id: str) -> None:
    """Log webhook deletion."""
    await log_audit_event(
        AuditEventType.WEBHOOK_DELETED,
        actor=actor,
        resource=webhook_id,
        resource_type="webhook",
    )


async def log_webhook_delivery_failed(webhook_id: str, url: str, error: str) -> None:
    """Log failed webhook delivery."""
    await log_audit_event(
        AuditEventType.WEBHOOK_DELIVERY_FAILED,
        actor="system",
        resource=webhook_id,
        resource_type="webhook",
        details={"url": url, "error": error},
        success=False,
        error_reason=error,
    )


async def log_auth_failed(ip_address: str | None, reason: str) -> None:
    """Log authentication failure."""
    await log_audit_event(
        AuditEventType.AUTH_FAILED,
        actor=ip_address or "unknown",
        details={"reason": reason},
        success=False,
        error_reason=reason,
    )


async def log_rate_limit_exceeded(ip_address: str, endpoint: str) -> None:
    """Log rate limit violation."""
    await log_audit_event(
        AuditEventType.RATE_LIMIT_EXCEEDED,
        actor=ip_address or "unknown",
        resource=endpoint,
        resource_type="api_endpoint",
        success=False,
        error_reason="rate_limit_exceeded",
    )

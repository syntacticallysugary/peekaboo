"""Receive completed-session alerts from the Jetson inference service."""
import logging
import uuid
from datetime import datetime, timezone

from auth import verify_api_key
from rate_limit import limiter
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from db.postgres import EVENTS, get_db
from services import system_state
from services.event_queue import DetectionEvent as BusEvent, event_bus
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_CLASSIFICATION_MAP = {
    "unknown_face":       "unknown",
    "unidentified_human": "no_face",
    "authorized":         "known",
    "unallowed":          "unallowed",
}


class SessionAlertRequest(BaseModel):
    camera_id: str
    session_id: str
    classification: str
    best_frame: str | None = None
    recording_path: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    peak_similarity: float | None = None


@router.post("", status_code=202)
@limiter.limit("100/minute")
async def receive_alert(request: Request, alert: SessionAlertRequest, _: str = Depends(verify_api_key)):
    if not system_state.is_armed():
        logger.info("System disarmed — discarding session alert from %s", alert.camera_id)
        return {"status": "discarded_disarmed"}

    classification = _CLASSIFICATION_MAP.get(alert.classification, alert.classification)
    detected_at = datetime.now(timezone.utc)
    eid = str(uuid.uuid4())

    db = get_db()
    await db.collection(EVENTS).document(eid).set({
        "camera_id": alert.camera_id,
        "detected_at": detected_at,
        "classification": classification,
        "person_id": None,
        "confidence": alert.peak_similarity,
        "recording_path": alert.recording_path,
        "best_frame": alert.best_frame,
    })

    await event_bus.publish(BusEvent(
        event_id=eid,
        camera_id=alert.camera_id,
        detected_at=detected_at,
        classification=classification,
        recording_path=alert.recording_path,
    ))

    await ws_manager.broadcast({
        "type":           "session_alert",
        "camera_id":      alert.camera_id,
        "session_id":     alert.session_id,
        "classification": classification,
        "recording_path": alert.recording_path,
        "detected_at":    detected_at.isoformat(),
    })

    logger.info(
        "Session alert from Jetson — camera=%s session=%s classification=%s",
        alert.camera_id, alert.session_id, classification,
    )
    return {"status": "accepted", "event_id": eid}

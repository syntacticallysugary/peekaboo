"""Camera registry and edge-report endpoints."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_api_key
from audit import log_camera_deleted, log_camera_registered
from rate_limit import limiter, LIMIT_DEFAULT, LIMIT_REGISTER, LIMIT_FIRMWARE, LIMIT_PERSON, LIMIT_WEBHOOK
from config import settings
from db.firestore import CAMERAS, EVENTS, PERSONS, get_db
from validation import validate_camera_id
from orchestration.state import SystemState, TriggerEvent
from orchestration.workflow import guard_workflow
from services import camera_registry, system_state
from services.event_queue import DetectionEvent as BusEvent, event_bus
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["cameras"])

# Shared workflow state — known_persons is loaded fresh per invocation
_system_state: SystemState = {
    "trigger": None,
    "frame_b64": None,
    "detected_faces": [],
    "recognition_match": None,
    "classification": None,
    "matched_person": None,
    "recording_path": None,
    "known_persons": [],
    "cooldowns": {},
    "inference_online": True,
    "inference_fallback_mode": False,
    "workflow_path": "",
    "error": None,
}


class RegisterRequest(BaseModel):
    camera_id: str
    type: str
    ip: str | None = None
    stream_url: str | None = None
    capabilities: str | None = None


class TriggerRequest(BaseModel):
    timestamp: str
    motion_score: float
    frame: str | None = None
    frame_url: str | None = None
    stream_url: str | None = None


class FaceEventRequest(BaseModel):
    camera_id: str
    frame: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int


class FaceEventResponse(BaseModel):
    action: str
    duration_s: int | None = None


class MotionEventRequest(BaseModel):
    camera_id: str


class CameraConfig(BaseModel):
    cooldown_s: int = 600
    motion_threshold: int = 20
    jpeg_quality: int = 12


class EdgeReportRequest(BaseModel):
    camera_id: str
    classification: str       # unknown | unallowed | false_alarm | arrival
    frame: str
    person_id: str | None = None
    similarity: float | None = None


@router.post("/register", status_code=201)
@limiter.limit("10/minute")
async def register(req: RegisterRequest, _: str = Depends(verify_api_key)):
    cam = await camera_registry.register_camera(req.camera_id, req.type, req.ip, req.stream_url)
    await log_camera_registered(actor="api", camera_id=cam.camera_id, camera_type=req.type, ip=req.ip)
    return {"camera_id": cam.camera_id, "status": cam.status}


@router.post("/{camera_id}/trigger", status_code=202)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def trigger(camera_id: str, req: TriggerRequest, bg: BackgroundTasks, _: str = Depends(verify_api_key)):
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc = await db.collection(CAMERAS).document(camera_id).get()
    if not doc.exists:
        raise HTTPException(404, f"Camera '{camera_id}' not registered")

    await camera_registry.heartbeat(camera_id)

    cooldown_until = _system_state["cooldowns"].get("known_person")
    if cooldown_until and datetime.now(timezone.utc) < cooldown_until:
        logger.debug("Known person cooldown active — trigger on %s ignored", camera_id)
        return {"status": "cooldown"}

    cam_data = doc.to_dict()
    trigger_event: TriggerEvent = {
        "camera_id": camera_id,
        "timestamp": req.timestamp,
        "motion_score": req.motion_score,
        "frame_b64": req.frame,
        "frame_url": req.frame_url or (f"http://{cam_data.get('ip')}/capture" if cam_data.get("ip") else None),
        "stream_url": req.stream_url or cam_data.get("stream_url"),
    }
    bg.add_task(_run_workflow, trigger_event)
    return {"status": "accepted"}


@router.get("")
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def list_cameras(_: str = Depends(verify_api_key)):
    db = get_db()
    cameras = []
    async for doc in db.collection(CAMERAS).stream():
        d = doc.to_dict()
        cameras.append({
            "camera_id": doc.id,
            "type": d.get("type"),
            "ip": d.get("ip"),
            "stream_url": d.get("stream_url"),
            "status": d.get("status"),
            "last_seen": d["last_seen"].isoformat() if d.get("last_seen") else None,
        })
    return cameras


@router.delete("/{camera_id}", status_code=204)
@limiter.limit("100/minute")
async def delete_camera(camera_id: str, _: str = Depends(verify_api_key)):
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc_ref = db.collection(CAMERAS).document(camera_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404, f"Camera '{camera_id}' not found")
    await doc_ref.delete()
    await log_camera_deleted(actor="api", camera_id=camera_id)


@router.get("/{camera_id}/config", response_model=CameraConfig)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def get_camera_config(camera_id: str, _: str = Depends(verify_api_key)):
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc = await db.collection(CAMERAS).document(camera_id).get()
    if not doc.exists:
        raise HTTPException(404, f"Camera '{camera_id}' not registered")
    await camera_registry.heartbeat(camera_id)
    return CameraConfig()


@router.post("/{camera_id}/face", response_model=FaceEventResponse)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def face_event(camera_id: str, req: FaceEventRequest, bg: BackgroundTasks, _: str = Depends(verify_api_key)):
    """DEPRECATED — kept for backward compatibility."""
    await camera_registry.heartbeat(camera_id)
    from services.inference_client import inference_client
    resp = await inference_client._client.post("/identify", json={
        "camera_id": camera_id,
        "frame": req.frame,
    })
    resp.raise_for_status()
    data = resp.json()
    if data["action"] == "alert":
        trigger_event: TriggerEvent = {
            "camera_id": camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "motion_score": 1.0,
            "frame_b64": req.frame,
            "frame_url": None,
            "stream_url": None,
        }
        bg.add_task(_run_workflow, trigger_event)
    return FaceEventResponse(action=data["action"], duration_s=600)


@router.post("/{camera_id}/heartbeat", status_code=200)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def camera_heartbeat(camera_id: str, _: str = Depends(verify_api_key)):
    """Called by the inference service when a camera is actively sending frames."""
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc = await db.collection(CAMERAS).document(camera_id).get()
    if doc.exists:
        await camera_registry.heartbeat(camera_id)
    return {"status": "ok"}


@router.post("/report", status_code=202)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def report_edge_event(req: EdgeReportRequest, bg: BackgroundTasks, _: str = Depends(verify_api_key)):
    """
    Edge-First Alert Receiver.
    The Jetson calls this after making its own classification decision.
    Classification is trusted directly — no re-inference.
    """
    if not system_state.is_armed():
        logger.debug("System disarmed — ignoring edge report from %s", req.camera_id)
        return {"status": "discarded_disarmed"}

    logger.info("Edge report from %s: %s (person=%s)", req.camera_id, req.classification, req.person_id)
    bg.add_task(_handle_edge_report, req)
    return {"status": "reported"}


async def _handle_edge_report(req: EdgeReportRequest) -> None:
    canonical = {
        "unknown": "unknown",
        "unallowed": "unallowed",
        "false_alarm": "known",
        "arrival": "known",
    }.get(req.classification, "unknown")

    person_name: str | None = None
    db = get_db()

    if req.person_id:
        person_doc = await db.collection(PERSONS).document(req.person_id).get()
        if person_doc.exists:
            person_name = person_doc.to_dict().get("name")

    # Unknown alerts are written to Firestore only when the session is finalized
    # (via /api/alerts), so they arrive with a recording attached. Skipping the
    # Firestore write here avoids a duplicate event with no recording.
    if canonical != "unknown":
        eid = str(uuid.uuid4())
        await db.collection(EVENTS).document(eid).set({
            "camera_id": req.camera_id,
            "detected_at": datetime.now(timezone.utc),
            "classification": canonical,
            "person_id": req.person_id,
            "confidence": req.similarity,
            "recording_path": None,
        })
        await event_bus.publish(BusEvent(
            event_id=eid,
            camera_id=req.camera_id,
            detected_at=datetime.now(timezone.utc),
            classification=canonical,
            person_id=req.person_id,
            confidence=req.similarity,
            extra={"edge_classification": req.classification, "person_name": person_name},
        ))

    await ws_manager.broadcast({
        "type": "detection_event",
        "camera_id": req.camera_id,
        "classification": canonical,
        "edge_classification": req.classification,
        "person_name": person_name,
        "recording_path": None,
    })


async def _require_camera(camera_id: str) -> None:
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc = await db.collection(CAMERAS).document(camera_id).get()
    if not doc.exists:
        raise HTTPException(404, f"Camera '{camera_id}' not registered")


@router.post("/{camera_id}/reboot", status_code=202)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def reboot_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """Send a secure reboot command to the camera over MQTT."""
    from services.mqtt_control import mqtt_control
    await _require_camera(camera_id)
    try:
        await mqtt_control.publish_command(camera_id, "reboot")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"status": "reboot_sent"}


@router.post("/{camera_id}/ota-check", status_code=202)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def ota_check_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """Ask the camera to poll for new firmware immediately."""
    camera_id = validate_camera_id(camera_id)
    from services.mqtt_control import mqtt_control
    await _require_camera(camera_id)
    try:
        await mqtt_control.publish_command(camera_id, "ota_check")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"status": "ota_check_sent"}


@router.post("/{camera_id}/diag")
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def diag_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """Request live diagnostics and wait briefly for the camera's response."""
    from services.mqtt_control import mqtt_control
    await _require_camera(camera_id)
    try:
        result = await mqtt_control.request_diag(camera_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    if result is None:
        raise HTTPException(504, "Camera did not respond — it may be offline")
    return result


@router.get("/{camera_id}/status")
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def camera_mqtt_status(camera_id: str, _: str = Depends(verify_api_key)):
    """Return the last status message received from the camera over MQTT."""
    camera_id = validate_camera_id(camera_id)
    from services.mqtt_control import latest_status
    return latest_status.get(camera_id) or {"event": "unknown"}


@router.post("/{camera_id}/motion", status_code=202)
@limiter.limit("100/minute")
@limiter.limit("100/minute")
async def motion_event(camera_id: str, req: MotionEventRequest, bg: BackgroundTasks, _: str = Depends(verify_api_key)):
    camera_id = validate_camera_id(camera_id)
    db = get_db()
    doc = await db.collection(CAMERAS).document(camera_id).get()
    if not doc.exists:
        raise HTTPException(404, f"Camera '{camera_id}' not registered")

    await camera_registry.heartbeat(camera_id)
    cam_data = doc.to_dict()
    trigger_event: TriggerEvent = {
        "camera_id": camera_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "motion_score": 1.0,
        "frame_b64": None,
        "frame_url": f"http://{cam_data.get('ip')}/capture" if cam_data.get("ip") else None,
        "stream_url": cam_data.get("stream_url"),
    }
    bg.add_task(_run_workflow, trigger_event)
    return {"status": "accepted"}


async def _load_known_persons() -> list[dict]:
    db = get_db()
    persons = []
    async for doc in db.collection(PERSONS).stream():
        d = doc.to_dict()
        persons.append({
            "person_id": doc.id,
            "name": d.get("name", ""),
            "is_blocked": d.get("is_blocked", False),
            "embeddings": [e["embedding"] for e in d.get("embeddings", [])],
        })
    return persons


async def _run_workflow(trigger: TriggerEvent) -> None:
    if not system_state.is_armed():
        logger.debug("System disarmed — skipping workflow for %s", trigger["camera_id"])
        return
    known = await _load_known_persons()
    state = {**_system_state, "trigger": trigger, "workflow_path": "start", "known_persons": known}
    try:
        await guard_workflow.ainvoke(state)
    except Exception as exc:
        logger.error("Workflow error for %s: %s", trigger["camera_id"], exc)

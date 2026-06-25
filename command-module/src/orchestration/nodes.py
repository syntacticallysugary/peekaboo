"""
LangGraph node functions. Each takes SystemState, mutates a copy, returns it.
"""
import base64
import logging
import uuid
from datetime import datetime, timezone

import httpx

from config import settings
from db.postgres import EVENTS, db_session
from orchestration.state import SystemState
from services.event_queue import DetectionEvent as BusEvent, event_bus
from services.inference_client import inference_client
from services.recording_service import check_storage_health, record_clip
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)


async def fetch_frame_node(state: SystemState) -> SystemState:
    trigger = state["trigger"]
    if not trigger:
        state["error"] = "No trigger in state"
        return state

    if trigger.get("frame_b64"):
        state["frame_b64"] = trigger["frame_b64"]
        return state

    url = trigger.get("frame_url")
    if url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                state["frame_b64"] = base64.b64encode(resp.content).decode()
        except Exception as exc:
            logger.warning("Frame fetch from %s failed: %s — proceeding without frame", url, exc)
    else:
        logger.debug("No frame in trigger for %s — motion-only path", trigger.get("camera_id"))
    return state


async def run_detection_node(state: SystemState) -> SystemState:
    if state.get("error"):
        return state
    frame = state.get("frame_b64")
    if not frame:
        logger.debug("No frame available — skipping detection, routing to record")
        return state

    try:
        result = await inference_client.detect(frame)
        state["detected_faces"] = result.get("faces", [])
        state["inference_online"] = True
        state["inference_fallback_mode"] = False
        logger.debug("Detected %d faces (%.1f ms)", len(state["detected_faces"]), result.get("inference_ms", 0))

        from services import capture_service
        faces = state["detected_faces"]
        if faces:
            best = max(faces, key=lambda f: f.get("confidence", 0))
            embedding = best.get("embedding", [])
            if embedding:
                capture_service.offer(embedding)
    except Exception as exc:
        logger.error("Detection failed: %s", exc)
        inference_client.online = False
        state["inference_online"] = False
        state["inference_fallback_mode"] = True
        state["detected_faces"] = []
    return state


async def run_recognition_node(state: SystemState) -> SystemState:
    if state.get("error"):
        return state
    faces = state.get("detected_faces", [])
    if not faces:
        return state

    best = max(faces, key=lambda f: f.get("confidence", 0))
    embedding = best.get("embedding", [])
    if not embedding:
        state["classification"] = "no_face"
        return state

    known = state.get("known_persons", [])
    candidates = [
        {"person_id": p["person_id"], "embedding": emb}
        for p in known
        for emb in p["embeddings"]
    ]

    if not candidates:
        state["recognition_match"] = None
        return state

    try:
        result = await inference_client.recognize(embedding, candidates)
        match = result.get("match")
        state["recognition_match"] = match
        if match:
            pid = match["person_id"]
            state["matched_person"] = next(
                (p for p in known if p["person_id"] == pid), None
            )
    except Exception as exc:
        logger.error("Recognition failed: %s", exc)
        state["recognition_match"] = None
    return state


async def start_recording_node(state: SystemState) -> SystemState:
    trigger = state["trigger"]
    camera_id = trigger["camera_id"] if trigger else "unknown"

    match = state.get("recognition_match")
    person = state.get("matched_person")
    faces = state.get("detected_faces", [])

    if not faces:
        classification = "no_face"
    elif match and person and person.get("is_blocked"):
        classification = "unallowed"
    else:
        classification = "unknown"

    state["classification"] = classification

    if not await check_storage_health():
        logger.error("Storage below minimum threshold — skipping recording")
        state["recording_path"] = None
        return state

    stream_url = trigger.get("stream_url") if trigger else None
    if stream_url:
        path = await record_clip(camera_id, stream_url, classification)
        state["recording_path"] = path
    else:
        logger.warning("No stream_url in trigger for %s — clip not recorded", camera_id)
        state["recording_path"] = None

    return state


async def suppress_recording_node(state: SystemState) -> SystemState:
    state["classification"] = "known"
    state["recording_path"] = None
    trigger = state["trigger"]
    camera_id = trigger["camera_id"] if trigger else "unknown"
    person_id = state.get("matched_person", {}).get("person_id", "unknown")
    from datetime import timedelta
    state["cooldowns"]["known_person"] = datetime.now(timezone.utc) + \
        timedelta(seconds=settings.known_person_cooldown_s)
    logger.info("Known person %s on %s — recording suppressed, all-camera cooldown set for %d sec",
                person_id, camera_id, settings.known_person_cooldown_s)
    return state


async def persist_event_node(state: SystemState) -> SystemState:
    trigger = state["trigger"]
    camera_id = trigger["camera_id"] if trigger else "unknown"
    classification = state.get("classification") or "unknown"
    person = state.get("matched_person")
    match = state.get("recognition_match")
    eid = str(uuid.uuid4())

    event_data = {
        "camera_id": camera_id,
        "detected_at": datetime.now(timezone.utc),
        "classification": classification,
        "person_id": person["person_id"] if person else None,
        "confidence": match["similarity"] if match else None,
        "recording_path": state.get("recording_path"),
    }
    async with db_session() as db:
        await db.collection(EVENTS).document(eid).set(event_data)

    bus_event = BusEvent(
        event_id=eid,
        camera_id=camera_id,
        detected_at=event_data["detected_at"],
        classification=classification,
        person_id=person["person_id"] if person else None,
        confidence=match["similarity"] if match else None,
        recording_path=state.get("recording_path"),
    )
    await event_bus.publish(bus_event)
    return state


async def notify_dashboard_node(state: SystemState) -> SystemState:
    trigger = state["trigger"]
    camera_id = trigger["camera_id"] if trigger else "unknown"
    classification = state.get("classification") or "error"
    person = state.get("matched_person")
    error = state.get("error")

    payload: dict = {
        "type": "detection_event",
        "camera_id": camera_id,
        "classification": classification,
        "recording_path": state.get("recording_path"),
        "person_name": person["name"] if person else None,
        "workflow_path": state.get("workflow_path", ""),
    }
    if error:
        payload["error"] = error

    await ws_manager.broadcast(payload)
    return state

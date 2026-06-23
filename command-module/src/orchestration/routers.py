import logging
from datetime import datetime, timezone
from orchestration.state import SystemState

logger = logging.getLogger(__name__)


def face_detection_router(state: SystemState) -> str:
    if state.get("error"):
        return "notify"
    if state.get("inference_fallback_mode"):
        # Jetson offline — record everything
        return "record"
    faces = state.get("detected_faces", [])
    return "recognize" if faces else "record"


def recognition_router(state: SystemState) -> str:
    if state.get("error"):
        return "notify"

    match = state.get("recognition_match")
    if match is None:
        return "record"  # unknown

    person = state.get("matched_person")
    if person and person.get("is_blocked"):
        return "record"  # unallowed — record with priority

    # Check if any camera has recognized a known person in the cooldown window
    cooldown_until = state["cooldowns"].get("known_person")

    if cooldown_until and datetime.now(timezone.utc) < cooldown_until:
        trigger = state["trigger"]
        camera_id = trigger["camera_id"] if trigger else "unknown"
        logger.debug("Known person cooldown active (expires in ~%d sec) — %s suppressed",
                     int((cooldown_until - datetime.now(timezone.utc)).total_seconds()), camera_id)
        return "notify"  # skip persist/record, just notify dashboard if needed

    return "suppress"    # known, not blocked, and NOT in cooldown

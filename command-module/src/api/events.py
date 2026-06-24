"""Detection event query endpoint."""
import uuid
from datetime import datetime, timezone

import httpx
from auth import verify_api_key
from rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from config import settings
from db.postgres import EVENTS, PERSONS, get_db
from services.inference_client import inference_client
from services.inference_sync import sync_identities_to_edge

router = APIRouter(prefix="/api/events", tags=["events"])


class IdentifyRequest(BaseModel):
    person_id: str


def _serialise(doc_id: str, d: dict) -> dict:
    return {
        "event_id":       doc_id,
        "camera_id":      d.get("camera_id"),
        "detected_at":    d["detected_at"].isoformat() if d.get("detected_at") else None,
        "classification": d.get("classification"),
        "person_id":      d.get("person_id"),
        "confidence":     d.get("confidence"),
        "recording_path": d.get("recording_path"),
    }


@router.get("")
@limiter.limit("100/minute")
async def list_events(
    camera_id: str | None = Query(None),
    classification: str | None = Query(None),
    limit: int = Query(100, le=500),
):
    """
    Returns events ordered by detected_at descending.
    Requires a Firestore composite index on (camera_id, detected_at DESC) when
    camera_id filter is used — create it via the GCP Console or `firebase deploy`.
    """
    db = get_db()

    events = []
    async for doc in db.collection(EVENTS).stream():
        data = doc.to_dict()
        # Apply filters
        if camera_id and data.get("camera_id") != camera_id:
            continue
        if classification and data.get("classification") != classification:
            continue
        events.append(_serialise(doc.id, data))

    # Sort by detected_at descending and limit
    events.sort(key=lambda e: e.get("detected_at", ""), reverse=True)
    return events[:limit]


@router.post("/{event_id}/identify")
@limiter.limit("100/minute")
async def identify_event(event_id: str, req: IdentifyRequest, _: str = Depends(verify_api_key)):
    """Identify an unknown event as a known person and enroll the face embedding."""
    db = get_db()
    event_ref = db.collection(EVENTS).document(event_id)
    event_doc = await event_ref.get()
    if not event_doc.exists:
        raise HTTPException(404, "Event not found")

    data = event_doc.to_dict()
    best_frame = data.get("best_frame")

    if not best_frame and data.get("recording_path"):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{settings.inference_node_url}/extract-frame/{data['recording_path']}"
                )
                if resp.status_code == 200:
                    best_frame = resp.json().get("frame")
        except Exception:
            pass

    if not best_frame:
        raise HTTPException(422, "No face frame available for this event — re-enroll via live capture")

    person_ref = db.collection(PERSONS).document(req.person_id)
    person_doc = await person_ref.get()
    if not person_doc.exists:
        raise HTTPException(404, "Person not found")

    detect_result = await inference_client.detect(best_frame)
    faces = detect_result.get("faces", [])
    if not faces:
        raise HTTPException(422, "No face detected in the stored frame")

    embedding = max(faces, key=lambda f: f.get("confidence", 0)).get("embedding", [])
    if not embedding:
        raise HTTPException(422, "Face detected but no embedding returned")

    embedding_id = str(uuid.uuid4())
    embeddings = person_doc.to_dict().get("embeddings", [])
    embeddings.append({
        "embedding_id": embedding_id,
        "embedding": embedding,
        "source_image": f"event:{event_id}",
        "created_at": datetime.now(timezone.utc),
    })
    await person_ref.update({"embeddings": embeddings})

    await event_ref.update({
        "classification": "known",
        "person_id": req.person_id,
    })

    await sync_identities_to_edge()
    return {"status": "identified", "event_id": event_id, "person_id": req.person_id}

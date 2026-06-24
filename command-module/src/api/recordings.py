"""Recording retrieval endpoints."""
from auth import verify_api_key
from rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query

from db.postgres import EVENTS, get_db
from storage.factory import get_storage_backend

router = APIRouter(prefix="/api/recordings", tags=["recordings"])
_storage = get_storage_backend()


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
async def list_recordings(
    camera_id: str | None = Query(None),
    classification: str | None = Query(None),
    limit: int = Query(50, le=200),
):
    """
    Returns only events that have a recording, ordered newest first.
    Requires Firestore composite indexes — see api/events.py note.
    """
    db = get_db()

    recordings = []
    async for doc in db.collection(EVENTS).stream():
        data = doc.to_dict()
        # Filter for recordings only
        if not data.get("recording_path"):
            continue
        # Apply other filters
        if camera_id and data.get("camera_id") != camera_id:
            continue
        if classification and data.get("classification") != classification:
            continue
        recordings.append(_serialise(doc.id, data))

    # Sort by recording_path, then by detected_at descending
    recordings.sort(key=lambda e: (e.get("recording_path", ""), -int(e.get("detected_at", "0")[:10])))
    return recordings[:limit]


@router.get("/{event_id}/url")
@limiter.limit("100/minute")
async def get_clip_url(event_id: str, _: str = Depends(verify_api_key)):
    db = get_db()
    doc = await db.collection(EVENTS).document(event_id).get()
    if not doc.exists or not doc.to_dict().get("recording_path"):
        raise HTTPException(404)
    url = await _storage.get_clip_url(doc.to_dict()["recording_path"])
    return {"url": url}

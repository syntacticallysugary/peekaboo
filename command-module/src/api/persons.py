"""Person management — CRUD and face enrollment."""
import asyncio
import base64
import logging
import math
import uuid
from datetime import datetime, timezone

import httpx
from auth import verify_api_key
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from config import settings
from db.firestore import PERSONS, get_db
from services.inference_client import inference_client
from services.inference_sync import sync_identities_to_edge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/persons", tags=["persons"])


_AUTO_ENROLL_SIM_THRESHOLD = 0.85  # skip if nearest existing embedding is already this close


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return dot / (norm_a * norm_b)


class PersonCreate(BaseModel):
    name: str


class AutoEnrollPayload(BaseModel):
    embedding: list[float]
    camera_id: str


class PersonUpdate(BaseModel):
    name: str | None = None
    is_blocked: bool | None = None


@router.get("")
async def list_persons(_: str = Depends(verify_api_key)):
    db = get_db()
    persons = []
    async for doc in db.collection(PERSONS).stream():
        d = doc.to_dict()
        persons.append({
            "person_id": doc.id,
            "name": d.get("name"),
            "is_blocked": d.get("is_blocked", False),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
            "embedding_count": len(d.get("embeddings", [])),
        })
    return persons


@router.post("", status_code=201)
async def create_person(data: PersonCreate, _: str = Depends(verify_api_key)):
    db = get_db()
    person_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.collection(PERSONS).document(person_id).set({
        "name": data.name,
        "is_blocked": False,
        "created_at": now,
        "embeddings": [],
    })
    return {"person_id": person_id, "name": data.name}


@router.post("/{person_id}/images", status_code=201)
async def add_face_image(person_id: str, image: UploadFile = File(...), _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(PERSONS).document(person_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404, f"Person '{person_id}' not found")

    raw = await image.read()
    frame_b64 = base64.b64encode(raw).decode()

    detect_result = await inference_client.detect(frame_b64)
    faces = detect_result.get("faces", [])
    if not faces:
        raise HTTPException(422, "No face detected in uploaded image")
    if len(faces) > 1:
        raise HTTPException(422, "Multiple faces detected — upload an image with a single face")

    embedding = faces[0].get("embedding", [])
    if not embedding:
        raise HTTPException(422, "Face detected but no embedding returned")

    embedding_id = str(uuid.uuid4())
    new_entry = {
        "embedding_id": embedding_id,
        "embedding": embedding,
        "source_image": image.filename,
        "created_at": datetime.now(timezone.utc),
    }

    current = doc.to_dict()
    embeddings = current.get("embeddings", [])
    embeddings.append(new_entry)
    await doc_ref.update({"embeddings": embeddings})

    await sync_identities_to_edge()
    return {"embedding_id": embedding_id, "person_id": person_id}


@router.put("/{person_id}")
async def update_person(person_id: str, data: PersonUpdate, _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(PERSONS).document(person_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404)

    updates: dict = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.is_blocked is not None:
        updates["is_blocked"] = data.is_blocked
    if updates:
        await doc_ref.update(updates)

    await sync_identities_to_edge()
    updated = doc.to_dict() | updates
    return {"person_id": person_id, "name": updated.get("name"), "is_blocked": updated.get("is_blocked")}


@router.post("/{person_id}/capture", status_code=202)
async def capture_face(person_id: str, _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(PERSONS).document(person_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404, f"Person '{person_id}' not found")

    # Arm the inference service capture — it will save the next face embedding
    # detected during a live camera session (frontal, motion-triggered frame).
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(f"{settings.inference_node_url}/capture")
        except Exception as exc:
            raise HTTPException(503, f"Inference service unreachable: {exc}")

        # Poll for the result — the inference service fills it when a session
        # detects a face (walk toward the camera to trigger).
        embedding: list[float] | None = None
        deadline = asyncio.get_event_loop().time() + 30.0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(2.0)
            try:
                res = await client.get(f"{settings.inference_node_url}/capture/result")
                if res.status_code == 200:
                    embedding = res.json().get("embedding")
                    if embedding:
                        break
            except Exception:
                pass

    if not embedding:
        raise HTTPException(408, "No face captured within 30 seconds — walk in front of the camera and try again")

    embedding_id = str(uuid.uuid4())
    new_entry = {
        "embedding_id": embedding_id,
        "embedding": embedding,
        "source_image": "live_capture",
        "created_at": datetime.now(timezone.utc),
    }

    current = doc.to_dict()
    embeddings = current.get("embeddings", [])
    embeddings.append(new_entry)
    await doc_ref.update({"embeddings": embeddings})

    await sync_identities_to_edge()
    logger.info("Enrolled %s via live capture", doc.to_dict().get("name"))
    return {"status": "enrolled", "person_id": person_id, "name": doc.to_dict().get("name")}


@router.post("/{person_id}/auto-enroll")
async def auto_enroll_face(person_id: str, payload: AutoEnrollPayload, _: str = Depends(verify_api_key)):
    """Add an embedding only if it represents a meaningfully new camera perspective.

    Skips if the nearest existing embedding already exceeds the similarity threshold,
    which avoids accumulating redundant shots from the same camera.
    """
    db = get_db()
    doc_ref = db.collection(PERSONS).document(person_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404, f"Person '{person_id}' not found")

    current = doc.to_dict()
    embeddings = current.get("embeddings", [])

    nearest_sim = 0.0
    for entry in embeddings:
        sim = _cosine_sim(payload.embedding, entry.get("embedding", []))
        if sim > nearest_sim:
            nearest_sim = sim

    if nearest_sim >= _AUTO_ENROLL_SIM_THRESHOLD:
        return {"added": False, "nearest_similarity": nearest_sim}

    embedding_id = str(uuid.uuid4())
    embeddings.append({
        "embedding_id": embedding_id,
        "embedding": payload.embedding,
        "source_image": f"auto:{payload.camera_id}",
        "created_at": datetime.now(timezone.utc),
    })
    await doc_ref.update({"embeddings": embeddings})
    await sync_identities_to_edge()

    logger.info("Auto-enrolled embedding for %s from %s (nearest_sim=%.3f)", person_id, payload.camera_id, nearest_sim)
    return {"added": True, "nearest_similarity": nearest_sim}


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: str, _: str = Depends(verify_api_key)):
    db = get_db()
    doc_ref = db.collection(PERSONS).document(person_id)
    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(404)
    await doc_ref.delete()
    await sync_identities_to_edge()

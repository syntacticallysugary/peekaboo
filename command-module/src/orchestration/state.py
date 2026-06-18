from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from typing_extensions import TypedDict


class TriggerEvent(TypedDict):
    camera_id: str
    timestamp: str
    motion_score: float
    frame_b64: Optional[str]      # JPEG frame already pushed by camera node
    frame_url: Optional[str]      # alternative: pull URL


class KnownPersonRecord(TypedDict):
    person_id: str
    name: str
    is_blocked: bool
    embeddings: list[list[float]]  # one or more 512-dim ArcFace embeddings


class SystemState(TypedDict):
    # ── Trigger being processed ──────────────────────────────────────────
    trigger: Optional[TriggerEvent]
    frame_b64: Optional[str]           # resolved frame for this trigger

    # ── Inference results ────────────────────────────────────────────────
    detected_faces: list[dict]         # raw /detect response faces
    recognition_match: Optional[dict]  # {person_id, similarity} | None

    # ── Decision ─────────────────────────────────────────────────────────
    classification: Optional[str]      # 'known' | 'unknown' | 'unallowed' | 'no_face'
    matched_person: Optional[KnownPersonRecord]
    recording_path: Optional[str]

    # ── Known persons (loaded at startup, refreshed on DB change) ────────
    known_persons: list[KnownPersonRecord]

    # ── Per-camera cooldown tracking (camera_id → datetime) ─────────────
    cooldowns: dict[str, datetime]

    # ── Inference Node health ────────────────────────────────────────────
    inference_online: bool
    inference_fallback_mode: bool      # record all motion when Jetson is offline

    # ── Workflow routing ─────────────────────────────────────────────────
    workflow_path: str
    error: Optional[str]

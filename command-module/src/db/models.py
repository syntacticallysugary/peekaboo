"""
Plain Python dataclasses that mirror the Firestore document shapes.
No ORM — these are used for type safety and serialisation only.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Camera:
    camera_id: str
    type: str
    ip: str | None = None
    stream_url: str | None = None
    status: str = "disconnected"
    last_seen: datetime | None = None


@dataclass
class EmbeddingRecord:
    embedding_id: str
    embedding: list[float]
    source_image: str | None = None
    created_at: datetime | None = None


@dataclass
class Person:
    person_id: str
    name: str
    is_blocked: bool = False
    created_at: datetime | None = None
    embeddings: list[EmbeddingRecord] = field(default_factory=list)


@dataclass
class DetectionEvent:
    event_id: str
    camera_id: str
    detected_at: datetime
    classification: str
    person_id: str | None = None
    confidence: float | None = None
    recording_path: str | None = None


@dataclass
class Webhook:
    webhook_id: str
    url: str
    secret: str | None = None
    active: bool = True
    created_at: datetime | None = None

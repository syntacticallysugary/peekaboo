from typing import Optional
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class DetectedFace(BaseModel):
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    embedding: list[float] = Field(description="512-dim ArcFace embedding")


class DetectRequest(BaseModel):
    frame: str = Field(description="Base64-encoded JPEG image")


class DetectResponse(BaseModel):
    faces: list[DetectedFace]
    inference_ms: float


class Candidate(BaseModel):
    person_id: str
    embedding: list[float] = Field(description="512-dim ArcFace embedding")


class RecognizeRequest(BaseModel):
    embedding: list[float] = Field(description="Query 512-dim embedding")
    candidates: list[Candidate] | None = Field(default=None, description="Known-person embeddings; uses local cache if None")


class RecognizeMatch(BaseModel):
    person_id: str
    similarity: float = Field(ge=0.0, le=1.0)


class RecognizeResponse(BaseModel):
    match: Optional[RecognizeMatch]
    inference_ms: float


class HealthResponse(BaseModel):
    status: str
    model_pack: str
    gpu_id: int
    gpu_available: bool
    queue_depth: int


class SyncRequest(BaseModel):
    candidates: list[Candidate] = Field(description="Full list of authorized person embeddings")


class IdentifyRequest(BaseModel):
    frame: str = Field(description="Base64-encoded JPEG image")
    camera_id: str


class IdentifyResponse(BaseModel):
    action: str = Field(description="'cooldown' | 'alert'")
    classification: str = Field(description="'authorized' | 'unknown' | 'unallowed'")
    person_id: Optional[str] = None
    similarity: Optional[float] = None
    inference_ms: float


class SessionFrameRequest(BaseModel):
    camera_id: str
    frame: str = Field(description="Base64-encoded JPEG image")


class SessionEndRequest(BaseModel):
    camera_id: str


class ArmedRequest(BaseModel):
    armed: bool

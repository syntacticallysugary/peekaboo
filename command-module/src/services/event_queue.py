"""
Internal async event bus.
Producers call publish(); consumers register with subscribe().
The webhook dispatcher and any future consumers (email, MQTT bridge, etc.) subscribe here.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class DetectionEvent:
    event_id: str
    camera_id: str
    detected_at: datetime
    classification: str          # 'known' | 'unknown' | 'unallowed' | 'no_face'
    person_id: str | None = None
    confidence: float | None = None
    recording_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "detected_at": self.detected_at.isoformat(),
            "classification": self.classification,
            "person_id": str(self.person_id) if self.person_id else None,
            "confidence": self.confidence,
            "recording_path": self.recording_path,
            **self.extra,
        }


Handler = Callable[[DetectionEvent], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: DetectionEvent) -> None:
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.error("Event handler %s raised: %s", handler.__name__, exc)


event_bus = EventBus()

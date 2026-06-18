import asyncio
from typing import Optional


class CaptureState:
    def __init__(self, person_id: str):
        self.person_id = person_id
        self.embedding: Optional[list[float]] = None
        self._event = asyncio.Event()

    async def wait(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def complete(self, embedding: list[float]):
        if not self._event.is_set():
            self.embedding = embedding
            self._event.set()


_current: Optional[CaptureState] = None


def arm(person_id: str) -> CaptureState:
    global _current
    _current = CaptureState(person_id=person_id)
    return _current


def offer(embedding: list[float]):
    """Called by run_detection_node when a face embedding is available."""
    if _current and not _current._event.is_set():
        _current.complete(embedding)


def clear():
    global _current
    _current = None

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)
        logger.debug("WebSocket connected; total=%d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws) if hasattr(self._active, "discard") else None
        try:
            self._active.remove(ws)
        except ValueError:
            pass
        logger.debug("WebSocket disconnected; total=%d", len(self._active))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()

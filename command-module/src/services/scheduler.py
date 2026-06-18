"""Optional daily arm/disarm schedule.

A manual arm/disarm (via the dashboard button) always takes effect immediately.
The schedule only acts at its two configured transition times and is a no-op if
the system is already in the target state — so a manual change made mid-window
holds until the next scheduled transition, rather than being fought continuously.
"""
import asyncio
import logging
from datetime import datetime

from db.firestore import SYSTEM, get_db
from services import system_state
from services.inference_client import inference_client
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)

_DOC_ID = "schedule"
_CHECK_INTERVAL_S = 30

_config: dict = {"enabled": False, "arm_time": None, "disarm_time": None}


async def load() -> None:
    global _config
    db = get_db()
    doc = await db.collection(SYSTEM).document(_DOC_ID).get()
    if doc.exists:
        _config.update(doc.to_dict())
    logger.info("Schedule loaded — %s", _config)


def get_config() -> dict:
    return dict(_config)


async def set_config(enabled: bool, arm_time: str | None, disarm_time: str | None) -> None:
    global _config
    _config = {"enabled": enabled, "arm_time": arm_time, "disarm_time": disarm_time}
    db = get_db()
    await db.collection(SYSTEM).document(_DOC_ID).set(_config)
    logger.info("Schedule updated — %s", _config)


async def _apply(armed: bool) -> None:
    await system_state.set_armed(armed)
    await inference_client.set_armed(armed)
    await ws_manager.broadcast({"type": "system_state", "armed": armed, "source": "schedule"})
    logger.info("Schedule %s system", "armed" if armed else "disarmed")


async def _loop() -> None:
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_S)
        if not _config.get("enabled"):
            continue
        now_hm = datetime.now().strftime("%H:%M")
        if now_hm == _config.get("arm_time") and not system_state.is_armed():
            await _apply(True)
        elif now_hm == _config.get("disarm_time") and system_state.is_armed():
            await _apply(False)


def start() -> asyncio.Task:
    return asyncio.create_task(_loop())

"""Global armed/disarmed state for the security system.

While disarmed, detection and recording on the Jetson continue unaffected —
this only gates whether the command module turns a report into a stored
event, webhook delivery, and dashboard notification.
"""
import logging

from db.postgres import SYSTEM, get_db

logger = logging.getLogger(__name__)

_DOC_ID = "state"
_armed: bool = True


async def load() -> None:
    global _armed
    db = get_db()
    doc = await db.collection(SYSTEM).document(_DOC_ID).get()
    if doc.exists:
        _armed = doc.to_dict().get("armed", True)
    logger.info("System state loaded — armed=%s", _armed)


def is_armed() -> bool:
    return _armed


async def set_armed(value: bool) -> None:
    global _armed
    _armed = value
    db = get_db()
    await db.collection(SYSTEM).document(_DOC_ID).set({"armed": value})
    logger.info("System %s", "armed" if value else "disarmed")

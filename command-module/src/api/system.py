"""Arm/disarm control for the security system."""
import re

from rate_limit import limiter
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import scheduler, system_state
from services.inference_client import inference_client
from websocket.manager import ws_manager

router = APIRouter(prefix="/api/system", tags=["system"])

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleRequest(BaseModel):
    enabled: bool
    arm_time: str | None = None     # "HH:MM", 24h, server-local time
    disarm_time: str | None = None  # "HH:MM", 24h, server-local time


@router.get("/status")
@limiter.limit("100/minute")
async def get_status():
    return {"armed": system_state.is_armed()}


@router.post("/arm")
@limiter.limit("100/minute")
async def arm():
    await system_state.set_armed(True)
    await inference_client.set_armed(True)
    await ws_manager.broadcast({"type": "system_state", "armed": True})
    return {"armed": True}


@router.post("/disarm")
@limiter.limit("100/minute")
async def disarm():
    await system_state.set_armed(False)
    await inference_client.set_armed(False)
    await ws_manager.broadcast({"type": "system_state", "armed": False})
    return {"armed": False}


@router.get("/schedule")
@limiter.limit("100/minute")
async def get_schedule():
    return scheduler.get_config()


@router.post("/schedule")
@limiter.limit("100/minute")
async def set_schedule(req: ScheduleRequest):
    if req.enabled:
        for t in (req.arm_time, req.disarm_time):
            if not t or not _HHMM.match(t):
                raise HTTPException(400, "arm_time and disarm_time must be HH:MM (24h) when schedule is enabled")
    await scheduler.set_config(req.enabled, req.arm_time, req.disarm_time)
    return scheduler.get_config()

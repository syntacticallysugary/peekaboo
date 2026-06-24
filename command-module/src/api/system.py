"""Arm/disarm control for the security system."""
import re

from auth import verify_api_key
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
async def get_status(_: str = Depends(verify_api_key)):
    return {"armed": system_state.is_armed()}


@router.post("/arm")
async def arm(_: str = Depends(verify_api_key)):
    await system_state.set_armed(True)
    await inference_client.set_armed(True)
    await ws_manager.broadcast({"type": "system_state", "armed": True})
    return {"armed": True}


@router.post("/disarm")
async def disarm(_: str = Depends(verify_api_key)):
    await system_state.set_armed(False)
    await inference_client.set_armed(False)
    await ws_manager.broadcast({"type": "system_state", "armed": False})
    return {"armed": False}


@router.get("/schedule")
async def get_schedule(_: str = Depends(verify_api_key)):
    return scheduler.get_config()


@router.post("/schedule")
async def set_schedule(req: ScheduleRequest, _: str = Depends(verify_api_key)):
    if req.enabled:
        for t in (req.arm_time, req.disarm_time):
            if not t or not _HHMM.match(t):
                raise HTTPException(400, "arm_time and disarm_time must be HH:MM (24h) when schedule is enabled")
    await scheduler.set_config(req.enabled, req.arm_time, req.disarm_time)
    return scheduler.get_config()

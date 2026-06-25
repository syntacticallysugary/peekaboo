import asyncio
import logging
from contextlib import asynccontextmanager

import httpx as _httpx

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from fastapi.security import HTTPBearer
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api import alerts, cameras, events, firmware, persons, recordings, system, webhooks
from config import settings
from rate_limit import limiter
from db.postgres import init_postgres, close_postgres
from orchestration.workflow import guard_workflow  # noqa: F401 — triggers graph compilation
from services import camera_registry, scheduler, system_state, webhook_dispatcher
from services.inference_client import inference_client
from services.mqtt_control import mqtt_control
from services.inference_sync import start_sync_service, sync_identities_to_edge
from websocket.manager import ws_manager

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

_bg_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    await system_state.load()
    await scheduler.load()
    webhook_dispatcher.register()
    _bg_tasks.append(camera_registry.start())
    _bg_tasks.append(asyncio.create_task(_inference_health_loop()))
    _bg_tasks.append(start_sync_service())
    _bg_tasks.append(scheduler.start())
    _bg_tasks.append(mqtt_control.start())
    logger.info("Peekaboo Command Module started")
    yield
    camera_registry.stop()
    for task in _bg_tasks:
        task.cancel()
    await close_postgres()
    await inference_client.close()
    logger.info("Peekaboo Command Module shut down")


async def _inference_health_loop():
    was_healthy = False
    while True:
        await asyncio.sleep(15)
        health = await inference_client.health()
        if health:
            await ws_manager.broadcast({"type": "inference_health", **health})
            if not was_healthy:
                logger.info("Inference service (re)started — re-syncing identities and armed state")
                await sync_identities_to_edge()
                await inference_client.set_armed(system_state.is_armed())
            was_healthy = True
        else:
            was_healthy = False


app = FastAPI(title="Peekaboo Command Module", version="2.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: Response(
    content="Rate limit exceeded", status_code=429, media_type="text/plain"
))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Frontend dev servers
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(alerts.router)
app.include_router(cameras.router)
app.include_router(persons.router)
app.include_router(recordings.router)
app.include_router(events.router)
app.include_router(firmware.router)
app.include_router(system.router)
app.include_router(webhooks.router)


@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket):
    """WebSocket connection requires Bearer token in query param: ws://host/ws/dashboard?token=API_KEY"""
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.get("/health")
async def health():
    inference = await inference_client.health()
    return {
        "status": "ok",
        "inference_node": inference or {"status": "unreachable"},
        "inference_node_url": settings.inference_node_url,
    }


@app.get("/proxy/recordings/{path:path}")
async def proxy_recording(path: str, request: Request):
    """Proxy recording clips from the inference service so the browser needs no direct access."""
    upstream = f"{settings.inference_node_url}/recordings/{path}"
    headers = {}
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]
    async with _httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(upstream, headers=headers)
    passthrough = {k: v for k, v in resp.headers.items()
                   if k.lower() in ("content-range", "accept-ranges", "content-length",
                                    "content-type", "last-modified", "etag")}
    return StreamingResponse(
        iter([resp.content]),
        status_code=resp.status_code,
        headers=passthrough,
        media_type=resp.headers.get("content-type", "video/mp4"),
    )


@app.get("/proxy/snapshot/{camera_id}")
async def proxy_snapshot(camera_id: str):
    """Proxy a JPEG snapshot from the inference service as an inline image."""
    upstream = f"{settings.inference_node_url}/snapshot/{camera_id}"
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(upstream)
    except _httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inference service unreachable")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="No frame available")
    return Response(content=resp.content, media_type="image/jpeg")


try:
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
except Exception:
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level=settings.log_level, reload=False)

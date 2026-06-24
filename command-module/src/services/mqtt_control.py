"""Secure MQTT control channel to the cameras.

Publishes commands (reboot / diag / ota_check) to per-camera command topics and
listens on the status topics for boot announcements, acknowledgements, and
diagnostics. Every command carries a random nonce and a unix timestamp so the
firmware can reject replays and stale messages. Commands are published
non-retained, so a reconnecting camera never receives a stale command.
"""
import asyncio
import json
import logging
import secrets
import time

import aiomqtt

from config import settings
from db.postgres import CAMERAS, get_db
from websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Commands the firmware understands. Anything else is refused here so a typo in
# the API can never put an unknown verb on the wire.
ALLOWED_COMMANDS = {"reboot", "diag", "ota_check"}

# Last status payload received per camera_id (boot, acks, diagnostics).
latest_status: dict[str, dict] = {}


class MqttControl:
    """Long-lived MQTT client: one background task owns the connection, the
    status subscription, and serves publishes from the API handlers."""

    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task | None = None
        self._diag_waiters: dict[str, asyncio.Future] = {}

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run())
        return self._task

    async def _run(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password or None,
                ) as client:
                    self._client = client
                    await client.subscribe(f"{settings.mqtt_status_prefix}/#", qos=1)
                    logger.info("MQTT control connected to %s:%d",
                                settings.mqtt_broker_host, settings.mqtt_broker_port)
                    async for message in client.messages:
                        await self._on_status(message)
            except Exception as exc:
                self._client = None
                logger.warning("MQTT control disconnected (%s) — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _on_status(self, message) -> None:
        topic = str(message.topic)
        camera_id = topic.rsplit("/", 1)[-1]
        try:
            payload = json.loads(message.payload)
        except (ValueError, TypeError):
            payload = {"raw": message.payload.decode(errors="replace")}

        latest_status[camera_id] = {"received_at": time.time(), **payload}
        logger.info("Camera %s status: %s", camera_id, payload.get("event", payload))

        # Wake any diag request waiting on this camera.
        if payload.get("event") == "diag":
            waiter = self._diag_waiters.get(camera_id)
            if waiter and not waiter.done():
                waiter.set_result(payload)
            if ip := payload.get("ip"):
                try:
                    await get_db().collection(CAMERAS).document(camera_id).update({"ip": ip})
                    logger.info("Updated IP for %s → %s", camera_id, ip)
                except Exception:
                    logger.warning("Failed to persist IP for %s", camera_id, exc_info=True)

        await ws_manager.broadcast({
            "type": "camera_mqtt_status",
            "camera_id": camera_id,
            "status": payload,
        })

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def publish_command(self, camera_id: str, cmd: str) -> None:
        """Publish a command to a single camera. Raises on unknown command or no
        broker connection."""
        if cmd not in ALLOWED_COMMANDS:
            raise ValueError(f"Unknown command '{cmd}'")
        if self._client is None:
            raise RuntimeError("MQTT broker not connected")

        payload = json.dumps({
            "cmd": cmd,
            "nonce": secrets.randbits(32),
            "ts": int(time.time()),
        })
        topic = f"{settings.mqtt_cmd_prefix}/{camera_id}"
        await self._client.publish(topic, payload, qos=1, retain=False)
        logger.info("Published '%s' to %s", cmd, topic)

    async def request_diag(self, camera_id: str, timeout: float = 5.0) -> dict | None:
        """Publish a diag command and wait for the camera's response."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._diag_waiters[camera_id] = future
        try:
            await self.publish_command(camera_id, "diag")
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._diag_waiters.pop(camera_id, None)

    async def close(self) -> None:
        if self._task:
            self._task.cancel()


mqtt_control = MqttControl()

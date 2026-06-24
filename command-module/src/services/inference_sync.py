"""Push all non-blocked person embeddings to the Jetson inference node."""
import asyncio
import logging


from config import settings
from db.postgres import PERSONS, get_db
from services.inference_client import inference_client

logger = logging.getLogger(__name__)


async def sync_identities_to_edge() -> bool:
    """Push all authorised (non-blocked) embeddings to the Jetson's local cache."""
    logger.info("Starting identity sync to edge...")
    db = get_db()

    candidates: list[dict] = []
    async for doc in db.collection(PERSONS).stream():
        data = doc.to_dict()
        # Skip blocked persons
        if data.get("is_blocked", False):
            continue
        for emb in data.get("embeddings", []):
            candidates.append({
                "person_id": doc.id,
                "embedding": emb["embedding"],
            })

    if not candidates:
        logger.warning("No authorised identities found to sync")

    try:
        resp = await inference_client._client.post(
            "/sync",
            json={"candidates": candidates},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "Synced %d identities to Jetson (node count: %d)",
            len(candidates), data.get("count", 0),
        )
        return True
    except Exception as exc:
        logger.error("Failed to sync identities to Jetson: %s", exc)
        return False


async def _periodic_sync_loop() -> None:
    while True:
        await sync_identities_to_edge()
        await asyncio.sleep(3600)


def start_sync_service() -> asyncio.Task:
    return asyncio.create_task(_periodic_sync_loop())

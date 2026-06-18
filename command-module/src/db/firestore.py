"""Firestore async client — singleton used across the whole application."""
from google.cloud.firestore_v1.async_client import AsyncClient

from config import settings

# Collection names
CAMERAS = "cameras"
PERSONS = "persons"
EVENTS = "events"
WEBHOOKS = "webhooks"
SYSTEM = "system"

_db: AsyncClient | None = None


def get_db() -> AsyncClient:
    if _db is None:
        raise RuntimeError("Firestore not initialised — call init_firestore() at startup")
    return _db


async def init_firestore() -> None:
    """
    Initialise the Firestore client.

    Credentials are resolved in order:
      1. GOOGLE_APPLICATION_CREDENTIALS env var (service account JSON path)
      2. Application Default Credentials (gcloud auth application-default login)
      3. Cloud Run / GCE metadata service (when deployed)

    Set FIRESTORE_EMULATOR_HOST=localhost:8080 to use the local emulator.
    """
    global _db
    _db = AsyncClient(project=settings.gcp_project_id)

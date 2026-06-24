#!/usr/bin/env python3
"""Migrate data from Firestore to PostgreSQL.

Usage:
    python migrate_firestore_to_postgres.py

This script:
1. Connects to Firestore using existing credentials
2. Exports all data (cameras, persons, events, webhooks, system)
3. Inserts into PostgreSQL tables via SQLAlchemy
4. Reports counts and any migration errors
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from db.postgres import (
    Base,
    CameraModel,
    PersonModel,
    EmbeddingModel,
    EventModel,
    WebhookModel,
    SystemModel,
    AuditLogModel,
    CAMERAS,
    PERSONS,
    EVENTS,
    WEBHOOKS,
    SYSTEM,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def migrate_firestore_to_postgres():
    """Main migration function."""

    # Initialize Firestore client (auto-detects project from Application Default Credentials)
    try:
        fs_client = AsyncClient()
        logger.info("Connected to Firestore using Application Default Credentials")
    except Exception as e:
        logger.error("Failed to connect to Firestore: %s", e)
        logger.error("Make sure you've run: gcloud auth application-default login")
        return

    # Initialize PostgreSQL (override for local host access)
    try:
        # Docker postgres is on 5435, but connection string needs to match
        database_url = settings.database_url.replace("localhost/peekaboo", "localhost:5435/peekaboo")
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables ready")
    except Exception as e:
        logger.error("Failed to initialize PostgreSQL: %s", e)
        return

    try:
        async with async_session() as session:
            counts = {
                "cameras": 0,
                "persons": 0,
                "embeddings": 0,
                "events": 0,
                "webhooks": 0,
                "system": 0,
            }

            # Migrate cameras
            logger.info("Migrating cameras...")
            try:
                cameras_docs = fs_client.collection(CAMERAS)
                async for doc in cameras_docs.stream():
                    data = doc.to_dict()
                    camera = CameraModel(camera_id=doc.id, **data)
                    session.add(camera)
                    counts["cameras"] += 1
                await session.commit()
                logger.info("✓ Migrated %d cameras", counts["cameras"])
            except Exception as e:
                logger.error("Error migrating cameras: %s", e)

            # Migrate persons (with embeddings)
            logger.info("Migrating persons...")
            try:
                persons_docs = fs_client.collection(PERSONS)
                async for doc in persons_docs.stream():
                    data = doc.to_dict()
                    embeddings_data = data.pop("embeddings", [])

                    person = PersonModel(person_id=doc.id, **data)
                    session.add(person)
                    counts["persons"] += 1

                    # Migrate embeddings for this person
                    for emb_entry in embeddings_data:
                        embedding = EmbeddingModel(
                            person_id=doc.id,
                            embedding_id=emb_entry.get("embedding_id"),
                            embedding=emb_entry.get("embedding"),
                            source_image=emb_entry.get("source_image"),
                            created_at=emb_entry.get("created_at", datetime.now(timezone.utc)),
                        )
                        session.add(embedding)
                        counts["embeddings"] += 1

                await session.commit()
                logger.info("✓ Migrated %d persons with %d embeddings", counts["persons"], counts["embeddings"])
            except Exception as e:
                logger.error("Error migrating persons: %s", e)

            # Migrate events
            logger.info("Migrating events...")
            try:
                events_docs = fs_client.collection(EVENTS)
                async for doc in events_docs.stream():
                    data = doc.to_dict()
                    event = EventModel(event_id=doc.id, **data)
                    session.add(event)
                    counts["events"] += 1
                await session.commit()
                logger.info("✓ Migrated %d events", counts["events"])
            except Exception as e:
                logger.error("Error migrating events: %s", e)

            # Migrate webhooks
            logger.info("Migrating webhooks...")
            try:
                webhooks_docs = fs_client.collection(WEBHOOKS)
                async for doc in webhooks_docs.stream():
                    data = doc.to_dict()
                    webhook = WebhookModel(webhook_id=doc.id, **data)
                    session.add(webhook)
                    counts["webhooks"] += 1
                await session.commit()
                logger.info("✓ Migrated %d webhooks", counts["webhooks"])
            except Exception as e:
                logger.error("Error migrating webhooks: %s", e)

            # Migrate system state
            logger.info("Migrating system state...")
            try:
                system_docs = fs_client.collection(SYSTEM)
                async for doc in system_docs.stream():
                    data = doc.to_dict()
                    # System state uses id=0 as singleton
                    data["id"] = 0
                    system = SystemModel(**data)
                    session.add(system)
                    counts["system"] += 1
                await session.commit()
                logger.info("✓ Migrated %d system states", counts["system"])
            except Exception as e:
                logger.error("Error migrating system state: %s", e)

            # Print summary
            logger.info("\n=== Migration Complete ===")
            logger.info("Cameras:   %d", counts["cameras"])
            logger.info("Persons:   %d", counts["persons"])
            logger.info("Embeddings: %d", counts["embeddings"])
            logger.info("Events:    %d", counts["events"])
            logger.info("Webhooks:  %d", counts["webhooks"])
            logger.info("System:    %d", counts["system"])

    except Exception as e:
        logger.error("Migration failed: %s", e)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate_firestore_to_postgres())

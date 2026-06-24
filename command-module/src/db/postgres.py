"""PostgreSQL async database using SQLAlchemy with Firestore-compatible API.

Provides get_db() and collection() interface that existing code uses,
backed by PostgreSQL instead of Google Cloud Firestore.

Models:
- cameras: device registry
- persons: face enrollment
- embeddings: face vectors
- events: detection logs
- webhooks: alert targets
- system: global state
- audit_logs: compliance trail
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    delete as sql_delete,
    select,
    update as sql_update,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy import Column

from config import settings

# Collection name constants (for backward compatibility with Firestore code)
CAMERAS = "cameras"
PERSONS = "persons"
EVENTS = "events"
WEBHOOKS = "webhooks"
SYSTEM = "system"

# Global state
_engine = None
_AsyncSessionLocal = None
_model_registry = {}


class Base(DeclarativeBase):
    """SQLAlchemy base class."""

    pass


class CameraModel(Base):
    """Camera device registry."""

    __tablename__ = "cameras"

    camera_id = Column(String(50), primary_key=True)
    type = Column(String(50), nullable=False)
    ip = Column(String(45), nullable=True)
    stream_url = Column(String(255), nullable=True)
    status = Column(String(20), default="disconnected")
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PersonModel(Base):
    """Face enrollment record."""

    __tablename__ = "persons"

    person_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    embeddings = relationship("EmbeddingModel", back_populates="person", cascade="all, delete-orphan")


class EmbeddingModel(Base):
    """Face embedding vector."""

    __tablename__ = "embeddings"

    embedding_id = Column(String(255), primary_key=True)
    person_id = Column(String(255), ForeignKey("persons.person_id"), nullable=False)
    embedding = Column(JSON, nullable=True)
    source_image = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    person = relationship("PersonModel", back_populates="embeddings")


class EventModel(Base):
    """Detection event log."""

    __tablename__ = "events"

    event_id = Column(String(255), primary_key=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    classification = Column(String(50), nullable=False)
    person_id = Column(String(255), ForeignKey("persons.person_id"), nullable=True)
    confidence = Column(Float, nullable=True)
    recording_path = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WebhookModel(Base):
    """Webhook alert target."""

    __tablename__ = "webhooks"

    webhook_id = Column(String(255), primary_key=True)
    url = Column(String(2048), nullable=False)
    secret = Column(String(255), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemModel(Base):
    """Global system state."""

    __tablename__ = "system"

    id = Column(Integer, primary_key=True, autoincrement=False)
    armed = Column(Boolean, default=False)
    schedule_enabled = Column(Boolean, default=False)
    schedule_arm_time = Column(String(8), nullable=True)
    schedule_disarm_time = Column(String(8), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditLogModel(Base):
    """Immutable audit trail."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    event_type = Column(String(50), nullable=False)
    actor = Column(String(255), nullable=False)
    resource = Column(String(255), nullable=True)
    resource_type = Column(String(50), nullable=True)
    success = Column(Boolean, default=True)
    error_reason = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)


# ============================================================================
# Firestore-compatible adapter layer
# ============================================================================


class DocumentSnapshot:
    """Mimics Firestore DocumentSnapshot."""

    def __init__(self, model_obj):
        self._obj = model_obj

    def to_dict(self):
        """Convert to dict."""
        if self._obj is None:
            return {}
        return {c.name: getattr(self._obj, c.name, None) for c in self._obj.__table__.columns}

    @property
    def exists(self):
        return self._obj is not None

    @property
    def id(self):
        if self._obj:
            pk_col = list(self._obj.__table__.primary_key.columns)[0]
            return getattr(self._obj, pk_col.name)
        return None

    @property
    def reference(self):
        return self._obj


class DocumentReference:
    """Mimics Firestore DocumentReference."""

    def __init__(self, session: AsyncSession, model_class, doc_id: str):
        self.session = session
        self.model_class = model_class
        self.doc_id = doc_id

    async def set(self, data: dict):
        """Set/replace document."""
        pk_col = list(self.model_class.__table__.primary_key.columns)[0]
        pk_name = pk_col.name

        data_with_id = {pk_name: self.doc_id, **data}

        # Delete old
        await self.session.execute(
            sql_delete(self.model_class).where(getattr(self.model_class, pk_name) == self.doc_id)
        )

        # Insert new
        obj = self.model_class(**data_with_id)
        self.session.add(obj)
        await self.session.commit()

    async def get(self):
        """Get document."""
        pk_col = list(self.model_class.__table__.primary_key.columns)[0]
        pk_name = pk_col.name
        result = await self.session.execute(
            select(self.model_class).where(getattr(self.model_class, pk_name) == self.doc_id)
        )
        obj = result.scalar_one_or_none()
        return DocumentSnapshot(obj)

    async def update(self, data: dict):
        """Partial update."""
        pk_col = list(self.model_class.__table__.primary_key.columns)[0]
        pk_name = pk_col.name
        await self.session.execute(
            sql_update(self.model_class)
            .where(getattr(self.model_class, pk_name) == self.doc_id)
            .values(**data)
        )
        await self.session.commit()

    async def delete(self):
        """Delete document."""
        pk_col = list(self.model_class.__table__.primary_key.columns)[0]
        pk_name = pk_col.name
        await self.session.execute(
            sql_delete(self.model_class).where(getattr(self.model_class, pk_name) == self.doc_id)
        )
        await self.session.commit()


class CollectionReference:
    """Mimics Firestore CollectionReference."""

    def __init__(self, session: AsyncSession, name: str):
        self.session = session
        self.name = name
        self.model_class = _model_registry[name]
        self._filters = []

    def document(self, doc_id: str) -> DocumentReference:
        """Get document reference."""
        return DocumentReference(self.session, self.model_class, doc_id)

    def where(self, filter=None):
        """Add filter."""
        if filter:
            self._filters.append(filter)
        return self

    async def stream(self):
        """Stream all matching documents."""
        query = select(self.model_class)

        # Apply filters
        for f in self._filters:
            if hasattr(f, "field") and hasattr(f, "value"):
                col = getattr(self.model_class, f.field.field_path)
                query = query.where(col == f.value)

        result = await self.session.execute(query)
        for obj in result.scalars().all():
            yield DocumentSnapshot(obj)


class Database:
    """Firestore-compatible database client."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def collection(self, name: str) -> CollectionReference:
        """Get collection reference."""
        return CollectionReference(self.session, name)


async def init_postgres() -> None:
    """Initialize PostgreSQL and register models."""
    global _engine, _AsyncSessionLocal, _model_registry

    database_url = settings.database_url
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Register models
    _model_registry[CAMERAS] = CameraModel
    _model_registry[PERSONS] = PersonModel
    _model_registry[EVENTS] = EventModel
    _model_registry[WEBHOOKS] = WebhookModel
    _model_registry[SYSTEM] = SystemModel

    # Create tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> Database:
    """Get database client."""
    if _AsyncSessionLocal is None:
        raise RuntimeError("PostgreSQL not initialized — call init_postgres() at startup")
    session = _AsyncSessionLocal()
    return Database(session)


async def close_postgres() -> None:
    """Close database engine."""
    if _engine:
        await _engine.dispose()

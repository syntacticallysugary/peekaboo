-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Camera node registry
CREATE TABLE IF NOT EXISTS cameras (
    camera_id    TEXT PRIMARY KEY,
    type         TEXT NOT NULL,        -- 'eye' | 'cam'
    stream_url   TEXT,
    ip           TEXT,
    last_seen    TIMESTAMPTZ,
    status       TEXT DEFAULT 'disconnected'
);

-- Known persons
CREATE TABLE IF NOT EXISTS persons (
    person_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    is_blocked  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Face embeddings (one person may have multiple reference images)
CREATE TABLE IF NOT EXISTS face_embeddings (
    embedding_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id     UUID REFERENCES persons(person_id) ON DELETE CASCADE,
    embedding     vector(512),        -- pgvector
    source_image  TEXT,              -- original filename for reference
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Detection events
CREATE TABLE IF NOT EXISTS detection_events (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id     TEXT REFERENCES cameras(camera_id),
    detected_at   TIMESTAMPTZ NOT NULL,
    classification TEXT NOT NULL,    -- 'known' | 'unknown' | 'unallowed' | 'no_face'
    person_id     UUID REFERENCES persons(person_id),
    confidence    FLOAT,
    recording_path TEXT              -- NULL if suppressed
);

-- Index for camera status lookups
CREATE INDEX IF NOT EXISTS idx_cameras_status ON cameras(status);

-- Index for detection event classification and time
CREATE INDEX IF NOT EXISTS idx_events_classification ON detection_events(classification);
CREATE INDEX IF NOT EXISTS idx_events_detected_at ON detection_events(detected_at);

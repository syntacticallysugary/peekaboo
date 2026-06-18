"""Active intrusion session tracking, one session per camera at a time."""
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SessionData:
    camera_id: str
    session_id: str
    started_at: datetime
    frames_dir: Path
    frame_count: int = 0
    known_person_id: str | None = None
    best_unknown_frame_b64: str | None = None
    best_face_confidence: float = 0.0
    any_person_detected: bool = False
    any_face_detected: bool = False
    alert_sent: bool = False
    first_face_seen_at: datetime | None = None
    best_similarity: float = 0.0
    person_absent_checks: int = 0   # consecutive person-detector misses since last hit
    person_check_frame: int = 0     # frame_count at last person check
    person_detect_streak: int = 0   # consecutive hits — must reach 2 before recording starts


class SessionManager:
    def __init__(self, recordings_dir: Path):
        self._recordings_dir = recordings_dir
        self._sessions: dict[str, SessionData] = {}
        self._lock = threading.Lock()

    def get_or_create(self, camera_id: str) -> SessionData:
        with self._lock:
            if camera_id not in self._sessions:
                sid = str(uuid.uuid4())
                frames_dir = self._recordings_dir / sid / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                self._sessions[camera_id] = SessionData(
                    camera_id=camera_id,
                    session_id=sid,
                    started_at=datetime.now(timezone.utc),
                    frames_dir=frames_dir,
                )
            return self._sessions[camera_id]

    def end(self, camera_id: str) -> SessionData | None:
        with self._lock:
            return self._sessions.pop(camera_id, None)

    def pop_all(self) -> list[SessionData]:
        """Remove and return every active session — used when disarming mid-session."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            return sessions

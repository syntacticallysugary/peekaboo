import asyncio
import base64
import logging
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from face_engine import engine
from recording import encode_mp4, purge_old_recordings, save_frame
from schemas import (
    ArmedRequest,
    DetectRequest,
    DetectResponse,
    HealthResponse,
    IdentifyRequest,
    IdentifyResponse,
    RecognizeRequest,
    RecognizeResponse,
    SessionEndRequest,
    SessionFrameRequest,
    SyncRequest,
)
from session_manager import SessionData, SessionManager

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

# Serialize GPU inference — one call at a time
_gpu_semaphore = asyncio.Semaphore(1)

# HTTP client for person detector sidecar
_person_detector: httpx.AsyncClient | None = None

# Latest raw JPEG bytes per camera_id — served by /stream/{camera_id}
_last_frame: dict[str, bytes] = {}

# Camera IDs that require 180° rotation before inference (e.g. mounted upside-down)
_rotate_set: set[str] = {c.strip() for c in settings.rotate_cameras.split(",") if c.strip()}

# System armed state — pushed from the command module. While disarmed, no frames
# are saved, no detection runs, and no recordings are produced.
_armed: bool = True

_recordings_dir = Path(settings.recordings_dir)
_captures_dir = Path(settings.recordings_dir) / "captures"
_recordings_dir.mkdir(parents=True, exist_ok=True)

_captures_dir.mkdir(parents=True, exist_ok=True)
session_manager = SessionManager(_recordings_dir)


async def _cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, purge_old_recordings, _recordings_dir, settings.retention_days
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _person_detector
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, engine._load)
    await loop.run_in_executor(None, purge_old_recordings, _recordings_dir, settings.retention_days)
    asyncio.create_task(_cleanup_loop())
    _person_detector = httpx.AsyncClient(base_url=settings.person_detector_url, timeout=2.0)
    yield
    await _person_detector.aclose()


app = FastAPI(title="Peekaboo Inference Service", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/recordings", StaticFiles(directory=str(_recordings_dir), html=False), name="recordings")


# ── Session endpoints (new architecture) ─────────────────────────────────────

_SESSION_MAX_AGE_S = 60        # rotate concluded sessions kept alive by heartbeat
_SESSION_HARD_MAX_AGE_S = 300  # force-rotate any session after 5 min regardless of state
_FACE_ALERT_DELAY_S = 5.0      # seconds of unrecognized face before firing unknown alert
_last_heartbeat: dict[str, float] = {}  # camera_id → epoch seconds of last heartbeat
_HEARTBEAT_INTERVAL_S = 30.0

@app.post("/session/frame", status_code=202)
async def session_frame(req: SessionFrameRequest):
    """Receive a JPEG frame from the camera. Detects async; saves only after a face is seen."""
    raw_b64 = req.frame.split(",", 1)[1] if "," in req.frame else req.frame
    frame_bytes = base64.b64decode(raw_b64)
    _last_frame[req.camera_id] = frame_bytes  # keeps live view working even while disarmed

    # Throttled heartbeat to command module so the dashboard shows camera as online
    import time as _time
    now_s = _time.monotonic()
    if now_s - _last_heartbeat.get(req.camera_id, 0) > _HEARTBEAT_INTERVAL_S:
        _last_heartbeat[req.camera_id] = now_s
        asyncio.create_task(_ping_camera_heartbeat(req.camera_id))

    if not _armed:
        # Disarmed — no session, no frame saved to disk, no recording. Still run
        # detection (no disk writes) when enrollment capture is armed, so "capture
        # a new face" keeps working even while the system is disarmed.
        if engine.capture_armed:
            asyncio.create_task(_capture_only(req.frame, req.camera_id))
        return {"session_id": None, "frame_index": -1, "status": "disarmed"}

    session = session_manager.get_or_create(req.camera_id)
    loop = asyncio.get_event_loop()

    age = (datetime.now(timezone.utc) - session.started_at).total_seconds()
    concluded = session.alert_sent or session.known_person_id is not None
    if (age > _SESSION_MAX_AGE_S and concluded) or age > _SESSION_HARD_MAX_AGE_S:
        logger.info("Auto-rotating session %s after %.0fs (concluded=%s)", session.session_id, age, concluded)
        ended_at = datetime.now(timezone.utc)
        old_session = session_manager.end(req.camera_id)
        if old_session:
            recording_path = old_session.frames_dir.parent / "recording.mp4"
            asyncio.create_task(_finalize_session(old_session, recording_path, ended_at))
        session = session_manager.get_or_create(req.camera_id)

    # Write every frame once a person has been initially detected.
    # The triggering frame is saved inside _detect_frame on first detection.
    # person_absent_checks gates session-end only — not frame saving — so the
    # recording captures the full duration even when individual checks miss.
    if session.any_person_detected and session.known_person_id is None:
        frame_idx = session.frame_count
        try:
            await loop.run_in_executor(None, save_frame, frame_bytes, session.frames_dir, frame_idx)
            session.frame_count += 1
        except OSError:
            pass  # frames dir deleted by concurrent known-person recognition
    else:
        frame_idx = -1

    if session.known_person_id is None:
        # Decide here (synchronously) whether this frame needs a person re-check.
        # Moving this decision out of _detect_frame prevents concurrent tasks from
        # each triggering a check in the same window, causing spurious absent counts.
        need_person_check = (
            not session.any_person_detected or
            session.frame_count - session.person_check_frame >= _PERSON_CHECK_EVERY_N
        )
        if need_person_check:
            session.person_check_frame = session.frame_count  # reserve slot synchronously
        asyncio.create_task(_detect_frame(session, req.frame, frame_bytes, need_person_check))

    return {"session_id": session.session_id, "frame_index": frame_idx}


async def _auto_enroll(person_id: str, embedding: list[float], camera_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.command_module_url}/api/persons/{person_id}/auto-enroll",
                json={"embedding": embedding, "camera_id": camera_id},
            )
            data = resp.json()
            if data.get("added"):
                logger.info(
                    "Auto-enrolled new embedding for %s from %s (nearest=%.3f)",
                    person_id, camera_id, data.get("nearest_similarity", 0),
                )
    except Exception as exc:
        logger.warning("Auto-enroll failed for %s: %s", person_id, exc)


async def _ping_camera_heartbeat(camera_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{settings.command_module_url}/api/cameras/{camera_id}/heartbeat")
    except Exception:
        pass


async def _capture_only(frame_b64: str, camera_id: str) -> None:
    """Run face detection with no recording or session — used only while disarmed,
    so the live-capture enrollment flow keeps working without writing anything to disk."""
    loop = asyncio.get_event_loop()
    async with _gpu_semaphore:
        try:
            faces, _ = await loop.run_in_executor(None, engine.detect, frame_b64, camera_id in _rotate_set)
        except ValueError:
            faces = []
    if not faces:
        return
    best = max(faces, key=lambda f: f.confidence)
    if best.embedding:
        engine.check_capture(best.embedding)


_PERSON_CHECK_EVERY_N    = 5     # re-check person detector every N frames during a session
_PERSON_ABSENT_LIMIT     = 12    # end session after this many consecutive no-person checks
_PERSON_SUSTAIN_THRESHOLD = 0.25  # lower confidence accepted to keep an active session alive


async def _detect_frame(
    session: SessionData, frame_b64: str, frame_bytes: bytes, check_person: bool
) -> None:
    loop = asyncio.get_event_loop()

    if check_person:
        try:
            resp = await _person_detector.post("/detect", json={"frame": frame_b64})
            result = resp.json()
            person_present = result.get("person", True)
            # Once a session is active, accept a lower confidence to avoid
            # ending the session on borderline frames mid-presence.
            if session.any_person_detected and not person_present:
                person_present = result.get("confidence", 0.0) >= _PERSON_SUSTAIN_THRESHOLD
        except Exception as exc:
            logger.warning("Person detector unreachable: %s — assuming person present", exc)
            person_present = True

        if person_present:
            session.person_absent_checks = 0
            session.person_detect_streak += 1
            if not session.any_person_detected and session.person_detect_streak >= 2:
                session.any_person_detected = True
                logger.info("Session %s: person confirmed — recording started", session.session_id)
                try:
                    await loop.run_in_executor(None, save_frame, frame_bytes, session.frames_dir, session.frame_count)
                    session.frame_count += 1
                except OSError:
                    pass
        else:
            session.person_detect_streak = 0
            if session.any_person_detected:
                session.person_absent_checks += 1
                logger.debug("Session %s: person absent %d/%d",
                             session.session_id, session.person_absent_checks, _PERSON_ABSENT_LIMIT)
                if session.person_absent_checks >= _PERSON_ABSENT_LIMIT:
                    logger.info("Session %s: person left — ending (%d frames)",
                                session.session_id, session.frame_count)
                    ended = session_manager.end(session.camera_id)
                    if ended:
                        recording_path = ended.frames_dir.parent / "recording.mp4"
                        asyncio.create_task(
                            _finalize_session(ended, recording_path, datetime.now(timezone.utc))
                        )
                    return
            else:
                return  # No person detected yet — skip face detection

    async with _gpu_semaphore:
        try:
            faces, ms = await loop.run_in_executor(
                None, engine.detect, frame_b64, session.camera_id in _rotate_set
            )
        except ValueError:
            faces, ms = [], 0.0

    if not faces:
        logger.debug("Session %s: no faces (%.0f ms)", session.session_id, ms)
        return

    if session.known_person_id is not None:
        return

    # First face detection — start recording if not already started.
    if not session.any_person_detected:
        session.any_person_detected = True
        frame_idx = session.frame_count
        try:
            await loop.run_in_executor(None, save_frame, frame_bytes, session.frames_dir, frame_idx)
            session.frame_count += 1
        except OSError:
            pass
    session.any_face_detected = True

    best = max(faces, key=lambda f: f.confidence)
    logger.info(
        "Session %s frame %d: %d face(s), best conf=%.3f (%.0f ms)",
        session.session_id, session.frame_count, len(faces), best.confidence, ms,
    )

    if best.confidence > session.best_face_confidence:
        session.best_face_confidence = best.confidence
        session.best_unknown_frame_b64 = frame_b64

    if not best.embedding:
        return

    engine.check_capture(best.embedding)

    match, _, sim = await loop.run_in_executor(
        None, engine.recognize, best.embedding, None, settings.recognition_threshold
    )
    if sim > session.best_similarity:
        session.best_similarity = sim

    if match:
        session.known_person_id = match.person_id
        asyncio.create_task(_auto_enroll(match.person_id, best.embedding, session.camera_id))
        session_dir = session.frames_dir.parent
        await loop.run_in_executor(None, shutil.rmtree, str(session_dir), True)
        session.frame_count = 0
        if session.alert_sent:
            logger.info(
                "Session %s: FALSE ALARM — recognized %s (similarity=%.3f) after alert, cancelling",
                session.session_id, match.person_id, match.similarity,
            )
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{settings.command_module_url}/api/cameras/report",
                        json={
                            "camera_id": session.camera_id,
                            "classification": "false_alarm",
                            "frame": frame_b64,
                            "person_id": match.person_id,
                        },
                    )
            except Exception as exc:
                logger.error("Failed to send false alarm cancel: %s", exc)
        else:
            logger.info(
                "Session %s: known person %s (similarity=%.3f) — discarding recording",
                session.session_id, match.person_id, match.similarity,
            )
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{settings.command_module_url}/api/cameras/report",
                        json={
                            "camera_id": session.camera_id,
                            "classification": "arrival",
                            "frame": frame_b64,
                            "person_id": match.person_id,
                            "similarity": match.similarity,
                        },
                    )
            except Exception as exc:
                logger.error("Failed to send arrival notification: %s", exc)
        return

    # Track elapsed time since first face was seen.
    now = datetime.now(timezone.utc)
    if session.first_face_seen_at is None:
        session.first_face_seen_at = now
    face_elapsed = (now - session.first_face_seen_at).total_seconds()

    logger.info(
        "Session %s: no match (similarity=%.3f, best=%.3f, %.1fs/%.0fs)",
        session.session_id, sim, session.best_similarity, face_elapsed, _FACE_ALERT_DELAY_S,
    )

    if session.alert_sent or face_elapsed < _FACE_ALERT_DELAY_S:
        return  # still in window, or alert already sent — keep trying silently

    # Don't fire unknown alerts while enrollment capture is armed — the session
    # that triggers the capture would otherwise alert on itself before the identity
    # is loaded.
    if engine.capture_armed:
        return

    # 5 seconds of unrecognized face — report unknown now, keep trying for false alarm.
    session.alert_sent = True
    logger.info(
        "Session %s: no recognition after %.1fs (best similarity=%.3f) — reporting unknown",
        session.session_id, face_elapsed, session.best_similarity,
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.command_module_url}/api/cameras/report",
                json={
                    "camera_id": session.camera_id,
                    "classification": "unknown",
                    "frame": frame_b64,
                },
            )
            logger.info("Command module response: HTTP %d", resp.status_code)
    except Exception as exc:
        logger.error("Failed to report unknown face to command module: %s", exc)


@app.post("/system/armed")
async def set_armed(req: ArmedRequest):
    """Pushed by the command module. Disarming discards any in-progress session
    immediately — its frames are deleted, not encoded, so nothing is recorded."""
    global _armed
    _armed = req.armed

    if not _armed:
        loop = asyncio.get_event_loop()
        sessions = session_manager.pop_all()
        for session in sessions:
            await loop.run_in_executor(None, shutil.rmtree, str(session.frames_dir.parent), True)
        if sessions:
            logger.info("Disarmed — discarded %d in-progress session(s)", len(sessions))
        else:
            logger.info("Disarmed")
    else:
        logger.info("Armed")

    return {"armed": _armed}


@app.post("/session/end")
async def session_end(req: SessionEndRequest):
    """Signal that an intrusion session has ended (15 s of no motion)."""
    session = session_manager.end(req.camera_id)
    if not session:
        logger.info("session/end for %s — no active session", req.camera_id)
        return {"status": "no_active_session"}
    logger.info(
        "session/end for %s — %d frames, any_face=%s, known=%s, alert_sent=%s",
        req.camera_id, session.frame_count, session.any_face_detected,
        session.known_person_id, session.alert_sent,
    )

    ended_at = datetime.now(timezone.utc)
    recording_path = session.frames_dir.parent / "recording.mp4"
    asyncio.create_task(_finalize_session(session, recording_path, ended_at))

    return {
        "session_id": session.session_id,
        "frames": session.frame_count,
        "known_person": session.known_person_id,
        "status": "finalizing",
    }


async def _finalize_session(
    session: SessionData, recording_path: Path, ended_at: datetime
) -> None:
    loop = asyncio.get_event_loop()

    if session.frame_count > 0:
        ok = await loop.run_in_executor(None, encode_mp4, session.frames_dir, recording_path)
        if ok:
            logger.info(
                "Session %s: encoded %d frames → %s",
                session.session_id, session.frame_count, recording_path,
            )
    else:
        # No face was ever detected — remove the empty session directory.
        session_dir = session.frames_dir.parent
        await loop.run_in_executor(None, shutil.rmtree, str(session_dir), True)
        logger.debug("Session %s: no frames, removed empty directory", session.session_id)
        return

    if session.known_person_id is not None:
        return

    classification = "unknown_face" if session.any_face_detected else "unidentified_human"
    recording_rel = f"{session.session_id}/recording.mp4" if recording_path.exists() else None
    payload = {
        "camera_id": session.camera_id,
        "session_id": session.session_id,
        "classification": classification,
        "best_frame": session.best_unknown_frame_b64,
        "recording_path": recording_rel,
        "started_at": session.started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "peak_similarity": session.best_similarity if session.any_face_detected else None,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.command_module_url}/api/alerts", json=payload
            )
            logger.info(
                "Alert dispatched for session %s: HTTP %d",
                session.session_id, resp.status_code,
            )
    except Exception as exc:
        logger.error("Alert dispatch failed for session %s: %s", session.session_id, exc)


# ── Recording frame extraction ───────────────────────────────────────────────

def _extract_first_frame_b64(path: Path) -> str | None:
    import cv2 as _cv2
    cap = _cv2.VideoCapture(str(path))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    _, buf = _cv2.imencode(".jpg", frame)
    return base64.b64encode(buf.tobytes()).decode()


@app.get("/extract-frame/{path:path}")
async def extract_frame(path: str):
    """Return the first frame of a recording as a base64 JPEG."""
    full = _recordings_dir / path
    if not full.exists():
        raise HTTPException(status_code=404, detail="Recording not found")
    loop = asyncio.get_event_loop()
    frame_b64 = await loop.run_in_executor(None, _extract_first_frame_b64, full)
    if frame_b64 is None:
        raise HTTPException(status_code=422, detail="Could not extract frame from recording")
    return {"frame": frame_b64}


# ── Live stream endpoint ──────────────────────────────────────────────────────

@app.get("/stream")
@app.get("/stream/{camera_id}")
async def stream(camera_id: str | None = None):
    """MJPEG stream of the most recently received frame for a camera (or any camera)."""
    async def generate():
        while True:
            if camera_id:
                frame = _last_frame.get(camera_id)
            else:
                frame = next(iter(_last_frame.values()), None) if _last_frame else None
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
            await asyncio.sleep(0.2)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/snapshot")
@app.get("/snapshot/{camera_id}")
async def snapshot(camera_id: str | None = None):
    """Return the most recently received frame as a downloadable JPEG."""
    if camera_id:
        frame = _last_frame.get(camera_id)
    else:
        frame = next(iter(_last_frame.values()), None) if _last_frame else None
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame received yet")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={"Content-Disposition": "attachment; filename=capture.jpg"},
    )


@app.post("/save")
@app.post("/save/{camera_id}")
async def save_current_frame(camera_id: str | None = None):
    """Save the current frame to /recordings/captures/ with a sequential filename."""
    if camera_id:
        frame = _last_frame.get(camera_id)
    else:
        frame = next(iter(_last_frame.values()), None) if _last_frame else None
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame received yet")
    existing = sorted(_captures_dir.glob("cap_*.jpg"))
    next_idx = int(existing[-1].stem.split("_")[1]) + 1 if existing else 1
    filename = f"cap_{next_idx:04d}.jpg"
    path = _captures_dir / filename
    path.write_bytes(frame)
    logger.info("Saved capture: %s", path)
    return {"filename": filename, "path": f"/recordings/captures/{filename}"}


@app.get("/", response_class=HTMLResponse)
async def viewer():
    """Simple browser UI: live stream + Capture button."""
    return HTMLResponse("""<!DOCTYPE html>
<html>
<head>
  <title>Peekaboo Camera</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { background:#111; display:flex; flex-direction:column; align-items:center;
           justify-content:center; min-height:100vh; margin:0; gap:16px; padding:16px;
           box-sizing:border-box; }
    img  { border:2px solid #444; max-width:100%; width:100%; }
    .btns { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; }
    button, a { padding:16px 32px; font:bold 18px sans-serif; border-radius:8px;
                border:none; cursor:pointer; text-decoration:none; display:inline-block; }
    #saveBtn  { background:#e03; color:#fff; }
    #saveBtn:active { background:#c02; }
    #snapBtn  { background:#444; color:#fff; }
    #snapBtn:active { background:#333; }
    #status   { color:#8f8; font:14px monospace; min-height:1.4em; }
  </style>
</head>
<body>
  <img src="/stream" alt="live feed" onerror="this.src='/snapshot'">
  <div class="btns">
    <button id="saveBtn" onclick="saveFrame()">Save Frame</button>
    <a id="snapBtn" href="/snapshot" download="capture.jpg">Download</a>
  </div>
  <div id="status"></div>
  <script>
    async function saveFrame() {
      const btn = document.getElementById('saveBtn');
      const status = document.getElementById('status');
      btn.disabled = true;
      status.textContent = 'Saving...';
      try {
        const r = await fetch('/save', {method:'POST'});
        const d = await r.json();
        status.textContent = 'Saved: ' + d.filename;
      } catch(e) {
        status.textContent = 'Error: ' + e;
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>""")


# ── Legacy endpoints (kept for Command Module compatibility) ──────────────────

@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    loop = asyncio.get_event_loop()
    async with _gpu_semaphore:
        try:
            faces, ms = await loop.run_in_executor(None, engine.detect, req.frame)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return DetectResponse(faces=faces, inference_ms=ms)


@app.post("/recognize", response_model=RecognizeResponse)
async def recognize(req: RecognizeRequest):
    loop = asyncio.get_event_loop()
    match, ms, _ = await loop.run_in_executor(
        None,
        engine.recognize,
        req.embedding,
        req.candidates,
        settings.recognition_threshold,
    )
    return RecognizeResponse(match=match, inference_ms=ms)


@app.post("/sync")
async def sync(req: SyncRequest):
    engine.sync(req.candidates)
    return {"status": "synced", "count": len(req.candidates)}


@app.post("/identify", response_model=IdentifyResponse)
async def identify(req: IdentifyRequest):
    loop = asyncio.get_event_loop()
    async with _gpu_semaphore:
        try:
            resp, _ = await loop.run_in_executor(
                None, engine.identify, req.frame, req.camera_id, req.camera_id in _rotate_set
            )
            return resp
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.post("/capture")
async def arm_capture():
    engine.arm_capture()
    return {"status": "armed"}


@app.get("/capture/result")
async def get_capture_result():
    result = engine.get_capture_result()
    if result is None:
        raise HTTPException(status_code=404, detail="No face captured yet")
    return {"embedding": result}


@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        import onnxruntime as ort
        gpu_available = "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        gpu_available = False

    return HealthResponse(
        status="ok",
        model_pack=settings.model_pack,
        gpu_id=settings.gpu_id,
        gpu_available=gpu_available,
        queue_depth=engine.queue_depth(),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level=settings.log_level)

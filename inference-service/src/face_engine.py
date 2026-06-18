import base64
import logging
import pickle
import threading
import time
from pathlib import Path

import cv2
import httpx
import numpy as np

from config import settings
from schemas import BoundingBox, Candidate, DetectedFace, IdentifyResponse, RecognizeMatch

logger = logging.getLogger(__name__)

_queue_depth = 0

# Capture-mode state — armed by /capture endpoint, filled by next identify() call
_capture_lock = threading.Lock()
_capture_armed: bool = False
_capture_result: list[float] | None = None


class FaceEngine:
    """
    Wrapper around InsightFace FaceAnalysis with Edge-First caching and reporting.
    """

    def __init__(self):
        self._app = None
        self._cache_path = Path(settings.data_dir) / "identities.pkl"
        self._identities: list[Candidate] = self._load_cache()
        # Direct link to Command Module (AWS) for reporting security events
        self._client = httpx.Client(base_url=settings.command_module_url, timeout=10.0)

    def _load_cache(self) -> list[Candidate]:
        if self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception as exc:
                logger.error("Failed to load identity cache: %s", exc)
        return []

    def _save_cache(self):
        try:
            with open(self._cache_path, "wb") as f:
                pickle.dump(self._identities, f)
        except Exception as exc:
            logger.error("Failed to save identity cache: %s", exc)

    def arm_capture(self):
        global _capture_armed, _capture_result
        with _capture_lock:
            _capture_armed = True
            _capture_result = None
        logger.info("Capture mode armed — waiting for next face")

    def check_capture(self, embedding: list[float]) -> None:
        global _capture_armed, _capture_result
        with _capture_lock:
            if _capture_armed:
                _capture_result = embedding
                _capture_armed = False
                logger.info("Capture: saved embedding for enrollment")

    def get_capture_result(self) -> list[float] | None:
        with _capture_lock:
            return _capture_result

    def sync(self, candidates: list[Candidate]):
        self._identities = candidates
        self._save_cache()
        logger.info("Synced %d identities to local cache", len(candidates))

    def _load(self):
        if self._app is not None:
            return
        from insightface.app import FaceAnalysis

        # Pre-warm the CUDA context before InsightFace/ONNX Runtime touches it.
        # On Jetson, the first ONNX Runtime CUDA session init can corrupt the
        # glibc heap if CUDA hasn't been fully initialised by a prior allocation.
        # Allocating and releasing a real tensor via PyTorch primes the BFC arena
        # so InsightFace finds it in a known-good state.
        try:
            import torch
            if torch.cuda.is_available():
                _device = torch.device(f"cuda:{settings.gpu_id}")
                _warm = torch.zeros(1024, 1024, device=_device)
                del _warm
                torch.cuda.synchronize(_device)
                torch.cuda.empty_cache()
                logger.info("CUDA context pre-warmed on device %d", settings.gpu_id)
        except Exception as exc:
            logger.warning("CUDA pre-warm skipped: %s", exc)
        try:
            import onnxruntime as ort
            _ = ort.SessionOptions()
        except Exception:
            pass

        logger.info("Loading InsightFace model pack '%s' on GPU %d", settings.model_pack, settings.gpu_id)
        # Explicit CUDA arena options to prevent BFC allocator overflow on CUDA
        # version mismatches between container (12.2) and host driver (12.6).
        cuda_options = {
            "device_id": settings.gpu_id,
            "arena_extend_strategy": "kSameAsRequested",
            "gpu_mem_limit": 2 * 1024 * 1024 * 1024,
            "cudnn_conv_algo_search": "DEFAULT",
            "do_copy_in_default_stream": True,
        }
        app = FaceAnalysis(
            name=settings.model_pack,
            root=settings.models_dir,
            allowed_modules=["detection", "recognition"],
            providers=[("CUDAExecutionProvider", cuda_options), "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=settings.gpu_id, det_size=(settings.det_size, settings.det_size), det_thresh=settings.det_thresh)
        self._app = app
        logger.info("InsightFace ready")

    @property
    def ready(self) -> bool:
        return self._app is not None

    def detect(self, frame_b64: str, rotate_180: bool = False) -> tuple[list[DetectedFace], float]:
        global _queue_depth
        _queue_depth += 1
        try:
            self._load()
            img = _decode_frame(frame_b64, rotate_180=rotate_180)
            t0 = time.perf_counter()
            faces = self._app.get(img)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            results: list[DetectedFace] = []
            for face in faces:
                x1, y1, x2, y2 = face.bbox.tolist()
                embedding = face.embedding.tolist() if face.embedding is not None else []
                results.append(
                    DetectedFace(
                        bbox=BoundingBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1),
                        confidence=float(face.det_score),
                        embedding=embedding,
                    )
                )
            return results, elapsed_ms
        finally:
            _queue_depth -= 1

    def recognize(
        self,
        query: list[float],
        candidates: list[Candidate] | None = None,
        threshold: float = 0.65,
    ) -> tuple[RecognizeMatch | None, float, float]:
        """Returns (match, inference_ms, best_sim). best_sim is always set even on no-match."""
        t0 = time.perf_counter()
        search_list = candidates if candidates is not None else self._identities

        if not search_list:
            return None, (time.perf_counter() - t0) * 1000, 0.0

        q = np.array(query, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + 1e-8)

        best_sim = -1.0
        best_id: str | None = None
        for candidate in search_list:
            c = np.array(candidate.embedding, dtype=np.float32)
            c_norm = c / (np.linalg.norm(c) + 1e-8)
            sim = float(np.dot(q_norm, c_norm))
            if sim > best_sim:
                best_sim = sim
                best_id = candidate.person_id

        elapsed_ms = (time.perf_counter() - t0) * 1000
        match = RecognizeMatch(person_id=best_id, similarity=best_sim) if best_id and best_sim >= threshold else None
        return match, elapsed_ms, best_sim

    def identify(self, frame_b64: str, camera_id: str, rotate_180: bool = False) -> tuple[IdentifyResponse, float]:
        """Edge-First: Detect and Recognize in one pass against local cache."""
        t_start = time.perf_counter()

        faces, _ = self.detect(frame_b64, rotate_180=rotate_180)
        if not faces:
            self._report_to_command(camera_id, "unknown", frame_b64)
            elapsed_total = (time.perf_counter() - t_start) * 1000
            return IdentifyResponse(
                action="alert",
                classification="unknown",
                inference_ms=elapsed_total
            ), elapsed_total

        best_face = max(faces, key=lambda f: f.confidence)

        global _capture_armed, _capture_result
        with _capture_lock:
            if _capture_armed:
                _capture_result = best_face.embedding
                _capture_armed = False
                logger.info("Capture: saved embedding for enrollment")

        match, _, _ = self.recognize(best_face.embedding, threshold=settings.recognition_threshold)
        
        elapsed_total = (time.perf_counter() - t_start) * 1000
        
        if match:
            return IdentifyResponse(
                action="cooldown",
                classification="authorized",
                person_id=match.person_id,
                similarity=match.similarity,
                inference_ms=elapsed_total
            ), elapsed_total
        else:
            resp = IdentifyResponse(
                action="alert",
                classification="unknown",
                inference_ms=elapsed_total
            )
            self._report_to_command(camera_id, "unknown", frame_b64)
            return resp, elapsed_total

    def _report_to_command(self, camera_id: str, classification: str, frame_b64: str):
        """Report a security event to the Command Module."""
        try:
            self._client.post("/api/cameras/report", json={
                "camera_id": camera_id,
                "classification": classification,
                "frame": frame_b64
            })
            logger.info("Reported security event for %s to Command Module", camera_id)
        except Exception as exc:
            logger.error("Failed to report security event: %s", exc)

    @property
    def capture_armed(self) -> bool:
        with _capture_lock:
            return _capture_armed

    def queue_depth(self) -> int:
        return _queue_depth


def _decode_frame(frame_b64: str, rotate_180: bool = False) -> np.ndarray:
    if "," in frame_b64:
        frame_b64 = frame_b64.split(",", 1)[1]
    data = base64.b64decode(frame_b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image from base64 payload")

    if rotate_180:
        img = cv2.rotate(img, cv2.ROTATE_180)

    if settings.max_detect_size > 0:
        h, w = img.shape[:2]
        long_edge = max(h, w)
        if long_edge > settings.max_detect_size:
            scale = settings.max_detect_size / long_edge
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


engine = FaceEngine()

"""YOLOv8n person presence detector — ONNX Runtime CPU, own process."""
import asyncio
import base64
import logging
from contextlib import asynccontextmanager

import cv2
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

_MODEL_PATH = "/models/yolov8n.onnx"
_CONF_THRESHOLD = 0.35
_INPUT_SHAPE = (1, 3, 640, 640)   # NCHW
_OUTPUT_SHAPE = (1, 84, 8400)     # YOLOv8 standard output

_session: ort.InferenceSession | None = None
_input_name: str | None = None


def _load() -> None:
    global _session, _input_name
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _session = ort.InferenceSession(_MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"])
    _input_name = _session.get_inputs()[0].name
    logger.info("YOLOv8n loaded on CPU: %s", _MODEL_PATH)


def _run(img: np.ndarray) -> tuple[bool, float]:
    h, w = img.shape[:2]
    scale = 640 / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))
    padded = np.zeros((640, 640, 3), dtype=np.uint8)
    padded[:new_h, :new_w] = resized

    blob = padded.astype(np.float32) / 255.0
    blob = np.ascontiguousarray(blob.transpose(2, 0, 1)[np.newaxis])  # NCHW

    output = _session.run(None, {_input_name: blob})[0]  # [1, 84, 8400]
    # YOLOv8 output rows 0-3 = bbox, row 4 = person (class 0) score
    person_scores = output[0, 4, :]
    max_score = float(np.max(person_scores))
    logger.info("Person score: %.3f (threshold %.2f) → %s", max_score, _CONF_THRESHOLD, "PERSON" if max_score > _CONF_THRESHOLD else "empty")
    return max_score > _CONF_THRESHOLD, max_score


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load)
    logger.info("Person detector ready")
    yield


app = FastAPI(title="Peekaboo Person Detector", version="2.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class DetectRequest(BaseModel):
    frame: str


class DetectResponse(BaseModel):
    person: bool
    confidence: float


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    raw_b64 = req.frame.split(",", 1)[1] if "," in req.frame else req.frame
    arr = np.frombuffer(base64.b64decode(raw_b64), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return DetectResponse(person=False, confidence=0.0)
    loop = asyncio.get_event_loop()
    person, confidence = await loop.run_in_executor(None, _run, img)
    return DetectResponse(person=person, confidence=confidence)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "yolov8n-cpu", "loaded": _session is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, log_level="info")

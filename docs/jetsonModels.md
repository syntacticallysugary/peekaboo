# Jetson Inference Models

Reference for the model choices running on the Jetson Orin Nano inference service.
Covers what runs, why it was chosen, and the decisions that shaped the current architecture.

---

## Hardware Context

**Jetson Orin Nano 8GB** — unified memory architecture. CPU and GPU share the same
physical LPDDR5 pool (8 GB total). There is no discrete VRAM to partition. GPU memory
limits are enforced via ONNX Runtime's `gpu_mem_limit` option or TensorRT's workspace
configuration, not at the hardware level.

---

## Face Detection — InsightFace buffalo_l / det_10g (RetinaFace)

**Model:** `det_10g.onnx` from the InsightFace `buffalo_l` model pack  
**Framework:** ONNX Runtime 1.16.3 with CUDAExecutionProvider  
**Input:** 640×640 RGB image  
**Purpose:** Locate faces and produce 5-point landmarks (eyes, nose, mouth corners)

### Why det_10g

det_10g is InsightFace's production-grade RetinaFace variant. It runs at 640×640 which
gives sufficient resolution for a face at door distance (~3–8 feet in an 800×600 frame)
to produce a usable landmark crop for recognition. The smaller scrfd variants (320×320)
degraded recognition quality unacceptably at that distance.

`DET_SIZE=640` is set explicitly in `docker-compose.yml`. The default in the InsightFace
library is lower; running at 320 produced embeddings with cosine similarity near 0.006
for the same person — effectively random noise at that face crop size.

### CUDA provider options

The Jetson's BFC (Best Fit with Coalescing) arena allocator has a known initialization
instability on first startup. These options are required:

```python
cuda_options = {
    "arena_extend_strategy": "kSameAsRequested",   # allocate exactly what's needed
    "gpu_mem_limit": 2 * 1024 * 1024 * 1024,       # 2 GB ceiling
    "cudnn_conv_algo_search": "DEFAULT",            # avoid exhaustive search on startup
    "do_copy_in_default_stream": True,
}
```

### CUDA pre-warm — required for reliable cold start

On a clean container start (or after `docker compose down && up`), the Tegra CUDA
driver's BFC arena is uninitialized. If the first thing to touch it is ONNX Runtime's
multi-model load inside InsightFace, the allocator reliably corrupts glibc's heap and
the process dies with `corrupted size vs. prev_size` or `double free or corruption`.

The fix is to force a real GPU allocation through PyTorch **before** InsightFace
initializes. This primes the BFC arena so ONNX Runtime finds it in a known-good state:

```python
import torch
device = torch.device("cuda:0")
warm = torch.zeros(1024, 1024, device=device)   # 4 MB allocation primes the arena
del warm
torch.cuda.synchronize(device)
torch.cuda.empty_cache()
```

Without this, the service would crash on every cold start and only recover after
Docker's restart policy ran the container a second time (which re-used the partially
initialized CUDA state left by the crashed process). After `docker compose down` that
residual state is gone, making every attempt a failing cold start.

`MALLOC_ARENA_MAX=2` is also set in the Dockerfile to reduce glibc arena contention.

### person-detector must have `runtime: nvidia`

Even though the person-detector runs on CPU (`CPUExecutionProvider`), it must be
started with `runtime: nvidia` in `docker-compose.yml`. Without it, the Jetson's CUDA
driver is not touched at all before the inference container starts, removing the
partial warm-up effect that the person-detector's startup provides. Additionally,
setting `CUDA_VISIBLE_DEVICES=""` in the person-detector container while
`runtime: nvidia` is active leaves the NVIDIA driver in a partial state that prevents
the inference container from initializing — do not set that variable.

---

## Face Recognition — InsightFace buffalo_l / w600k_r50 (ArcFace)

**Model:** `w600k_r50.onnx` from the InsightFace `buffalo_l` model pack  
**Framework:** ONNX Runtime 1.16.3 with CUDAExecutionProvider  
**Input:** 112×112 RGB face crop (aligned by det_10g landmarks)  
**Output:** 512-dimensional L2-normalized embedding  
**Purpose:** Produce an identity embedding for comparison against enrolled persons

### Why ArcFace / w600k_r50

ArcFace (Additive Angular Margin loss) produces embeddings where cosine similarity
directly encodes identity distance. w600k_r50 is a ResNet-50 backbone trained on
600K identities — the standard buffalo_l recognition model. It outperforms lighter
alternatives on real-world variation (lighting, pose, partial occlusion) which matters
for a door camera with uncontrolled conditions.

### Recognition threshold

Default InsightFace threshold is 0.65. In production at this camera position and
distance, same-person scores across different sessions land in the 0.55–0.79 range.
The threshold is set to **0.55** in `docker-compose.yml` (`RECOGNITION_THRESHOLD=0.55`).

Different-person scores on ArcFace buffalo_l typically fall in the 0.10–0.35 range,
so 0.55 leaves a comfortable margin against false positive matches.

### Enrollment

Embeddings are generated by the inference service's `/detect` endpoint and stored
in the command module's PostgreSQL database as `face_embedding` records. The inference
service receives them via `/sync` on startup and after any enrollment change.

Four enrollment samples (cap_0016–0019) are stored for the enrolled person. More
samples from varied angles improve coverage. Enrollment images should be captured
in the same lighting and at the same distance as live operation.

---

## Person Detection — YOLOv8n

**Model:** `yolov8n.onnx` (or `yolov8n.trt` if TensorRT build succeeded)  
**Framework:** TensorRT 8.6.2 (preferred) or ONNX Runtime CPUExecutionProvider (fallback)  
**Input:** 640×640 RGB image (letterboxed)  
**Output:** `[1, 84, 8400]` — 4 bbox coords + 80 class scores per anchor; class 0 = person  
**Purpose:** Gate recording and face detection — only activate when a human is in frame  
**Confidence threshold:** 0.35

### Why person detection exists

Without it, the camera's JPEG delta motion detection fires on everything: ceiling fans,
passing shadows, lighting changes. The inference service was saving frames and running
face detection on every heartbeat frame from an empty room.

Person detection gates two things:
1. **Recording** — no frames written to disk until a person is confirmed present
2. **Face detection** — the GPU-heavy ArcFace pipeline doesn't run on empty frames

Sessions with no person detected produce no recording and are cleaned up automatically.

### Why YOLOv8n

YOLOv8n-nano is the smallest YOLO model (12 MB ONNX, ~3–5 ms on GPU). The task is
binary — person present or not — not multi-class detection or precise localization.
YOLOv8n is sufficient. Larger variants (YOLOv8s/m/l) add latency without meaningful
benefit for a presence gate.

### TensorRT vs ONNX Runtime — the key decision

Running a second ONNX Runtime CUDAExecutionProvider session in the same container
as InsightFace caused consistent heap corruption (`double free or corruption`) on the
Jetson. This is a known Tegra-specific issue with the BFC arena allocator when two
ONNX Runtime CUDA sessions share a process address space or are initialized in close
temporal proximity across containers.

**Why TensorRT fixes this:** TRT manages its own CUDA memory independently of the
ONNX Runtime BFC arena. It pre-allocates exactly the memory required at engine build
time and does not use the arena allocator at inference time. Two TRT sessions (or one
TRT + one ORT session) do not collide.

Additional benefit: TRT FP16 on Jetson Orin Nano runs YOLOv8n at ~3–5 ms vs
~10–15 ms for ONNX Runtime CUDA.

### Container isolation

This service runs in its own Docker container (`peekaboo-person-detector`, port 8002)
following the same pattern used on the DGX Spark: each model gets its own container
with its own CUDA context. The inference service calls it via HTTP — local loopback
latency (~3–8 ms) is negligible compared to inference time.

The inference service (`peekaboo-inference`, port 8001) depends on person-detector
being healthy before it starts (`depends_on: condition: service_healthy`).

### Why not on the ESP32

The original ESP32S3 firmware ran a TFLite Micro pedestrian detector on-device.
Switching the camera from RGB565 to JPEG format (required for SVGA resolution)
broke this: the hardware JPEG decoder on ESP32S3 fails at all downscale factors
(`esp_jpeg_decode` error 6), making it impossible to decode JPEG frames back to
the RGB565 format TFLite requires. The Jetson has the GPU to run proper models;
on-device detection was removed and not replaced on the ESP32.

---

## Engine Build — One-time Step

The TensorRT engine must be built on the target hardware. It cannot be copied from
another machine or generated at container build time.

```bash
# Run once, engine stored in models volume
docker exec peekaboo-person-detector /usr/src/tensorrt/bin/trtexec \
    --onnx=/models/yolov8n.onnx \
    --saveEngine=/models/yolov8n.trt \
    --fp16 \
    --memPoolSize=workspace:1024MiB
```

Build time: 5–15 minutes. The resulting `.trt` file is hardware-specific to this
Jetson Orin Nano and will not run on a different Jetson model or architecture.

---

## Model Files in Volume

All model files live in `inference-service/models/` on the Jetson host, mounted into
containers at:
- `/root/.insightface/models/` — inference service (InsightFace expects this path)
- `/models/` — person-detector service

| File | Size | Notes |
|---|---|---|
| `buffalo_l/det_10g.onnx` | ~17 MB | RetinaFace detector |
| `buffalo_l/w600k_r50.onnx` | ~250 MB | ArcFace recognition |
| `buffalo_l/1k3d68.onnx` | loaded but ignored | 3D landmark (not used) |
| `buffalo_l/2d106det.onnx` | loaded but ignored | 2D landmark (not used) |
| `buffalo_l/genderage.onnx` | loaded but ignored | Gender/age (not used) |
| `yolov8n.onnx` | 12 MB | Person detector source |
| `yolov8n.trt` | ~8–12 MB | TRT engine (FP16, Orin Nano only) |

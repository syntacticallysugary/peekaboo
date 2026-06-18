"""End-to-end recognition test harness.

Tests the full detect → recognize pipeline against enrolled persons,
using local JPEG images so no camera presence is required.

Usage:
    python tools/test_recognition.py [--dir /path/to/testdata] [--url http://host:8001]

Talks to the inference service directly via HTTP, so the container
must be running (locally or on the Jetson via SSH port-forward).
Defaults can also be set via the INFERENCE_NODE_URL and TEST_DATA_DIR env vars.
"""
import argparse
import base64
import os
import sys
from pathlib import Path

import httpx

INFERENCE_URL = os.environ.get("INFERENCE_NODE_URL", "http://localhost:8001")
DEFAULT_TEST_DIR = Path(os.environ.get("TEST_DATA_DIR", "./testdata"))


def encode(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode()


def detect(b64: str, url: str) -> tuple[list[dict], float]:
    resp = httpx.post(f"{url}/detect", json={"frame": b64}, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return data.get("faces", []), data.get("inference_ms", 0.0)


def identify(b64: str, url: str) -> dict:
    resp = httpx.post(f"{url}/identify", json={"frame": b64, "camera_id": "test"}, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def health(url: str) -> dict:
    resp = httpx.get(f"{url}/health", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def run_tests(test_dir: Path, url: str) -> None:
    images = sorted(test_dir.glob("*.jpg")) + sorted(test_dir.glob("*.png"))
    if not images:
        print(f"No images found in {test_dir}")
        sys.exit(1)

    h = health(url)
    print(f"Inference service: {url}")
    print(f"  model={h['model_pack']}  gpu={h['gpu_available']}  queue={h['queue_depth']}")
    print()

    # ── Phase 1: detection ────────────────────────────────────────────────────
    print(f"{'=== DETECTION':}")
    print(f"{'File':<18} {'Faces':>5} {'Best conf':>10} {'Has emb':>8} {'ms':>7}")
    print("-" * 55)

    for img_path in images:
        try:
            b64 = encode(img_path)
            faces, ms = detect(b64, url)
        except Exception as exc:
            print(f"{img_path.name:<18}  ERROR: {exc}")
            continue

        if faces:
            best = max(faces, key=lambda f: f["confidence"])
            has_emb = "yes" if best.get("embedding") else "no"
            print(f"{img_path.name:<18} {len(faces):>5} {best['confidence']:>10.3f} {has_emb:>8} {ms:>6.0f}ms")
        else:
            print(f"{img_path.name:<18} {'0':>5} {'—':>10} {'—':>8} {ms:>6.0f}ms")

    # ── Phase 2: end-to-end /identify ─────────────────────────────────────────
    print(f"\n{'=== IDENTIFY (end-to-end)':}")
    print(f"{'File':<18} {'Action':>10} {'Classification':>16} {'Person':>10} {'ms':>7}")
    print("-" * 65)

    for img_path in images:
        try:
            b64 = encode(img_path)
            result = identify(b64, url)
        except Exception as exc:
            print(f"{img_path.name:<18}  ERROR: {exc}")
            continue

        action = result.get("action", "?")
        cls = result.get("classification", "?")
        pid = (result.get("person_id") or "—")
        if pid and pid != "—":
            pid = pid[:8] + "…"
        ms = result.get("inference_ms", 0)
        print(f"{img_path.name:<18} {action:>10} {cls:>16} {pid:>10} {ms:>6.0f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_TEST_DIR)
    parser.add_argument("--url", default=INFERENCE_URL)
    args = parser.parse_args()

    run_tests(args.dir, args.url)


if __name__ == "__main__":
    main()

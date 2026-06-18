"""Send test frames through the inference service /detect endpoint and report results.

Usage:
    INFERENCE_NODE_URL=http://<your-inference-host>:8001 TEST_DATA_DIR=/path/to/jpgs \\
        python tools/test_detection.py
"""
import base64
import os
import sys
from pathlib import Path

import httpx

INFERENCE_URL = os.environ.get("INFERENCE_NODE_URL", "http://localhost:8001")
TEST_DIR = Path(os.environ.get("TEST_DATA_DIR", "./testdata"))


def test_frame(image_path: Path) -> dict:
    with open(image_path, "rb") as f:
        frame_b64 = base64.b64encode(f.read()).decode()
    resp = httpx.post(f"{INFERENCE_URL}/detect", json={"frame": frame_b64}, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    images = sorted(TEST_DIR.glob("*.jpg"))
    if not images:
        print(f"No .jpg files found in {TEST_DIR}")
        sys.exit(1)

    print(f"Testing {len(images)} frames against {INFERENCE_URL}/detect\n")
    print(f"{'File':<15} {'Faces':>5} {'Best conf':>10} {'Embedding':>10} {'ms':>8}")
    print("-" * 55)

    for img_path in images:
        try:
            result = test_frame(img_path)
        except Exception as exc:
            print(f"{img_path.name:<15} ERROR: {exc}")
            continue

        faces = result.get("faces", [])
        ms = result.get("inference_ms", 0)

        if faces:
            best = max(faces, key=lambda f: f["confidence"])
            has_emb = "yes" if best.get("embedding") else "no"
            print(f"{img_path.name:<15} {len(faces):>5} {best['confidence']:>10.3f} {has_emb:>10} {ms:>7.0f}ms")
        else:
            print(f"{img_path.name:<15} {'0':>5} {'—':>10} {'—':>10} {ms:>7.0f}ms")


if __name__ == "__main__":
    main()

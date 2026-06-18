"""Sort a directory of JPEG frames into person/ and no_person/ subdirectories.

Uses a locally-hosted Qwen vision model via vLLM's OpenAI-compatible API.
Thinking mode is explicitly disabled for fast YES/NO classification.

Reads defaults from tools/.env (VLLM_ENDPOINT, VLLM_MODEL, VLLM_TIMEOUT).
CLI flags override .env values.

Usage:
    python sort_images.py <input_dir>
    python sort_images.py <input_dir> --endpoint https://HOST/path --model MODEL_NAME
"""

import argparse
import base64
import os
import shutil
import sys
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv(Path(__file__).parent / ".env")


PROMPT = (
    "Does this image contain a person (human body or any clearly visible body part)? "
    "Reply with exactly one word: YES or NO."
)


def encode_image(path: Path) -> str:
    """Return base64-encoded JPEG."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def classify(image_path: Path, endpoint: str, model: str, timeout: int) -> bool | None:
    """Return True if person detected, False if not, None on error."""
    b64 = encode_image(image_path)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 5,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        resp = requests.post(
            f"{endpoint.rstrip('/')}/chat/completions",
            json=payload,
            timeout=timeout,
            verify=False,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip().upper()
        if "YES" in text:
            return True
        if "NO" in text:
            return False
        print(f"  [WARN] ambiguous response for {image_path.name!r}: {text!r}")
        return None
    except Exception as exc:
        print(f"  [ERR]  {image_path.name}: {exc}")
        return None


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Sort frames into person/no_person.")
    parser.add_argument("input_dir", type=Path, help="Directory of JPEG frames")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("VLLM_ENDPOINT"),
        help="vLLM base URL (overrides VLLM_ENDPOINT in .env)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("VLLM_MODEL"),
        help="Model name as registered in vLLM (overrides VLLM_MODEL in .env)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("VLLM_TIMEOUT", 30)),
        help="Per-request timeout in seconds (default from .env or 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print decisions without moving files",
    )
    args = parser.parse_args()

    if not args.endpoint:
        sys.exit("No endpoint set — provide --endpoint or set VLLM_ENDPOINT in tools/.env")
    if not args.model:
        sys.exit("No model set — provide --model or set VLLM_MODEL in tools/.env")

    input_dir: Path = args.input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        sys.exit(f"Not a directory: {input_dir}")

    images = sorted(input_dir.glob("*.jpg")) + sorted(input_dir.glob("*.jpeg"))
    if not images:
        sys.exit(f"No JPEG files found in {input_dir}")

    person_dir = input_dir / "person"
    no_person_dir = input_dir / "no_person"
    ambiguous_dir = input_dir / "ambiguous"
    if not args.dry_run:
        person_dir.mkdir(exist_ok=True)
        no_person_dir.mkdir(exist_ok=True)
        ambiguous_dir.mkdir(exist_ok=True)

    counts = {"person": 0, "no_person": 0, "ambiguous": 0, "error": 0}

    for i, img in enumerate(images, 1):
        result = classify(img, args.endpoint, args.model, args.timeout)

        if result is True:
            label = "person"
            dest = person_dir
        elif result is False:
            label = "no_person"
            dest = no_person_dir
        else:
            label = "ambiguous"
            dest = ambiguous_dir
            counts["error"] += (1 if result is None and "ERR" in str(result) else 0)

        counts[label] += 1
        print(f"[{i:>5}/{len(images)}] {img.name:<30} → {label}")

        if not args.dry_run:
            shutil.move(str(img), dest / img.name)

    print(
        f"\nDone. person={counts['person']}  "
        f"no_person={counts['no_person']}  "
        f"ambiguous={counts['ambiguous']}"
    )
    if args.dry_run:
        print("(dry-run — no files moved)")


if __name__ == "__main__":
    main()

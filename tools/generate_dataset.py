"""Generate synthetic training images for the Peekaboo FOMO classifier.

Pipeline:
  1. Download COCO val2017 annotations (one-time, ~241 MB zip)
  2. Extract person crops from COCO images with persons
  3. Paste crops onto real no_person backgrounds (your house) → person class
  4. no_person class = real no_person frames + COCO no_person images (degraded)
  5. Apply JPEG degradation (quality 4-12) to match ESP32-CAM output

Usage:
    python generate_dataset.py
    python generate_dataset.py --n_person 500 --n_no_person 500
"""

import argparse
import io
import json
import random
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


COCO_ANN_URL  = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"
COCO_IMG_BASE = "http://images.cocodataset.org/val2017/{}"
MIN_CROP_PX   = 60


def _ensure_annotations(cache_dir: Path) -> dict:
    ann_file = cache_dir / "instances_val2017.json"
    if ann_file.exists():
        print("COCO annotations cached — skipping download")
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        print("Downloading COCO annotations (~241 MB, one-time)…")
        zip_path = cache_dir / "annotations.zip"
        urllib.request.urlretrieve(COCO_ANN_URL, zip_path)
        print("Extracting instances_val2017.json…")
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("annotations/instances_val2017.json") as src:
                ann_file.write_bytes(src.read())
        zip_path.unlink()
        print("Done.")
    with open(ann_file) as f:
        return json.load(f)


def _split_image_ids(coco: dict) -> tuple[list[int], list[int], dict]:
    """Return (ids_with_person, ids_without_person, img_to_anns)."""
    person_cat_id = next(c["id"] for c in coco["categories"] if c["name"] == "person")
    with_person: set[int] = set()
    img_to_anns: dict[int, list] = {}
    for ann in coco["annotations"]:
        if ann["category_id"] != person_cat_id:
            continue
        w, h = ann["bbox"][2], ann["bbox"][3]
        if w < MIN_CROP_PX or h < MIN_CROP_PX:
            continue
        with_person.add(ann["image_id"])
        img_to_anns.setdefault(ann["image_id"], []).append(ann)
    all_ids = {img["id"] for img in coco["images"]}
    without_person = list(all_ids - with_person)
    return list(with_person), without_person, img_to_anns


def _fetch(img_cache: Path, info: dict) -> Image.Image | None:
    img_path = img_cache / info["file_name"]
    if not img_path.exists():
        try:
            urllib.request.urlretrieve(COCO_IMG_BASE.format(info["file_name"]), img_path)
        except Exception as exc:
            print(f"  [WARN] download failed for {info['file_name']}: {exc}")
            return None
    try:
        return Image.open(img_path).convert("RGB")
    except Exception:
        return None


def _degrade(img: Image.Image) -> Image.Image:
    quality = random.randint(4, 12)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).copy()


def _composite(background: Image.Image, crop: np.ndarray) -> Image.Image | None:
    """Paste a person crop onto a background at random scale and position."""
    bg = background.copy()
    bw, bh = bg.size
    scale = random.uniform(0.25, 0.75)
    ph = int(bh * scale)
    pw = int(crop.shape[1] * ph / max(crop.shape[0], 1))
    if pw < 10 or pw >= bw or ph >= bh:
        return None
    person = Image.fromarray(crop).resize((pw, ph), Image.LANCZOS)
    px = random.randint(0, bw - pw)
    py = random.randint(0, bh - ph)
    bg.paste(person, (px, py))
    return bg


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Generate synthetic Peekaboo training data.")
    parser.add_argument("--output_dir",      type=Path, default=Path("Training_Data/synthetic"))
    parser.add_argument("--backgrounds_dir", type=Path, default=Path("Training_Data/combined/no_person"),
                        help="Real no_person frames used as backgrounds for compositing")
    parser.add_argument("--coco_cache",      type=Path, default=Path("Training_Data/coco_cache"))
    parser.add_argument("--n_person",        type=int,  default=200)
    parser.add_argument("--n_no_person",     type=int,  default=200,
                        help="no_person images: split evenly between real frames and COCO")
    parser.add_argument("--coco_images",     type=int,  default=400,
                        help="Max COCO source images to download for crops")
    parser.add_argument("--seed",            type=int,  default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    out_person    = args.output_dir / "person"
    out_no_person = args.output_dir / "no_person"
    out_person.mkdir(parents=True, exist_ok=True)
    out_no_person.mkdir(parents=True, exist_ok=True)

    img_cache = args.coco_cache / "val2017"
    img_cache.mkdir(parents=True, exist_ok=True)

    real_backgrounds = sorted(args.backgrounds_dir.glob("*.jpg"))
    if not real_backgrounds:
        raise SystemExit(f"No background images found in {args.backgrounds_dir}")
    print(f"Real backgrounds: {len(real_backgrounds)}")

    print("\n── COCO annotations ─────────────────────────────────────────────")
    coco = _ensure_annotations(args.coco_cache)
    id_to_info = {img["id"]: img for img in coco["images"]}

    with_person, without_person, img_to_anns = _split_image_ids(coco)
    print(f"COCO val2017: {len(with_person)} images with person, {len(without_person)} without")

    # ── Collect person crops ──────────────────────────────────────────────────
    print(f"\n── Collecting person crops (up to {args.coco_images} source images) ──")
    random.shuffle(with_person)
    crops: list[np.ndarray] = []
    for img_id in with_person[:args.coco_images]:
        info = id_to_info[img_id]
        pil = _fetch(img_cache, info)
        if pil is None:
            continue
        for ann in img_to_anns[img_id]:
            x, y, w, h = (int(v) for v in ann["bbox"])
            pad = max(4, int(min(w, h) * 0.08))
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(pil.width, x + w + pad), min(pil.height, y + h + pad)
            crops.append(np.array(pil.crop((x1, y1, x2, y2))))
    print(f"Person crops available: {len(crops)}")
    if not crops:
        raise SystemExit("No COCO person crops — cannot generate person images.")

    # ── Synthetic person images: crop pasted onto real backgrounds ────────────
    print(f"\n── Generating {args.n_person} person images ────────────────────")
    generated, attempts = 0, 0
    while generated < args.n_person and attempts < args.n_person * 20:
        attempts += 1
        bg   = Image.open(random.choice(real_backgrounds)).convert("RGB")
        crop = random.choice(crops)
        img  = _composite(bg, crop)
        if img is None:
            continue
        img = _degrade(img)
        img.save(out_person / f"syn_{generated:06d}.jpg", quality=95)
        generated += 1
        if generated % 50 == 0:
            print(f"  {generated}/{args.n_person}")
    print(f"Generated {generated} person images")

    # ── no_person: half real frames, half COCO no_person ─────────────────────
    print(f"\n── Generating {args.n_no_person} no_person images ──────────────")
    n_real = args.n_no_person // 2
    n_coco = args.n_no_person - n_real

    for i in range(n_real):
        bg_path = real_backgrounds[i % len(real_backgrounds)]
        img = _degrade(Image.open(bg_path).convert("RGB"))
        img.save(out_no_person / f"syn_real_{i:06d}.jpg", quality=95)

    random.shuffle(without_person)
    coco_saved = 0
    for img_id in without_person:
        if coco_saved >= n_coco:
            break
        pil = _fetch(img_cache, id_to_info[img_id])
        if pil is None:
            continue
        _degrade(pil).save(out_no_person / f"syn_coco_{coco_saved:06d}.jpg", quality=95)
        coco_saved += 1

    total_np = n_real + coco_saved
    print(f"Generated {total_np} no_person images ({n_real} real + {coco_saved} COCO)")

    n_p  = len(list(out_person.glob("*.jpg")))
    n_np = len(list(out_no_person.glob("*.jpg")))
    print(f"\nDone → {args.output_dir}")
    print(f"  person:    {n_p}")
    print(f"  no_person: {n_np}")
    print(f"  total:     {n_p + n_np}")


if __name__ == "__main__":
    main()

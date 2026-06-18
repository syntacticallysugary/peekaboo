"""Train a MobileNetV2 binary classifier (person / no_person) for ESP32-S3 deployment.

Combines real and synthetic training data, applies focal loss to handle class
imbalance, and exports a TFLite int8 model ready for TFLite Micro.

Usage:
    python train.py
    python train.py --epochs 30 --threshold 0.35 --img_size 96

Outputs (in models/):
    peekaboo.tflite       — float32, for accuracy reference
    peekaboo_int8.tflite  — int8 quantized, deploy this to ESP32
    peekaboo_int8.h       — C array for embedding in firmware
"""

import argparse
import io
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
import tensorflow as tf
from tensorflow import keras


# ── Focal loss ────────────────────────────────────────────────────────────────

def focal_loss(gamma: float = 2.0, alpha: float = 0.25):
    """Binary focal loss — down-weights easy negatives, focuses on hard cases."""
    def loss(y_true, y_pred):
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1.0 - 1e-7)
        bce = -y_true * tf.math.log(y_pred) - (1 - y_true) * tf.math.log(1 - y_pred)
        p_t = y_true * y_pred + (1 - y_true) * (1 - y_pred)
        fl  = alpha * tf.pow(1.0 - p_t, gamma) * bce
        return tf.reduce_mean(fl)
    return loss


# ── Data loading ──────────────────────────────────────────────────────────────

def load_dataset(
    data_dirs: list[Path],
    img_size: int,
    val_split: float,
    seed: int,
) -> tuple:
    """Load person/no_person images from one or more directories, return train/val datasets."""
    images, labels = [], []

    for data_dir in data_dirs:
        for label, subdir in [(1, "person"), (0, "no_person")]:
            folder = data_dir / subdir
            if not folder.exists():
                continue
            for path in folder.glob("*.jpg"):
                try:
                    img = tf.io.read_file(str(path))
                    img = tf.image.decode_jpeg(img, channels=3)
                    img = tf.image.resize(img, [img_size, img_size])
                    images.append(img.numpy().astype(np.float32) / 255.0)
                    labels.append(label)
                except Exception:
                    pass

    images = np.array(images, dtype=np.float32)
    labels = np.array(labels, dtype=np.float32)

    # Shuffle
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(images))
    images, labels = images[idx], labels[idx]

    n_val   = int(len(images) * val_split)
    n_train = len(images) - n_val

    x_train, y_train = images[:n_train], labels[:n_train]
    x_val,   y_val   = images[n_train:], labels[n_train:]

    print(f"Train: {n_train}  (person={int(y_train.sum())}  no_person={int((1-y_train).sum())})")
    print(f"Val:   {n_val}    (person={int(y_val.sum())}    no_person={int((1-y_val).sum())})")
    return x_train, y_train, x_val, y_val


def make_tf_dataset(x: np.ndarray, y: np.ndarray, batch_size: int, augment: bool) -> tf.data.Dataset:
    ds = tf.data.Dataset.from_tensor_slices((x, y))
    if augment:
        aug = keras.Sequential([
            keras.layers.RandomFlip("horizontal"),
            keras.layers.RandomRotation(0.08),
            keras.layers.RandomZoom(0.10),
            keras.layers.RandomBrightness(0.15),
            keras.layers.RandomContrast(0.15),
        ])
        ds = ds.map(lambda img, lbl: (aug(img, training=True), lbl),
                    num_parallel_calls=tf.data.AUTOTUNE)
    return ds.shuffle(1024).batch(batch_size).prefetch(tf.data.AUTOTUNE)


# ── Model ─────────────────────────────────────────────────────────────────────

def build_model(img_size: int) -> keras.Model:
    base = keras.applications.MobileNetV2(
        input_shape=(img_size, img_size, 3),
        alpha=0.35,
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False

    inputs = keras.Input(shape=(img_size, img_size, 3))
    x = keras.applications.mobilenet_v2.preprocess_input(inputs * 255.0)
    x = base(x, training=False)
    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.25)(x)
    outputs = keras.layers.Dense(1, activation="sigmoid")(x)

    return keras.Model(inputs, outputs)


# ── TFLite export ─────────────────────────────────────────────────────────────

def export_float32(model: keras.Model, out_path: Path) -> None:
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    out_path.write_bytes(converter.convert())
    print(f"float32 TFLite: {out_path}  ({out_path.stat().st_size // 1024} KB)")


def export_int8(model: keras.Model, rep_data: np.ndarray, out_path: Path) -> None:
    def representative_dataset():
        for i in range(min(200, len(rep_data))):
            yield [rep_data[i:i+1]]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type  = tf.int8
    converter.inference_output_type = tf.int8

    tflite_bytes = converter.convert()
    out_path.write_bytes(tflite_bytes)
    print(f"int8 TFLite:    {out_path}  ({out_path.stat().st_size // 1024} KB)")


def export_c_header(tflite_path: Path, header_path: Path) -> None:
    data = tflite_path.read_bytes()
    var  = "peekaboo_model"
    lines = [f"// Auto-generated from {tflite_path.name} — do not edit",
             f"#pragma once",
             f"#include <stdint.h>",
             f"const uint8_t {var}[] = {{"]
    for i in range(0, len(data), 12):
        chunk = data[i:i+12]
        lines.append("  " + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
    lines += [f"}};", f"const unsigned int {var}_len = {len(data)};"]
    header_path.write_text("\n".join(lines) + "\n")
    print(f"C header:       {header_path}")


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(model: keras.Model, x_val: np.ndarray, y_val: np.ndarray,
             threshold: float, out_dir: Path) -> None:
    probs = model.predict(x_val, verbose=0).flatten()
    preds = (probs >= threshold).astype(int)

    print(f"\nClassification report (threshold={threshold}):")
    print(classification_report(y_val.astype(int), preds,
                                 target_names=["no_person", "person"]))

    cm = confusion_matrix(y_val.astype(int), preds)
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["no_person", "person"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["no_person", "person"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.png", dpi=150)
    plt.close(fig)
    print(f"Confusion matrix saved → {out_dir / 'confusion_matrix.png'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Train Peekaboo person classifier.")
    parser.add_argument("--real_data",      type=Path, default=Path("Training_Data/combined"))
    parser.add_argument("--synthetic_data", type=Path, default=Path("Training_Data/synthetic"))
    parser.add_argument("--output_dir",     type=Path, default=Path("models"))
    parser.add_argument("--img_size",  type=int,   default=96)
    parser.add_argument("--epochs",    type=int,   default=20)
    parser.add_argument("--batch",     type=int,   default=32)
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="Classification threshold — lower = more sensitive to person")
    parser.add_argument("--val_split", type=float, default=0.20)
    parser.add_argument("--seed",      type=int,   default=42)
    parser.add_argument("--fine_tune_epochs", type=int, default=10,
                        help="Additional epochs with top MobileNetV2 layers unfrozen (0 = skip)")
    args = parser.parse_args()

    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Data ──────────────────────────────────────────────────────────────────
    data_dirs = [d for d in [args.real_data, args.synthetic_data] if d.exists()]
    print(f"Loading data from: {[str(d) for d in data_dirs]}")
    x_train, y_train, x_val, y_val = load_dataset(
        data_dirs, args.img_size, args.val_split, args.seed)

    train_ds = make_tf_dataset(x_train, y_train, args.batch, augment=True)
    val_ds   = make_tf_dataset(x_val,   y_val,   args.batch, augment=False)

    # ── Phase 1: train head only ───────────────────────────────────────────────
    print("\n── Phase 1: training classification head ────────────────────────")
    model = build_model(args.img_size)
    model.compile(
        optimizer=keras.optimizers.Adam(1e-3),
        loss=focal_loss(gamma=2.0, alpha=0.25),
        metrics=["accuracy",
                 keras.metrics.Recall(name="recall"),
                 keras.metrics.Precision(name="precision")],
    )
    model.summary(line_length=80)

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_recall", patience=5,
                                       restore_best_weights=True, mode="max"),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5,
                                           patience=3, min_lr=1e-6),
    ]
    model.fit(train_ds, validation_data=val_ds,
              epochs=args.epochs, callbacks=callbacks)

    # ── Phase 2: fine-tune top MobileNetV2 layers ────────────────────────────
    if args.fine_tune_epochs > 0:
        print("\n── Phase 2: fine-tuning top layers ─────────────────────────────")
        base = next(l for l in model.layers if isinstance(l, keras.Model))
        base.trainable = True
        # Freeze everything except the last 30 layers
        for layer in base.layers[:-30]:
            layer.trainable = False

        model.compile(
            optimizer=keras.optimizers.Adam(1e-5),
            loss=focal_loss(gamma=2.0, alpha=0.25),
            metrics=["accuracy",
                     keras.metrics.Recall(name="recall"),
                     keras.metrics.Precision(name="precision")],
        )
        model.fit(train_ds, validation_data=val_ds,
                  epochs=args.fine_tune_epochs, callbacks=callbacks)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    print("\n── Evaluation ───────────────────────────────────────────────────")
    evaluate(model, x_val, y_val, args.threshold, args.output_dir)

    # ── Export ────────────────────────────────────────────────────────────────
    print("\n── Exporting models ─────────────────────────────────────────────")
    export_float32(model, args.output_dir / "peekaboo.tflite")
    export_int8(model, x_train[:200], args.output_dir / "peekaboo_int8.tflite")
    export_c_header(args.output_dir / "peekaboo_int8.tflite",
                    args.output_dir / "peekaboo_int8.h")

    print(f"\nDone. Models written to {args.output_dir}/")
    print(f"Deploy peekaboo_int8.h to camera firmware.")


if __name__ == "__main__":
    main()

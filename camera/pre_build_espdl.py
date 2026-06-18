Import("env")
import glob
import os
import subprocess


def _load_dotenv(project_dir):
    """Load .env into os.environ so cmake $ENV{} picks up credentials."""
    env_file = os.path.join(project_dir, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def _resolve_mqtt_password(env):
    """Select the per-device MQTT password keyed by CAMERA_ID.

    Each camera authenticates to the broker as its own user (= camera_id), so
    each build needs that device's password. .env holds one entry per device
    (MQTT_PASSWORD_<CAMERA_ID>, e.g. MQTT_PASSWORD_S3EYE_01); this copies the
    matching one into MQTT_PASSWORD for the credentials.h generation. Falls back
    to any pre-set MQTT_PASSWORD if no per-device entry exists.
    """
    import re
    camera_id = None
    for define in env.get("CPPDEFINES", []):
        if isinstance(define, (list, tuple)) and len(define) == 2 and define[0] == "CAMERA_ID":
            camera_id = re.sub(r"[^A-Za-z0-9_-]", "", str(define[1]))
    # CPPDEFINES is often empty this early in the build; fall back to scanning the
    # raw build flags for the CAMERA_ID token (e.g. -D CAMERA_ID="\"s3eye-01\"").
    if not camera_id:
        m = re.search(r"CAMERA_ID[^A-Za-z0-9]+([A-Za-z0-9]+-\d+)", env.subst("$BUILD_FLAGS"))
        if m:
            camera_id = m.group(1)
    if not camera_id:
        print("Pre-build: WARNING could not determine CAMERA_ID — MQTT_PASSWORD left unset")
        return
    key = "MQTT_PASSWORD_" + camera_id.upper().replace("-", "_")
    if key in os.environ:
        os.environ["MQTT_PASSWORD"] = os.environ[key]
        print(f"Pre-build: MQTT password resolved for {camera_id} (from {key})")
    else:
        print(f"Pre-build: WARNING {key} not in environment — MQTT_PASSWORD left unset")


def _pack_model(build_dir, esp_dl_dir, managed_dir, component_name, packed_name, cmake_bin):
    """Pack all .espdl files from a managed component's s3 models dir and embed as .S."""
    component_dir = os.path.join(managed_dir, f"espressif__{component_name}")
    pack_script   = os.path.join(esp_dl_dir, "fbs_loader", "pack_espdl_models.py")
    cmake_script  = os.path.join(esp_dl_dir, "fbs_loader", "cmake",
                                 "data_file_embed_asm_aligned.cmake")

    models_out_dir = os.path.join(build_dir, "espdl_models")
    packed_model   = os.path.join(models_out_dir, f"{packed_name}.espdl")
    asm_file       = os.path.join(build_dir, f"{packed_name}.espdl.S")

    model_src = sorted(glob.glob(os.path.join(component_dir, "models", "s3", "*.espdl")))
    if not model_src:
        print(f"Pre-build: no s3 models found for {component_name} — skipping pack")
        return

    os.makedirs(models_out_dir, exist_ok=True)

    if not os.path.exists(packed_model):
        print(f"Pre-build: packing {component_name} models...")
        r = subprocess.run(
            ["python3", pack_script, "--model_path"] + model_src + ["--out_file", packed_model],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"pack_espdl_models.py failed for {component_name}:", r.stderr)
            return
        print(f"Pre-build: packed → {packed_model}")

    if not os.path.exists(asm_file):
        print(f"Pre-build: generating {packed_name}.espdl.S ...")
        r = subprocess.run(
            [cmake_bin,
             "-D", f"DATA_FILE={packed_model}",
             "-D", f"SOURCE_FILE={asm_file}",
             "-D", "FILE_TYPE=BINARY",
             "-P", cmake_script],
            cwd=build_dir, capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"data_file_embed_asm_aligned.cmake failed for {component_name}:", r.stderr)
            return
        print(f"Pre-build: generated → {asm_file}")


def _embed_tflite(build_dir, project_dir, cmake_bin):
    """Pre-generate peekaboo_int8.tflite.S so IDF's ninja finds it before linking."""
    tflite_file = os.path.join(project_dir, "src", "s3eye", "peekaboo_int8.tflite")
    asm_file    = os.path.join(build_dir, "peekaboo_int8.tflite.S")

    if os.path.exists(asm_file):
        return

    idf_dir     = os.path.join(os.path.expanduser("~"), ".platformio", "packages",
                               "framework-espidf")
    embed_script = os.path.join(idf_dir, "tools", "cmake", "scripts",
                                "data_file_embed_asm.cmake")

    if not os.path.exists(embed_script):
        print(f"Pre-build: WARNING: {embed_script} not found — skipping tflite embed")
        return

    print("Pre-build: generating peekaboo_int8.tflite.S ...")
    r = subprocess.run(
        [cmake_bin,
         "-D", f"DATA_FILE={tflite_file}",
         "-D", f"SOURCE_FILE={asm_file}",
         "-D", "FILE_TYPE=BINARY",
         "-P", embed_script],
        cwd=build_dir, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("data_file_embed_asm.cmake failed:", r.stderr)
    else:
        print(f"Pre-build: generated → {asm_file}")


def _generate_espdl_files(env):
    build_dir   = env.subst("$BUILD_DIR")
    project_dir = env.subst("$PROJECT_DIR")

    if not os.path.isdir(build_dir):
        return

    cmake_bin = os.path.join(os.path.expanduser("~"), ".platformio", "packages",
                             "tool-cmake", "bin", "cmake")

    # XIAO: pre-generate the TFLite model .S; skip ESP-DL packing
    if env.subst("$PIOENV").startswith("xiao_s3"):
        _embed_tflite(build_dir, project_dir, cmake_bin)
        return

    # ESP32-CAM: no ML models — pure streaming camera, Jetson does all inference
    if env.subst("$PIOENV").startswith("esp32cam"):
        return

    managed = os.path.join(project_dir, "managed_components")
    esp_dl  = os.path.join(managed, "espressif__esp-dl")
    _pack_model(build_dir, esp_dl, managed, "pedestrian_detect", "pedestrian_detect", cmake_bin)


def _pre_action_callback(source, target, env):
    _generate_espdl_files(env)


# Inject .env into os.environ before cmake configure so $ENV{} substitutions work.
_load_dotenv(env.subst("$PROJECT_DIR"))
_resolve_mqtt_password(env)

# Run immediately so the .S file exists before cmake --build starts compilation.
_generate_espdl_files(env)

# Keep as a pre-link action so clean builds that somehow reach linking still work.
env.AddPreAction("$BUILD_DIR/firmware.elf", _pre_action_callback)

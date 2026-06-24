# XIAO Flash Recovery — RESOLVED 2026-06-21

xiao-01 is online and face recognition is working.

## Root cause of crashes

`camera/src/CMakeLists.txt` links `espressif__esp-tflite-micro` into every
XIAO build regardless of whether inference_task uses TFLite, because it keys
on the sdkconfig path containing "xiao_s3":

```cmake
if(SDKCONFIG MATCHES "xiao_s3")
    set(_embed_files "${CMAKE_SOURCE_DIR}/src/s3eye/peekaboo_int8.tflite")
    set(_extra_requires "espressif__esp-tflite-micro")
```

TFLite's NN assembly kernels attempt a store to the PSRAM arena at startup,
causing a `StoreProhibited` exception. Fix: add `CONFIG_NN_ANSI_C=y` to
`sdkconfig.xiao_peekaboo.defaults` to force the portable ANSI C kernel path.

## Fix applied

Added to `camera/sdkconfig.xiao_peekaboo.defaults`:
```
CONFIG_NN_ANSI_C=y
```

## Flash procedure for future reference

The XIAO ESP32-S3 Sense has no visible BOOT or RST buttons on the top — they
are tiny pads/buttons found by feel or close inspection near the USB-C end.

Bootloader entry sequence:
1. Press and hold BOOT
2. Press and release RST
3. Release BOOT
4. Device enumerates as `303a:1001` (USB JTAG/serial debug unit)
5. `pio run -e xiao_s3_01 -t upload`
6. Press RST once to boot into application (`303a:0009`)

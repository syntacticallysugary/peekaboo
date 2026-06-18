FILE(GLOB app_sources
    ${CMAKE_SOURCE_DIR}/src/s3eye/*.cpp
    ${CMAKE_SOURCE_DIR}/src/s3eye/*.c
)

# Write credentials directly to a header file at cmake configure time.
# target_compile_definitions passes values through cmake→ninja→shell which
# expands $8 and similar patterns as shell positional parameters, corrupting
# passwords that contain dollar signs (e.g. "!A$8ad$8ear!").
# file(WRITE) writes the env var value as raw bytes with no shell involved.
file(WRITE "${CMAKE_BINARY_DIR}/credentials.h"
    "#pragma once\n"
    "#define WIFI_SSID \"$ENV{WIFI_SSID}\"\n"
    "#define WIFI_PASSWORD \"$ENV{WIFI_PASSWORD}\"\n"
    "#define COMMAND_MODULE_URL \"$ENV{COMMAND_MODULE_URL}\"\n"
    "#define JETSON_URL \"$ENV{JETSON_URL}\"\n"
    "#define SECRET_PSK \"$ENV{SECRET_PSK}\"\n"
    "#define MQTT_BROKER_HOST \"$ENV{MQTT_BROKER_HOST}\"\n"
    "#define MQTT_BROKER_PORT $ENV{MQTT_BROKER_PORT}\n"
    "#define MQTT_PASSWORD \"$ENV{MQTT_PASSWORD}\"\n"
)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/.env")

# Embed the MQTT broker CA as a C string. EMBED_TXTFILES would be cleaner, but the
# PlatformIO+IDF flow here doesn't reliably generate the embed .S (same reason the
# TFLite model is pre-generated), so we bake the PEM into a header instead.
file(READ "${CMAKE_SOURCE_DIR}/certs/mqtt_ca.pem" _mqtt_ca_pem)
string(REPLACE "\n" "\\n" _mqtt_ca_pem "${_mqtt_ca_pem}")
file(WRITE "${CMAKE_BINARY_DIR}/mqtt_ca_cert.h"
    "#pragma once\n"
    "static const char MQTT_CA_CERT[] = \"${_mqtt_ca_pem}\";\n"
)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/certs/mqtt_ca.pem")

# Embed peekaboo TFLite model only for XIAO builds (saves 629 KB on S3-EYE).
# Key on SDKCONFIG path — PlatformIO passes -DSDKCONFIG=<project>/sdkconfig.<env>
# so build flags are not yet in CMAKE_C_FLAGS at configure time.
if(SDKCONFIG MATCHES "xiao_s3")
    set(_embed_files "${CMAKE_SOURCE_DIR}/src/s3eye/peekaboo_int8.tflite")
    set(_extra_requires "espressif__esp-tflite-micro")
else()
    set(_embed_files "")
    set(_extra_requires "")
endif()

idf_component_register(
    SRCS ${app_sources}
    INCLUDE_DIRS "${CMAKE_SOURCE_DIR}/src/s3eye" "${CMAKE_BINARY_DIR}"
    EMBED_FILES ${_embed_files}
    REQUIRES
        esp_wifi
        esp_http_client
        esp_event
        esp_netif
        esp_timer
        mqtt
        lwip
        nvs_flash
        json
        mbedtls
        freertos
        log
        ${_extra_requires}
)

# Redirect esp-nn SIMD scratch-buffer setters to a DRAM buffer we own.
# The ESP32-S3 PIE instructions can only write to internal SRAM; without this
# wrap the kernels crash (StoreProhibited) when the arena lives in PSRAM.
if(SDKCONFIG MATCHES "xiao_s3")
    target_link_options(${COMPONENT_LIB} INTERFACE
        -Wl,--wrap=esp_nn_set_depthwise_conv_scratch_buf_esp32s3
        -Wl,--wrap=esp_nn_set_conv_scratch_buf_esp32s3)
endif()

cmake_minimum_required(VERSION 3.16.0)
# Bypass ESP-IDF git describe — camera/ is a monorepo subdirectory
set(PROJECT_VER "1.0.0")
# Enable the IDF component manager so idf_component.yml deps are fetched
set(IDF_COMPONENT_MANAGER 1)
set(IDF_COMPONENT_MANAGER_VENV_PATH "$ENV{HOME}/.platformio/penv/.espidf-5.5.0")
# Select sdkconfig defaults based on environment. PlatformIO passes
# -DSDKCONFIG=<project>/sdkconfig.<env>, so we can branch on the path.
if(SDKCONFIG MATCHES "xiao_s3")
    set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.xiao_peekaboo.defaults")
else()
    set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_SOURCE_DIR}/sdkconfig.s3eye.defaults")
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(camera)

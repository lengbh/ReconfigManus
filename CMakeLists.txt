cmake_minimum_required(VERSION 3.20)

project(ReconfigManus)
set(CMAKE_CXX_STANDARD 20)

if(APPLE)
    set(OPERATING_SYSTEM "macOS")
elseif(UNIX AND NOT APPLE)
    set(OPERATING_SYSTEM "Linux")
elseif(WIN32)
    set(OPERATING_SYSTEM "Windows")
else()
    set(OPERATING_SYSTEM "Other")
endif()

set(ROOT_DIR ${CMAKE_CURRENT_SOURCE_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${ROOT_DIR}/bin/${OPERATING_SYSTEM})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${ROOT_DIR}/bin/${OPERATING_SYSTEM})
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${ROOT_DIR}/lib/${OPERATING_SYSTEM})

add_subdirectory(MQTTServer)
add_subdirectory(MESServer)

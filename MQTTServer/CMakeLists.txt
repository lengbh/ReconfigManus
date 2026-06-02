cmake_minimum_required(VERSION 3.20)

project(MQTTServer)

add_library(${PROJECT_NAME} STATIC
        MQTTServer.cpp
)

target_include_directories(${PROJECT_NAME}
        PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
        PRIVATE
        ${ROOT_DIR}/TCPConn
)

find_package(PahoMqttCpp CONFIG REQUIRED)

target_link_libraries(${PROJECT_NAME}
        PUBLIC
        PahoMqttCpp::paho-mqttpp3
)

cmake_minimum_required(VERSION 3.20)

project(MESServer)

add_executable(${PROJECT_NAME} main.cpp
        MESServer.cpp
        GraphManager.cpp
        ProcessManager.cpp
        OrderManager.cpp
        ProductManager.cpp
)

# copy config files to working dir
file(GLOB CFG_FILES "cfgs/*")

foreach(cfg ${CFG_FILES})
    get_filename_component(name ${cfg} NAME)
    configure_file(${cfg}
            ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/${name}
)
endforeach()


# nlohmann::json
find_package(nlohmann_json CONFIG REQUIRED)
target_link_libraries(${PROJECT_NAME} PRIVATE nlohmann_json::nlohmann_json)


# boost
set(Boost_USE_MULTITHREAD ON)
find_package(Boost REQUIRED)
target_include_directories(${PROJECT_NAME} PRIVATE ${Boost_INCLUDE_DIRS})
if (WIN32)
    set_target_properties(TCPConn PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
    add_definitions(-D_WIN32_WINNT=0x0A00)
    set(Boost_NO_WARN_NEW_VERSIONS 1)
    set(Boost_USE_STATIC_LIBS ON)
endif ()


# TCPConn
target_include_directories(${PROJECT_NAME} PRIVATE ${ROOT_DIR}/TCPConn)

if (TARGET TCPConn)
    target_link_libraries(${PROJECT_NAME} PRIVATE TCPConn)
else()
    find_library(TCPConn_LIB
            NAMES TCPConn libTCPConn TCPConn.lib libTCPConn.dll.a
            HINTS
                ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY}
                ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}
                ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}
    )

    if (NOT TCPConn_LIB)
        message(FATAL_ERROR "Could not find TCPConn library, please confirm it has been built.
        Looked in: ${CMAKE_ARCHIVE_OUTPUT_DIRECTORY}; ${CMAKE_LIBRARY_OUTPUT_DIRECTORY}; ${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
    endif()

    target_link_libraries(${PROJECT_NAME} PRIVATE ${TCPConn_LIB})
endif()
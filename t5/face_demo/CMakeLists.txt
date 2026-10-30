##
# @file CMakeLists.txt
# @brief DeskBot 脸第一版（照 examples/graphics/lvgl_demo 的结构）
#/

# APP_PATH
set(APP_PATH ${CMAKE_CURRENT_LIST_DIR})

# APP_NAME
get_filename_component(APP_NAME ${APP_PATH} NAME)

# APP_SRCS
aux_source_directory(${APP_PATH}/src APP_SRCS)

########################################
# Target Configure
########################################
add_library(${EXAMPLE_LIB})

target_sources(${EXAMPLE_LIB}
    PRIVATE
        ${APP_SRCS}
    )

target_compile_options(${EXAMPLE_LIB}
    PRIVATE
        -Wall -DLV_LVGL_H_INCLUDE_SIMPLE
    )

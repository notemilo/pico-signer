# บอก MicroPython ว่ามีโมดูล C เพิ่มมาหนึ่งตัว
add_library(usermod_sha512 INTERFACE)

target_sources(usermod_sha512 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/sha512mod.c
)

target_include_directories(usermod_sha512 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_sha512)

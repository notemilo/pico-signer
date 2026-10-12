# รวมโมดูล C ทั้งหมดของ Pico — ส่งไฟล์นี้ให้ USER_C_MODULES
#   make -C ports/rp2 BOARD=RPI_PICO2 USER_C_MODULES=<repo>/firmware/usermods.cmake
include(${CMAKE_CURRENT_LIST_DIR}/usermod_sha512/micropython.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/usermod_secp256k1/micropython.cmake)

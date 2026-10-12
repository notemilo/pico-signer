# โมดูล C: สะพานไป libsecp256k1 (Bitcoin Core) — ใช้กับพอร์ต rp2 (cmake)
#
# ซอร์ส libsecp256k1 ไม่ได้เก็บในโปรเจค ต้องโคลนเอง แล้วชี้ด้วย SECP256K1_DIR
#   git clone --depth 1 --branch v0.8.0 https://github.com/bitcoin-core/secp256k1
#   (commit ต้องเป็น 6e2c8bc4ecdc6e71dbe7a368f360d8d453ce435d)
if(NOT DEFINED SECP256K1_DIR)
    if(DEFINED ENV{SECP256K1_DIR})
        set(SECP256K1_DIR $ENV{SECP256K1_DIR})
    else()
        set(SECP256K1_DIR $ENV{HOME}/picobuild/secp256k1)
    endif()
endif()
if(NOT EXISTS ${SECP256K1_DIR}/src/secp256k1.c)
    message(FATAL_ERROR "ไม่เจอ libsecp256k1 ที่ ${SECP256K1_DIR} — ตั้ง SECP256K1_DIR")
endif()

add_library(usermod_secp256k1 INTERFACE)

target_sources(usermod_secp256k1 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/secp256k1mod.c
    ${CMAKE_CURRENT_LIST_DIR}/libsecp256k1_unity.c
)

target_include_directories(usermod_secp256k1 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${SECP256K1_DIR}/include
    ${SECP256K1_DIR}/src
)

# ตารางคำนวณล่วงหน้าให้เล็กพอสำหรับไมโครคอนโทรลเลอร์:
#   ECMULT_WINDOW_SIZE=4 → ตารางสำหรับตรวจลายเซ็นเล็กมาก (ค่าปกติ 15 = 1 MB ใส่ไม่ได้)
#   COMB 11×6 → ตารางสำหรับเซ็น/สร้าง pubkey 22 KB (ค่ากลางที่ไลบรารีมีให้)
# ไม่เปิด module เสริม (schnorr/musig/ecdh/...) — ใช้แค่ ECDSA + บวก tweak
target_compile_definitions(usermod_secp256k1 INTERFACE
    ECMULT_WINDOW_SIZE=4
    COMB_BLOCKS=11
    COMB_TEETH=6
)


target_link_libraries(usermod INTERFACE usermod_secp256k1)

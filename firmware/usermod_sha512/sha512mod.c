/* sha512mod.c — เปิดทางให้ Python เรียก SHA-512 ที่มีอยู่แล้วในเฟิร์มแวร์
 *
 * ทำไมต้องมี:
 *   MicroPython hashlib มีแค่ md5 / sha1 / sha256 — **ไม่มี sha512 เลย**
 *   แต่ BIP39 (PBKDF2-HMAC-SHA512) กับ BIP32 (HMAC-SHA512) ต้องใช้
 *   ถ้าเขียน SHA-512 ด้วย Python จะช้ามาก: วัดจริงบน RP2350 ได้ 47 ms/ครั้ง
 *   → แปลง 24 คำเป็น seed ใช้เวลา 414 วินาที (7 นาที) ทุกครั้งที่เปิดเครื่อง
 *
 * 🔑 ไฟล์นี้ **ไม่มีโค้ดเข้ารหัสของตัวเองเลยสักบรรทัด**
 *   ตัว SHA-512 จริงคือของ mbedtls ซึ่งถูกคอมไพล์เข้าเฟิร์มแวร์ rp2 อยู่แล้ว
 *   (ports/rp2/CMakeLists.txt ลิงก์ micropy_lib_mbedtls แบบไม่มีเงื่อนไข และ
 *    extmod/mbedtls/mbedtls_config_common.h เปิด MBEDTLS_SHA512_C ไว้แล้ว)
 *   ที่เพิ่มเข้ามาคือสะพานเชื่อมล้วน ๆ → พื้นที่ที่ต้องเชื่อใจเพิ่มน้อยที่สุด
 *
 * ใช้งาน:
 *   import sha512
 *   sha512.digest(b"abc")          -> bytes 64 ตัว (ครั้งเดียวจบ)
 *   h = sha512.new(); h.update(b); h.digest()   -> ทยอยป้อนได้
 */

#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "mbedtls/sha512.h"

/* ── แบบครั้งเดียวจบ ─────────────────────────────────────────────── */
static mp_obj_t mod_sha512_digest(mp_obj_t data_in) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_in, &bufinfo, MP_BUFFER_READ);

    vstr_t out;
    vstr_init_len(&out, 64);
    /* พารามิเตอร์ตัวท้าย 0 = SHA-512 (ถ้าเป็น 1 คือ SHA-384) */
    if (mbedtls_sha512((const unsigned char *)bufinfo.buf, bufinfo.len,
                       (unsigned char *)out.buf, 0) != 0) {
        vstr_clear(&out);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("sha512 failed"));
    }
    return mp_obj_new_bytes_from_vstr(&out);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_sha512_digest_obj, mod_sha512_digest);

/* ── แบบทยอยป้อน (ให้หน้าตาเหมือน hashlib ของ Python) ──────────── */
typedef struct _sha512_ctx_obj_t {
    mp_obj_base_t base;
    mbedtls_sha512_context ctx;
    bool finished;
} sha512_ctx_obj_t;

/* หมายเหตุ: ไม่ต้องประกาศ sha512_ctx_type ล่วงหน้า — MP_DEFINE_CONST_OBJ_TYPE
   ประกาศให้เองและถูกนิยามก่อนจุดที่ใช้จริง (mod_sha512_new) อยู่แล้ว */

static mp_obj_t sha512_ctx_update(mp_obj_t self_in, mp_obj_t data_in) {
    sha512_ctx_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->finished) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("already finalized"));
    }
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_in, &bufinfo, MP_BUFFER_READ);
    mbedtls_sha512_update(&self->ctx, (const unsigned char *)bufinfo.buf, bufinfo.len);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(sha512_ctx_update_obj, sha512_ctx_update);

static mp_obj_t sha512_ctx_digest(mp_obj_t self_in) {
    sha512_ctx_obj_t *self = MP_OBJ_TO_PTR(self_in);
    vstr_t out;
    vstr_init_len(&out, 64);
    mbedtls_sha512_context tmp;
    mbedtls_sha512_init(&tmp);
    mbedtls_sha512_clone(&tmp, &self->ctx);      /* ไม่ทำลายของเดิม เรียกซ้ำได้ */
    mbedtls_sha512_finish(&tmp, (unsigned char *)out.buf);
    mbedtls_sha512_free(&tmp);
    return mp_obj_new_bytes_from_vstr(&out);
}
static MP_DEFINE_CONST_FUN_OBJ_1(sha512_ctx_digest_obj, sha512_ctx_digest);

static const mp_rom_map_elem_t sha512_ctx_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_update), MP_ROM_PTR(&sha512_ctx_update_obj) },
    { MP_ROM_QSTR(MP_QSTR_digest), MP_ROM_PTR(&sha512_ctx_digest_obj) },
};
static MP_DEFINE_CONST_DICT(sha512_ctx_locals, sha512_ctx_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(
    sha512_ctx_type,
    MP_QSTR_sha512ctx,
    MP_TYPE_FLAG_NONE,
    locals_dict, &sha512_ctx_locals
);

static mp_obj_t mod_sha512_new(size_t n_args, const mp_obj_t *args) {
    sha512_ctx_obj_t *o = mp_obj_malloc(sha512_ctx_obj_t, &sha512_ctx_type);
    o->finished = false;
    mbedtls_sha512_init(&o->ctx);
    mbedtls_sha512_starts(&o->ctx, 0);
    if (n_args > 0) {
        mp_buffer_info_t bufinfo;
        mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);
        mbedtls_sha512_update(&o->ctx, (const unsigned char *)bufinfo.buf, bufinfo.len);
    }
    return MP_OBJ_FROM_PTR(o);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_sha512_new_obj, 0, 1, mod_sha512_new);

static const mp_rom_map_elem_t sha512_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_sha512) },
    { MP_ROM_QSTR(MP_QSTR_digest),   MP_ROM_PTR(&mod_sha512_digest_obj) },
    { MP_ROM_QSTR(MP_QSTR_new),      MP_ROM_PTR(&mod_sha512_new_obj) },
};
static MP_DEFINE_CONST_DICT(sha512_module_globals, sha512_module_globals_table);

const mp_obj_module_t sha512_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&sha512_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_sha512, sha512_user_cmodule);

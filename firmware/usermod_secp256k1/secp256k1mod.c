/* secp256k1mod.c — ให้ Python เรียก libsecp256k1 (ไลบรารีของ Bitcoin Core) แทนโค้ดเส้นโค้งที่เราเขียนเอง
 *
 * ทำไมต้องมี (12 ต.ค. 2026):
 *   src/secp256k1.py เขียนเองด้วย Python ล้วน — เป็นจุดอ่อนใหญ่สุดของโปรเจค
 *   (เทสเทียบไลบรารีมาตรฐานผ่าน แต่ไม่เคยมีคนนอกตรวจ และไม่ใช่ constant-time)
 *   libsecp256k1 คือไลบรารีที่ Bitcoin Core ใช้เอง ผ่านการตรวจมาหลายปี
 *
 * 🔑 ไฟล์นี้ **ไม่มีคณิตศาสตร์เส้นโค้งของตัวเองเลย** — เป็นสะพานเชื่อมล้วน ๆ
 *   ทุกการคำนวณเรียก API สาธารณะของ libsecp256k1 (include/secp256k1.h) เท่านั้น
 *   รุ่นที่ใช้: v0.8.0 (commit 6e2c8bc4ecdc6e71dbe7a368f360d8d453ce435d)
 *
 * ใช้งาน (หน้าตาเดียวกับฟังก์ชันใน src/secp256k1.py):
 *   import secp256k1c as c
 *   c.privkey_to_pubkey(priv32)            -> pubkey บีบอัด 33 ไบต์
 *   c.tweak_add_private(priv32, tweak32)   -> priv 32 ไบต์ (BIP32 ฝั่ง xprv)
 *   c.tweak_add_public(pub33, tweak32)     -> pub 33 ไบต์ (BIP32 ฝั่ง xpub)
 *   c.sign(msg32, priv32)                  -> r||s 64 ไบต์ (RFC6979 · low-S · ไม่ใช้ตัวสุ่ม)
 *   c.verify(msg32, sig64, pub33)          -> True/False
 *   ข้อมูลผิดรูป/กุญแจใช้ไม่ได้ = ValueError
 *
 * การตั้งค่า (ดู micropython.cmake):
 *   - context จองในหน่วยความจำคงที่ ไม่เรียก malloc ของ C (rp2 แทบไม่มี C heap)
 *   - ไม่เรียก context_randomize = ไม่ใช้ตัวสุ่มของเครื่องเลย (ผู้ใช้ ไม่ไว้ใจ RNG ของชิป)
 *     ผลคือไม่มี blinding กัน side channel ตอนสร้าง pubkey/เซ็น
 *     แต่ก็ยังดีกว่าเดิม (โค้ด Python เดิมไม่ constant-time เลย)
 *   - callback "เรียกผิดวิธี" (illegal) ของไลบรารีปกติจะ abort()
 *     เราแทนด้วยตัวที่ตั้งธง แล้ว **เช็คธงหลังทุกการเรียก** → ValueError
 *     (เอกสาร v0.8.0: หลัง illegal callback คืนกลับ ค่าที่คืนและ output เป็น undefined ห้ามใช้)
 *   - callback "ข้อผิดพลาดภายใน" (error) ห้าม return (เอกสาร: return แล้วอะไรก็เกิดได้)
 *     → หยุดเครื่องค้างไว้ ผู้ใช้ปิดเปิดใหม่ (ดีกว่าทำงานต่อด้วยข้อมูลที่เชื่อไม่ได้)
 *   แก้ 13 ต.ค. 2026 ตามผู้รีวิวภายนอก ข้อ 3 (เดิมตั้งธงแต่ไม่เคยเช็ค และ error callback คืนกลับ)
 */

#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "secp256k1.h"
#include "secp256k1_preallocated.h"

/* context ขนาดของ libsecp256k1 รุ่นนี้เล็กมาก (ราวร้อยกว่าไบต์) จองเผื่อไว้แล้วเช็คตอนสร้าง */
#define CTX_BUF_SIZE 512
static unsigned char ctx_buf[CTX_BUF_SIZE] __attribute__((aligned(16)));
static secp256k1_context *ctx = NULL;
static volatile int illegal_flag = 0;

static void on_illegal(const char *msg, void *data) {
    (void)msg; (void)data;
    illegal_flag = 1;
}

static void on_error(const char *msg, void *data) {
    (void)msg; (void)data;
    for (;;) {
        /* ห้าม return — หยุดตรงนี้ ปิดเปิดเครื่องใหม่ */
    }
}

/* เรียกหลังทุกการเรียกไลบรารี — ธงตั้ง = ผลลัพธ์เชื่อไม่ได้ ห้ามใช้ */
#define CHECK_ILLEGAL() do { \
        if (illegal_flag) { \
            illegal_flag = 0; \
            mp_raise_ValueError(MP_ERROR_TEXT("secp256k1 illegal argument")); \
        } \
    } while (0)

static secp256k1_context *get_ctx(void) {
    if (ctx == NULL) {
        size_t need = secp256k1_context_preallocated_size(SECP256K1_CONTEXT_NONE);
        if (need > CTX_BUF_SIZE) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("secp256k1 ctx buffer too small"));
        }
        /* preallocated_create ทำ selftest ให้ด้วย */
        ctx = secp256k1_context_preallocated_create(ctx_buf, SECP256K1_CONTEXT_NONE);
        secp256k1_context_set_illegal_callback(ctx, on_illegal, NULL);
        secp256k1_context_set_error_callback(ctx, on_error, NULL);
    }
    illegal_flag = 0;
    return ctx;
}

static const unsigned char *get_bytes(mp_obj_t o, size_t want) {
    mp_buffer_info_t b;
    mp_get_buffer_raise(o, &b, MP_BUFFER_READ);
    if (b.len != want) {
        mp_raise_ValueError(MP_ERROR_TEXT("wrong length"));
    }
    return (const unsigned char *)b.buf;
}

static mp_obj_t ser_pub(secp256k1_context *c, const secp256k1_pubkey *pk) {
    unsigned char out[33];
    size_t outlen = sizeof(out);
    int ok = secp256k1_ec_pubkey_serialize(c, out, &outlen, pk, SECP256K1_EC_COMPRESSED);
    CHECK_ILLEGAL();
    if (!ok || outlen != 33) {
        mp_raise_ValueError(MP_ERROR_TEXT("pubkey serialize failed"));
    }
    return mp_obj_new_bytes(out, 33);
}

/* priv 32 -> pub 33 */
static mp_obj_t mod_privkey_to_pubkey(mp_obj_t priv_in) {
    secp256k1_context *c = get_ctx();
    const unsigned char *priv = get_bytes(priv_in, 32);
    secp256k1_pubkey pk;
    int ok = secp256k1_ec_pubkey_create(c, &pk, priv);
    CHECK_ILLEGAL();
    if (!ok) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid private key"));
    }
    return ser_pub(c, &pk);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_privkey_to_pubkey_obj, mod_privkey_to_pubkey);

/* (priv + tweak) mod n */
static mp_obj_t mod_tweak_add_private(mp_obj_t priv_in, mp_obj_t tweak_in) {
    secp256k1_context *c = get_ctx();
    unsigned char k[32];
    memcpy(k, get_bytes(priv_in, 32), 32);
    const unsigned char *t = get_bytes(tweak_in, 32);
    int ok = secp256k1_ec_seckey_tweak_add(c, k, t);
    if (illegal_flag || !ok) {
        memset(k, 0, sizeof(k));
        CHECK_ILLEGAL();
        mp_raise_ValueError(MP_ERROR_TEXT("tweak result invalid"));
    }
    mp_obj_t r = mp_obj_new_bytes(k, 32);
    memset(k, 0, sizeof(k));
    return r;
}
static MP_DEFINE_CONST_FUN_OBJ_2(mod_tweak_add_private_obj, mod_tweak_add_private);

/* P + tweak*G */
static mp_obj_t mod_tweak_add_public(mp_obj_t pub_in, mp_obj_t tweak_in) {
    secp256k1_context *c = get_ctx();
    const unsigned char *p = get_bytes(pub_in, 33);
    const unsigned char *t = get_bytes(tweak_in, 32);
    secp256k1_pubkey pk;
    int ok = secp256k1_ec_pubkey_parse(c, &pk, p, 33);
    CHECK_ILLEGAL();
    if (!ok) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid public key"));
    }
    ok = secp256k1_ec_pubkey_tweak_add(c, &pk, t);
    CHECK_ILLEGAL();
    if (!ok) {
        mp_raise_ValueError(MP_ERROR_TEXT("tweak result invalid"));
    }
    return ser_pub(c, &pk);
}
static MP_DEFINE_CONST_FUN_OBJ_2(mod_tweak_add_public_obj, mod_tweak_add_public);

/* เซ็น: nonce = RFC6979 ของไลบรารี (ndata = NULL → ไม่มีความสุ่มเพิ่ม) · คืน r||s แบบ low-S */
static mp_obj_t mod_sign(mp_obj_t msg_in, mp_obj_t priv_in) {
    secp256k1_context *c = get_ctx();
    const unsigned char *msg = get_bytes(msg_in, 32);
    const unsigned char *priv = get_bytes(priv_in, 32);
    secp256k1_ecdsa_signature sig;
    int ok = secp256k1_ecdsa_sign(c, &sig, msg, priv, secp256k1_nonce_function_rfc6979, NULL);
    CHECK_ILLEGAL();
    if (!ok) {
        mp_raise_ValueError(MP_ERROR_TEXT("sign failed"));
    }
    unsigned char out[64];
    secp256k1_ecdsa_signature_serialize_compact(c, out, &sig);
    CHECK_ILLEGAL();
    mp_obj_t r = mp_obj_new_bytes(out, 64);
    memset(&sig, 0, sizeof(sig));
    memset(out, 0, sizeof(out));
    return r;
}
static MP_DEFINE_CONST_FUN_OBJ_2(mod_sign_obj, mod_sign);

/* ตรวจ: รับ r||s 64 ไบต์ · ไลบรารีรับเฉพาะ low-S (ลายเซ็นของเราเป็น low-S อยู่แล้ว) */
static mp_obj_t mod_verify(mp_obj_t msg_in, mp_obj_t sig_in, mp_obj_t pub_in) {
    secp256k1_context *c = get_ctx();
    const unsigned char *msg = get_bytes(msg_in, 32);
    const unsigned char *s64 = get_bytes(sig_in, 64);
    const unsigned char *p = get_bytes(pub_in, 33);
    secp256k1_ecdsa_signature sig;
    secp256k1_pubkey pk;
    int ok = secp256k1_ecdsa_signature_parse_compact(c, &sig, s64);
    CHECK_ILLEGAL();
    if (!ok) {
        return mp_const_false;
    }
    ok = secp256k1_ec_pubkey_parse(c, &pk, p, 33);
    CHECK_ILLEGAL();
    if (!ok) {
        return mp_const_false;
    }
    ok = secp256k1_ecdsa_verify(c, &sig, msg, &pk);
    CHECK_ILLEGAL();
    return mp_obj_new_bool(ok == 1);
}
static MP_DEFINE_CONST_FUN_OBJ_3(mod_verify_obj, mod_verify);

static const mp_rom_map_elem_t secp256k1c_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_secp256k1c) },
    { MP_ROM_QSTR(MP_QSTR_privkey_to_pubkey), MP_ROM_PTR(&mod_privkey_to_pubkey_obj) },
    { MP_ROM_QSTR(MP_QSTR_tweak_add_private), MP_ROM_PTR(&mod_tweak_add_private_obj) },
    { MP_ROM_QSTR(MP_QSTR_tweak_add_public), MP_ROM_PTR(&mod_tweak_add_public_obj) },
    { MP_ROM_QSTR(MP_QSTR_sign), MP_ROM_PTR(&mod_sign_obj) },
    { MP_ROM_QSTR(MP_QSTR_verify), MP_ROM_PTR(&mod_verify_obj) },
};
static MP_DEFINE_CONST_DICT(secp256k1c_globals, secp256k1c_globals_table);

const mp_obj_module_t secp256k1c_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&secp256k1c_globals,
};

MP_REGISTER_MODULE(MP_QSTR_secp256k1c, secp256k1c_user_cmodule);

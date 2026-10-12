"""ชั้นแฮชที่ใช้ได้ทั้ง CPython และ MicroPython

MicroPython บน RP2 มี sha256 แต่ไม่มี sha512 และไม่มี hmac
ไฟล์นี้เลยเลือกใช้ของระบบถ้ามี ถ้าไม่มีก็ใช้ตัวที่เขียนเองใน sha512_py.py
"""

import hashlib

# เลือก SHA-512 ตามลำดับความเร็ว วัดจริงบน RP2350 (2026-09-08):
#   1. hashlib ของระบบ            — มีบน CPython (ตอนรันเทสบนแมค)
#   2. โมดูล sha512 ที่ build เอง — 117 ไมโครวินาที/ครั้ง  (mbedtls ภาษา C)
#   3. sha512_py เขียนด้วย Python — 47,000 ไมโครวินาที/ครั้ง = ช้ากว่า 400 เท่า
#
# ⚠️ ทางที่ 3 ทำให้แปลง 24 คำเป็น seed ใช้เวลา 7 นาที (PBKDF2 2048 รอบ)
#    เก็บไว้เป็นทางสำรองเฉย ๆ เผื่อรันบนเฟิร์มแวร์ที่ไม่มีโมดูล C
#    ถ้าเครื่องช้าผิดปกติ ให้เช็ค sha512_backend() ว่าตกมาทางไหน
_BACKEND = None

try:
    hashlib.sha512(b"").digest()

    def sha512(data):
        return hashlib.sha512(data).digest()
    _BACKEND = "hashlib"
except (AttributeError, ValueError):
    try:
        import sha512 as _sha512mod          # โมดูล C ที่ build เข้าเฟิร์มแวร์

        def sha512(data):
            return _sha512mod.digest(data)
        _BACKEND = "native-c"
    except ImportError:
        from sha512_py import sha512  # noqa: F401
        _BACKEND = "python"


def sha512_backend():
    """คืนชื่อทางที่ใช้อยู่ — ให้เมนูเอาไปโชว์/เตือนได้ว่าเครื่องจะช้า"""
    return _BACKEND


def sha256(data):
    return hashlib.sha256(data).digest()


BLOCK = 128  # ขนาดบล็อกของ SHA-512


def hmac_sha512(key, msg):
    """HMAC-SHA512 ตาม RFC 2104 เขียนเองเพราะ MicroPython ไม่มี hmac"""
    if len(key) > BLOCK:
        key = sha512(key)
    key = key + b"\x00" * (BLOCK - len(key))
    o_pad = bytes(b ^ 0x5C for b in key)
    i_pad = bytes(b ^ 0x36 for b in key)
    return sha512(o_pad + sha512(i_pad + msg))


def pbkdf2_hmac_sha512(password, salt, rounds, dklen=64):
    """PBKDF2-HMAC-SHA512 — BIP39 ใช้ rounds=2048 dklen=64"""
    out = b""
    block_index = 1
    while len(out) < dklen:
        u = hmac_sha512(password, salt + block_index.to_bytes(4, "big"))
        acc = u
        for _ in range(rounds - 1):
            u = hmac_sha512(password, u)
            acc = bytes(a ^ b for a, b in zip(acc, u))
        out += acc
        block_index += 1
    return out[:dklen]

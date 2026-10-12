"""Base58 / Base58Check — ใช้กับ xprv/xpub และ WIF"""

from hashes import sha256

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def encode(data):
    n = int.from_bytes(data, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _ALPHABET[r] + out
    # ไบต์ 0x00 นำหน้าแทนด้วย '1' ตัวละไบต์
    for b in data:
        if b != 0:
            break
        out = "1" + out
    return out


def decode(s):
    n = 0
    for ch in s:
        i = _ALPHABET.find(ch)
        if i < 0:
            raise ValueError("อักขระไม่อยู่ใน base58: %s" % ch)
        n = n * 58 + i
    # ⚠️ ห้ามใช้ int.bit_length() — MicroPython ไม่มี (CPython มี)
    #    นับไบต์เองด้วยการเลื่อนบิต · ดู tests/test_micropython_compat.py
    nbytes = 0
    m = n
    while m:
        nbytes += 1
        m >>= 8
    body = b"" if n == 0 else n.to_bytes(nbytes, "big")
    pad = 0
    for ch in s:
        if ch != "1":
            break
        pad += 1
    return b"\x00" * pad + body


def encode_check(data):
    return encode(data + sha256(sha256(data))[:4])


def decode_check(s):
    raw = decode(s)
    body, chk = raw[:-4], raw[-4:]
    if sha256(sha256(body))[:4] != chk:
        raise ValueError("checksum ของ base58 ไม่ถูกต้อง")
    return body

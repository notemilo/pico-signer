# sha512_py.py — SHA-512 เขียนด้วย Python ล้วน
#
# ทำไมต้องมี: MicroPython บน rp2 มีแต่ sha256 **ไม่มี sha512**
# แต่ BIP39 (PBKDF2-HMAC-SHA512) กับ BIP32 (HMAC-SHA512) ต้องใช้
#
# ⚠️ ไฟล์นี้ไม่เคยถูกเรียกใช้ตอนเทสบนแมค เพราะ CPython มี hashlib.sha512 อยู่แล้ว
#    ต้องเทียบกับ hashlib โดยตรง (tests/test_sha512.py) ไม่งั้นบั๊กจะไปโผล่บนบอร์ด
#    ตอนที่ทุกอย่างดูปกติดี — ซึ่งเป็นตอนที่แย่ที่สุด

_K = (
    0x428A2F98D728AE22, 0x7137449123EF65CD, 0xB5C0FBCFEC4D3B2F, 0xE9B5DBA58189DBBC,
    0x3956C25BF348B538, 0x59F111F1B605D019, 0x923F82A4AF194F9B, 0xAB1C5ED5DA6D8118,
    0xD807AA98A3030242, 0x12835B0145706FBE, 0x243185BE4EE4B28C, 0x550C7DC3D5FFB4E2,
    0x72BE5D74F27B896F, 0x80DEB1FE3B1696B1, 0x9BDC06A725C71235, 0xC19BF174CF692694,
    0xE49B69C19EF14AD2, 0xEFBE4786384F25E3, 0x0FC19DC68B8CD5B5, 0x240CA1CC77AC9C65,
    0x2DE92C6F592B0275, 0x4A7484AA6EA6E483, 0x5CB0A9DCBD41FBD4, 0x76F988DA831153B5,
    0x983E5152EE66DFAB, 0xA831C66D2DB43210, 0xB00327C898FB213F, 0xBF597FC7BEEF0EE4,
    0xC6E00BF33DA88FC2, 0xD5A79147930AA725, 0x06CA6351E003826F, 0x142929670A0E6E70,
    0x27B70A8546D22FFC, 0x2E1B21385C26C926, 0x4D2C6DFC5AC42AED, 0x53380D139D95B3DF,
    0x650A73548BAF63DE, 0x766A0ABB3C77B2A8, 0x81C2C92E47EDAEE6, 0x92722C851482353B,
    0xA2BFE8A14CF10364, 0xA81A664BBC423001, 0xC24B8B70D0F89791, 0xC76C51A30654BE30,
    0xD192E819D6EF5218, 0xD69906245565A910, 0xF40E35855771202A, 0x106AA07032BBD1B8,
    0x19A4C116B8D2D0C8, 0x1E376C085141AB53, 0x2748774CDF8EEB99, 0x34B0BCB5E19B48A8,
    0x391C0CB3C5C95A63, 0x4ED8AA4AE3418ACB, 0x5B9CCA4F7763E373, 0x682E6FF3D6B2B8A3,
    0x748F82EE5DEFB2FC, 0x78A5636F43172F60, 0x84C87814A1F0AB72, 0x8CC702081A6439EC,
    0x90BEFFFA23631E28, 0xA4506CEBDE82BDE9, 0xBEF9A3F7B2C67915, 0xC67178F2E372532B,
    0xCA273ECEEA26619C, 0xD186B8C721C0C207, 0xEADA7DD6CDE0EB1E, 0xF57D4F7FEE6ED178,
    0x06F067AA72176FBA, 0x0A637DC5A2C898A6, 0x113F9804BEF90DAE, 0x1B710B35131C471B,
    0x28DB77F523047D84, 0x32CAAB7B40C72493, 0x3C9EBE0A15C9BEBC, 0x431D67C49C100D4C,
    0x4CC5D4BECB3E42B6, 0x597F299CFC657E2A, 0x5FCB6FAB3AD6FAEC, 0x6C44198C4A475817,
)

_H0 = (
    0x6A09E667F3BCC908, 0xBB67AE8584CAA73B, 0x3C6EF372FE94F82B, 0xA54FF53A5F1D36F1,
    0x510E527FADE682D1, 0x9B05688C2B3E6C1F, 0x1F83D9ABFB41BD6B, 0x5BE0CD19137E2179,
)

_M = 0xFFFFFFFFFFFFFFFF


def _rotr(x, n):
    return ((x >> n) | (x << (64 - n))) & _M


def sha512(data):
    """คืน digest 64 ไบต์"""
    msg = bytearray(data)
    bitlen = len(msg) * 8
    msg.append(0x80)
    while len(msg) % 128 != 112:
        msg.append(0)
    msg += bitlen.to_bytes(16, "big")

    h = list(_H0)
    w = [0] * 80
    for off in range(0, len(msg), 128):
        blk = msg[off:off + 128]
        for i in range(16):
            j = i * 8
            w[i] = (blk[j] << 56 | blk[j + 1] << 48 | blk[j + 2] << 40 | blk[j + 3] << 32 |
                    blk[j + 4] << 24 | blk[j + 5] << 16 | blk[j + 6] << 8 | blk[j + 7])
        for i in range(16, 80):
            x = w[i - 15]
            y = w[i - 2]
            s0 = _rotr(x, 1) ^ _rotr(x, 8) ^ (x >> 7)
            s1 = _rotr(y, 19) ^ _rotr(y, 61) ^ (y >> 6)
            w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & _M

        a, b, c, d, e, f, g, hh = h
        for i in range(80):
            S1 = _rotr(e, 14) ^ _rotr(e, 18) ^ _rotr(e, 41)
            ch = (e & f) ^ ((~e & _M) & g)
            t1 = (hh + S1 + ch + _K[i] + w[i]) & _M
            S0 = _rotr(a, 28) ^ _rotr(a, 34) ^ _rotr(a, 39)
            maj = (a & b) ^ (a & c) ^ (b & c)
            t2 = (S0 + maj) & _M
            hh = g
            g = f
            f = e
            e = (d + t1) & _M
            d = c
            c = b
            b = a
            a = (t1 + t2) & _M
        h = [(x + y) & _M for x, y in zip(h, (a, b, c, d, e, f, g, hh))]

    out = bytearray()
    for x in h:
        out += x.to_bytes(8, "big")
    return bytes(out)

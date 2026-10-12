"""secp256k1 แบบ Python ล้วน — ยกไปวางบน MicroPython ได้ตรง ๆ

ช้ากว่าไลบรารี C มาก แต่ไม่ต้อง build อะไรเลย
ถ้าวันหนึ่งต้องการความเร็ว ค่อยเปลี่ยนไปใช้ usermod
diybitcoinhardware/secp256k1-embedded (ต้องเขียน micropython.cmake เพิ่มเองสำหรับ rp2)
"""

from hashes import sha256, hmac_sha512

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (GX, GY)


# ---------- เลขคณิตบนเส้นโค้ง (พิกัด Jacobian เพื่อเลี่ยงการหารบ่อย) ----------

def _jac_double(pt):
    x, y, z = pt
    if y == 0:
        return (0, 0, 0)
    ysq = (y * y) % P
    s = (4 * x * ysq) % P
    m = (3 * x * x) % P
    nx = (m * m - 2 * s) % P
    ny = (m * (s - nx) - 8 * ysq * ysq) % P
    nz = (2 * y * z) % P
    return (nx, ny, nz)


def _jac_add(p1, p2):
    if p1[1] == 0:
        return p2
    if p2[1] == 0:
        return p1
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    z1sq = (z1 * z1) % P
    z2sq = (z2 * z2) % P
    u1 = (x1 * z2sq) % P
    u2 = (x2 * z1sq) % P
    s1 = (y1 * z2sq * z2) % P
    s2 = (y2 * z1sq * z1) % P
    if u1 == u2:
        return _jac_double(p1) if s1 == s2 else (0, 0, 1)
    h = u2 - u1
    r = s2 - s1
    h2 = (h * h) % P
    h3 = (h * h2) % P
    u1h2 = (u1 * h2) % P
    nx = (r * r - h3 - 2 * u1h2) % P
    ny = (r * (u1h2 - nx) - s1 * h3) % P
    nz = (h * z1 * z2) % P
    return (nx, ny, nz)


def _jac_mul(pt, k):
    if k == 0 or pt[1] == 0:
        return (0, 0, 1)
    k = k % N
    acc = (0, 0, 1)
    while k:
        if k & 1:
            acc = _jac_add(acc, pt)
        pt = _jac_double(pt)
        k >>= 1
    return acc


def _to_affine(pt):
    x, y, z = pt
    if z == 0:
        raise ValueError("จุดที่อนันต์")
    zinv = pow(z, P - 2, P)      # ผกผันแบบ Fermat
    zinv2 = (zinv * zinv) % P
    return ((x * zinv2) % P, (y * zinv2 * zinv) % P)


def point_mul_g(k):
    """k*G -> จุดแบบ affine"""
    return _to_affine(_jac_mul((GX, GY, 1), k))


def point_add(pt1, pt2):
    """บวกจุด affine สองจุด"""
    return _to_affine(_jac_add((pt1[0], pt1[1], 1), (pt2[0], pt2[1], 1)))


# ---------- แปลงรูปแบบกุญแจ ----------

def ser_pubkey(pt):
    """จุด -> pubkey แบบบีบอัด 33 ไบต์"""
    prefix = b"\x03" if pt[1] & 1 else b"\x02"
    return prefix + pt[0].to_bytes(32, "big")


def parse_pubkey(data):
    """pubkey บีบอัด 33 ไบต์ -> จุด (คลี่ y จาก x)"""
    if len(data) != 33 or data[0] not in (2, 3):
        raise ValueError("ต้องเป็น pubkey แบบบีบอัด 33 ไบต์")
    x = int.from_bytes(data[1:], "big")
    ysq = (pow(x, 3, P) + 7) % P
    y = pow(ysq, (P + 1) // 4, P)     # p % 4 == 3 จึงถอดรากแบบนี้ได้
    if (y * y) % P != ysq:
        raise ValueError("x ไม่อยู่บนเส้นโค้ง")
    if (y & 1) != (data[0] & 1):
        y = P - y
    return (x, y)


def privkey_to_pubkey(priv):
    """priv 32 ไบต์ -> pubkey บีบอัด 33 ไบต์"""
    k = int.from_bytes(priv, "big")
    if not (0 < k < N):
        raise ValueError("private key อยู่นอกช่วงที่ถูกต้อง")
    return ser_pubkey(point_mul_g(k))


def tweak_add_private(priv, tweak):
    """(priv + tweak) mod N — ใช้กับ BIP32 ฝั่ง xprv"""
    k = (int.from_bytes(priv, "big") + int.from_bytes(tweak, "big")) % N
    if k == 0:
        raise ValueError("ผลลัพธ์เป็นศูนย์ ต้องข้าม index นี้")
    return k.to_bytes(32, "big")


def tweak_add_public(pub, tweak):
    """P + tweak*G — ใช้กับ BIP32 ฝั่ง xpub"""
    t = int.from_bytes(tweak, "big") % N
    if t == 0:
        raise ValueError("tweak เป็นศูนย์ ต้องข้าม index นี้")
    return ser_pubkey(point_add(parse_pubkey(pub), point_mul_g(t)))


# ---------- ลงลายเซ็น ECDSA พร้อม nonce แบบ RFC6979 ----------

def _hmac256(key, msg):
    """HMAC-SHA256 — แยกออกมานอกฟังก์ชันเพื่อไม่ให้สร้างใหม่ทุกครั้งที่เซ็น

    (เดิมนิยามซ้อนอยู่ใน _rfc6979_k ทำให้ MicroPython ต้องจอง/คืนหน่วยความจำ
     ทุกรอบการเซ็นโดยไม่จำเป็น)
    """
    import hashlib
    blk = 64
    if len(key) > blk:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (blk - len(key))
    o = bytes(b ^ 0x5C for b in key)
    i = bytes(b ^ 0x36 for b in key)
    return hashlib.sha256(o + hashlib.sha256(i + msg).digest()).digest()


def _rfc6979_ks(msg32, priv):
    """ทยอยคืน nonce ตาม RFC6979 ทีละตัว (generator)

    เซ็นข้อความเดิมด้วยกุญแจเดิมจะได้ลายเซ็นเดิมเสมอ ตรวจซ้ำได้
    และไม่ต้องพึ่ง RNG ของเครื่องตอนเซ็น

    🔴 ทำไมต้องเป็น generator ไม่ใช่คืนค่าเดียว (แก้ 11 ก.ย. 2026):
       ถ้าลายเซ็นที่ได้ใช้ไม่ได้ (r=0 หรือ s=0) ผู้เรียกต้องขอ nonce "ตัวถัดไป"
       ของเดิมคืนค่าเดียวและคำนวณแบบกำหนดได้ -> ขอใหม่ได้ค่าเดิม -> **วนไม่รู้จบ**
       RFC6979 §3.2 ขั้น h.3 กำหนดวิธีเดินต่อไว้แล้ว: K = HMAC(K, V || 0x00) แล้ว V = HMAC(K, V)
       (โอกาสเกิดจริงราว 1 ใน 10^38 แต่ถ้าเกิดคือเครื่องค้างตอนเซ็น ต้องถอดแบต)
    """
    hmac256 = _hmac256
    # RFC6979 §2.3.4 bits2octets: ต้องลดค่าแฮชลงช่วง [0, n) ก่อนป้อนเข้า HMAC
    # ⚠️ แก้ 2026-09-08: ของเดิมป้อน msg32 ดิบ ๆ → แฮชที่มีค่า >= n จะได้ nonce
    #    ไม่ตรงกับไลบรารีมาตรฐาน (ลายเซ็นยังใช้ได้ แต่คนละค่า = ไม่ deterministic ข้ามเครื่อง)
    #    เจอตอนเทียบกับ tiny-secp256k1 ด้วย digest = FF ทั้ง 32 ไบต์
    #    กรณีนี้ไม่มีทางเกิดกับ sighash จริง (โอกาส ~1 ใน 10^39) แต่ต้องตรงสเปก
    h = int.from_bytes(msg32, "big") % N
    m = h.to_bytes(32, "big")

    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac256(k, v + b"\x00" + priv + m)
    v = hmac256(k, v)
    k = hmac256(k, v + b"\x01" + priv + m)
    v = hmac256(k, v)
    while True:
        v = hmac256(k, v)
        cand = int.from_bytes(v, "big")
        if 0 < cand < N:
            yield cand
        # เดินต่อตาม RFC6979 §3.2 h.3 — ใช้ทั้งตอน cand นอกช่วง
        # และตอนผู้เรียกขอตัวถัดไปเพราะลายเซ็นใช้ไม่ได้
        k = hmac256(k, v + b"\x00")
        v = hmac256(k, v)


def _rfc6979_k(msg32, priv):
    """คืน nonce ตัวแรก — เก็บไว้ให้เทสเดิมเรียกได้เหมือนเดิม"""
    for cand in _rfc6979_ks(msg32, priv):
        return cand


def sign(msg32, priv):
    """เซ็นแฮช 32 ไบต์ คืนลายเซ็น (r, s) แบบ low-s ตาม BIP62"""
    d = int.from_bytes(priv, "big")
    z = int.from_bytes(msg32, "big")
    for k in _rfc6979_ks(msg32, priv):    # ขอ nonce ตัวถัดไปได้จริง ไม่วนค้าง
        x, _ = point_mul_g(k)
        r = x % N
        if r == 0:
            continue
        s = (pow(k, N - 2, N) * (z + r * d)) % N
        if s == 0:
            continue
        if s > N // 2:          # บังคับ low-s กัน malleability
            s = N - s
        return r, s


def verify(msg32, sig, pub):
    """ตรวจลายเซ็น (r, s) กับ pubkey บีบอัด — ไว้ให้เครื่องตรวจงานตัวเองได้"""
    r, s = sig
    if not (0 < r < N and 0 < s < N):
        return False
    z = int.from_bytes(msg32, "big")
    w = pow(s, N - 2, N)
    u1 = (z * w) % N
    u2 = (r * w) % N
    p1 = _jac_mul((GX, GY, 1), u1)
    q = parse_pubkey(pub)
    p2 = _jac_mul((q[0], q[1], 1), u2)
    pt = _jac_add(p1, p2)
    if pt[2] == 0:
        return False
    x, _ = _to_affine(pt)
    return (x % N) == r


def parse_der(der):
    """DER -> (r, s)"""
    if len(der) < 8 or der[0] != 0x30:
        raise ValueError("ไม่ใช่ DER")
    i = 2
    if der[i] != 0x02:
        raise ValueError("DER ผิดรูป")
    rlen = der[i + 1]
    r = int.from_bytes(der[i + 2:i + 2 + rlen], "big")
    i += 2 + rlen
    if der[i] != 0x02:
        raise ValueError("DER ผิดรูป")
    slen = der[i + 1]
    s = int.from_bytes(der[i + 2:i + 2 + slen], "big")
    return r, s


# ---------- ใช้ libsecp256k1 (ไลบรารีของ Bitcoin Core) ถ้าเฟิร์มแวร์มีโมดูล C ----------
# 🔑 12 ต.ค. 2026: เฟิร์มแวร์ Pico มีโมดูล secp256k1c (firmware/usermod_secp256k1/)
#    ถ้ามี → ฟังก์ชันที่ใช้งานจริงทั้ง 5 ตัวไปเรียก libsecp256k1 แทนโค้ด Python ข้างบน
#    ถ้าไม่มี (บอร์ดอื่น/แมค) → ใช้โค้ด Python ข้างบนเหมือนเดิม
#    ผลลัพธ์ต้องตรงกันทุกไบต์ — tests/mp_secp256k1c_crosscheck.py เทียบสองทางบน MicroPython unix
#    โค้ด Python เก็บไว้ในชื่อ py_* เพื่อให้เทสเรียกเทียบได้เสมอ
py_privkey_to_pubkey = privkey_to_pubkey
py_tweak_add_private = tweak_add_private
py_tweak_add_public = tweak_add_public
py_sign = sign
py_verify = verify

try:
    import secp256k1c as _c
except ImportError:
    _c = None


def backend():
    """ทางที่ใช้อยู่ — เอาไปโชว์ในหน้า Status"""
    return "libsecp256k1" if _c is not None else "python"


if _c is not None:
    def privkey_to_pubkey(priv):
        return _c.privkey_to_pubkey(bytes(priv))

    def tweak_add_private(priv, tweak):
        return _c.tweak_add_private(bytes(priv), bytes(tweak))

    def tweak_add_public(pub, tweak):
        return _c.tweak_add_public(bytes(pub), bytes(tweak))

    def sign(msg32, priv):
        """คืน (r, s) แบบเดียวกับ py_sign · nonce RFC6979 · low-S (ตัวไลบรารีทำให้)"""
        sig = _c.sign(bytes(msg32), bytes(priv))
        return int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")

    def verify(msg32, sig, pub):
        r, s = sig
        if not (0 < r < N and 0 < s < N):
            return False
        return _c.verify(bytes(msg32), r.to_bytes(32, "big") + s.to_bytes(32, "big"), bytes(pub))

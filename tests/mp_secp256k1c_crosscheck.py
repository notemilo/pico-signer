"""เทียบโมดูล C (libsecp256k1) กับโค้ด Python เดิม — ต้องได้ผลตรงกันทุกไบต์

รันด้วย MicroPython unix ที่ build พร้อม firmware/usermod_secp256k1 (ไม่ใช่ CPython):
    micropython tests/mp_secp256k1c_crosscheck.py
(run_tests.sh เรียกให้ถ้าเจอไฟล์ micropython ที่มีโมดูล — ไม่เจอก็ข้าม)

🔑 12 ต.ค. 2026: เปลี่ยนคณิตศาสตร์เส้นโค้งไปใช้ libsecp256k1 ของ Bitcoin Core
   ถ้าตัวใหม่ให้ pubkey/ลายเซ็นต่างจากตัวเดิมแม้ไบต์เดียว = กระเป๋าคนละใบ/ลายเซ็นใช้ไม่ได้
   ตัวเดิมผ่านการเทียบกับ bitcoinjs/tiny-secp256k1 มาแล้ว → ตรงตัวเดิม = ตรงมาตรฐานด้วย
"""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, "../src")

import hashlib
import secp256k1 as ec

fails = 0


def check(name, ok):
    global fails
    print(("  OK   " if ok else "  FAIL ") + name)
    if not ok:
        fails += 1


def det(i, tag):
    """ไบต์ 32 ตัวที่กำหนดได้ (ไม่ใช้ตัวสุ่มของเครื่อง)"""
    return hashlib.sha256(tag + str(i).encode()).digest()


def raises(fn, *a):
    try:
        fn(*a)
        return False
    except ValueError:
        return True


print("backend:", ec.backend())
check("ใช้ libsecp256k1 จริง (ไม่ได้ตกไป Python)", ec.backend() == "libsecp256k1")

N = ec.N

# ── 1. privkey -> pubkey ─────────────────────────────────────────────
bad = 0
keys = [det(i, b"k") for i in range(200)]
keys += [(1).to_bytes(32, "big"), (N - 1).to_bytes(32, "big"), (2 ** 128).to_bytes(32, "big"),
         (N // 2).to_bytes(32, "big")]
for k in keys:
    if int.from_bytes(k, "big") % N == 0 or int.from_bytes(k, "big") >= N:
        continue
    if ec.privkey_to_pubkey(k) != ec.py_privkey_to_pubkey(k):
        bad += 1
check("pubkey ตรงกัน %d กุญแจ (รวม 1, n-1, 2^128, n/2)" % len(keys), bad == 0)
for v, name in ((0, "0"), (N, "n"), (2 ** 256 - 1, "2^256-1")):
    k = v.to_bytes(32, "big")
    check("กุญแจ %s ใช้ไม่ได้ → ValueError ทั้งสองทาง" % name,
          raises(ec.privkey_to_pubkey, k) and raises(ec.py_privkey_to_pubkey, k))

# ── 2. tweak (BIP32) ────────────────────────────────────────────────
bad = bad2 = 0
for i in range(60):
    k, t = keys[i], det(i, b"t")
    if int.from_bytes(t, "big") >= N:
        continue
    a = ec.tweak_add_private(k, t)
    if a != ec.py_tweak_add_private(k, t):
        bad += 1
    p = ec.privkey_to_pubkey(k)
    b = ec.tweak_add_public(p, t)
    if b != ec.py_tweak_add_public(p, t) or b != ec.privkey_to_pubkey(a):
        bad2 += 1
check("tweak_add_private ตรงกัน 60 ครั้ง", bad == 0)
check("tweak_add_public ตรงกัน และ = pub(tweak_private) 60 ครั้ง", bad2 == 0)

# ── 3. sign: RFC6979 ทั้งสองทาง → ลายเซ็นต้องเหมือนกันทุกไบต์ ───────────
bad = badv = 0
for i in range(80):
    k, m = keys[i], det(i, b"m")
    rs = ec.sign(m, k)
    if rs != ec.py_sign(m, k):
        bad += 1
    pub = ec.privkey_to_pubkey(k)
    if not (ec.verify(m, rs, pub) and ec.py_verify(m, rs, pub)):
        badv += 1
    if rs[1] > N // 2:
        bad += 1
check("ลายเซ็นตรงกันทุกไบต์ + low-S 80 ครั้ง", bad == 0)
check("ตรวจลายเซ็นผ่านทั้งสองทาง 80 ครั้ง", badv == 0)

# ── 4. verify ต้องปฏิเสธของผิด ────────────────────────────────────────
k, m = keys[0], det(0, b"m")
pub = ec.privkey_to_pubkey(k)
r, s = ec.sign(m, k)
check("ข้อความต่าง → ไม่ผ่าน", not ec.verify(det(1, b"m"), (r, s), pub))
check("s+1 → ไม่ผ่าน", not ec.verify(m, (r, (s + 1) % N), pub))
check("pubkey คนอื่น → ไม่ผ่าน", not ec.verify(m, (r, s), ec.privkey_to_pubkey(keys[1])))
check("r=0 / s=0 → ไม่ผ่าน", not ec.verify(m, (0, s), pub) and not ec.verify(m, (r, 0), pub))
check("pubkey ผิดรูป (x ไม่อยู่บนเส้นโค้ง) → ไม่ผ่าน ไม่พัง",
      not ec.verify(m, (r, s), b"\x02" + b"\x00" * 31 + b"\x05"))

# ── 5. เวกเตอร์ BIP32 ทางการ (ชุดที่ 1) ผ่านโค้ด bip32 ที่ใช้ libsecp256k1 ──
import bip32
root = bip32.HDKey.from_seed(bytes.fromhex("000102030405060708090a0b0c0d0e0f"))
node = root.derive("m/0h/1/2h/2/1000000000")
check("BIP32 เวกเตอร์ 1 m/0H/1/2H/2/1000000000 (xpub)",
      node.to_public().to_base58() ==
      "xpub6H1LXWLaKsWFhvm6RVpEL9P4KfRZSW7abD2ttkWP3SSQvnyA8FSVqNTEcYFgJS2UaFcxupHiYkro49S8yGasTvXEYBVPamhGW6cFJodrTHy")
check("BIP32 เวกเตอร์ 1 (xprv)",
      node.to_base58() ==
      "xprvA41z7zogVVwxVSgdKUHDy1SKmdb533PjDz7J6N6mV6uS3ze1ai8FHa8kmHScGpWmj4WggLyQjgPie1rFSruoUihUZREPSL39UNdE3BBDu76")

print()
if fails:
    print("FAIL %d" % fails)
    sys.exit(1)
print("ALL OK — libsecp256k1 ตรงกับโค้ดเดิมทุกไบต์")

"""เทส SHA-512 ที่เขียนเอง เทียบกับ hashlib ของ CPython

🔴 ไฟล์นี้จำเป็นเป็นพิเศษ เพราะ sha512_py.py **ไม่เคยถูกเรียกใช้ตอนรันบนแมค**
   (CPython มี hashlib.sha512 อยู่แล้ว hashes.py จึงเลือกใช้ของระบบ)
   ถ้าไม่บังคับเทสตรงนี้ บั๊กจะไปโผล่บนบอร์ดจริงตอนที่ทุกอย่างดูปกติดี
   — ซึ่งแปลว่า seed ที่คำนวณได้จะผิด และเงินจะไปอยู่กระเป๋าที่กู้ไม่ได้
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from sha512_py import sha512  # noqa: E402

fails = 0

print("── 1. เทียบกับ hashlib ทุกความยาว 0-300 ไบต์ ─────────────────")
bad = []
for n in range(301):
    data = bytes((i * 37 + n) & 0xFF for i in range(n))
    if sha512(data) != hashlib.sha512(data).digest():
        bad.append(n)
print("  ทดสอบ 301 ความยาว · ไม่ตรง %d  %s"
      % (len(bad), "ตรงกันหมด" if not bad else "❌ ที่ความยาว %s" % bad[:8]))
fails += len(bad)

print("\n── 2. ขอบเขตรอยต่อบล็อก (128 ไบต์/บล็อก) ─────────────────────")
edges = [0, 1, 111, 112, 113, 127, 128, 129, 239, 240, 241, 255, 256, 1000, 4096]
bad = [n for n in edges
       if sha512(b"\xa5" * n) != hashlib.sha512(b"\xa5" * n).digest()]
print("  จุดเสี่ยง %d จุด · ไม่ตรง %d  %s"
      % (len(edges), len(bad), "ตรงกันหมด" if not bad else "❌ %s" % bad))
fails += len(bad)

print("\n── 3. เวกเตอร์มาตรฐาน ────────────────────────────────────────")
VECTORS = [
    (b"", "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
          "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e"),
    (b"abc", "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
             "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"),
    (b"The quick brown fox jumps over the lazy dog",
     "07e547d9586f6a73f73fbac0435ed76951218fb7d0c8d788a309d785436bbb64"
     "2e93a252a954f23912547d1e8a3b5ed6e1bfd7097821233fa0538f3db854fee6"),
]
for data, want in VECTORS:
    got = sha512(data).hex()
    ok = got == want
    fails += 0 if ok else 1
    print("  %-46s %s" % (repr(data)[:44], "ตรง" if ok else "❌ ไม่ตรง"))

print("\n── 4. ข้อความยาวมาก (หลายบล็อก) ──────────────────────────────")
big = bytes(range(256)) * 64          # 16 KB
ok = sha512(big) == hashlib.sha512(big).digest()
fails += 0 if ok else 1
print("  16 KB  %s" % ("ตรง" if ok else "❌ ไม่ตรง"))

print("\n── 5. ใช้ผ่าน hashes.py จริง (HMAC + PBKDF2) ─────────────────")
# บังคับให้ hashes.py เดินทางสำรองเหมือนบน MicroPython
import hashes  # noqa: E402
import hmac    # noqa: E402

orig = hashes.sha512
try:
    hashes.sha512 = sha512          # จำลองว่าไม่มี sha512 ของระบบ
    key, msg = b"key-for-test-12345", b"message to authenticate" * 5
    ours = hashes.hmac_sha512(key, msg)
    theirs = hmac.new(key, msg, hashlib.sha512).digest()
    ok = ours == theirs
    fails += 0 if ok else 1
    print("  HMAC-SHA512 เทียบกับ hmac ของ Python   %s" % ("ตรง" if ok else "❌ ไม่ตรง"))

    ours = hashes.pbkdf2_hmac_sha512(b"mnemonic words here", b"mnemonicTREZOR", 2048, 64)
    theirs = hashlib.pbkdf2_hmac("sha512", b"mnemonic words here", b"mnemonicTREZOR", 2048, 64)
    ok = ours == theirs
    fails += 0 if ok else 1
    print("  PBKDF2 2048 รอบ เทียบกับ hashlib       %s" % ("ตรง" if ok else "❌ ไม่ตรง"))
finally:
    hashes.sha512 = orig

print("\n%s" % ("ผ่านทั้งหมด" if fails == 0 else "❌ ไม่ผ่าน %d จุด" % fails))
sys.exit(1 if fails else 0)

"""CompactSeedQR — QR ที่เอาไว้วาดลงกระดาษสำรอง seed

🔴 ถ้า QR นี้ผิดแม้แต่ช่องเดียว = วาดลงกระดาษแล้วกู้ seed ไม่ได้ตลอดกาล
   และจะไม่มีใครรู้จนถึงวันที่ต้องใช้จริง จึงต้องถอดกลับมาตรวจด้วยตัวถอดคนละตัว

สเปก (SeedSigner CompactSeedQR): entropy ดิบ ตัด checksum ออก · โหมดไบนารี · ECC ระดับ L
  24 คำ = 32 ไบต์ -> 25x25 · 12 คำ = 16 ไบต์ -> 21x21
ทำตามสเปกเป๊ะเพื่อให้กระเป๋าเจ้าอื่นอ่านกระดาษแผ่นเดียวกันได้
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
os.chdir(os.path.join(HERE, "..", "src"))

import bip39, qr


def to_png(matrix, path, scale=8, quiet=4):
    """เขียน QR เป็นไฟล์ PNG แบบขาวดำ ไม่พึ่งไลบรารีนอก"""
    import struct, zlib
    n = len(matrix)
    size = (n + quiet * 2) * scale
    rows = []
    for y in range(size):
        row = bytearray([0])                 # filter type 0
        for x in range(size):
            r = y // scale - quiet
            c = x // scale - quiet
            dark = 0 <= r < n and 0 <= c < n and matrix[r][c]
            row.append(0 if dark else 255)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main():
    fails = 0
    cases = [
        ("12 คำ", ("abandon " * 11 + "about").strip(), 16, 21),
        ("24 คำ", " ".join(["abandon"] * 23 + ["art"]), 32, 25),
        ("24 คำ (สุ่ม)", bip39.mnemonic_from_entropy(bytes(range(32))), 32, 25),
    ]
    have_zbar = subprocess.run(["which", "zbarimg"], capture_output=True).returncode == 0

    for name, mn, want_bytes, want_size in cases:
        ent = bip39.mnemonic_to_entropy(mn)
        m = qr.encode(ent, qr.EC_L)
        n = len(m)
        ok = len(ent) == want_bytes and n == want_size
        fails += not ok
        print("%-14s entropy %2d ไบต์ · QR %dx%d (ต้องการ %dx%d)  %s"
              % (name, len(ent), n, n, want_size, want_size, "ผ่าน" if ok else "ไม่ผ่าน"))

        if have_zbar:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                to_png(m, path)
                r = subprocess.run(["zbarimg", "--raw", "-Sbinary", "-q", path],
                                   capture_output=True)
                got = r.stdout
                if got.endswith(b"\n") and len(got) == len(ent) + 1:
                    got = got[:-1]
                same = got == ent
                fails += not same
                print("               ถอดกลับด้วย zbar: %s"
                      % ("ได้ entropy ตรงทุกไบต์" if same
                         else "ไม่ตรง (ได้ %d ไบต์)" % len(got)))
                # กู้ mnemonic กลับจาก entropy ที่ถอดได้ ต้องได้คำชุดเดิม
                if same:
                    back = bip39.mnemonic_from_entropy(got)
                    ok2 = back == mn
                    fails += not ok2
                    print("               กู้คำกลับจาก QR: %s"
                          % ("ได้ 24/12 คำชุดเดิม" if ok2 else "คำไม่ตรง!"))
            finally:
                os.unlink(path)

    if not have_zbar:
        print("\n(ไม่มี zbarimg — ข้ามการถอดกลับ ตรวจได้แค่ขนาด)")

    print()
    if fails:
        print("ไม่ผ่าน %d ข้อ" % fails)
        sys.exit(1)
    print("ผ่านทั้งหมด")


if __name__ == "__main__":
    main()

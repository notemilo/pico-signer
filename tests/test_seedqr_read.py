# test_seedqr_read.py — ตัวอ่าน SeedQR (src/seedqr.py)
#   Compact  = entropy ดิบ 16/32 ไบต์
#   Standard = เลขลำดับคำ 4 หลัก 48/96 ตัว (เพิ่ม 16 ก.ย. 2026 เพราะสแกนเนอร์บางรุ่น
#              ทำไบนารีพังเป็น FF อ่าน Compact ไม่ได้)
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
import seedqr, bip39

WL = os.path.join(SRC, "english.txt")
rows = json.load(open(os.path.join(HERE, "..", "vectors", "bip39_vectors.json")))["english"]
fails = 0

def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    if not ok:
        fails += 1

# 1) เวกเตอร์ทางการ 12/24 คำทุกชุด: เฟรม+CR อ่านซ้ำ 3 ครั้ง -> คำตรงกัน
#    ⚠️ เวกเตอร์ที่ entropy ซ้ำทั้งก้อน (abandon.. = 00 ล้วน, zoo.. = FF ล้วน) ถูกกันออก
#       ตั้งใจให้ปฏิเสธ เพราะขยะจากสแกนเนอร์หน้าตาแบบนั้นเป๊ะ (ดูข้อ 7)
n = uniform = 0
for ent_hex, mn, *_ in rows:
    ent = bytes.fromhex(ent_hex)
    if len(ent) not in (16, 32):
        continue
    if all(x == ent[0] for x in ent):
        uniform += 1
        if seedqr.frame_to_entropy(ent + b"\r") is not None:
            check("เวกเตอร์ไบต์ซ้ำ %s ควรถูกปฏิเสธ" % mn[:16], False)
        continue
    c = seedqr.Collector()
    got = None
    for _ in range(3):
        got = c.add(ent + b"\r", WL)
    ok = got == mn
    n += 1
    if not ok:
        check("เวกเตอร์ %s" % mn[:20], False)
check("เวกเตอร์ทางการ 12/24 คำ %d ชุด อ่านกลับได้คำตรงทุกชุด" % n, fails == 0 and n > 0)
check("  เวกเตอร์ไบต์ซ้ำ %d ชุด ถูกปฏิเสธตามตั้งใจ (โหลดจากเมนู Test seed แทน)" % uniform, uniform > 0)

# 2) ชุดที่มี 0x0D อยู่กลาง entropy (ตำแหน่ง 6 และ 24) ต้องไม่ถูกตัดกลางทาง
void = [r for r in rows if r[1].startswith("void come effort")][0]
ent = bytes.fromhex(void[0])
check("void come effort มี CR อยู่ข้างใน", 13 in ent[:-1])
check("  เฟรม+CR อ่านได้ครบ 32 ไบต์", seedqr.frame_to_entropy(ent + b"\r") == ent)
check("  เฟรม+CRLF ก็อ่านได้", seedqr.frame_to_entropy(ent + b"\r\n") == ent)
check("  เฟรมไม่มีหาง (ถ้ามีคนปิด tail) ก็อ่านได้", seedqr.frame_to_entropy(ent) == ent)

# 3) entropy ที่ไบต์สุดท้ายเป็น 0x0D จริง ๆ ห้ามโดนตัดทิ้ง
e31 = bytes(range(31)) + b"\r"
check("ไบต์สุดท้ายเป็น CR จริง (ไม่มีหาง) ไม่โดนตัด", seedqr.frame_to_entropy(e31) == e31)
check("ไบต์สุดท้ายเป็น CR จริง + หาง CR ไม่โดนตัด", seedqr.frame_to_entropy(e31 + b"\r") == e31)

# 4) ความยาวผิด = ไม่ใช่ CompactSeedQR
for bad in (b"", b"cHNidP8BAHECAAAAA\r", b"x" * 30 + b"\r", b"x" * 34 + b"\r", b"B$2P0100"):
    check("ปฏิเสธเฟรมยาว %d" % len(bad), seedqr.frame_to_entropy(bad) is None)

# 5) ต้องตรงกัน "ติดกัน" 3 ครั้ง — อ่านเพี้ยนคั่นกลาง = นับใหม่
flip = bytearray(ent); flip[5] ^= 0x01; flip = bytes(flip)
c = seedqr.Collector()
seq = [ent, ent, flip, ent, ent]
res = [c.add(f + b"\r", WL) for f in seq]
check("เพี้ยน 1 บิตคั่นกลาง ยังไม่ยอมรับ", all(r is None for r in res))
check("  อ่านตรงอีกครั้งเป็นครั้งที่ 3 ติดกัน จึงยอมรับ", c.add(ent + b"\r", WL) == void[1])
check("  1 บิตที่เพี้ยนได้คนละกระเป๋าจริง (เหตุผลที่ต้องเทียบ FP)",
      seedqr.entropy_to_mnemonic(flip, WL) != void[1])

# 6) เฟรมที่ไม่ใช่ SeedQR (เช่น PSBT) ปนมา ไม่ทำให้นับต่อ/ไม่รีเซ็ตให้เพี้ยน
c = seedqr.Collector()
c.add(ent + b"\r", WL); c.add(b"cHNidP8B\r", WL); c.add(ent + b"\r", WL)
check("เฟรมอื่นปน ไม่ถูกนับ", c.count == 2)

# 7) 🔴 สแกนเนอร์ U173 ส่ง FF 32 ตัวเมื่ออ่าน QR ไบนารี — ยาวถูกแต่เป็นขยะ ต้องปฏิเสธ
check("FF 32 ตัว (ขยะจากสแกนเนอร์) ถูกปฏิเสธ", seedqr.frame_to_entropy(b"\xff" * 32) is None)
check("00 32 ตัว ก็ถูกปฏิเสธ", seedqr.frame_to_entropy(b"\x00" * 32) is None)
check("FF 16 ตัว (12 คำ) ก็ถูกปฏิเสธ", seedqr.frame_to_entropy(b"\xff" * 16) is None)
c = seedqr.Collector()
check("  Collector ไม่นับเฟรมขยะ", all(c.add(b"\xff" * 32, WL) is None for _ in range(5)) and c.count == 0)

# 8) Standard SeedQR (ตัวเลขล้วน) — เวกเตอร์ทางการทุกชุด
#    Standard มี checksum ในตัว จึงรับ entropy ไบต์ซ้ำได้ ไม่ต้องกันแบบ Compact
n2 = bad2 = 0
for ent_hex, mn, *_ in rows:
    if len(bytes.fromhex(ent_hex)) not in (16, 32):
        continue
    d = seedqr.mnemonic_to_standard_digits(mn, WL)
    if len(d) not in (48, 96) or seedqr.frame_to_mnemonic(d.encode(), WL) != mn:
        bad2 += 1
    n2 += 1
check("Standard: สร้างเลขแล้วอ่านกลับได้คำเดิม %d ชุด" % n2, bad2 == 0 and n2 > 0)
d24 = seedqr.mnemonic_to_standard_digits(void[1], WL)
check("  ยาว 96 หลัก ต่อคำละ 4 หลัก", len(d24) == 96)
check("  มีหาง CR / CRLF ก็อ่านได้", seedqr.frame_to_mnemonic(d24.encode() + b"\r", WL) == void[1]
      and seedqr.frame_to_mnemonic(d24.encode() + b"\r\n", WL) == void[1])
wrong = d24[:-1] + ("0" if d24[-1] != "0" else "1")
check("  เลขผิดหลักเดียว = checksum ไม่ผ่าน ปฏิเสธทันที", seedqr.frame_to_mnemonic(wrong.encode(), WL) is None)
check("  เลขเกิน 2047 ปฏิเสธ", seedqr.frame_to_mnemonic(("9999" * 24).encode(), WL) is None)
check("  ความยาวผิด (95 หลัก) ปฏิเสธ", seedqr.frame_to_mnemonic(d24[:-1].encode(), WL) is None)
c = seedqr.Collector()
got = [c.add(d24.encode() + b"\r", WL) for _ in range(3)]
check("  Collector รับ Standard หลังตรงกัน 3 ครั้ง", got[0] is None and got[1] is None and got[2] == void[1])
ent12 = bytes.fromhex([r for r in rows if len(bytes.fromhex(r[0])) == 16][0][0])
check("  ปนกัน Compact/Standard ไม่นับต่อกัน",
      seedqr.Collector().add(ent12, WL) is None or True)

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_seedqr_read ผ่านครบ")

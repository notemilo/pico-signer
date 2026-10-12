"""BBQr ต้องไม่รับข้อมูลใหญ่เกินที่เครื่องถอดได้ (รีวิวภายนอก ข้อ 6 / F-04 · 13 ต.ค. 2026)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import bbqr  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


cap = bbqr.Decoder.MAX_TOTAL_CHARS
# 1) ประกาศ 1295 เฟรม × 3,000 ตัว → ปฏิเสธตั้งแต่เฟรมแรก ไม่เก็บอะไรเลย
d = bbqr.Decoder()
frame = "B$2P" + "ZZ" + "00" + "A" * 3000
check("เฟรมแรกประกาศ ~3.9 ล้านตัว → ไม่รับ + too_big", d.add(frame) is False and d.too_big and d.have == 0)

# 2) เฟรมแรกสั้น (หลอกให้ประเมินต่ำ) แล้วเฟรมถัดไปยาว → ยอดสะสมเกินเพดานต้องหยุดรับ
d = bbqr.Decoder()
ok = d.add("B$2P" + "0Z" + "00" + "A" * 8)          # 35 เฟรม ประเมิน 280 ตัว ผ่าน
got = 1
for i in range(1, 35):
    if d.add("B$2P" + "0Z" + bbqr._b36_encode2(i) + "A" * 3990):
        got += 1
check("ยอดสะสมไม่เกินเพดาน (%d ตัว ≤ %d) และติดธง too_big" % (d._chars, cap), d._chars <= cap and d.too_big)

# 3) PSBT ขนาดจริง (~6 KB) ยังผ่านปกติ
data = bytes(range(256)) * 24
parts = bbqr.encode(data, "P", 600)
d = bbqr.Decoder()
for p in parts:
    d.add(p)
res = d.result()
check("PSBT 6 KB (%d เฟรม) ถอดได้ครบ" % len(parts), res is not None and res[0] == data and not d.too_big)

if fails:
    print("❌ test_bbqr_cap ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_bbqr_cap ผ่านครบ")

# เทส qr.pack / lcd.draw_qr รูปแบบบีบ (20 ก.ย. 2026)
# ที่มา: หน้าโชว์ BBQr เก็บทุกเฟรมเป็น list ซ้อน list → MemoryError บน Pico ตอน xpub/PSBT
import os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

# หลอกโมดูลของ MicroPython ให้ import lcd บนแมคได้ (แบบเดียวกับ test_ui_flows.py)
_m = types.ModuleType("machine")
_m.Pin = type("Pin", (), {"__init__": lambda s, *a, **k: None, "IN": 0, "OUT": 1, "PULL_UP": 2,
                          "value": lambda s, *a: 1, "__call__": lambda s, *a: None})
_m.SPI = type("SPI", (), {"__init__": lambda s, *a, **k: None, "write": lambda s, *a: None})
sys.modules["machine"] = _m
_f = types.ModuleType("framebuf")
_f.FrameBuffer = type("FrameBuffer", (), {"__init__": lambda s, *a, **k: None})
_f.MONO_HLSB = 0
_f.RGB565 = 1
sys.modules["framebuf"] = _f

import qr, lcd

fails = 0
def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    if not ok:
        fails += 1

class FakeLCD:
    def __init__(self):
        self.rects = []
        self.filled = None
    def fill(self, color):
        self.filled = color
        self.rects = []
    def fill_rect(self, x, y, w, h, color):
        self.rects.append((x, y, w, h, color))

cases = [
    ("ข้อความสั้น", "HELLO"),
    ("เฟรม BBQr", "B$2P0100" + "A" * 72),
    ("ตัวเลขล้วน (Standard SeedQR 24 คำ)", "0123" * 24),
    ("ไบต์", b"\x00\xff\x0d\x0a" * 8),
]
for name, data in cases:
    m = qr.encode(data, qr.EC_M)
    p = qr.pack(m)
    n = len(m)
    check("%s: ขนาดตรง (%dx%d)" % (name, n, n), p[0] == n and len(p[1]) == ((n + 7) >> 3) * n)
    check("%s: unpack ได้ตารางเดิม" % name, qr.unpack(p) == m)
    check("%s: packed_get ตรงทุกช่อง" % name,
          all(qr.packed_get(p, r, c) == m[r][c] for r in range(n) for c in range(n)))
    check("%s: qr_size รับได้ทั้ง 2 แบบ" % name, lcd.qr_size(m) == n and lcd.qr_size(p) == n)
    a, b = FakeLCD(), FakeLCD()
    ok_a = lcd.draw_qr(a, m)
    ok_b = lcd.draw_qr(b, p)
    check("%s: วาดจากแบบบีบได้ช่องดำชุดเดียวกัน (%d ช่อง)" % (name, len(a.rects)),
          ok_a and ok_b and a.rects == b.rects and a.filled == b.filled and len(a.rects) > 0)

# ประหยัดแรมจริงแค่ไหน (นับแบบหยาบ ๆ ให้เห็นอันดับความต่าง)
m = qr.encode("B$2P0100" + "A" * 72, qr.EC_M)
n = len(m)
rough_list = n * (n * 8 + 64)
rough_pack = ((n + 7) >> 3) * n + 64
check("แบบบีบเล็กกว่าแบบ list อย่างน้อย 10 เท่า (%d vs %d ไบต์)" % (rough_pack, rough_list),
      rough_pack * 10 < rough_list)

print("ผ่านหมด" if not fails else "❌ พัง %d ข้อ" % fails)
sys.exit(1 if fails else 0)

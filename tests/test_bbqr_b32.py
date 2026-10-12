"""base32 ของ BBQr ต้องตรงกับไลบรารีมาตรฐาน และต้องไม่สะสมเลขยักษ์

🔑 27 ก.ย. 2026 บอร์ด ESP32 ที่ไม่มี PSRAM ดับ (MemoryError 4096 ไบต์) ตอนสร้าง QR ของ PSBT ที่เซ็นแล้ว
   ต้นเหตุ: b32_encode เดิมเลื่อนบิตสะสมใน val ไม่เคยตัดทิ้ง → PSBT 600 ไบต์ = เลข 4,800 บิต
   จองแรมใหม่ทุกไบต์ · วัดบนบอร์ด ESP32: 600 ไบต์ 520 ms → 10 ms · 1,500 ไบต์ 2,755 ms → 24 ms
   ผลลัพธ์เดิมถูกอยู่แล้ว เทสผลอย่างเดียวจับบั๊กนี้ไม่ได้ → เช็คว่าค่าที่สะสมไม่โตตามขนาดข้อมูลด้วย
"""
import base64
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import bbqr  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


rng = random.Random(2709)
lens = list(range(0, 80)) + [rng.randint(80, 5000) for _ in range(200)]
bad = []
for n in lens:
    d = bytes(rng.getrandbits(8) for _ in range(n))
    ref = base64.b32encode(d).decode().rstrip("=")
    e = bbqr.b32_encode(d)
    if e != ref or bbqr.b32_decode(e) != d:
        bad.append(n)
check("encode ตรง base64.b32encode และถอดกลับได้ (%d ความยาว)" % len(lens), not bad)
check("คืน str", isinstance(bbqr.b32_encode(b"abc"), str))
check("ถอดอักขระนอกชุดคืน None", bbqr.b32_decode("AB1") is None)

# ── ค่าที่สะสมต้องไม่โตตามขนาดข้อมูล ──────────────────────────────
# วัดด้วยการแทน int ของบิตที่เลื่อน: ถ้าไม่ตัดทิ้ง val จะยาวหลายพันบิต
import sys as _s  # noqa: E402
peak = [0]


def _tracer(frame, event, arg):
    if frame.f_code.co_name in ("b32_encode", "b32_decode") and event == "line":
        v = frame.f_locals.get("val")
        if isinstance(v, int) and v.bit_length() > peak[0]:
            peak[0] = v.bit_length()
    return _tracer


data = bytes(rng.getrandbits(8) for _ in range(1500))
_s.settrace(_tracer)
enc = bbqr.b32_encode(data)
bbqr.b32_decode(enc)
_s.settrace(None)
check("val ใหญ่สุดไม่เกิน 13 บิต (ข้อมูล 1,500 ไบต์ · เดิมโตถึง ~12,000 บิต) — ได้ %d" % peak[0], peak[0] <= 13)

# PSBT ทั้งก้อนผ่าน encode → decode ของ BBQr ได้ครบ
parts = bbqr.encode(data, "P", 90)
dec = bbqr.Decoder() if hasattr(bbqr, "Decoder") else None
if dec is not None:
    for p in parts:
        dec.add(p)
    res = dec.result()
    check("BBQr 90 ตัว/เฟรม ต่อกลับได้ข้อมูลเดิม", res is not None and res[0] == data)

if fails:
    print("❌ test_bbqr_b32 พัง %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_bbqr_b32 ผ่านครบ")

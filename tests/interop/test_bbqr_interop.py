# เทสไขว้ BBQr: Pico (Python) <-> wallet (JavaScript)
#
# ทำไมต้องมีไฟล์นี้: โค้ดฝั่ง Pico ผมเขียนเองและเทสเอง = "ผมบอกเองว่าผ่าน"
# การเอาไปเทียบกับ implementation คนละภาษาที่ใช้งานจริงอยู่แล้ว (wallet)
# ทำให้ผลลัพธ์ไม่ได้ขึ้นกับความเห็นของผมฝ่ายเดียว
#
# ทดสอบ 2 ทิศทาง:
#   1. Pico เข้ารหัส -> wallet ถอด    (เครื่องเซ็นคายผลออกมาให้ wallet อ่าน)
#   2. wallet เข้ารหัส -> Pico ถอด    (wallet ส่ง PSBT ให้เครื่องเซ็นอ่าน)

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src import bbqr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "ref_bbqr.js")


def js_call(fn, arg_json):
    """เรียกฟังก์ชัน BBQr ของ wallet ผ่าน node แล้วรับผลกลับเป็น JSON"""
    code = (
        "const m=require(%s);"
        "const a=JSON.parse(process.argv[1]);"
        "let r;"
        "if(a.fn==='encode'){r=m.bbqrEncode(Uint8Array.from(a.bytes),a.type,a.maxChunk);}"
        "else{const d=m.bbqrDecode(a.parts);"
        "r=d?{type:d.type,total:d.total,partial:!!d.partial,"
        "bytes:d.bytes?Array.from(d.bytes):null}:null;}"
        "process.stdout.write(JSON.stringify(r));"
    ) % json.dumps(JS)
    out = subprocess.run(
        ["node", "-e", code, json.dumps(dict(fn=fn, **arg_json))],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def make_psbt_like(n, seed=0x5A):
    """ข้อมูลจำลองแบบ deterministic — ไม่ต้องพึ่ง random ให้ผลไม่คงที่"""
    out = bytearray()
    x = seed
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        out.append((x >> 16) & 0xFF)
    return bytes(out)


# หมายเหตุ: ไม่ใส่เคส b"" เพราะทั้งสองฝั่งตั้งกฎ "เฟรมต้องยาว >= 9 ตัวอักษร"
# → payload ว่าง (เฟรมยาว 8) ถูกปฏิเสธทั้งคู่ ซึ่งถูกต้อง (PSBT ขนาด 0 ไบต์ไม่มีจริง)
# เคสนี้เทสแยกไว้ด้านล่างว่า "ทั้งสองฝั่งปฏิเสธเหมือนกัน"
CASES = [
    ("1 ไบต์", b"\x00"),
    ("PSBT magic", b"psbt\xff" + make_psbt_like(60)),
    ("พอดี 1 เฟรม", make_psbt_like(300)),
    ("คาบเกี่ยว 2 เฟรม", make_psbt_like(400)),
    ("PSBT ขนาดจริง", make_psbt_like(1200)),
    ("หลายเฟรม", make_psbt_like(5000)),
    ("ใหญ่ 20KB", make_psbt_like(20000)),
    ("ไบต์ 0x00 ล้วน", b"\x00" * 777),
    ("ไบต์ 0xFF ล้วน", b"\xff" * 777),
]

fails = 0
print("── ทิศทาง 1: Pico เข้ารหัส → wallet ถอด ─────────────────────")
for name, data in CASES:
    parts = bbqr.encode(data, "P")
    got = js_call("decode", {"parts": parts})
    ok = got is not None and not got["partial"] and bytes(got["bytes"]) == data and got["type"] == "P"
    fails += 0 if ok else 1
    print("  %-20s %5d ไบต์ → %2d เฟรม  %s" % (name, len(data), len(parts), "ตรงกัน" if ok else "❌ ไม่ตรง"))

print("\n── ทิศทาง 2: wallet เข้ารหัส → Pico ถอด ─────────────────────")
for name, data in CASES:
    parts = js_call("encode", {"bytes": list(data), "type": "P", "maxChunk": 600})
    got = bbqr.decode(parts)
    ok = got is not None and got[0] == data and got[1] == "P"
    fails += 0 if ok else 1
    print("  %-20s %5d ไบต์ → %2d เฟรม  %s" % (name, len(data), len(parts), "ตรงกัน" if ok else "❌ ไม่ตรง"))

print("\n── ข้อมูลว่าง: ต้องปฏิเสธ 'เหมือนกันทั้งสองฝั่ง' ────────────")
empty_parts = bbqr.encode(b"", "P")
py_rej = bbqr.decode(empty_parts) is None
js_rej = js_call("decode", {"parts": empty_parts}) is None
ok = py_rej and js_rej and len(empty_parts[0]) == 8
fails += 0 if ok else 1
print("  เฟรมยาว %d ตัวอักษร → Pico %s · wallet %s   %s" % (
    len(empty_parts[0]), "ปฏิเสธ" if py_rej else "รับ", "ปฏิเสธ" if js_rej else "รับ",
    "ตรงกัน" if ok else "❌ ไม่ตรงกัน"))

print("\n── สแกนมั่วลำดับ / ซ้ำ / ปนชุดอื่น ──────────────────────────")
data = make_psbt_like(3000)
parts = bbqr.encode(data, "P")
d = bbqr.Decoder()
order = list(range(len(parts)))[::-1]          # สแกนย้อนหลัง
for i in order:
    d.add(parts[i])
    d.add(parts[i])                            # ยิงซ้ำใบเดิม
ok = d.done and d.result()[0] == data
fails += 0 if ok else 1
print("  สแกนย้อนลำดับ + ยิงซ้ำทุกใบ            %s" % ("ได้ข้อมูลถูก" if ok else "❌"))

d2 = bbqr.Decoder()
d2.add(parts[0])
other = bbqr.encode(make_psbt_like(3000, seed=0x11), "P")
accepted = d2.add(other[1])                    # เฟรมจากคนละชุด (total เท่ากันแต่ข้อมูลคนละอัน)
print("  เฟรมจากคนละชุด total เท่ากัน           %s" % ("ปฏิเสธถูกต้อง" if accepted is False or not d2.done else "รับเข้ามา (ดูด้านล่าง)"))

# header เสีย → ปฏิเสธตั้งแต่ add()
bad_header = ["ไม่ใช่ BBQr", "B$2P0102AAAA", "B$XP0100AAAA", "", "B$2P"]
rejected = sum(1 for b in bad_header if bbqr.Decoder().add(b) is False)
ok = rejected == len(bad_header)
fails += 0 if ok else 1
print("  header เสีย %d แบบ → ปฏิเสธตั้งแต่ add()   %s" % (
    len(bad_header), "ปฏิเสธครบ" if ok else "❌ ปฏิเสธแค่ %d" % rejected))

# header ถูกแต่ payload ไม่ใช่ base32 → รับเข้ามาก่อน แล้วต้องตายตอน result()
# (จงใจให้เป็นแบบนี้ ตรงกับ wallet — ตรวจ payload ตอนถอดจริงทีเดียว)
d3 = bbqr.Decoder()
d3.add("B$2P0100!!!!")
ok = d3.done and d3.result() is None
fails += 0 if ok else 1
print("  payload ไม่ใช่ base32 → ตายตอน result()  %s" % ("คืน None ถูกต้อง" if ok else "❌ หลุดออกมาได้"))

print("\n── ตัว type อื่น (T = ธุรกรรม finalize แล้ว) ─────────────────")
tx = make_psbt_like(800)
parts = bbqr.encode(tx, "T")
got = js_call("decode", {"parts": parts})
ok = got and bytes(got["bytes"]) == tx and got["type"] == "T"
fails += 0 if ok else 1
print("  Pico เข้ารหัส type=T → wallet        %s" % ("ตรงกัน type=T" if ok else "❌"))

print("\n%s" % ("✅ เทสไขว้ผ่านทั้งหมด" if fails == 0 else "❌ ไม่ผ่าน %d เคส" % fails))
sys.exit(1 if fails else 0)

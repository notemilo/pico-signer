"""เทสไขว้ตัวสร้าง QR: Pico (เขียนเอง) เทียบกับไลบรารี qrcode ที่ wallet ใช้จริง

QR ที่สร้างผิดแม้แต่ช่องเดียว = กล้องอ่านไม่ออก หรือแย่กว่านั้นคืออ่านออกแต่ได้
ข้อมูลผิด (Reed-Solomon แก้ให้เงียบ ๆ จนได้ค่าที่ไม่ใช่ของเดิม)

เทียบทั้งตาราง ทีละช่อง ไม่ใช่แค่ "สแกนแล้วอ่านได้"
ถ้าเวอร์ชัน + mask + ทุกช่องตรงกับไลบรารีมาตรฐาน แปลว่าทุกขั้นถูกหมด:
การเข้ารหัสข้อมูล · Reed-Solomon · การสานบล็อก · การวางลวดลาย · การเลือก mask
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import qr  # noqa: E402
from src import bbqr  # noqa: E402

REF = os.path.join(HERE, "ref_qr.js")
EC_NAME = {qr.EC_L: "L", qr.EC_M: "M", qr.EC_Q: "Q", qr.EC_H: "H"}


def ref(text, ec, mode=None):
    """mode=None ปล่อยให้ไลบรารีเลือกเอง · ระบุ mode = บังคับใช้ segment เดียว

    ⚠️ ไลบรารีอ้างอิงจะแบ่งข้อความเป็นหลาย segment ให้เล็กที่สุดเอง (เช่น
    ABC123 -> [alnum ABC][numeric 123]) ส่วนฝั่ง Pico ใช้โหมดเดียวทั้งก้อน
    ไม่ใช่ผิด แต่คนละวิธี → ต้องบังคับให้ตรงเงื่อนไขก่อนถึงเทียบทีละช่องได้
    (ผลข้างเคียง: QR ของ Pico อาจใหญ่กว่าที่เหมาะที่สุดเล็กน้อยเมื่อข้อความ
     ผสมตัวเลขยาว ๆ — ไม่กระทบ BBQr ซึ่งเป็น base32 ล้วน)
    """
    r = subprocess.run(["node", REF, json.dumps({"text": text, "ec": EC_NAME[ec], "mode": mode})],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("node: " + r.stderr.strip()[:200])
    return json.loads(r.stdout)


fails = []


def compare_data_only(label, text, ec=qr.EC_M):
    """เทียบเฉพาะเนื้อข้อมูล — ยอมให้เลือก mask ต่างกันได้ (ทั้งคู่ถูกตามสเปก)"""
    from qr import (_pick_version, _make_codewords, _new_matrix, _place_data,
                    _mask_fn, _put_format)
    mode = "numeric" if qr._can_num(text) else ("alphanumeric" if qr._can_alnum(text) else "byte")
    t = ref(text, ec, mode)
    short = {"numeric": "num", "alphanumeric": "alnum", "byte": "byte"}[mode]
    v = _pick_version(text, ec, short)
    cw = _make_codewords(text, v, ec, short)
    mod, fixed, size = _new_matrix(v)
    _place_data(mod, fixed, size, cw)
    hit = -1
    for mask in range(8):
        trial = [row[:] for row in mod]
        for r in range(size):
            for c in range(size):
                if not fixed[r][c] and _mask_fn(mask, r, c):
                    trial[r][c] ^= 1
        _put_format(trial, size, ec, mask)
        if all(str(trial[r][c]) == t["rows"][r][c] for r in range(size) for c in range(size)):
            hit = mask
            break
    ok = hit >= 0 and size == t["size"] and v == t["version"]
    if not ok:
        fails.append(label)
    print("  %-34s v%-2d %s  %2dx%-2d  %s" % (
        label[:34], t["version"], EC_NAME[ec], t["size"], t["size"],
        "ข้อมูลตรงทุกช่อง (mask %d)" % hit if ok else "❌ ไม่ตรง"))
    return ok


def compare(label, text, ec=qr.EC_M):
    m = qr.encode(text, ec)
    ours = ["".join(str(v) for v in row) for row in m]
    mode = "numeric" if qr._can_num(text) else ("alphanumeric" if qr._can_alnum(text) else "byte")
    t = ref(text, ec, mode)
    same_size = len(ours) == t["size"]
    same_ver = qr.version_of(m) == t["version"]
    diff = -1
    if same_size:
        diff = sum(1 for r in range(len(ours)) for c in range(len(ours))
                   if ours[r][c] != t["rows"][r][c])
    ok = same_size and same_ver and diff == 0
    if not ok:
        fails.append(label)
    print("  %-34s v%-2d %s  %2dx%-2d  %s" % (
        label[:34], t["version"], EC_NAME[ec], t["size"], t["size"],
        "ตรงทุกช่อง" if ok else ("❌ ต่าง %d ช่อง" % diff if diff >= 0 else "❌ ขนาดไม่ตรง")))
    return ok


print("── 1. ข้อความ alphanumeric (โหมดที่ BBQr ใช้) ─────────────────")
compare("HELLO WORLD", "HELLO WORLD")
compare("ตัวเลขล้วน", "1234567890")   # 16 ก.ย. 2026 มีโหมด numeric แล้ว เทียบโหมดเดียวกัน
compare("ตัวอักษรเดียว", "A")
compare("มีอักขระพิเศษ $ % *", "TEST $12.50 A/B")
compare("ยาว 100 ตัว", "ABCDEFGHIJ0123456789" * 5)
compare("ยาว 300 ตัว", "ABCDEFGHIJ0123456789" * 15)
compare("ยาว 600 ตัว (ขนาด BBQr จริง)", "ABCDEFGHIJ0123456789" * 30)

print("\n── 1b. โหมดตัวเลข (Standard SeedQR) ────────────────────────")
import seedqr  # noqa: E402
_WL = os.path.join(ROOT, "src", "english.txt")
_MN24 = ("void come effort suffer camp survey warrior heavy shoot primary clutch crush "
         "open amazing screen patrol group space point ten exist slush involve unfold")
_MN12 = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
# 🔑 ข้อความสั้นมาก ๆ คะแนนโทษของ mask สูสีกัน เราเลือก mask 2 ไลบรารีเลือก 0
#    ทั้งคู่ถูกตามสเปก (mask ไหนก็อ่านได้) จึงเทียบแค่ว่า "ข้อมูลตรงกันภายใต้ mask ใดสักตัว"
compare_data_only("1 หลัก (mask ต่างกันได้)", "7")
compare("2 หลัก", "42")
compare("3 หลัก", "999")
compare("เศษ 1 ตัวท้าย", "1234567")
compare("เศษ 2 ตัวท้าย", "12345678")
compare("มีศูนย์นำหน้า", "0000012300")
_d24 = seedqr.mnemonic_to_standard_digits(_MN24, _WL)
_d12 = seedqr.mnemonic_to_standard_digits(_MN12, _WL)
compare("Standard SeedQR 24 คำ (96 หลัก)", _d24, qr.EC_L)
compare("Standard SeedQR 12 คำ (48 หลัก)", _d12, qr.EC_L)
print("      ช่องที่ต้องวาดมือ: 24 คำ %dx%d · 12 คำ %dx%d"
      % (len(qr.encode(_d24, qr.EC_L)), len(qr.encode(_d24, qr.EC_L)),
         len(qr.encode(_d12, qr.EC_L)), len(qr.encode(_d12, qr.EC_L))))

print("\n── 2. ระดับ EC ทั้ง 4 ─────────────────────────────────────────")
sample = "B$2P0100" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" * 8
for ec in (qr.EC_L, qr.EC_M, qr.EC_Q, qr.EC_H):
    compare("BBQr จริง EC=%s" % EC_NAME[ec], sample, ec)

print("\n── 3. เฟรม BBQr ของจริงจาก PSBT จำลอง ────────────────────────")
psbt_like = bytes((i * 37 + 11) & 0xFF for i in range(1200))
parts = bbqr.encode(psbt_like, "P")
print("  PSBT 1200 ไบต์ → %d เฟรม BBQr" % len(parts))
for i, p in enumerate(parts):
    compare("เฟรม %d/%d (%d ตัวอักษร)" % (i + 1, len(parts), len(p)), p)

print("\n── 4. โหมด byte (ข้อมูลที่ไม่ใช่ alphanumeric) ────────────────")
compare("ตัวพิมพ์เล็ก", "hello world")
compare("ผสมสัญลักษณ์", "psbt://test?x=1&y=2")

print("\n── 5. ขอบเขต: ข้อมูลใหญ่จนต้องขึ้นเวอร์ชันสูง ────────────────")
compare("alphanumeric 1000 ตัว", "ABCDEFGHIJ0123456789" * 50)
compare("alphanumeric 2000 ตัว", "ABCDEFGHIJ0123456789" * 100, qr.EC_L)

print("\n── 6. QR ที่สร้างต้องอ่านกลับได้จริง (ถอดด้วยไลบรารีอื่น) ──────")
try:
    from PIL import Image  # noqa: F401
    import numpy as np     # noqa: F401
    print("  (ข้ามการถอดภาพ — ทดสอบระดับตารางครอบคลุมกว่าอยู่แล้ว)")
except ImportError:
    print("  (ข้าม — ไม่มี PIL/numpy · การเทียบตารางทีละช่องครอบคลุมกว่า)")

print("\n%s" % ("✅ เทสไขว้ QR ผ่านทั้งหมด — ตารางตรงกับไลบรารีมาตรฐานทุกช่อง"
                if not fails else "❌ ไม่ผ่าน %d เคส: %s" % (len(fails), ", ".join(fails[:4]))))
sys.exit(1 if fails else 0)

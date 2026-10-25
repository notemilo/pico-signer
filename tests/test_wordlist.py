"""bip39.WordList — รายการคำแบบก้อนเดียว (15 ต.ค. 2026 · แก้ MemoryError ตอนถอด SeedQR บนเครื่อง)

ต้องทำงานเหมือน list เดิมทุกจุดที่โค้ดใช้ และปฏิเสธไฟล์ที่ผิดรูป (binary search พึ่งการเรียงตัวอักษร)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import bip39  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


raw = open(os.path.join(HERE, "..", "src", "english.txt"), "rb").read()
ref = raw.decode().split()
w = bip39.WordList(raw)
check("ทุกคำตรงกับ list เดิม (ลำดับ + จำนวน)", list(w) == ref and len(w) == 2048)
check("index() ตรงทุกคำ · [i] ตรงทุกตำแหน่ง · [-1] = zoo",
      all(w.index(x) == i for i, x in enumerate(ref)) and all(w[i] == x for i, x in enumerate(ref)) and w[-1] == "zoo")
bad = 0
for x in ("", "a", "zzz", "abandonx", "Abandon", "aban", "ก"):
    try:
        w.index(x)
        bad += 1
    except ValueError:
        pass
check("คำที่ไม่มีในรายการ → ValueError (รวมตัวใหญ่ · คำนำหน้า · ไทย)", bad == 0)
check("in / not in", "zoo" in w and "zzz" not in w)
pre = set()
for x in ref:
    pre.add(x[:1]); pre.add(x[:2]); pre.add(x[:3])
check("with_prefix ตรงกับการกรองทั้งรายการ (%d prefix)" % len(pre),
      all(w.with_prefix(p) == [x for x in ref if x.startswith(p)] for p in pre))
pre |= {"", "zoo", "zz", "abandon", "car"}
check("prefix_range ครอบคำที่ขึ้นต้นด้วย prefix พอดี (\"\" = ทั้ง 2,048 คำ · 25 ต.ค. 2026)",
      all([ref[k] for k in range(*w.prefix_range(p))] == [x for x in ref if x.startswith(p)] for p in pre)
      and w.prefix_range("") == (0, 2048))
check("with_prefix(p, 4) = 4 คำแรกเท่านั้น",
      all(w.with_prefix(p, 4) == [x for x in ref if x.startswith(p)][:4] for p in pre))
check("ไฟล์แบบ CRLF อ่านได้ผลเดียวกัน", list(bip39.WordList(raw.replace(b"\n", b"\r\n"))) == ref)
for name, data in (("2047 คำ", b"\n".join(raw.split(b"\n")[:2047])),
                   ("ไม่เรียงตัวอักษร", b"\n".join([ref[1].encode(), ref[0].encode()] + [x.encode() for x in ref[2:]])),
                   ("มีบรรทัดว่างกลางไฟล์", raw.replace(b"\nzoo", b"\n\nzoo"))):
    try:
        bip39.WordList(data)
        ok = False
    except ValueError:
        ok = True
    check("ปฏิเสธไฟล์ผิดรูป: %s" % name, ok)
try:
    w[2048]
    ok = False
except IndexError:
    ok = True
check("[2048] → IndexError", ok)

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_wordlist ผ่านครบ")

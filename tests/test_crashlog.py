"""crash.txt ต้องไม่เก็บข้อความ error (อาจมีคำ seed) — ผู้รีวิวภายนอก ข้อ 5 (13 ต.ค. 2026)"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import crashlog  # noqa: E402
import bip39  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


SECRET = "abandon zebra legal winner"


def boom():
    raise ValueError("ไม่พบคำ: " + SECRET)


try:
    boom()
except ValueError as e:
    tb = crashlog.safe_traceback(e)
    path = os.path.join(tempfile.mkdtemp(), "crash.txt")
    crashlog.save(e, path)
    saved = open(path).read()

check("ไม่มีข้อความ error ในไฟล์", SECRET not in saved and "ไม่พบคำ" not in saved)
check("ยังมีชนิด error + บรรทัดของฟังก์ชันที่พัง", "ValueError" in saved and "boom" in saved and "line" in saved)
check("save() ไม่พังแม้ path เขียนไม่ได้", crashlog.save(ValueError("x"), "/no/such/dir/crash.txt") is None)

# ข้อความของ bip39 ต้องไม่มีตัวคำที่ผู้ใช้พิมพ์
try:
    bip39.mnemonic_to_entropy("abandon " * 11 + "zzzsecret")
    msg = ""
except ValueError as e:
    msg = str(e)
check("bip39 บอกตำแหน่งคำ ไม่บอกตัวคำ (%r)" % msg, "zzzsecret" not in msg and "12" in msg)
try:
    bip39.last_word_candidates("abandon " * 10 + "zzzsecret")
    msg = ""
except ValueError as e:
    msg = str(e)
check("last_word_candidates ก็เช่นกัน", "zzzsecret" not in msg and "11" in msg)

if fails:
    print("❌ test_crashlog ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_crashlog ผ่านครบ")

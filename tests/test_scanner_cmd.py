"""สั่งงานสแกนเนอร์ผ่าน UART: ตรวจค่าตั้งตอนเปิด · คืนค่าโรงงานเมื่อโดนแก้ · หยุดสแกนนอกหน้าสแกน

🔑 18 ต.ค. 2026 (รีวิวภายนอก GHSA-334h-x4f4-34h3 ข้อ 5 · วิธีจาก Specter-DIY hosts/qr.py):
   โมดูลจำลองตอบโปรโตคอล 7E 00 แบบเดียวกับตัวจริง (คู่มือ Waveshare ภาคผนวก D)
   ค่าเริ่มต้น = ค่าที่อ่านจากโมดูลของ ผู้ใช้ จริงวันที่ 18 ต.ค. 2026
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

time.ticks_ms = lambda: int(time.monotonic() * 1000)
time.ticks_diff = lambda a, b: a - b
time.sleep_ms = lambda ms: None

FACTORY = {0x0000: 0xD6, 0x0002: 0x00, 0x0005: 0x0A, 0x0006: 0x00, 0x000D: 0x00, 0x0013: 0x00,
           0x002A: 0x39, 0x002B: 0x01, 0x002C: 0x04, 0x003F: 0x01, 0x00E2: 0x01}


class Module:
    """โมดูลสแกนเนอร์จำลอง: ทะเบียนค่าตั้ง + คำสั่งอ่าน/เขียน/คืนค่าโรงงาน"""

    def __init__(self, silent=False, ignore_reset=False):
        self.regs = dict(FACTORY)
        self.silent = silent
        self.ignore_reset = ignore_reset
        self.out = b""
        self.resets = 0
        self.writes = []

    def rx(self, b):
        if self.silent:
            return
        if b == b"\x7e\x00\x09\x01\x00\x00\xff\xc0\x38":
            self.resets += 1
            if not self.ignore_reset:
                self.regs = dict(FACTORY)
            self.out += b"\x02\x00\x00\x01\x00\x33\x31"
            return
        assert b[:2] == b"\x7e\x00" and b[-2:] == b"\xab\xcd", b
        typ, addr = b[2], (b[4] << 8) | b[5]
        if typ == 0x07:
            n = b[6]
            data = bytes(self.regs.get(addr + k, 0) for k in range(n))
            self.out += b"\x02\x00\x00" + bytes([n]) + data + b"\x12\x34"
        elif typ == 0x08:
            self.regs[addr] = b[6]
            self.writes.append((addr, b[6]))
            self.out += b"\x02\x00\x00\x01\x00\x33\x31"


MOD = Module()


class FakeUART:
    def __init__(self, *a, **k):
        pass

    def any(self):
        return len(MOD.out)

    def read(self, n=None):
        d, MOD.out = (MOD.out, b"") if n is None else (MOD.out[:n], MOD.out[n:])
        return d

    def write(self, b):
        MOD.rx(bytes(b))

    def deinit(self):
        pass


_m = types.ModuleType("machine")
_m.UART = FakeUART
_m.Pin = lambda *a, **k: None
sys.modules["machine"] = _m

import scanner  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


def fresh(**k):
    global MOD
    MOD = Module(**k)
    return MOD


print("── ตรวจตอนเปิดเครื่อง (boot_check)")
m = fresh()
st = scanner.boot_check()
check("ค่าโรงงาน → OK · ไม่คืนค่า · จอดไว้ที่โหมดรอคำสั่ง (0xD5)",
      st == ("OK", []) and m.resets == 0 and m.regs[0x0000] == 0xD5)
m = fresh()
m.regs[0x0000] = 0xD5                      # ค้างโหมดรอคำสั่งจากรอบก่อน (ยังไม่ปิดเครื่อง) — ไม่นับว่าโดนแก้
check("โหมดรอคำสั่งค้างจากรอบก่อน → ยัง OK (เทียบเฉพาะบิตบน)", scanner.boot_check()[0] == "OK" and m.resets == 0)
m = fresh()
m.regs[0x0005] = 0x02                      # มีคนสแกน QR "เว้นช่วง 200ms"
st = scanner.boot_check()
check("ค่าเว้นช่วงโดนแก้ → RESET [0x0005] · คืนค่าโรงงาน 1 ครั้ง · ค่ากลับ · จอดรอคำสั่ง",
      st == ("RESET", [0x0005]) and m.resets == 1 and m.regs[0x0005] == 0x0A and m.regs[0x0000] == 0xD5)
m = fresh()
m.regs[0x003F] = 0x00                      # ปิดการอ่าน QR
check("ปิดการอ่าน QR → RESET", scanner.boot_check() == ("RESET", [0x003F]))
m = fresh()
m.regs[0x002A] = 0x1A
check("baud โดนแก้ (แต่ยังตอบที่ 9600) → RESET", scanner.boot_check()[0] == "RESET")
m = fresh(ignore_reset=True)
m.regs[0x0005] = 0x02
check("คืนค่าแล้วยังไม่ตรง → BAD", scanner.boot_check()[0] == "BAD")
fresh(silent=True)
check("โมดูลไม่ตอบ (สายหลุด / baud ถูกเปลี่ยน) → NO REPLY", scanner.boot_check() == ("NO REPLY", []))

print("── หน้าสแกน: เข้า = เริ่มสแกน · ออก = หยุด")
m = fresh()
m.regs[0x0000] = 0xD5
sc = scanner.Scanner()
check("Scanner() → โหมดสแกนตลอดเวลา (0xD6) บิตบนไม่เปลี่ยน", m.regs[0x0000] == 0xD6)
m.out += b"PICO TEST 123\r"
check("poll() ยังอ่านข้อมูลสแกนได้ตามเดิม", sc.poll() == ["PICO TEST 123"])
sc.deinit()
check("deinit() → กลับโหมดรอคำสั่ง (0xD5)", m.regs[0x0000] == 0xD5)
m = fresh()
sc = scanner.Scanner(start=False)
check("Scanner(start=False) ไม่แตะโหมด", m.writes == [])
m.out += b"leftover scan data\r"
check("คำตอบมีข้อมูลสแกนค้างหน้า → ทิ้งก่อนถาม อ่านค่าถูก", sc.read_reg(0x0005) == b"\x0a")
sc.deinit(stop=False)
fresh(silent=True)
sc = scanner.Scanner()
check("โมดูลไม่ตอบ → สร้าง Scanner ได้ไม่พัง · set_scanning คืน False", sc.set_scanning(True) is False)
sc.deinit()

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_scanner_cmd ผ่านครบ")

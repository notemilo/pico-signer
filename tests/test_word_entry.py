"""จำลองการใส่คำบนเครื่อง — ทุกคำใน 2048 คำต้องใส่ได้จริง

🔑 ทำไมต้องมี (เจอ 10 ก.ย. 2026):
   วิธีเลือกตัวอักษรแบบเดิมบังคับให้เลือก "ตัวถัดไป" เสมอ
   คำที่เป็นคำนำหน้าของคำอื่น (car, add, art, sun, you, ... 49 คำ)
   จึงใส่ไม่ได้เลย — พิมพ์ car แล้วได้แต่ carbon/card/cargo
   seed 24 คำมีโอกาส ~44% ที่จะมีคำแบบนี้ = ใส่กลับเข้าเครื่องไม่ได้
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# ui.py ต้องมี machine/framebuf ซึ่งมีแต่บนเครื่อง — ใส่ตัวหลอกให้ import ผ่าน
# (เราใช้แค่ฟังก์ชัน next_letters ที่เป็นตรรกะล้วน ไม่แตะฮาร์ดแวร์)
import types

_m = types.ModuleType("machine")
_m.Pin = type("Pin", (), {"__init__": lambda s, *a, **k: None,
                          "IN": 0, "OUT": 1, "PULL_UP": 2,
                          "value": lambda s, *a: 1, "__call__": lambda s, *a: None})
_m.SPI = type("SPI", (), {"__init__": lambda s, *a, **k: None,
                          "write": lambda s, *a: None})
# ui.py ดึง ups.py ซึ่งต้องการ I2C — ใส่ตัวหลอกไว้ให้ import ผ่าน
_m.I2C = type("I2C", (), {"__init__": lambda s, *a, **k: None,
                          "scan": lambda s: [],
                          "readfrom_mem": lambda s, *a: b"\x00\x00"})
_m.UART = type("UART", (), {"__init__": lambda s, *a, **k: None, "any": lambda s: 0,
                            "read": lambda s, *a: b"", "deinit": lambda s: None})   # ui import scanner ตั้งแต่โหลด (15 ต.ค. 2026)
sys.modules["machine"] = _m

_f = types.ModuleType("framebuf")
_f.FrameBuffer = type("FrameBuffer", (), {"__init__": lambda s, *a, **k: None})
_f.MONO_HLSB = 0
_f.RGB565 = 1
sys.modules["framebuf"] = _f

import bip39
from ui import next_letters

WORDS = bip39.wordlist()


def presses_for(target):
    """จำนวนครั้งที่ต้องกดเพื่อใส่คำนี้ — คืน None ถ้าใส่ไม่ได้"""
    prefix = ""
    presses = 0
    for _ in range(12):                       # กันวนไม่จบ
        opts = next_letters(WORDS, prefix)
        want = "" if prefix == target else target[len(prefix)]
        if want not in opts:
            return None
        i = opts.index(want)
        # เลื่อนขึ้นหรือลงก็ได้ เลือกทางที่ใกล้กว่า แล้วกด A อีก 1 ครั้ง
        presses += min(i, len(opts) - i) + 1
        if want == "":
            return presses
        matches = [w for w in WORDS if w.startswith(prefix + want)]
        if len(matches) == 1:
            return presses if matches[0] == target else None
        prefix += want
    return None


def main():
    bad = []
    total = 0
    worst = (0, "")
    for w in WORDS:
        n = presses_for(w)
        if n is None:
            bad.append(w)
            continue
        total += n
        if n > worst[0]:
            worst = (n, w)
    print("ทดสอบครบ %d คำ" % len(WORDS))
    if bad:
        print("ใส่ไม่ได้ %d คำ: %s" % (len(bad), bad[:20]))
        sys.exit(1)
    print("ใส่ได้ครบทุกคำ")
    print("กดเฉลี่ย %.1f ครั้ง/คำ · มากสุด %d ครั้ง (%s)"
          % (total / len(WORDS), worst[0], worst[1]))
    print("seed 24 คำ = ประมาณ %d ครั้ง" % round(total / len(WORDS) * 24))


if __name__ == "__main__":
    main()

"""เทียบโค้ดใน src/ กับ API ที่ MicroPython บนเครื่องมีจริง

🔑 ทำไมต้องมีเทสนี้:
   เทสอื่นทั้งหมดรันด้วย CPython บนแมค ซึ่ง "มีเมธอดเยอะกว่า" เครื่องจริง
   โค้ดที่เรียก str.ljust() จึงผ่านเทสบนแมคหมดทุกข้อ แล้วไปพังบนเครื่อง
   (เกิดขึ้นจริง 10 ก.ย. 2026 — หน้าทอยเต๋าพังทันทีที่เปิด ทั้งที่เทส 990 บรรทัดผ่าน)

   tests/mp_api.json = ผลของ dir() ที่ถามจากบอร์ดจริง ไม่ใช่ที่ผมจำมา
   อัปเดตด้วย: mpremote exec "import builtins; print(dir(str))" ฯลฯ
"""

import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")

with open(os.path.join(HERE, "mp_api.json")) as f:
    MP = json.load(f)

# เมธอดที่ CPython มีแต่เครื่องไม่มี — เอาชื่อพวกนี้ไปหาในโค้ด
# 🔑 ต้องรวมทุกชนิดก่อนค่อยลบ ไม่ใช่ลบทีละชนิดแล้วรวม
#    เช่น .pop() ไม่มีใน str แต่มีใน list — ถ้าลบทีละชนิดจะโดนธงผิด
_TYPES = (("str", str), ("bytes", bytes), ("list", list), ("dict", dict),
          ("int", int), ("set", set), ("tuple", tuple), ("bytearray", bytearray))
_device = set()
_cpython = set()
for name, cls in _TYPES:
    _device |= set(MP[name])
    _cpython |= set(a for a in dir(cls) if not a.startswith("_"))
MISSING_METHODS = _cpython - _device

MISSING_BUILTINS = set(
    a for a in dir(__builtins__ if isinstance(__builtins__, dict) else __builtins__)
) if False else set()
import builtins as _b
MISSING_BUILTINS = set(a for a in dir(_b) if not a.startswith("_")) - set(MP["builtins"])
# พวกนี้เป็นคลาส exception/เครื่องมือที่เราไม่ได้เรียกเป็นฟังก์ชันอยู่แล้ว
MISSING_BUILTINS -= {"copyright", "credits", "license", "help", "quit", "exit"}


_PROJECT_METHODS = None


def _project_methods():
    """ชื่อเมธอด/ฟังก์ชันที่โปรเจกต์นิยามเอง — ชนชื่อกับ CPython ได้ ไม่ใช่บั๊ก

    เช่น lcd.LCD.clear() ชนกับ dict.clear() ที่เครื่องไม่มีใน str
    """
    global _PROJECT_METHODS
    if _PROJECT_METHODS is None:
        names = set()
        for fn in os.listdir(SRC):
            if not fn.endswith(".py") or ".bak" in fn:
                continue
            with open(os.path.join(SRC, fn), encoding="utf-8") as f:
                t = ast.parse(f.read(), filename=fn)
            for n in ast.walk(t):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(n.name)
        _PROJECT_METHODS = names
    return _PROJECT_METHODS


def scan(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    bad = []
    # ชื่อเมธอดที่ไฟล์นี้นิยามเอง — ไม่ต้องเตือน
    own = _project_methods()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in MISSING_METHODS \
                and node.attr not in own:
            bad.append((node.lineno, "เมธอด ." + node.attr + "()"))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) \
                and node.id in MISSING_BUILTINS:
            bad.append((node.lineno, "ฟังก์ชัน " + node.id + "()"))
    return bad


def main():
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".py"))
    files = [f for f in files if ".bak" not in f]
    total = 0
    print("ตรวจ %d ไฟล์ เทียบกับ API จริงบนบอร์ด" % len(files))
    print("เมธอดที่เครื่องไม่มี %d ชื่อ · ฟังก์ชันที่เครื่องไม่มี %d ชื่อ"
          % (len(MISSING_METHODS), len(MISSING_BUILTINS)))
    for fn in files:
        bad = scan(os.path.join(SRC, fn))
        for lineno, what in bad:
            total += 1
            print("  %s:%d  ใช้ %s ซึ่งเครื่องไม่มี" % (fn, lineno, what))
    # ตรวจ main.py กับ boot.py ด้วย
    for top in ("main.py", "boot.py"):
        m = os.path.join(HERE, "..", top)
        for lineno, what in scan(m):
            total += 1
            print("  %s:%d  ใช้ %s ซึ่งเครื่องไม่มี" % (top, lineno, what))
    print()
    if total:
        print("พบ %d จุดที่จะพังบนเครื่อง" % total)
        sys.exit(1)
    print("ผ่านทั้งหมด — ไม่มีจุดไหนใช้ของที่เครื่องไม่มี")


if __name__ == "__main__":
    main()

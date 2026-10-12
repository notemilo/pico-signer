"""ตรวจว่าข้อความบนจอไม่ยาวเกินจนโดนตัดเงียบ ๆ

🔑 ทำไมต้องมี:
   _chrome() ตัดหัวเรื่องที่ 14 ตัวอักษรโดยไม่เตือน
   "DICE ROLL 1/256" จึงกลายเป็น "DICE ROLL 1/25" บนจอจริง
   ผู้ใช้อ่านแล้วเข้าใจว่าต้องทอย 25 ครั้ง ทั้งที่ต้องทอย 256
   (เจอจากรูปถ่ายหน้าจอ 10 ก.ย. 2026 — ไม่มีเทสไหนจับได้เพราะโค้ดไม่ error)

   เทสนี้เดาค่าที่แย่ที่สุดของ %d / %s แล้ววัดความยาว
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "src", "ui.py")

TITLE_COLS = 10          # scale 2 ที่ x=4 · เหลือที่มุมขวาให้เปอร์เซ็นต์แบต
HINT_COLS = 15
WORST_D = "256"          # ตัวเลขมากสุดที่จอนี้เจอจริง (จำนวนทอย) — ใช้กับหัวเรื่อง/แถบปุ่ม
# บรรทัดเนื้อความกับรายการเมนูไม่มีตัวนับทอย ตัวเลขมากสุดคือ account 99 / จำนวนคำ 24
WORST_D_BODY = "99"
WORST_S = "XXXXXXXX"     # ข้อความแทรกยาวสุดที่คาดไว้
TITLE_CALLS = ("_chrome", "message", "menu", "confirm")
MENU_COLS = 13          # menu() วาด ">" + ชื่อ[:13] ที่ scale 2
BODY_COLS = 14          # message() ตัดบรรทัดเนื้อความที่ 14 ตัว (scale 2)
SMALL_COLS = 29         # self.d.text() เป็น scale 1 -> 240/8 = 30 ตัว เผื่อขอบเหลือ 29


def worst_case(node, worst_d=None):
    """คืนข้อความที่ยาวที่สุดที่ node นี้จะกลายเป็น หรือ None ถ้าเดาไม่ได้"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = worst_case(node.left)
        if left is None:
            return None
        return left.replace("%d", worst_d or WORST_D).replace("%s", WORST_S)
    return None


def main():
    with open(UI, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename="ui.py")
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else None
        if name not in TITLE_CALLS or not node.args:
            continue
        title = worst_case(node.args[0])
        if title is not None and len(title) > TITLE_COLS:
            bad.append((node.lineno, "หัวเรื่อง", title, TITLE_COLS))
        # รายการเมนู: menu(title, [...]) — ชื่อยาวเกินโดนตัดเงียบ ๆ (เจอจริง 16 ก.ย. 2026
        # "Standard (any scanner)" กลายเป็น "Standard (any" บนจอ)
        if name == "menu" and len(node.args) > 1 and isinstance(node.args[1], ast.List):
            for el in node.args[1].elts:
                it = worst_case(el, WORST_D_BODY)
                if it is not None and len(it) > MENU_COLS:
                    bad.append((node.lineno, "รายการเมนู", it, MENU_COLS))
        # บรรทัดเนื้อความของ message()
        if name == "message" and len(node.args) > 1 and isinstance(node.args[1], ast.List):
            for el in node.args[1].elts:
                ln = worst_case(el, WORST_D_BODY)
                if ln is not None and len(ln) > BODY_COLS:
                    bad.append((node.lineno, "บรรทัดเนื้อความ", ln, BODY_COLS))
        # อาร์กิวเมนต์ hint ของ _chrome/message อยู่ตัวที่ 3
        hi = 1 if name == "_chrome" else 2
        if len(node.args) > hi:
            h = worst_case(node.args[hi])
            if h is not None:
                for w in h.split():
                    if len(w) > HINT_COLS:
                        bad.append((node.lineno, "คำในแถบปุ่ม", w, HINT_COLS))
    # ตัวอักษรเล็ก (scale 1) ที่วาดตรง ๆ — ถ้ายาวเกิน 29 ตัวจะหลุดขอบจอเงียบ ๆ
    # (เจอจริง 11 ก.ย. 2026: แถบใต้ QR ยาว 32 ตัว "B=EXIT" เลยเหลือ "B=EX")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "text"):
            continue
        if not node.args:
            continue
        t = worst_case(node.args[0])
        if t is not None and len(t) > SMALL_COLS:
            bad.append((node.lineno, "ตัวอักษรเล็ก", t, SMALL_COLS))
    print("ตรวจข้อความบนจอใน ui.py (หัวเรื่อง %d ตัว · แถบปุ่ม %d ตัว/บรรทัด · ตัวเล็ก %d ตัว)"
          % (TITLE_COLS, HINT_COLS, SMALL_COLS))
    for lineno, kind, text, lim in bad:
        print("  ui.py:%d  %s ยาว %d ตัว (เกิน %d) -> %r"
              % (lineno, kind, len(text), lim, text))
    print()
    if bad:
        print("พบ %d จุดที่จะโดนตัดบนจอ" % len(bad))
        sys.exit(1)
    print("ผ่านทั้งหมด — ไม่มีข้อความไหนโดนตัด")


if __name__ == "__main__":
    main()

"""ตาราง 2,048 คำที่แจกใน repo ต้องตรงกับที่เครื่องคิดจริงทุกแถว (dice.rolls_to_word)

🔑 19 ต.ค. 2026: เพิ่มตาราง + ใบจดผลทอยให้คนที่ทำตาม (public/docs/) — ถ้าตารางผิดแม้แถวเดียว
   คนที่เช็คคำบนกระดาษจะคิดว่าเครื่องผิด หรือแย่กว่านั้นคือเชื่อตารางที่ผิด
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
os.chdir(SRC)
import dice  # noqa: E402

DOCS = os.path.join(HERE, "..", "public", "docs")        # repo ต้นฉบับ
if not os.path.isdir(DOCS):
    DOCS = os.path.join(HERE, "..", "docs")              # สำเนาสาธารณะ
fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


md = open(os.path.join(DOCS, "dice-word-table.md"), encoding="utf-8").read()
rows = re.findall(r"^\| (\d+) \| `([01]{4}) ([01]{4}) ([01]{3})` \| ([a-z]+) \|$", md, re.M)
bad = [r for r in rows
       if dice.rolls_to_word([1 if c == "1" else 2 for c in r[1] + r[2] + r[3]]) != r[4]
       or int(r[0]) != int(r[1] + r[2] + r[3], 2) + 1]
check("dice-word-table.md: %d แถว · ตรงกับ dice.rolls_to_word ทุกแถว (ผิด %d)" % (len(rows), len(bad)),
      len(rows) == 2048 and not bad)
html = open(os.path.join(DOCS, "dice-word-table.html"), encoding="utf-8").read()
hrows = re.findall(r'<td class="b1">([01]{4})</td><td>([01]{4})</td><td>([01]{3})</td><td class="w">([a-z]+)</td>', html)
hbad = [r for r in hrows if dice.rolls_to_word([1 if c == "1" else 2 for c in r[0] + r[1] + r[2]]) != r[3]]
check("dice-word-table.html (พิมพ์ได้): %d แถว · ตรงทุกแถว (ผิด %d)" % (len(hrows), len(hbad)),
      len(hrows) == 2048 and not hbad)
check("ไม่มีอักษรไทยในไฟล์ภาษาอังกฤษ", not re.search("[฀-๿]", html + md))
sheet = open(os.path.join(DOCS, "dice-roll-sheet.html"), encoding="utf-8").read()
check("ใบจดผลทอยมี 24 คำ (ช่องสุดท้าย 3) และ 12 คำ (ช่องสุดท้าย 7)",
      "24 words" in sheet and "12 words" in sheet and "roll 3 more times" in sheet and "roll 7 more times" in sheet)

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_dice_docs ผ่านครบ")

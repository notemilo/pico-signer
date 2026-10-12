# test_dice_12.py — New seed ด้วยเต๋า รองรับ 12 คำ (เพิ่ม 14 ก.ย. 2026)
#
# สิ่งที่ต้องจริงเสมอ (หัวใจของการใช้เต๋า):
#   1. entropy ที่ได้ = บิตจากเต๋าตรง ๆ ทุกบิต (ไม่มี hash คั่น)
#   2. ตัวเลือกคำสุดท้ายเรียง a->z = เรียงตามค่า entropy -> ทอยเลือกได้ไม่มี bias
#   3. ของเดิม 24 คำยังทำงานเหมือนเดิม
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
import dice, bip39

WL = os.path.join(SRC, "english.txt")
WORDS = bip39.wordlist(WL)
fails = 0

def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1

def raises(fn):
    try:
        fn()
        return False
    except ValueError:
        return True

def bits_bytes(rolls):
    n = 0
    for r in rolls:
        n = (n << 1) | (int(r) & 1)
    return n.to_bytes(len(rolls) // 8, "big")

rng = random.Random(20260914)

print("── 1. จำนวนทอย")
check("12 คำ = 128 ทอย", dice.need_rolls(12) == 128)
check("24 คำ = 256 ทอย", dice.need_rolls(24) == 256)
check("18 คำ ไม่รองรับ", raises(lambda: dice.need_rolls(18)))

print("── 2. entropy = บิตจากเต๋าตรง ๆ ทุกบิต")
for count, ncand in ((12, 128), (24, 8)):
    ok = True
    for _ in range(25):
        rolls = [rng.randint(1, 6) for _ in range(dice.need_rolls(count))]
        mn, cands = dice.build_mnemonic(rolls, WL)
        parts = mn.split()
        ok &= len(parts) == count and bip39.is_valid(mn, WL) and len(cands) == ncand
        ok &= bip39.mnemonic_to_entropy(mn, WL) == bits_bytes(rolls)
    check("%d คำ สุ่ม 25 ชุด: ครบคำ · checksum ถูก · %d ตัวเลือก · entropy ตรงบิตเต๋า" % (count, ncand), ok)

print("── 3. ตัวเลือกคำสุดท้าย a->z = ลำดับค่า entropy")
for count, csbits in ((12, 4), (24, 8)):
    ok = True
    for _ in range(20):
        first = [WORDS[rng.randrange(2048)] for _ in range(count - 1)]
        cands = bip39.last_word_candidates(" ".join(first), WL)
        ok &= cands == sorted(cands)
        ok &= all((WORDS.index(w) >> csbits) == pos for pos, w in enumerate(cands))
    check("%d คำ: เรียงตัวอักษร และตำแหน่ง = ค่า entropy (20 ชุด)" % count, ok)

print("── 4. เลือกคำสุดท้ายด้วยทอย")
first11 = [WORDS[rng.randrange(2048)] for _ in range(11)]
w, c = dice.last_word_from_rolls(first11, [1] * 7, WL)
check("12 คำ ทอยคี่ 7 ครั้ง = ตัวเลือกที่ 127 (ตัวสุดท้าย)", len(c) == 128 and w == c[127])
w, c = dice.last_word_from_rolls(first11, [2] * 7, WL)
check("12 คำ ทอยคู่ 7 ครั้ง = ตัวเลือกที่ 0", w == c[0])
w, c = dice.last_word_from_rolls(first11, [1, 2, 2, 2, 2, 2, 2], WL)
check("12 คำ 1000000 = ตัวเลือกที่ 64", w == c[64])
check("12 คำ ทอย 3 ครั้ง (ผิด) ถูกปฏิเสธ", raises(lambda: dice.last_word_from_rolls(first11, [1] * 3, WL)))
first23 = [WORDS[rng.randrange(2048)] for _ in range(23)]
w, c = dice.last_word_from_rolls(first23, [1, 2, 1], WL)
check("24 คำ (ของเดิม) ทอย 101 = ตัวเลือกที่ 5 จาก 8", len(c) == 8 and w == c[5])
check("24 คำ ทอย 7 ครั้ง (ผิด) ถูกปฏิเสธ", raises(lambda: dice.last_word_from_rolls(first23, [1] * 7, WL)))
check("ให้ 17 คำ (ไม่รองรับ) ถูกปฏิเสธ", raises(lambda: dice.last_word_from_rolls(first23[:17], [1] * 3, WL)))

print("── 5. จำนวนทอยทั้งหมดผิด")
for n in (0, 127, 129, 255, 257):
    check("ทอย %d ครั้ง ถูกปฏิเสธ" % n, raises(lambda: dice.build_mnemonic([1] * n, WL)))

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails); sys.exit(1)
print("✅ test_dice_12 ผ่านครบ")

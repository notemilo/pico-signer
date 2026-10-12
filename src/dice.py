# dice.py — สร้าง seed จากลูกเต๋าที่ทอยด้วยมือ
#
# 🔑 ทำไมต้องมีไฟล์นี้ แทนที่จะให้เครื่องสุ่มเอง:
#    entropy ทั้ง 256 บิตมาจากลูกเต๋าในมือคน **เครื่องไม่สุ่มอะไรเลยสักบิต**
#    ตัดความเสี่ยงแบบเดียวกับบั๊ก RNG ของ Coldcard (ก.ค. 2026) ที่เฟิร์มแวร์
#    ตกไปใช้ตัวสุ่มอ่อน ๆ เงียบ ๆ อยู่ 5 ปีโดยไม่มีใครรู้
#    (และบน MicroPython พอร์ต rp2 ตอนนี้ os.urandom() ยังดึงจาก ring oscillator
#     ซึ่งเอกสาร Raspberry Pi เตือนเองว่าใช้กับงานความปลอดภัยไม่ได้)
#
# วิธี: ทอย 11 ครั้งต่อ 1 คำ · คี่ = 1 · คู่ = 0 · อ่านจากซ้ายไปขวาเป็นเลขฐานสอง
#       11 บิต = 0-2047 = ลำดับคำใน BIP39 พอดี
#       23 คำ = 253 ทอย = entropy 253 บิต · อีก 3 บิตอยู่ในคำที่ 24
#       ทอยอีก 3 ครั้งเลือกคำที่ 24 จาก 8 ตัวเลือก → ครบ 256 บิต
#
# ⚠️ **SHA-256 ไม่แตะ entropy เลย** — เต๋า → บิต → เปิดตาราง → คำ ตรง ๆ
#    ต่างจากฟีเจอร์ dice ในตัวเครื่องบางยี่ห้อที่เอา SHA-256 มาคั่นกลาง
#    (ตรงกับใบตารางกระดาษที่ ผู้ใช้ ทำไว้และตรวจครบ 2,048 แถวแล้ว)

import bip39

WORDS_PER_ROLL = 11        # ทอย 11 ครั้ง = 1 คำ
LAST_WORD_ROLLS = 3        # (ชื่อเดิม) คำสุดท้ายของ 24 คำ

# บิต entropy ที่อยู่ในคำสุดท้าย = 11 - บิต checksum (checksum = ENT/32)
#   12 คำ: ENT 128 · checksum 4 -> คำสุดท้ายมี entropy 7 บิต = 128 ตัวเลือก
#   24 คำ: ENT 256 · checksum 8 -> 3 บิต = 8 ตัวเลือก
# (เพิ่ม 12 คำ 14 ก.ย. 2026 — ผู้ใช้ ออกแบบเมนู New Seed ให้เลือก 12/24 เอง)
LAST_ROLLS = {12: 7, 24: 3}


def need_rolls(count):
    """จำนวนทอยทั้งหมด: 12 คำ = 11*11+7 = 128 · 24 คำ = 23*11+3 = 256"""
    if count not in LAST_ROLLS:
        raise ValueError("รองรับ 12 หรือ 24 คำ ได้ %r" % (count,))
    return (count - 1) * WORDS_PER_ROLL + LAST_ROLLS[count]


def roll_bit(roll):
    """ลูกเต๋า 1 ลูก -> 1 บิต · คี่ = 1 · คู่ = 0"""
    r = int(roll)
    if r < 1 or r > 6:
        raise ValueError("ผลทอยต้องเป็น 1-6 ได้ %r" % (roll,))
    return r & 1


def rolls_to_bits(rolls):
    """list ของผลทอย -> list ของบิต"""
    return [roll_bit(r) for r in rolls]


def bits_to_index(bits):
    """11 บิต (ซ้าย = บิตสูง) -> ลำดับคำ 0-2047"""
    if len(bits) != WORDS_PER_ROLL:
        raise ValueError("ต้องมี 11 บิต ได้ %d" % len(bits))
    n = 0
    for b in bits:
        n = (n << 1) | (1 if b else 0)
    return n


def rolls_to_word(rolls, path="english.txt"):
    """ทอย 11 ครั้ง -> 1 คำ"""
    if len(rolls) != WORDS_PER_ROLL:
        raise ValueError("ต้องทอย 11 ครั้งต่อคำ ได้ %d" % len(rolls))
    return bip39.wordlist(path)[bits_to_index(rolls_to_bits(rolls))]


def rolls_to_words(rolls, path="english.txt"):
    """ทอยหลายชุด -> หลายคำ (ความยาวต้องหารด้วย 11 ลงตัว)"""
    if len(rolls) % WORDS_PER_ROLL != 0:
        raise ValueError("จำนวนการทอยต้องหารด้วย 11 ลงตัว ได้ %d" % len(rolls))
    words = bip39.wordlist(path)
    out = []
    for i in range(0, len(rolls), WORDS_PER_ROLL):
        chunk = rolls[i:i + WORDS_PER_ROLL]
        out.append(words[bits_to_index(rolls_to_bits(chunk))])
    return out


def last_word_from_rolls(first_words, rolls, path="english.txt"):
    """เลือกคำสุดท้ายจากผลทอย (23 คำ -> ทอย 3 ครั้ง · 11 คำ -> ทอย 7 ครั้ง)

    🔑 คำสุดท้ายเก็บ entropy k บิต + checksum → มีคำที่ใช้ได้ 2^k คำพอดี
       และ **คำเหล่านั้นเรียงตามตัวอักษร = เรียงตามค่า entropy 0..2^k-1 พอดี**
       (เพราะ entropy อยู่บิตสูงของลำดับคำ ค่ามากขึ้น = ลำดับคำมากขึ้นเสมอ)
       → ทอย k ครั้งได้เลขแล้วหยิบตัวที่ตรงกันได้เลย ไม่มี bias
    """
    count = len(first_words) + 1
    if count not in LAST_ROLLS:
        raise ValueError("ต้องให้ 11 หรือ 23 คำ ได้ %d" % len(first_words))
    k = LAST_ROLLS[count]
    if len(rolls) != k:
        raise ValueError("ต้องทอย %d ครั้ง ได้ %d" % (k, len(rolls)))
    cands = bip39.last_word_candidates(" ".join(first_words), path)
    if len(cands) != (1 << k):
        raise ValueError("คาดว่าจะมี %d ตัวเลือก ได้ %d" % (1 << k, len(cands)))
    idx = 0
    for b in rolls_to_bits(rolls):
        idx = (idx << 1) | b
    return cands[idx], cands


def build_mnemonic(rolls, path="english.txt"):
    """ทอยทั้งหมด -> mnemonic (รู้เองจากจำนวนทอย: 128 = 12 คำ · 256 = 24 คำ)

    คืน (mnemonic, ตัวเลือกคำสุดท้ายทั้งหมด) — ให้จอโชว์ได้ว่าเครื่องเลือกจากอะไร
    """
    n = len(rolls)
    count = None
    for c in LAST_ROLLS:
        if need_rolls(c) == n:
            count = c
    if count is None:
        raise ValueError("ต้องทอยทั้งหมด 128 (12 คำ) หรือ 256 (24 คำ) ครั้ง ได้ %d" % n)
    m = (count - 1) * WORDS_PER_ROLL
    first = rolls_to_words(rolls[:m], path)
    last, cands = last_word_from_rolls(first, rolls[m:], path)
    return " ".join(first + [last]), cands


def check_dice_fairness(rolls, tol=0.25):
    """ตรวจคร่าว ๆ ว่าเต๋าไม่ถ่วง — ใช้กับรอบทดสอบก่อนทอยจริง

    ไม่ใช่การทดสอบทางสถิติที่เข้มงวด แค่จับกรณีเต๋าเสียชัด ๆ
    คืน (ผ่านไหม, ตารางนับ, ข้อความอธิบาย)
    """
    counts = [0] * 7
    for r in rolls:
        v = int(r)
        if v < 1 or v > 6:
            raise ValueError("ผลทอยต้องเป็น 1-6")
        counts[v] += 1
    n = len(rolls)
    if n < 60:
        return False, counts[1:], "ทอยน้อยเกินไป ควรทอยอย่างน้อย 60 ครั้ง"
    expect = n / 6.0
    worst = 0.0
    for v in range(1, 7):
        dev = abs(counts[v] - expect) / expect
        if dev > worst:
            worst = dev
    ok = worst <= tol
    return ok, counts[1:], "หน้าที่เบี่ยงมากสุด %.0f%% (เกณฑ์ %.0f%%)" % (worst * 100, tol * 100)

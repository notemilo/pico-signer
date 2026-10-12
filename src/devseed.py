# devseed.py — seed สำหรับ "ทดสอบเครื่อง" เท่านั้น
#
# 🔴🔴 กระเป๋าทุกใบในไฟล์นี้เป็นของสาธารณะ ใครก็เปิดได้ ห้ามใส่เงินเด็ดขาด 🔴🔴
#
# ทำไมถึงเป็นค่าคงที่ ไม่ใช่การสุ่ม:
#   1. **ไม่ต้องมีโค้ด RNG ในเครื่องเลยสักบรรทัด** — ไม่มีตัวสุ่ม ก็ไม่มีตัวสุ่มให้พัง
#      (บั๊ก RNG ของ Coldcard ก.ค. 2026 ทำเงินหายกว่า $100M · และบน MicroPython
#       พอร์ต rp2 ตอนนี้ os.urandom() ยังดึงจาก ring oscillator ที่เอกสาร
#       Raspberry Pi เตือนเองว่าใช้กับงานความปลอดภัยไม่ได้)
#   2. ผลเหมือนเดิมทุกครั้ง → เทียบผลการทดสอบข้ามรอบได้
#   3. **ไม่มีทางเผลอใช้กับเงิน** เพราะเป็นชุดคำที่เผยแพร่ในเอกสาร BIP39
#      และคู่มือของทุกเจ้า ใครก็กวาดเงินได้ทันที
#
# seed มาจากลูกเต๋าเท่านั้น — ดู dice.py

import bip39

# ⚠️ ห้ามเพิ่มชุดคำที่ "คิดขึ้นเอง" ลงตารางนี้เด็ดขาด
#    ต้องเป็นชุดที่เผยแพร่สาธารณะแล้วเท่านั้น เพื่อให้มั่นใจว่าไม่มีใครเผลอใส่เงิน
_A11 = "abandon " * 11
_A23 = "abandon " * 23
TEST_MNEMONICS = (
    ("vector-12", (_A11 + "about").strip(),
     "BIP39 test vector — entropy เป็นศูนย์ทั้งหมด (12 คำ)"),
    ("vector-24", (_A23 + "art").strip(),
     "BIP39 test vector — entropy เป็นศูนย์ทั้งหมด (24 คำ)"),
    ("vector-alt", "legal winner thank year wave sausage worth useful legal winner thank yellow",
     "BIP39 test vector ชุดที่สอง — ไว้เทสหลายกระเป๋าพร้อมกัน"),
    ("vector-max", ("zoo " * 23 + "vote").strip(),
     "BIP39 test vector — entropy เป็นหนึ่งทั้งหมด (24 คำ)"),
)

WARNING = "!! TEST SEED - PUBLIC - NO REAL FUNDS !!"


def names():
    return [n for n, _, _ in TEST_MNEMONICS]


def get(name="vector-24"):
    """คืน (mnemonic, คำอธิบาย) ของชุดทดสอบ"""
    for n, mn, desc in TEST_MNEMONICS:
        if n == name:
            return mn, desc
    raise ValueError("ไม่รู้จักชุดทดสอบ %r (มี: %s)" % (name, ", ".join(names())))


def is_test_mnemonic(mnemonic):
    """เครื่องใช้ฟังก์ชันนี้ตรวจว่ากำลังใช้ seed ทดสอบอยู่หรือเปล่า

    🔑 นี่คือกันพลาดชั้นที่สำคัญที่สุดของไฟล์นี้:
       ถ้าคืน True หน้าจอต้องขึ้นคำเตือนค้างไว้ตลอด และควรปฏิเสธการเซ็น
       ธุรกรรมที่มียอดเกินที่ตั้งไว้ — กันกรณีลืมว่ากำลังใช้ seed ทดสอบอยู่
    """
    norm = " ".join(str(mnemonic).lower().split())
    for _, mn, _ in TEST_MNEMONICS:
        if norm == mn:
            return True
    return False


def self_check(path="english.txt"):
    """ตรวจว่าทุกชุดในตารางเป็น mnemonic ที่ถูกต้องจริง

    ถ้าพิมพ์ตกไปตัวเดียว checksum จะไม่ผ่าน แล้วจะไปเจอตอนเทสเครื่อง
    ซึ่งเสียเวลาเดาว่าอะไรพัง — ตรวจตรงนี้ให้จบก่อน
    """
    bad = []
    for n, mn, _ in TEST_MNEMONICS:
        if not bip39.is_valid(mn, path):
            bad.append(n)
    return bad

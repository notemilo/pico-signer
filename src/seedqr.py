# seedqr.py — อ่าน CompactSeedQR (ไบต์ดิบจากสแกนเนอร์) กลับเป็น 12/24 คำ
#
# สเปก CompactSeedQR ของ SeedSigner: เนื้อ QR = entropy ดิบ ตัด checksum ออก
#   24 คำ = 32 ไบต์ · 12 คำ = 16 ไบต์  (ตรงกับที่ ui.screen_seedqr สร้าง)
#
# 🔴 ทำไมใช้ scanner.poll() ตัวเดิมไม่ได้:
#    ตัวเดิมตัดบรรทัดที่ CR/LF แล้วทิ้งไบต์ที่ไม่ใช่ ASCII
#    แต่ entropy สุ่ม 32 ไบต์ **มีไบต์เกิน 0x7F แทบทุกครั้ง (100%)**
#    และ **มี 0x0D/0x0A ปนอยู่ ~22%** (วัดด้วยการสุ่ม 20,000 ครั้ง 14 ก.ย. 2026)
#    -> ต้องรับเป็นไบต์ดิบ แล้วตัดเฟรมด้วย "ความยาว + ช่วงเงียบ" แทน CR
#
# 🔴 checksum ถูกตัดทิ้งไปแล้วใน Compact -> **entropy อะไรก็แปลงเป็นคำได้เสมอ**
#    ไบต์เพี้ยนไป 1 บิต = กระเป๋าคนละใบ โดยไม่มี error เตือน
#    กันด้วย 2 ชั้น: (1) ต้องอ่านได้ไบต์ตรงกันติดกัน NEED ครั้ง
#                   (2) ผู้ใช้ต้องเทียบ fingerprint กับที่จดไว้บนกระดาษ
#
# ไฟล์นี้เป็น core (ไม่แตะฮาร์ดแวร์) รันเทสบนแมคได้ ใช้ร่วมกับบอร์ดอื่นได้

import bip39

COMPACT_LENS = (16, 32)      # 12 คำ / 24 คำ (entropy ดิบ)
STANDARD_LENS = (48, 96)     # 12 คำ / 24 คำ (เลขลำดับคำ 4 หลักต่อคำ)


def _all_same(b):
    """ทุกไบต์เหมือนกันหมดไหม

    🔴 16 ก.ย. 2026: สแกนเนอร์ U173 ส่ง FF มา 32 ตัวเมื่ออ่าน QR ไบนารี
       (มันตีความข้อมูลเป็นข้อความ UTF-8 ไบต์ที่ไม่เข้าหลักกลายเป็น FF)
       ความยาวถูก 32 พอดี -> เครื่องรับเป็น seed ได้ทั้งที่เป็นขยะ = กระเป๋าผิดใบ
       entropy จริงที่ทุกไบต์เหมือนกันมีโอกาส 2 ใน 2^248 ถือว่าไม่มีทางเกิด
       (ยกเว้น seed ทดสอบ vector-24 = 00 ล้วน และ vector-max = FF ล้วน
        สองอันนั้นโหลดจากเมนู Test seed ได้อยู่แล้ว ไม่ต้องสแกน)
    """
    for x in b:
        if x != b[0]:
            return False
    return True


def frame_to_entropy(frame):
    """เฟรมที่อ่านได้ 1 ครั้ง -> entropy (bytes) หรือ None ถ้าไม่ใช่ CompactSeedQR

    ค่าโรงงานของโมดูล (D) ปิดท้ายด้วย CR 1 ตัว · รับ CRLF ด้วยเผื่อมีคนไปตั้งค่า
    ตัดหางออกเฉพาะเมื่อความยาวที่เหลือพอดี 16/32 เท่านั้น
    (ห้ามตัด CR ทิ้งแบบไม่ดูความยาว เพราะ CR อาจเป็นไบต์สุดท้ายของ entropy จริง)
    """
    if not frame:
        return None
    b = bytes(frame)
    n = len(b)
    if n - 2 in COMPACT_LENS and b[-2:] == b"\r\n":
        b = b[:-2]
    elif n - 1 in COMPACT_LENS and b[-1] == 0x0D:
        b = b[:-1]
    if len(b) not in COMPACT_LENS:
        return None
    if _all_same(b):
        return None          # ขยะจากสแกนเนอร์ ไม่ใช่ entropy
    return b


def frame_to_mnemonic(frame, path="english.txt"):
    """เฟรมเดียวจากสแกนเนอร์ -> ชุดคำ หรือ None ถ้าไม่ใช่ SeedQR

    รองรับ 2 รูปแบบ:
      Compact  = entropy ดิบ 16/32 ไบต์ (ไม่มี checksum -> ต้องให้ผู้ใช้ยืนยัน FP)
      Standard = เลขลำดับคำ 4 หลักต่อคำ 48/96 ตัว (มี checksum ในตัว ตรวจได้ทันที)
    🔑 สแกนเนอร์ U173 อ่าน Compact ไม่ได้เพราะสแกนเนอร์ทำไบนารีพัง -> ใช้ Standard แทน
    """
    if not frame:
        return None
    b = bytes(frame)
    txt = None
    if len(b) - 2 in STANDARD_LENS and b[-2:] == b"\r\n":
        b = b[:-2]
    elif len(b) - 1 in STANDARD_LENS and b[-1] in (0x0D, 0x0A):
        b = b[:-1]
    if len(b) in STANDARD_LENS:
        ok = True
        for x in b:
            if x < 0x30 or x > 0x39:
                ok = False
                break
        if ok:
            txt = "".join(chr(x) for x in b)
    if txt is not None:
        words = bip39.wordlist(path)
        parts = []
        for i in range(0, len(txt), 4):
            n = int(txt[i:i + 4])
            if n >= len(words):
                return None
            parts.append(words[n])
        mn = " ".join(parts)
        # Standard มี checksum อยู่ในคำสุดท้าย -> ผิดแม้เลขเดียวก็จับได้ทันที
        return mn if bip39.is_valid(mn, path) else None
    ent = frame_to_entropy(frame)
    if ent is None:
        return None
    return entropy_to_mnemonic(ent, path)


def mnemonic_to_standard_digits(mnemonic, path="english.txt"):
    """ชุดคำ -> ข้อความตัวเลขของ Standard SeedQR (4 หลักต่อคำ)"""
    words = bip39.wordlist(path)
    out = []
    for w in mnemonic.split():
        out.append("%04d" % words.index(w))
    return "".join(out)


class Collector:
    """รับเฟรมทีละอัน ยอมรับเมื่อได้ entropy ตรงกัน "ติดกัน" ครบ NEED ครั้ง

    สแกนเนอร์โหมด continuous อ่านซ้ำเองทุก ~1 วินาที -> ครบ 3 ครั้งราว 3 วินาที
    """
    NEED = 3

    def __init__(self, need=None):
        self.need = need or self.NEED
        self._last = None
        self.count = 0

    def add(self, frame, path="english.txt"):
        """คืน "ชุดคำ" เมื่ออ่านได้ตรงกันครบ need ครั้งติด (เดิมคืน entropy)"""
        mn = frame_to_mnemonic(frame, path)
        if mn is None:
            return None
        if mn == self._last:
            self.count += 1
        else:
            self._last = mn
            self.count = 1
        return mn if self.count >= self.need else None


def entropy_to_mnemonic(ent, path="english.txt"):
    return bip39.mnemonic_from_entropy(ent, path)

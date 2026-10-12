# bbqr.py — BBQr: รูปแบบ QR หลายเฟรมที่ Coldcard และ wallet ใช้คุยกัน
#
# รูปแบบ 1 เฟรม:  B$ <enc> <type> <total> <index> <payload>
#                  0-1   2      3      4-5     6-7      8...
#   enc   '2' = base32 (ที่เราใช้) · 'H' = hex · 'Z' = zlib+base32 (ไม่รองรับ)
#   type  'P' = PSBT · 'T' = ธุรกรรมที่ finalize แล้ว · 'J' = JSON · 'C' = CBOR · 'U' = ข้อความ
#   total/index = เลขฐาน 36 สองหลัก ตัวพิมพ์ใหญ่ (00-ZZ = สูงสุด 1295 เฟรม)
#
# 🔑 ทำไมเลือก base32 ไม่ใช่ hex: QR เล็กลง ~37% ที่ข้อมูลเท่ากัน
#    และ A-Z2-7 อยู่ในชุดอักขระ alphanumeric ของ QR → เข้ารหัสได้แน่นกว่าตัวพิมพ์เล็ก
#
# ⚠️ เขียนให้ยกไปวางบน MicroPython ได้ตรง ๆ: ไม่ใช้ typing / int(s,36) / re
#    (ต่อสายกับ src/ อื่น ๆ ในโปรเจกต์นี้ที่ยึดกฎเดียวกัน)

_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_B32B = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

MAX_PARTS = 1295          # 36^2 - 1
_HEADER = 8


def _b36_encode2(n):
    """เลขฐาน 36 สองหลัก เช่น 0 -> '00', 35 -> '0Z', 1295 -> 'ZZ'"""
    if n < 0 or n > MAX_PARTS:
        raise ValueError("เลขเฟรมเกินช่วง")
    return _B36[n // 36] + _B36[n % 36]


def _b36_decode2(s):
    """คืน -1 ถ้าไม่ใช่ฐาน 36 สองหลักที่ถูกต้อง (ไม่ throw — ผู้เรียกเช็คเอง)"""
    if len(s) != 2:
        return -1
    hi = _B36.find(s[0])
    lo = _B36.find(s[1])
    if hi < 0 or lo < 0:
        return -1
    return hi * 36 + lo


def b32_encode(data):
    """base32 RFC4648 ไม่ใส่ = ท้าย (ตรงกับฝั่ง wallet)

    🔴 27 ก.ย. 2026 บอร์ด ESP32 ที่ไม่มี PSRAM ดับตอนสร้าง QR ของ PSBT ที่เซ็นแล้ว (MemoryError 4096 ไบต์ ในฟังก์ชันนี้)
       เดิม val สะสมบิตไม่เคยตัดทิ้ง → PSBT 600 ไบต์ = เลข 4,800 บิต จองแรมก้อนใหม่ทุกไบต์ → แรมแตกเป็นเศษ
       + เก็บผลเป็น list ของตัวอักษร (4 ไบต์ต่อตัว) ต้องขยายเป็นก้อนติดกันหลาย KB
       แก้: ตัด val เหลือ 13 บิต (ก่อนเลื่อนเหลือไม่ถึง 5 บิต + 8 ใหม่) · เขียนลง bytearray ที่จองครั้งเดียว
    """
    out = bytearray((len(data) * 8 + 4) // 5)
    j = 0
    bits = 0
    val = 0
    for b in data:
        val = ((val << 8) | b) & 0x1FFF
        bits += 8
        while bits >= 5:
            bits -= 5
            out[j] = _B32B[(val >> bits) & 31]
            j += 1
    if bits > 0:
        out[j] = _B32B[(val << (5 - bits)) & 31]
        j += 1
    return bytes(out[:j]).decode()


def b32_decode(s):
    """คืน bytes · คืน None ถ้ามีอักขระนอกชุด (ไม่ throw)"""
    out = bytearray()
    bits = 0
    val = 0
    for ch in s:
        v = _B32.find(ch)
        if v < 0:
            return None
        val = ((val << 5) | v) & 0x1FFF        # ตัดทิ้งเหมือน b32_encode (เดิมสะสมเป็นเลขยักษ์)
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((val >> bits) & 0xFF)
    return bytes(out)


def _hex_decode(s):
    if len(s) == 0 or len(s) % 2 != 0:
        return None
    out = bytearray()
    for i in range(0, len(s), 2):
        hi = _B36.find(s[i].upper())
        lo = _B36.find(s[i + 1].upper())
        if hi < 0 or hi > 15 or lo < 0 or lo > 15:
            return None
        out.append(hi * 16 + lo)
    return bytes(out)


def encode(data, type_="P", max_chunk=600):
    """bytes -> list ของสตริง QR

    max_chunk 600 = QR ราว version 14-16 · ค่านี้ลอกจาก wallet ซึ่งลองกับ
    กล้อง Coldcard มาแล้วว่าอ่านออกชัวร์ (เคยใช้ 1000 แล้ว Q อ่านไม่ออก)
    """
    if len(type_) != 1:
        raise ValueError("type ต้องเป็นตัวอักษรเดียว")
    payload = b32_encode(data)
    # 🔑 ตัดให้ลงตัว 8 ตัวอักษร = 5 ไบต์พอดี → แต่ละเฟรมถอดเองได้ ไม่ต้องรอต่อกันครบ
    #    (wallet ต่อสตริงก่อนถอดอยู่แล้ว ทำแบบนี้เข้ากันได้ทั้งสองทาง และตรงสเปกกว่า)
    chunk = ((max_chunk - _HEADER) // 8) * 8
    if chunk < 8:
        raise ValueError("max_chunk เล็กเกินไป")
    total = (len(payload) + chunk - 1) // chunk
    if total < 1:
        total = 1
    if total > MAX_PARTS:
        raise ValueError("ข้อมูลใหญ่เกิน BBQr")
    tot_s = _b36_encode2(total)
    parts = []
    for i in range(total):
        parts.append("B$2" + type_ + tot_s + _b36_encode2(i) + payload[i * chunk:(i + 1) * chunk])
    return parts


class Decoder:
    """สะสมเฟรมที่สแกนได้ทีละใบ — ใช้กับสแกนเนอร์ที่ยิงมาเรื่อย ๆ

        d = Decoder()
        d.add(text)          -> True ถ้าเป็นเฟรม BBQr ที่รับไว้ (False = ไม่ใช่/ซ้ำ/เสีย)
        d.have, d.total      -> ความคืบหน้าสำหรับโชว์บนจอ
        d.done               -> ครบหรือยัง
        d.result()           -> (bytes, type) เมื่อครบ · None เมื่อยังไม่ครบ
    """

    MAX_PART_CHARS = 4000

    def __init__(self):
        self.reset()

    def reset(self):
        self._parts = {}
        self.total = 0
        self.type = None
        self.enc = None

    @property
    def have(self):
        return len(self._parts)

    @property
    def done(self):
        return self.total > 0 and len(self._parts) >= self.total

    def add(self, text):
        if not text or len(text) < 9 or len(text) > self.MAX_PART_CHARS:
            return False
        if text[0] != "B" or text[1] != "$":
            return False
        enc = text[2]
        typ = text[3]
        if enc not in ("H", "2", "Z"):
            return False
        tot = _b36_decode2(text[4:6])
        idx = _b36_decode2(text[6:8])
        if tot < 1 or tot > MAX_PARTS:
            return False
        if idx < 0 or idx >= tot:
            return False
        # ⚠️ ล็อก total/type/encoding ตั้งแต่เฟรมแรก — เฟรมหลังที่ไม่ตรงคือคนละชุด ทิ้ง
        #    (กันสแกนสองชุดปนกันแล้วได้ข้อมูลมั่ว ซึ่งอันตรายกว่าสแกนไม่ติด)
        if self.total == 0:
            self.total = tot
            self.type = typ
            self.enc = enc
        elif tot != self.total or typ != self.type or enc != self.enc:
            return False
        if idx in self._parts:
            return False        # ซ้ำ — ไม่ใช่ error แต่ไม่นับเพิ่ม
        self._parts[idx] = text[8:]
        return True

    def result(self):
        if not self.done:
            return None
        payload = "".join(self._parts[i] for i in range(self.total))
        if self.enc == "2":
            data = b32_decode(payload)
        elif self.enc == "H":
            data = _hex_decode(payload)
        else:
            return None          # 'Z' (zlib) ยังไม่รองรับ — Coldcard/wallet ไม่ได้ใช้
        if data is None:
            return None
        return (data, self.type)


def decode(parts):
    """ถอดจาก list ทั้งชุดในทีเดียว — คืน (bytes, type) หรือ None"""
    d = Decoder()
    for p in parts:
        d.add(p)
    return d.result()

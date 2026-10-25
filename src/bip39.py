"""BIP39 — mnemonic กับ seed

เขียนให้รันได้ทั้ง CPython (ตอนพัฒนา/เทสบนแมค) และ MicroPython (ตอนลงบอร์ด)
ข้อจำกัดที่ตั้งใจ: ไม่ใช้ typing, ไม่ใช้ unicodedata, ไม่ใช้ hmac ของ stdlib
"""

from hashes import sha256, pbkdf2_hmac_sha512

_WORDLIST = None


class WordList:
    """รายการคำ 2,048 คำเก็บเป็น "ก้อนเดียว" (ไบต์ทั้งไฟล์ + ตารางตำแหน่ง) แทน list ของ str 2,048 ชิ้น

    🔴 15 ต.ค. 2026: เครื่อง CRASH (MemoryError) ตอนโหลดรายการคำเพื่อถอด SeedQR (crash.txt: bip39.py listcomp)
       วัดบน Pico: list 2,048 str กินแรม 68 KB และหั่นแรมเป็นเศษ — ก้อนติดกันใหญ่สุดเหลือ 28 KB
       แบบนี้: ไฟล์ ~13 KB + ตารางตำแหน่ง 4 KB = 2 ก้อน · ไม่ทิ้งเศษ
    ใช้ได้เหมือน list ในส่วนที่โค้ดใช้: [i] · index(w) · len · for · in · with_prefix(p)
    🔑 รายการ BIP39 ภาษาอังกฤษเรียงตามตัวอักษร → index/with_prefix ใช้ binary search (ตรวจตอนโหลด)
    """

    def __init__(self, data):
        if b"\r" in data:
            data = data.replace(b"\r", b"")
        data = data.strip()
        starts = [0]
        i = data.find(b"\n")
        while i >= 0:
            starts.append(i + 1)
            i = data.find(b"\n", i + 1)
        if len(starts) != 2048:
            raise ValueError("wordlist ต้องมี 2048 คำ ได้ %d" % len(starts))
        try:
            from array import array
            self._s = array("H", starts)        # ตำแหน่งเริ่มของแต่ละคำ (ไฟล์ < 64 KB)
        except ImportError:
            self._s = starts
        self._d = bytes(data)
        prev = b""
        for k in range(2048):
            w = self._raw(k)
            if not w or w <= prev:
                raise ValueError("wordlist ต้องเรียงตามตัวอักษรและไม่ว่าง (คำที่ %d)" % (k + 1))
            prev = w

    def _raw(self, k):
        e = self._s[k + 1] - 1 if k < 2047 else len(self._d)
        return self._d[self._s[k]:e]

    def __len__(self):
        return 2048

    def __getitem__(self, k):
        if k < 0:
            k += 2048
        if k < 0 or k >= 2048:
            raise IndexError("wordlist index")
        return self._raw(k).decode()

    def __iter__(self):
        for k in range(2048):
            yield self._raw(k).decode()

    def _lower(self, b):
        """ลำดับแรกที่คำ >= b"""
        lo, hi = 0, 2048
        while lo < hi:
            mid = (lo + hi) // 2
            if self._raw(mid) < b:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def index(self, w):
        b = w.encode() if isinstance(w, str) else bytes(w)
        k = self._lower(b)
        if k < 2048 and self._raw(k) == b:
            return k
        raise ValueError("not in wordlist")

    def __contains__(self, w):
        try:
            self.index(w)
            return True
        except ValueError:
            return False

    def prefix_range(self, prefix):
        """(ลำดับแรก, ลำดับสุดท้าย+1) ของคำที่ขึ้นต้นด้วย prefix — ไม่จองแรมเป็นก้อน

        🔴 25 ต.ค. 2026: CRASH MemoryError ตอนเข้า EXISTING SEED > พิมพ์คำ (crash.txt: with_prefix ← next_letters)
           หน้าตัวอักษรแรก prefix = "" → with_prefix สร้าง list คำครบ 2,048 คำ (~68 KB) ทุกครั้ง
           ผู้เรียกที่ต้องการแค่ "มีกี่คำ / ตัวอักษรถัดไป" ใช้ช่วงนี้แทน
        """
        b = prefix.encode()
        # คำในรายการเป็นตัวพิมพ์เล็กล้วน → ทุกคำที่ขึ้นต้นด้วย b น้อยกว่า b + 0xFF
        return self._lower(b), self._lower(b + b"\xff")

    def with_prefix(self, prefix, limit=2048):
        """คำที่ขึ้นต้นด้วย prefix (เรียงตามตัวอักษร) ไม่เกิน limit คำ — ไม่ต้องไล่ทั้ง 2,048 คำ"""
        lo, hi = self.prefix_range(prefix)
        return [self._raw(k).decode() for k in range(lo, min(hi, lo + limit))]


def wordlist(path="english.txt"):
    """โหลด wordlist ครั้งเดียวแล้วจำไว้ (แบบก้อนเดียว — ดู WordList)"""
    global _WORDLIST
    if _WORDLIST is None:
        with open(path, "rb") as f:
            _WORDLIST = WordList(f.read())
    return _WORDLIST


def release_wordlist():
    """ปล่อยรายการคำคืนแรม — เรียกครั้งหน้าจะอ่านไฟล์ใหม่เอง

    🔑 15 ต.ค. 2026: วัดบน Pico รายการ 2,048 คำกินแรม 68 KB และเดิมค้างไว้ตลอดหลังใส่ seed
       (test seed ไม่โหลดรายการนี้ — เครื่องค้าง/แรมหมดจึงเกิดเฉพาะตอนใช้ seed )
    """
    global _WORDLIST
    _WORDLIST = None


def _bits_from_entropy(entropy):
    """คืนสตริงบิต = entropy + checksum"""
    if len(entropy) not in (16, 20, 24, 28, 32):
        raise ValueError("entropy ต้องเป็น 16/20/24/28/32 ไบต์")
    bits = "".join("{:08b}".format(b) for b in entropy)
    checksum_len = len(entropy) * 8 // 32
    checksum = "{:08b}".format(sha256(entropy)[0])[:checksum_len]
    # checksum ยาวเกิน 8 บิตได้ถ้า entropy 32 ไบต์ (8 บิตพอดี) จึงใช้ไบต์แรกพอ
    if checksum_len > 8:
        raise ValueError("checksum ยาวเกินที่รองรับ")
    return bits + checksum


def mnemonic_from_entropy(entropy, path="english.txt"):
    """entropy (bytes) -> ประโยค mnemonic"""
    words = wordlist(path)
    bits = _bits_from_entropy(entropy)
    out = []
    for i in range(0, len(bits), 11):
        out.append(words[int(bits[i:i + 11], 2)])
    return " ".join(out)


def mnemonic_to_entropy(mnemonic, path="english.txt"):
    """mnemonic -> entropy (bytes) พร้อมตรวจ checksum ผิดจะ raise"""
    words = wordlist(path)
    parts = mnemonic.split()
    if len(parts) not in (12, 15, 18, 21, 24):
        raise ValueError("จำนวนคำต้องเป็น 12/15/18/21/24 ได้ %d" % len(parts))
    bits = ""
    for w in parts:
        try:
            bits += "{:011b}".format(words.index(w))
        except ValueError:
            raise ValueError("ไม่พบคำนี้ใน wordlist (คำที่ %d)" % (parts.index(w) + 1))  # ไม่ใส่ตัวคำ — อาจเป็นคำ seed (13 ต.ค. 2026)
    checksum_len = len(parts) * 11 // 33
    entropy_bits, checksum_bits = bits[:-checksum_len], bits[-checksum_len:]
    entropy = bytes(int(entropy_bits[i:i + 8], 2) for i in range(0, len(entropy_bits), 8))
    if "{:08b}".format(sha256(entropy)[0])[:checksum_len] != checksum_bits:
        raise ValueError("checksum ไม่ถูกต้อง")
    return entropy


def is_valid(mnemonic, path="english.txt"):
    try:
        mnemonic_to_entropy(mnemonic, path)
        return True
    except ValueError:
        return False


def last_word_candidates(partial, path="english.txt"):
    """ให้ 11/14/17/20/23 คำ คืนคำสุดท้ายทุกคำที่ทำให้ checksum ถูก

    ใช้กับกรณีทอยเต๋าได้ 23 คำแล้วต้องหาคำที่ 24

    ⚡ คำนวณตรง ๆ ไม่ไล่ลองทีละคำ:
       คำสุดท้ายประกอบด้วย entropy ที่เหลือ + checksum
       ลองเฉพาะค่า entropy ที่เป็นไปได้ (8 ค่าสำหรับ 24 คำ · 128 สำหรับ 12 คำ)
       แล้วคำนวณ checksum ของแต่ละค่า → ได้ลำดับคำตรง ๆ
       (ของเดิมไล่ทุกคำใน 2,048 คำแล้วตรวจ checksum ทีละคำ — บนบอร์ดจริง
        ใช้เวลา 72 วินาที ซึ่งช้าเกินรับได้ · แบบนี้เหลือระดับมิลลิวินาที)

    🔑 ผลลัพธ์เรียงจากค่า entropy น้อยไปมาก ซึ่ง**ตรงกับลำดับตัวอักษร**พอดี
       เพราะ entropy อยู่บิตสูงของลำดับคำ (dice.py พึ่งคุณสมบัตินี้)
    """
    words = wordlist(path)
    parts = partial.split() if isinstance(partial, str) else list(partial)
    n = len(parts)
    if n not in (11, 14, 17, 20, 23):
        raise ValueError("ต้องให้ 11/14/17/20/23 คำ ได้ %d" % n)

    total_words = n + 1
    checksum_len = total_words * 11 // 33          # 4/5/6/7/8 บิต
    ent_bits_in_last = 11 - checksum_len           # บิต entropy ที่อยู่ในคำสุดท้าย

    bits = ""
    for w in parts:
        try:
            bits += "{:011b}".format(words.index(w))
        except ValueError:
            raise ValueError("ไม่พบคำนี้ใน wordlist (คำที่ %d)" % (parts.index(w) + 1))  # ไม่ใส่ตัวคำ — อาจเป็นคำ seed (13 ต.ค. 2026)

    out = []
    for v in range(1 << ent_bits_in_last):
        full = bits + "{:0{}b}".format(v, ent_bits_in_last)
        entropy = bytes(int(full[i:i + 8], 2) for i in range(0, len(full), 8))
        cs = "{:08b}".format(sha256(entropy)[0])[:checksum_len]
        out.append(words[int(full[-ent_bits_in_last:] + cs, 2) if ent_bits_in_last else int(cs, 2)])
    return out


def seed(mnemonic, passphrase=""):
    """mnemonic -> seed 64 ไบต์ (BIP39: PBKDF2-HMAC-SHA512, 2048 รอบ)

    หมายเหตุ: BIP39 กำหนดให้ normalize เป็น NFKD ก่อน
    wordlist อังกฤษเป็น ASCII ล้วน และ NFKD ของ ASCII = ตัวเดิม จึงไม่มีผล

    🔴 13 ต.ค. 2026 (รีวิวภายนอก F-02): MicroPython ไม่มี unicodedata ทำ NFKD ไม่ได้
       อักขระนอก ASCII (เช่น é ที่เขียนได้ 2 แบบ) จะได้ seed ต่างจากกระเป๋าอื่นแบบเงียบ ๆ
       → ปฏิเสธตั้งแต่ระดับฟังก์ชัน (หน้าจอพิมพ์ passphrase ก็รับแค่ ASCII อยู่แล้ว · นี่คือด่านกันพลาด)
    """
    for label, txt in (("mnemonic", mnemonic), ("passphrase", passphrase)):
        for ch in txt:
            if ord(ch) > 0x7E or ord(ch) < 0x20:
                raise ValueError("%s ต้องเป็นตัวอักษรอังกฤษ/สัญลักษณ์ ASCII เท่านั้น (ทำ NFKD ไม่ได้)" % label)
    return pbkdf2_hmac_sha512(
        mnemonic.encode("utf-8"),
        ("mnemonic" + passphrase).encode("utf-8"),
        2048,
        64,
    )

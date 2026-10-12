"""BIP39 — mnemonic กับ seed

เขียนให้รันได้ทั้ง CPython (ตอนพัฒนา/เทสบนแมค) และ MicroPython (ตอนลงบอร์ด)
ข้อจำกัดที่ตั้งใจ: ไม่ใช้ typing, ไม่ใช้ unicodedata, ไม่ใช้ hmac ของ stdlib
"""

from hashes import sha256, pbkdf2_hmac_sha512

_WORDLIST = None


def wordlist(path="english.txt"):
    """โหลด wordlist ครั้งเดียวแล้วจำไว้"""
    global _WORDLIST
    if _WORDLIST is None:
        with open(path) as f:
            _WORDLIST = [w.strip() for w in f if w.strip()]
        if len(_WORDLIST) != 2048:
            raise ValueError("wordlist ต้องมี 2048 คำ ได้ %d" % len(_WORDLIST))
    return _WORDLIST


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

# qr.py — สร้าง QR Code (ISO/IEC 18004) เพื่อคายผลลัพธ์ออกทางจอ
#
# ทำไมต้องเขียนเอง: MicroPython ไม่มีให้ และเครื่องเซ็นต้อง air-gap
# ทางเดียวที่ข้อมูลออกจากเครื่องได้คือ "แสดงบนจอให้กล้องอ่าน"
#
# รองรับ 2 โหมด:
#   alphanumeric — 0-9 A-Z และ space $%*+-./: · 11 บิตต่อ 2 ตัวอักษร
#   byte         — ข้อมูลอะไรก็ได้ · 8 บิตต่อ 1 ไบต์
# 🔑 BBQr เป็นตัวพิมพ์ใหญ่ + ตัวเลข + '$' ล้วน = เข้าโหมด alphanumeric ได้ทั้งหมด
#    ทำให้ QR เล็กลงกว่า byte mode ราว 27% ที่ข้อมูลเท่ากัน (สแกนง่ายขึ้นมาก)
#
# ⚠️ เขียนให้ยกไปวางบน MicroPython ได้: ไม่ใช้ typing / f-string / ไลบรารีนอก

ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"

# EC ระดับต่าง ๆ — ค่าที่ใช้ในบิต format info (ไม่เรียงตามความแข็งแรง)
EC_L = 0
EC_M = 1
EC_Q = 2
EC_H = 3
_EC_FMT = {EC_L: 1, EC_M: 0, EC_Q: 3, EC_H: 2}

# จำนวน codeword ทั้งหมดของแต่ละเวอร์ชัน (1-40)
_TOTAL_CW = (
    26, 44, 70, 100, 134, 172, 196, 242, 292, 346,
    404, 466, 532, 581, 655, 733, 815, 901, 991, 1085,
    1156, 1258, 1364, 1474, 1588, 1706, 1828, 1921, 2051, 2185,
    2323, 2465, 2611, 2761, 2876, 3034, 3196, 3362, 3532, 3706,
)

# (จำนวน EC codeword ต่อบล็อก, จำนวนบล็อก) เรียง L, M, Q, H ในแต่ละเวอร์ชัน
# 🔑 เก็บแค่ 2 ตัวนี้พอ — ขนาดข้อมูลต่อบล็อกคำนวณเอาได้ (ดู _blocks_for)
_ECC = (
    ((7,1),(10,1),(13,1),(17,1)),      ((10,1),(16,1),(22,1),(28,1)),
    ((15,1),(26,1),(18,2),(22,2)),     ((20,1),(18,2),(26,2),(16,4)),
    ((26,1),(24,2),(18,4),(22,4)),     ((18,2),(16,4),(24,4),(28,4)),
    ((20,2),(18,4),(18,6),(26,5)),     ((24,2),(22,4),(22,6),(26,6)),
    ((30,2),(22,5),(20,8),(24,8)),     ((18,4),(26,5),(24,8),(28,8)),
    ((20,4),(30,5),(28,8),(24,11)),    ((24,4),(22,8),(26,10),(28,11)),
    ((26,4),(22,9),(24,12),(22,16)),   ((30,4),(24,9),(20,16),(24,16)),
    ((22,6),(24,10),(30,12),(24,18)),  ((24,6),(28,10),(24,17),(30,16)),
    ((28,6),(28,11),(28,16),(28,19)),  ((30,6),(26,13),(28,18),(28,21)),
    ((28,7),(26,14),(26,21),(26,25)),  ((28,8),(26,16),(30,20),(28,25)),
    ((28,8),(26,17),(28,23),(30,25)),  ((28,9),(28,17),(30,23),(24,34)),
    ((30,9),(28,18),(30,25),(30,30)),  ((30,10),(28,20),(30,27),(30,32)),
    ((26,12),(28,21),(30,29),(30,35)), ((28,12),(28,23),(28,34),(30,37)),
    ((30,12),(28,25),(30,34),(30,40)), ((30,13),(28,26),(30,35),(30,42)),
    ((30,14),(28,28),(30,38),(30,45)), ((30,15),(28,29),(30,40),(30,48)),
    ((30,16),(28,31),(30,43),(30,51)), ((30,17),(28,33),(30,45),(30,54)),
    ((30,18),(28,35),(30,48),(30,57)), ((30,19),(28,37),(30,51),(30,60)),
    ((30,19),(28,38),(30,53),(30,63)), ((30,20),(28,40),(30,56),(30,66)),
    ((30,21),(28,43),(30,59),(30,70)), ((30,22),(28,45),(30,62),(30,74)),
    ((30,24),(28,47),(30,65),(30,77)), ((30,25),(28,49),(30,68),(30,81)),
)

# ตำแหน่งกึ่งกลางของ alignment pattern (เวอร์ชัน 1 ไม่มี)
_ALIGN = (
    (), (6,18), (6,22), (6,26), (6,30), (6,34),
    (6,22,38), (6,24,42), (6,26,46), (6,28,50), (6,30,54), (6,32,58), (6,34,62),
    (6,26,46,66), (6,26,48,70), (6,26,50,74), (6,30,54,78), (6,30,56,82),
    (6,30,58,86), (6,34,62,90),
    (6,28,50,72,94), (6,26,50,74,98), (6,30,54,78,102), (6,28,54,80,106),
    (6,32,58,84,110), (6,30,58,86,114), (6,34,62,90,118),
    (6,26,50,74,98,122), (6,30,54,78,102,126), (6,26,52,78,104,130),
    (6,30,56,82,108,134), (6,34,60,86,112,138), (6,30,58,86,114,142),
    (6,34,62,90,118,146),
    (6,30,54,78,102,126,150), (6,24,50,76,102,128,154), (6,28,54,80,106,132,158),
    (6,32,58,84,110,136,162), (6,26,54,82,110,138,166), (6,30,58,86,114,142,170),
)

# ─── เลขคณิตบนสนามจำกัด GF(256) สำหรับ Reed-Solomon ────────────────────
_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D           # พหุนามลดทอนของ QR
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n):
    """พหุนามกำเนิดดีกรี n"""
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j in range(len(g)):
            ng[j] ^= g[j]
            ng[j + 1] ^= _gf_mul(g[j], _EXP[i])
        g = ng
    return g


def _rs_ec(data, n):
    """คำนวณ EC codeword n ตัวจากข้อมูล"""
    gen = _rs_generator(n)
    rem = [0] * n
    for d in data:
        factor = d ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(n):
            rem[i] ^= _gf_mul(gen[i + 1], factor)
    return rem


# ─── ตัวช่วยเรื่องบิต ────────────────────────────────────────────────────
class _Bits:
    def __init__(self):
        self.buf = bytearray()
        self.n = 0

    def put(self, val, length):
        for i in range(length - 1, -1, -1):
            if self.n % 8 == 0:
                self.buf.append(0)
            if (val >> i) & 1:
                self.buf[self.n >> 3] |= 0x80 >> (self.n & 7)
            self.n += 1


def _blocks_for(version, ec):
    """คืน (จำนวน EC ต่อบล็อก, list ของขนาดข้อมูลแต่ละบล็อก)"""
    ecw, nblocks = _ECC[version - 1][ec]
    total_data = _TOTAL_CW[version - 1] - ecw * nblocks
    short_len = total_data // nblocks
    n_long = total_data % nblocks          # บล็อกที่ยาวกว่า 1 ไบต์
    sizes = [short_len] * (nblocks - n_long) + [short_len + 1] * n_long
    return ecw, sizes


def _capacity_bits(version, ec):
    ecw, sizes = _blocks_for(version, ec)
    return sum(sizes) * 8


def _cci_bits(version, mode):
    """จำนวนบิตของตัวนับความยาว ขึ้นกับเวอร์ชันและโหมด"""
    if mode == "num":
        return 10 if version <= 9 else (12 if version <= 26 else 14)
    if mode == "alnum":
        return 9 if version <= 9 else (11 if version <= 26 else 13)
    return 8 if version <= 9 else 16        # byte


def _can_alnum(s):
    for ch in s:
        if ALNUM.find(ch) < 0:
            return False
    return True


def _can_num(s):
    """ตัวเลขล้วน — โหมดนี้กินที่น้อยสุด 10 บิตต่อ 3 ตัว

    🔑 ใช้กับ Standard SeedQR (เลขลำดับคำ 4 หลัก x 12/24 คำ = 48/96 ตัว)
       24 คำ: โหมดตัวเลขได้ QR 29x29 · โหมด alphanumeric ต้องใช้ 33x33
       = วาดมือน้อยลง 248 ช่อง
    """
    if not s:
        return False
    for ch in s:
        if ch < "0" or ch > "9":
            return False
    return True


def _encode_payload(data, version, mode):
    b = _Bits()
    if mode == "num":
        b.put(0b0001, 4)
        b.put(len(data), _cci_bits(version, mode))
        i = 0
        while i + 2 < len(data):
            b.put(int(data[i:i + 3]), 10)
            i += 3
        left = len(data) - i
        if left == 2:
            b.put(int(data[i:i + 2]), 7)
        elif left == 1:
            b.put(int(data[i]), 4)
    elif mode == "alnum":
        b.put(0b0010, 4)
        b.put(len(data), _cci_bits(version, mode))
        i = 0
        while i + 1 < len(data):
            b.put(ALNUM.index(data[i]) * 45 + ALNUM.index(data[i + 1]), 11)
            i += 2
        if i < len(data):
            b.put(ALNUM.index(data[i]), 6)
    else:
        b.put(0b0100, 4)
        b.put(len(data), _cci_bits(version, mode))
        for byte in data:
            b.put(byte, 8)
    return b


def _pick_version(data, ec, mode, min_version=1):
    for v in range(min_version, 41):
        need = _encode_payload(data, v, mode).n
        if need + 4 <= _capacity_bits(v, ec) or need <= _capacity_bits(v, ec):
            if need <= _capacity_bits(v, ec):
                return v
    raise ValueError("ข้อมูลใหญ่เกินกว่า QR จะเก็บได้")


def _make_codewords(data, version, ec, mode):
    b = _Bits()
    payload = _encode_payload(data, version, mode)
    b.buf = payload.buf
    b.n = payload.n
    cap = _capacity_bits(version, ec)
    # terminator ไม่เกิน 4 บิต
    for _ in range(min(4, cap - b.n)):
        b.put(0, 1)
    # เติมให้เต็มไบต์
    while b.n % 8:
        b.put(0, 1)
    # เติมไบต์สลับ 0xEC / 0x11 จนเต็ม
    pad = (0xEC, 0x11)
    i = 0
    while b.n < cap:
        b.put(pad[i & 1], 8)
        i += 1

    ecw, sizes = _blocks_for(version, ec)
    raw = bytes(b.buf)
    blocks = []
    ecblocks = []
    pos = 0
    for sz in sizes:
        chunk = raw[pos:pos + sz]
        pos += sz
        blocks.append(chunk)
        ecblocks.append(_rs_ec(chunk, ecw))
    # สานข้อมูลสลับบล็อก (interleave) ตามสเปก
    out = bytearray()
    for i in range(max(sizes)):
        for blk in blocks:
            if i < len(blk):
                out.append(blk[i])
    for i in range(ecw):
        for eb in ecblocks:
            out.append(eb[i])
    return bytes(out)


# ─── วางลวดลายลงตาราง ──────────────────────────────────────────────────
def _bch_format(fmt):
    d = fmt << 10
    for i in range(4, -1, -1):
        if d & (1 << (i + 10)):
            d ^= 0x537 << i
    return ((fmt << 10) | d) ^ 0x5412


def _bch_version(ver):
    d = ver << 12
    for i in range(5, -1, -1):
        if d & (1 << (i + 12)):
            d ^= 0x1F25 << i
    return (ver << 12) | d


def _mask_fn(m, r, c):
    if m == 0: return (r + c) % 2 == 0
    if m == 1: return r % 2 == 0
    if m == 2: return c % 3 == 0
    if m == 3: return (r + c) % 3 == 0
    if m == 4: return (r // 2 + c // 3) % 2 == 0
    if m == 5: return (r * c) % 2 + (r * c) % 3 == 0
    if m == 6: return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


def _new_matrix(version):
    size = version * 4 + 17
    mod = [[0] * size for _ in range(size)]      # 0/1 = สี
    fixed = [[False] * size for _ in range(size)]  # True = ห้ามเขียนทับด้วยข้อมูล

    def finder(r0, c0):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if not (0 <= rr < size and 0 <= cc < size):
                    continue
                inner = (0 <= r <= 6 and c in (0, 6)) or (0 <= c <= 6 and r in (0, 6)) \
                    or (2 <= r <= 4 and 2 <= c <= 4)
                mod[rr][cc] = 1 if inner else 0
                fixed[rr][cc] = True

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)

    # timing pattern
    for i in range(8, size - 8):
        mod[6][i] = mod[i][6] = 1 if i % 2 == 0 else 0
        fixed[6][i] = fixed[i][6] = True

    # alignment
    # ⚠️ กฎที่ถูกคือ "ข้ามเฉพาะ 3 มุมที่ทับ finder pattern" เท่านั้น
    #    เคยเขียนเป็น `if fixed[r][c]: continue` ซึ่งพลอยข้ามอันที่จุดกึ่งกลาง
    #    อยู่บนเส้น timing ไปด้วย (เช่น (6,22)) → เหลือช่องว่างเกินมา 40 ช่อง
    #    ข้อมูลทั้งแผ่นเลื่อนตำแหน่งหมด กล้องอ่านไม่ออก
    coords = _ALIGN[version - 1]
    n = len(coords)
    for i in range(n):
        for j in range(n):
            if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                continue
            r, c = coords[i], coords[j]
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    mod[r + dr][c + dc] = 1 if (max(abs(dr), abs(dc)) != 1) else 0
                    fixed[r + dr][c + dc] = True

    # จุดดำบังคับ + พื้นที่ format info
    mod[size - 8][8] = 1
    fixed[size - 8][8] = True
    for i in range(9):
        if not fixed[8][i]:
            fixed[8][i] = True
        if not fixed[i][8]:
            fixed[i][8] = True
    for i in range(8):
        fixed[8][size - 1 - i] = True
        fixed[size - 1 - i][8] = True

    # version info (เวอร์ชัน 7 ขึ้นไป)
    if version >= 7:
        bits = _bch_version(version)
        for i in range(18):
            b = (bits >> i) & 1
            r, c = i // 3, i % 3
            mod[size - 11 + c][r] = b
            fixed[size - 11 + c][r] = True
            mod[r][size - 11 + c] = b
            fixed[r][size - 11 + c] = True
    return mod, fixed, size


def _place_data(mod, fixed, size, cw):
    bitidx = 0
    total = len(cw) * 8
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:        # ข้ามคอลัมน์ timing
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if fixed[r][c]:
                    continue
                bit = 0
                if bitidx < total:
                    bit = (cw[bitidx >> 3] >> (7 - (bitidx & 7))) & 1
                    bitidx += 1
                mod[r][c] = bit
        upward = not upward
        col -= 2


def _penalty(m, size):
    """คะแนนโทษตามสเปก (ยิ่งน้อยยิ่งดี) — ใช้เลือก mask

    ⚡ เขียนด้วยการค้นหาในสตริงแทนการวนทีละช่อง เพราะบน RP2350 แบบวนลูป
       ใช้เวลา 1,339 ms ต่อ mask x8 mask = 10.7 วินาที ต่อ QR หนึ่งใบ
       ซึ่งช้าเกินรับได้ · str.count / str.find ทำงานในภาษา C จึงเร็วกว่ามาก
       ผลลัพธ์ต้องเท่าเดิมทุกกรณี (เทสไขว้กับไลบรารีมาตรฐานเป็นตัวยืนยัน)
    """
    rows = ["".join("1" if v else "0" for v in row) for row in m]
    cols = ["".join(rows[r][c] for r in range(size)) for c in range(size)]

    score = 0

    # กฎ 1: ช่องสีเดียวกันเรียงติดกันตั้งแต่ 5 ช่องขึ้นไป
    for lines in (rows, cols):
        for line in lines:
            run = 1
            prev = line[0]
            for ch in line[1:]:
                if ch == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + (run - 5)
                    run = 1
                    prev = ch
            if run >= 5:
                score += 3 + (run - 5)

    # กฎ 2: บล็อก 2x2 สีเดียวกัน
    for r in range(size - 1):
        r0 = rows[r]
        r1 = rows[r + 1]
        for c in range(size - 1):
            v = r0[c]
            if v == r0[c + 1] and v == r1[c] and v == r1[c + 1]:
                score += 3

    # กฎ 3: ลวดลายคล้าย finder pattern (1011101 ตามด้วย/นำหน้าด้วยช่องว่าง 4 ช่อง)
    p1 = "10111010000"
    p2 = "00001011101"
    for lines in (rows, cols):
        for line in lines:
            score += 40 * (line.count(p1) + line.count(p2))

    # กฎ 4: สัดส่วนช่องดำเบี่ยงจาก 50%
    dark = 0
    for line in rows:
        dark += line.count("1")
    pct = dark * 100 // (size * size)
    score += 10 * (abs(pct - 50) // 5)
    return score


def _put_format(mod, size, ec, mask):
    """วางบิต format info 15 บิต ลง 2 ตำแหน่งรอบ finder

    ⚠️ จุดที่พลาดง่ายและเคยพลาดมาแล้ว: บิตแรกที่วาง (ช่อง 8,0) คือ **บิตที่ 14
    (บิตสูงสุด)** ไม่ใช่บิตที่ 0 · ตอนแรกเขียนกลับหัว ผลคือทุกอย่างถูกหมด
    ยกเว้น 13 ช่องรอบ finder → กล้องอ่านไม่ออกเลยทั้งที่ข้อมูลข้างในถูก
    เขียนเป็นตารางพิกัดตรง ๆ จะได้ไม่ต้องเดาลำดับอีก
    """
    bits = _bch_format((_EC_FMT[ec] << 3) | mask)
    # เรียงตามบิตที่ 14 ลงมาถึงบิตที่ 0
    copy1 = ((8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
             (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8))
    copy2 = ((size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
             (size - 5, 8), (size - 6, 8), (size - 7, 8),
             (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
             (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1))
    for i in range(15):
        b = (bits >> (14 - i)) & 1
        mod[copy1[i][0]][copy1[i][1]] = b
        mod[copy2[i][0]][copy2[i][1]] = b


def encode(data, ec=EC_M, min_version=1):
    """สร้าง QR — คืน list ของ list (0/1) ขนาด size x size

    data : str (เข้าโหมด alphanumeric อัตโนมัติถ้าทำได้) หรือ bytes
    ec   : EC_L / EC_M / EC_Q / EC_H
    """
    if isinstance(data, str):
        if _can_num(data):
            mode = "num"
        elif _can_alnum(data):
            mode = "alnum"
        else:
            mode = "byte"
            data = data.encode("utf-8")
    else:
        mode = "byte"
    version = _pick_version(data, ec, mode, min_version)
    cw = _make_codewords(data, version, ec, mode)
    mod, fixed, size = _new_matrix(version)
    _place_data(mod, fixed, size, cw)

    # เลือก mask ที่คะแนนโทษต่ำสุด (สเปกกำหนดให้เลือกแบบนี้)
    best = None
    best_score = -1
    for mask in range(8):
        trial = [row[:] for row in mod]
        for r in range(size):
            for c in range(size):
                if not fixed[r][c] and _mask_fn(mask, r, c):
                    trial[r][c] ^= 1
        _put_format(trial, size, ec, mask)
        sc = _penalty(trial, size)
        if best is None or sc < best_score:
            best, best_score, = trial, sc
    return best


def version_of(matrix):
    return (len(matrix) - 17) // 4


def to_text(matrix, quiet=2, dark="██", light="  "):
    """แสดงเป็นข้อความ — ไว้ดูตอนพัฒนา/เทสบนคอม"""
    size = len(matrix)
    out = []
    blank = light * (size + quiet * 2)
    for _ in range(quiet):
        out.append(blank)
    for row in matrix:
        out.append(light * quiet + "".join(dark if v else light for v in row) + light * quiet)
    for _ in range(quiet):
        out.append(blank)
    return "\n".join(out)


# ── บีบ QR ให้เล็กลงก่อนเก็บไว้หลายเฟรม (20 ก.ย. 2026) ──────────────────
# ทำไม: `encode()` คืน list ซ้อน list — 1 เฟรม 33x33 กินแรมบน Pico ~10KB
#       หน้าโชว์ BBQr เก็บทุกเฟรมพร้อมกัน (xpub 7 เฟรม · PSBT ที่เซ็นแล้ว 12 เฟรม)
#       → 73-125KB ค้างในแรม ทำให้ MemoryError และช้าลงเรื่อย ๆ เพราะ gc ต้องกวาดทุกครั้ง
# แบบนี้: 1 เฟรม = bytearray ก้อนเดียว (33x33 = 165 ไบต์) เก็บ 12 เฟรมไม่ถึง 3KB
# รูปแบบ: (ขนาด, bytearray) · บิตซ้ายสุดของไบต์แรก = ช่อง (0,0)

def pack(matrix):
    """list ซ้อน list -> (n, bytearray) บิตละช่อง"""
    n = len(matrix)
    stride = (n + 7) >> 3
    buf = bytearray(stride * n)
    for r in range(n):
        row = matrix[r]
        base = r * stride
        for c in range(n):
            if row[c]:
                buf[base + (c >> 3)] |= 128 >> (c & 7)
    return n, buf


def packed_get(packed, r, c):
    """อ่านค่าช่อง (r, c) จากรูปแบบบีบ — 0/1"""
    n, buf = packed
    return (buf[r * ((n + 7) >> 3) + (c >> 3)] >> (7 - (c & 7))) & 1


def unpack(packed):
    """คืนเป็น list ซ้อน list เหมือน encode() — ใช้ตอนเทสบนแมค"""
    n, buf = packed
    stride = (n + 7) >> 3
    return [[(buf[r * stride + (c >> 3)] >> (7 - (c & 7))) & 1 for c in range(n)]
            for r in range(n)]

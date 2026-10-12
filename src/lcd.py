# lcd.py — ไดรเวอร์จอ Waveshare Pico-LCD-1.3 (ST7789VW 240x240 IPS)
#
# ขาที่ใช้ (จากเอกสารทางการ Waveshare — บอร์ดเสียบทับ Pico ตรง ๆ ไม่ต้องต่อสาย):
#   DIN=GP11 (MOSI) · CLK=GP10 (SCK) · CS=GP9 · DC=GP8 · RST=GP12 · BL=GP13
#   ปุ่ม A=GP15 B=GP17 X=GP19 Y=GP21
#   จอย  UP=GP2 DOWN=GP18 LEFT=GP16 RIGHT=GP20 CTRL=GP3
#   ⚠️ VCC ของจอกินจาก **VSYS** ไม่ใช่ 3V3
#
# 🔑 ทำไมใช้ framebuf ของ MicroPython: มันเขียนด้วยภาษา C มาแล้ว
#    วาดสี่เหลี่ยม/ตัวอักษรเร็วกว่าวนลูป Python หลายสิบเท่า
#    เฟรมบัฟเฟอร์ 240x240 RGB565 = 115,200 ไบต์ (RAM มี 512 KB พอ)
#
# ⚠️ ไฟล์นี้แตะฮาร์ดแวร์ ทดสอบบนแมคไม่ได้ — ต้องทดสอบบนบอร์ดจริงเท่านั้น
#    ตรรกะที่ตรวจสอบได้ (เช่น แปลงตาราง QR เป็นพิกเซล) แยกไปไว้ที่ฟังก์ชัน
#    ที่ไม่แตะฮาร์ดแวร์ เพื่อให้เทสบนแมคได้

from machine import Pin, SPI
import framebuf

# ── ฟอนต์ตัวใหญ่ (text_big) ─────────────────────────────────────────────
# "sfmono"  = SF Mono Semibold แบบบิตแมป (ผู้ใช้ เลือก 15 ก.ย. 2026 — ฟอนต์เดิมเหลี่ยม ไม่สวย)
# "classic" = ฟอนต์ในตัว MicroPython 8x8 ขยาย (ของเดิม ใช้งานได้ดี ขนาดกำลังดี)
# 🔑 อยากกลับไปใช้ฟอนต์เดิม: เปลี่ยนบรรทัดข้างล่างเป็น "classic" บรรทัดเดียว แล้วส่งไฟล์นี้ขึ้นเครื่อง
#    ช่องตัวอักษรกว้างเท่ากันทั้งสองแบบ (8 x scale) หน้าจอจึงวางเหมือนเดิมทุกหน้า
FONT_STYLE = "sfmono"

# 🔴 โหลดฟอนต์ "ตอนวาดตัวอักษรครั้งแรก" ไม่ใช่ตอน import lcd (แก้ 15 ก.ย. 2026)
#    เจอบนเครื่องจริง: โหลดฟอนต์ (~35KB) ก่อน แล้วค่อยสร้างจอ → จองเฟรมบัฟเฟอร์ 115KB
#    ไม่ได้ (MemoryError) ทั้งที่แรมรวมยังว่าง 353KB เพราะแรมแตกเป็นชิ้น
#    → ปล่อยให้ LCD() จองก้อนใหญ่ก่อนเสมอ แล้วฟอนต์ค่อยตามมา
#    โหลดไม่ขึ้นด้วยเหตุผลใดก็ตาม (ไม่มีไฟล์ / แรมไม่พอ / ไฟล์เสีย) → ใช้ฟอนต์เดิม ไม่ลองซ้ำ
#    🔑 ห้ามปล่อยให้ฟอนต์ทำเครื่องเปิดไม่ขึ้น — จอที่เหลี่ยมยังดีกว่าจอที่ไม่ขึ้น
_FONT = None           # None = ยังไม่ได้ลองโหลด · False = โหลดไม่ขึ้น · module = พร้อมใช้


def _font():
    global _FONT
    if _FONT is None:
        try:
            import font_sfmono            # สร้างด้วย tools/make_font.py
            _FONT = font_sfmono
        except Exception:
            _FONT = False
    return _FONT or None

WIDTH = 240
HEIGHT = 240

# สี RGB565 — **เก็บแบบสลับไบต์แล้ว**
#
# 🔴 กับดักที่เสียเวลาไปรอบหนึ่ง: framebuf ของ MicroPython เก็บ RGB565 ลงบัฟเฟอร์
#    แบบ little-endian แต่ ST7789 อ่านไบต์แรกเป็นไบต์สูง → สีที่ออกจอคือค่าที่
#    ไบต์สลับกัน (RED 0xF800 กลายเป็น 0x00F8 = น้ำเงิน · BLUE กลายเป็นเขียว)
#    แก้ที่ค่าคงที่เลย ไม่ต้องสลับไบต์ตอนส่งทั้งเฟรม (ซึ่งจะช้า)
#
# ⚠️ **ห้ามให้ ผู้ใช้ เป็นคนตรวจว่าสีถูกไหม** — คนตาบอดสี
#    RED→น้ำเงิน กับ GREEN→ชมพู เป็นคู่ที่แยกยากสำหรับเขา รอบแรกจึงหลุดไป
#    ต้องตรวจจากรูปถ่าย หรือคำนวณย้อนจากค่าไบต์เอง


def rgb565(r, g, b):
    """r,g,b 0-255 -> ค่าที่เขียนลง framebuf แล้วออกจอถูกสี (สลับไบต์ให้แล้ว)"""
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((v & 0xFF) << 8) | (v >> 8)


BLACK = 0x0000
WHITE = 0xFFFF
RED = 0x00F8        # 0xF800 สลับไบต์
GREEN = 0xE007      # 0x07E0
BLUE = 0x1F00       # 0x001F
YELLOW = 0xE0FF     # 0xFFE0
ORANGE = 0x00FC     # 0xFC00
GREY = 0x1084       # 0x8410
DARKBLUE = 0x0B00   # 0x000B — พื้นแถบหัวเรื่อง

# ค่า MADCTL 4 ทิศ — index 0..3 (0 = ค่าที่ทดสอบแล้วว่าถูกกับบอร์ดนี้)
# 🔑 หาค่าที่ถูกด้วยการลองจริงบนบอร์ด อย่าเดาจากเอกสาร ทุกโมดูลติดพาเนลไม่เหมือนกัน
MADCTL = (0x60, 0xA0, 0x00, 0xC0)


# ─── ปุ่ม ───────────────────────────────────────────────────────────────
# ทุกปุ่มต่อแบบ pull-up: กด = 0 · ปล่อย = 1
KEYS = {
    "A": 15, "B": 17, "X": 19, "Y": 21,
    "UP": 2, "DOWN": 18, "LEFT": 16, "RIGHT": 20, "CTRL": 3,
}


class Keys:
    def __init__(self):
        self._pins = {n: Pin(g, Pin.IN, Pin.PULL_UP) for n, g in KEYS.items()}

    def pressed(self, name):
        return self._pins[name].value() == 0

    def any_pressed(self):
        return [n for n, p in self._pins.items() if p.value() == 0]


class LCD(framebuf.FrameBuffer):
    def __init__(self, rotate=0):
        self.width = WIDTH
        self.height = HEIGHT
        self._cs = Pin(9, Pin.OUT, value=1)
        self._dc = Pin(8, Pin.OUT, value=0)
        self._rst = Pin(12, Pin.OUT, value=1)
        self._bl = Pin(13, Pin.OUT, value=1)
        # ST7789 รับ SPI ได้เร็วมาก · 62.5 MHz เป็นค่าที่ Waveshare ใช้ในตัวอย่าง
        self._spi = SPI(1, 62_500_000, polarity=0, phase=0,
                        sck=Pin(10), mosi=Pin(11), miso=None)
        self._buf = bytearray(WIDTH * HEIGHT * 2)
        super().__init__(self._buf, WIDTH, HEIGHT, framebuf.RGB565)
        self._rotate = rotate
        self._init_display()

    # ── ระดับล่าง ────────────────────────────────────────────────────
    def _cmd(self, c):
        self._cs(1); self._dc(0); self._cs(0)
        self._spi.write(bytearray([c]))
        self._cs(1)

    def _data(self, d):
        self._cs(1); self._dc(1); self._cs(0)
        self._spi.write(d if isinstance(d, (bytes, bytearray)) else bytearray([d]))
        self._cs(1)

    def _init_display(self):
        self._rst(1); self._rst(0); self._rst(1)

        # MADCTL — ทิศทางการสแกน · บิต MY=0x80 MX=0x40 MV=0x20 (MV = สลับแกน x/y)
        # ⚠️ ค่า 0x00 ทำให้ตัวหนังสือวิ่งจากล่างขึ้นบน (จอหมุน 90 องศา)
        #    ต้องเปิด MV เพื่อสลับแกนก่อน แล้วเลือก MX/MY ให้หันถูกด้าน
        self._cmd(0x36)
        self._data(MADCTL[self._rotate % 4])
        self._cmd(0x3A); self._data(0x05)    # COLMOD — 16 บิต/พิกเซล (RGB565)

        self._cmd(0xB2)
        self._data(bytearray([0x0C, 0x0C, 0x00, 0x33, 0x33]))
        self._cmd(0xB7); self._data(0x35)
        self._cmd(0xBB); self._data(0x19)
        self._cmd(0xC0); self._data(0x2C)
        self._cmd(0xC2); self._data(0x01)
        self._cmd(0xC3); self._data(0x12)
        self._cmd(0xC4); self._data(0x20)
        self._cmd(0xC6); self._data(0x0F)
        self._cmd(0xD0); self._data(bytearray([0xA4, 0xA1]))
        self._cmd(0xE0)
        self._data(bytearray([0xD0, 0x04, 0x0D, 0x11, 0x13, 0x2B, 0x3F,
                              0x54, 0x4C, 0x18, 0x0D, 0x0B, 0x1F, 0x23]))
        self._cmd(0xE1)
        self._data(bytearray([0xD0, 0x04, 0x0C, 0x11, 0x13, 0x2C, 0x3F,
                              0x44, 0x51, 0x2F, 0x1F, 0x1F, 0x20, 0x23]))
        self._cmd(0x21)                      # กลับสี (จอ IPS ตัวนี้ต้องใช้)
        self._cmd(0x11)                      # ออกจากโหมดหลับ
        self._cmd(0x29)                      # เปิดการแสดงผล

    def show(self):
        """ส่งทั้งเฟรมขึ้นจอ"""
        self._cmd(0x2A)                      # ช่วงคอลัมน์
        self._data(bytearray([0x00, 0x00, 0x00, 0xEF]))
        self._cmd(0x2B)                      # ช่วงแถว
        self._data(bytearray([0x00, 0x00, 0x00, 0xEF]))
        self._cmd(0x2C)                      # เริ่มเขียนข้อมูล
        self._cs(1); self._dc(1); self._cs(0)
        self._spi.write(self._buf)
        self._cs(1)

    def backlight(self, on=True):
        self._bl(1 if on else 0)

    # ── ตัวช่วยระดับบน ───────────────────────────────────────────────
    def clear(self, color=BLACK):
        self.fill(color)

    def text_big(self, s, x, y, color=WHITE, scale=2):
        """วาดตัวอักษรขยายใหญ่

        ⚠️ ฟอนต์ในตัวของ MicroPython สูง 8 พิกเซล = 0.8 มม. บนจอนี้ เล็กเกินอ่าน
        วิธีขยาย: วาดลงบัฟเฟอร์ 1 บิตเล็ก ๆ ก่อน แล้วค่อยขยายทีละพิกเซลด้วย
        fill_rect (ซึ่งเขียนด้วย C จึงเร็ว) — เร็วกว่าวนลูปเช็คทีละจุดใน Python มาก
        """
        if scale <= 1:
            self.text(s, x, y, color)
            return
        if not s:
            return          # บรรทัดว่าง — FrameBuffer กว้าง 0 จะ throw ValueError
        fm = _font() if FONT_STYLE == "sfmono" else None
        f = fm.SCALES.get(scale) if fm is not None else None
        if f is not None:
            self._text_bitmap(f, s, x, y, color)
            return
        w = len(s) * 8
        tmp = bytearray(((w + 7) // 8) * 8)
        fb = framebuf.FrameBuffer(tmp, w, 8, framebuf.MONO_HLSB)
        fb.fill(0)
        fb.text(s, 0, 0, 1)
        for row in range(8):
            run_start = -1
            for col in range(w + 1):
                on = col < w and fb.pixel(col, row)
                if on and run_start < 0:
                    run_start = col
                elif not on and run_start >= 0:
                    self.fill_rect(x + run_start * scale, y + row * scale,
                                   (col - run_start) * scale, scale, color)
                    run_start = -1

    def _text_bitmap(self, f, s, x, y, color):
        """วาดด้วยฟอนต์บิตแมป (font_sfmono) — ตัวละช่องกว้าง 8 x scale เท่าฟอนต์เดิม

        runs = (แถว, คอลัมน์, ความยาว) ต่อกัน → fill_rect ทีละช่วง (fill_rect เขียนด้วย C จึงเร็ว)
        แถว 0 ของบิตแมป = y + y0 (y0 ติดลบ = ส่วนที่ยื่นเหนือขอบบนตัวพิมพ์ใหญ่ เช่น วงเล็บ)
        ตัวอักษรนอก ASCII 32-126 วาดเป็น "?" แทนการหายเงียบ
        """
        cell, y0, _h, glyphs = f
        first = 32                              # font_sfmono.FIRST (ASCII 32-126)
        count = len(glyphs)
        fill = self.fill_rect
        ty = y + y0
        for n, ch in enumerate(s):
            i = ord(ch) - first
            if i < 0 or i >= count:
                i = 63 - first                  # "?"
            g = glyphs[i]
            cx = x + n * cell
            for k in range(0, len(g), 3):
                fill(cx + g[k + 1], ty + g[k], g[k + 2], 1, color)

    def text_center(self, s, y, color=WHITE, scale=1):
        """วางข้อความกลางจอตามแนวนอน"""
        x = max(0, (WIDTH - len(s) * 8 * scale) // 2)
        if scale > 1:
            self.text_big(s, x, y, color, scale)
        else:
            self.text(s, x, y, color)

    def banner(self, s, y=0, fg=BLACK, bg=YELLOW):
        """แถบเตือนพาดเต็มความกว้าง — ใช้ตอนใช้ seed ทดสอบ"""
        self.fill_rect(0, y, WIDTH, 12, bg)
        x = max(0, (WIDTH - len(s) * 8) // 2)
        self.text(s, x, y + 2, fg)


# ─── แปลงตาราง QR เป็นการวาด (แยกออกมาเพื่อให้เทสบนแมคได้) ────────────
def qr_layout(matrix_size, screen=WIDTH, quiet=2):
    """คำนวณขนาดต่อช่องและจุดเริ่มวาด ให้ QR ใหญ่สุดเท่าที่ลงจอ

    คืน (scale, x0, y0) · scale = 0 แปลว่าใหญ่เกินจอ
    🔑 ขอบขาวรอบ QR (quiet zone) จำเป็นจริง ๆ ไม่ใช่ของประดับ
       ถ้าไม่มี กล้องหาขอบ QR ไม่เจอ — สเปกกำหนดอย่างน้อย 4 ช่อง
       แต่บนจอเล็กใช้ 2 ช่องพอไหว แลกกับได้ช่องใหญ่ขึ้น
    """
    total = matrix_size + quiet * 2
    scale = screen // total
    if scale < 1:
        return 0, 0, 0
    used = total * scale
    off = (screen - used) // 2 + quiet * scale
    return scale, off, off


def qr_size(matrix):
    """ขนาดด้านของ QR — รับทั้ง list ซ้อน list และรูปแบบบีบ (n, bytearray)"""
    return matrix[0] if isinstance(matrix, tuple) else len(matrix)


def draw_qr(lcd, matrix, quiet=2):
    """วาด QR ลงจอ — พื้นขาว ช่องดำ

    รับได้ 2 แบบ: list ซ้อน list จาก qr.encode() หรือรูปแบบบีบ (n, bytearray)
    จาก qr.pack() ซึ่งหน้าโชว์หลายเฟรมใช้ เพื่อไม่ให้แรมเต็ม (ดูคอมเมนต์ใน qr.py)

    ⚠️ ต้องเป็น "ดำบนขาว" เท่านั้น กล้องอ่าน QR กลับสีไม่ได้
       (บทเรียนจาก wallet: Jade สแกน QR บนพื้นเข้มไม่ติดเลย)
    """
    n = qr_size(matrix)
    scale, x0, y0 = qr_layout(n, quiet=quiet)
    if scale == 0:
        return False
    lcd.fill(WHITE)
    if isinstance(matrix, tuple):
        buf = matrix[1]
        stride = (n + 7) >> 3
        for r in range(n):
            base = r * stride
            y = y0 + r * scale
            for c in range(n):
                if (buf[base + (c >> 3)] >> (7 - (c & 7))) & 1:
                    lcd.fill_rect(x0 + c * scale, y, scale, scale, BLACK)
        return True
    for r in range(n):
        row = matrix[r]
        y = y0 + r * scale
        for c in range(n):
            if row[c]:
                lcd.fill_rect(x0 + c * scale, y, scale, scale, BLACK)
    return True

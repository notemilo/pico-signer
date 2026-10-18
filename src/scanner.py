# scanner.py — อ่านข้อมูลจากโมดูลสแกนบาร์โค้ด Waveshare Barcode Scanner Module (D)
#
# การต่อสาย (ตามขา ไม่ใช่ตามสี — สีสายต่างกันระหว่างบอร์ดทดลองกับเครื่องจริงในเคส):
#   VCC -> 3V3 (3.3V เท่านั้น)   GND -> GND
#   GP0 (= UART0 TX ของ Pico  ->  ขา RX ของสแกนเนอร์)
#   GP1 (= UART0 RX ของ Pico  <-  ขา TX ของสแกนเนอร์)
#   สีบนบอร์ดทดลองเดิม: น้ำตาล=VCC เทา=GND น้ำเงิน=GP0 ส้ม=GP1
#   เครื่องจริงในเคส (ผู้ใช้ บัดกรีเอง ต.ค. 2026): เขียว ขาว น้ำเงิน เหลือง · ดูรูป pico-signer-notes-archive/hw-photos-2026-10-12/
#
# ⚠️ อย่าสลับ GP0/GP1 — บน RP2350 GP0 คือ TX, GP1 คือ RX เสมอ
#
# ค่าโรงงานที่เราตั้งใจใช้ (อย่าไปตั้งค่าใหม่โดยไม่จำเป็น):
#   9600 8N1 · โหมด continuous · เว้นช่วงระหว่างการอ่าน 1000 ms · ปิดท้ายด้วย CR
#
# 🔑 บทเรียน 9 ก.ย. 2026: เคยยิงบาร์โค้ดตั้งค่า "เว้นช่วง 200ms" (WSM02050002.)
#    แล้วโมดูลอ่านติด (ไฟเขียวกระพริบ) แต่ "ไม่ส่งอะไรออกทาง UART เลย"
#    ต้องยิง "Restore factory setting" (WSM00010000.) ถึงกลับมาปกติ
#    -> ห้ามแตะค่าเว้นช่วงอีก ถ้าอยากให้เก็บเฟรมเร็วขึ้นให้ไปยืดเวลาโชว์ QR
#       ฝั่งที่แสดงผลแทน (wallet) ซึ่งแก้ง่ายกว่าและไม่มีทางทำเครื่องใบ้

from machine import UART, Pin
import time

TX_PIN = 0
RX_PIN = 1
BAUD = 9600

MAX_LINE = 4096          # ยาวกว่า bbqr.Decoder.MAX_PART_CHARS (4000) เล็กน้อย
STALE_MS = 2500          # ค้างครึ่ง ๆ กลาง ๆ นานเกินนี้ = ทิ้ง (สัญญาณขาด/กวน)

# ── สั่งงานโมดูลผ่าน UART (18 ต.ค. 2026) ─────────────────────────────
# 🔴 รีวิวภายนอก GHSA-334h-x4f4-34h3 ข้อ 5: โมดูลอ่าน "QR ตั้งค่าเครื่อง" ได้ตลอด (ค่าโรงงานเปิดไว้)
#    จอกระเป๋าที่โดนเจาะโชว์ QR ตั้งค่าแทรกตอนเราสแกนได้ · ปิดผ่าน UART ไม่ได้ (คู่มือไม่มีคำสั่ง)
#    ทางที่ทำได้ (ลองบนเครื่องจริงแล้ว 18 ต.ค.):
#      1) เปิดเครื่อง: อ่านค่าตั้ง ถ้าไม่ตรงค่าที่ควรเป็น = มีคนแอบตั้ง → คืนค่าโรงงาน + เตือน
#      2) นอกหน้าสแกน: โหมดรอคำสั่ง = ไม่ถอดรหัสอะไรเลย (ไฟไม่เขียว ไม่ส่งข้อมูล) → QR ตั้งค่าใช้ได้แค่ตอนอยู่หน้าสแกน
#    เขียนแบบไม่ save — ปิดเครื่องแล้วโมดูลกลับเป็นค่าที่บันทึกไว้เสมอ (ยืนยันบนเครื่องแล้ว)
#    ไฟวงแหวนสีน้ำเงินสั่งปิดไม่ได้ (ลองล้างทุกบิตของ 0x0000 แล้ว ยังติด)
# โปรโตคอล: คู่มือ Waveshare Barcode Scanner Module (D) ภาคผนวก D (7E 00 ...) = แบบเดียวกับ GM65 ที่ Specter-DIY ใช้
#   อ่าน 7E 00 07 01 <addr 2> <len> AB CD · เขียน 7E 00 08 01 <addr 2> <val> AB CD (AB CD = ไม่ตรวจ checksum)
#   ตอบ 02 00 00 <len> <data> <crc 2> · เขียนสำเร็จ = 02 00 00 01 00 33 31
REG_MODE = 0x0000
MODE_CMD = 0x01          # รอคำสั่ง = ไม่สแกน
MODE_CONT = 0x02         # สแกนตลอดเวลา (ค่าโรงงาน)
# ค่าที่อ่านจากโมดูลของ ผู้ใช้ หลังคืนค่าโรงงาน (18 ต.ค. 2026) · 0x0000 เทียบเฉพาะบิตบน (บิต 1-0 = โหมด ที่แอปสลับเอง)
EXPECT = ((0x0000, 0xD4, 0xFC), (0x0005, 0x0A, 0xFF), (0x0006, 0x00, 0xFF), (0x000D, 0x00, 0xFF),
          (0x0013, 0x00, 0xFF), (0x002C, 0x04, 0xFF), (0x003F, 0x01, 0xFF))
REG_BAUD = 0x002A
BAUD_9600 = b"\x39\x01"
FACTORY_RESET = b"\x7e\x00\x09\x01\x00\x00\xff\xc0\x38"     # ตามคู่มือตรงตัว (มี checksum จริง)


class Scanner:
    """อ่านทีละบรรทัด แบบไม่บล็อก

        s = Scanner()
        for text in s.poll():
            ...
    """

    def __init__(self, uart_id=0, baud=BAUD, tx=TX_PIN, rx=RX_PIN, start=True):
        self.uart = UART(uart_id, baudrate=baud, bits=8, parity=None, stop=1,
                         tx=Pin(tx), rx=Pin(rx))
        self._buf = b""
        self._last = time.ticks_ms()
        if start:
            self.set_scanning(True)      # เข้าหน้าสแกน = เริ่มสแกน (นอกหน้าสแกนจอดไว้ที่โหมดรอคำสั่ง)
        self.flush()

    # ── คำสั่ง ────────────────────────────────────────────────
    def _reply(self, timeout_ms=200):
        """รอคำตอบรูปแบบ 02 00 00 <len> <data> <crc 2> — คืน data หรือ None"""
        t0 = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            if self.uart.any():
                buf += self.uart.read()
                i = buf.find(b"\x02\x00\x00")
                if i >= 0 and len(buf) >= i + 4:
                    n = buf[i + 3]
                    if len(buf) >= i + 4 + n + 2:
                        return buf[i + 4:i + 4 + n]
            time.sleep_ms(5)
        return None

    def _send(self, cmd, timeout_ms=200):
        while self.uart.any():           # ทิ้งของค้าง (เช่นข้อมูลสแกน) ก่อนถาม
            self.uart.read()
        self.uart.write(cmd)
        return self._reply(timeout_ms)

    def read_reg(self, addr, n=1):
        return self._send(b"\x7e\x00\x07\x01" + bytes([addr >> 8, addr & 0xFF, n]) + b"\xab\xcd")

    def write_reg(self, addr, val):
        """เขียน 1 ไบต์แบบไม่ save — คืน True ถ้าโมดูลตอบว่าสำเร็จ"""
        r = self._send(b"\x7e\x00\x08\x01" + bytes([addr >> 8, addr & 0xFF, val]) + b"\xab\xcd")
        return r == b"\x00"

    def set_scanning(self, on):
        """สลับสแกนตลอดเวลา / รอคำสั่ง (ไม่ save) · คืน False ถ้าโมดูลไม่ตอบ"""
        try:
            v = self.read_reg(REG_MODE)
            if not v:
                return False
            return self.write_reg(REG_MODE, (v[0] & 0xFC) | (MODE_CONT if on else MODE_CMD))
        except Exception:
            return False

    def check(self):
        """เทียบค่าตั้งกับค่าที่ควรเป็น — คืน (สถานะ, [addr ที่ไม่ตรง])

        "OK" ตรงหมด · "RESET" ไม่ตรงแล้วคืนค่าโรงงานสำเร็จ · "BAD" คืนแล้วยังไม่ตรง · "NO REPLY" โมดูลไม่ตอบ
        (ถ้ามีคนเปลี่ยน baud โมดูลจะไม่ตอบที่ 9600 = NO REPLY)
        """
        def diff():
            out = []
            for addr, want, mask in EXPECT:
                v = self.read_reg(addr)
                if v is None:
                    return None
                if v[0] & mask != want:
                    out.append(addr)
            b = self.read_reg(REG_BAUD, 2)
            if b is None:
                return None
            if b != BAUD_9600:
                out.append(REG_BAUD)
            return out

        try:
            bad = diff()
            if bad is None:
                return "NO REPLY", []
            if not bad:
                return "OK", []
            self.uart.write(FACTORY_RESET)       # เขียนลง flash ของโมดูล — ทำเฉพาะตอนค่าไม่ตรง
            time.sleep_ms(800)
            while self.uart.any():
                self.uart.read()
            again = diff()
            return ("RESET" if again == [] else "BAD"), bad
        except Exception:
            return "NO REPLY", []

    def flush(self):
        """ทิ้งของค้างในบัฟเฟอร์ — เรียกก่อนเริ่มสแกนชุดใหม่เสมอ

        สแกนเนอร์ยิงตลอดเวลาในโหมด continuous ถ้าไม่ล้างก่อน
        เฟรมของชุดก่อนหน้าจะปนเข้ามาในชุดใหม่
        """
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < 200:
            if self.uart.any():
                self.uart.read()
                t0 = time.ticks_ms()
            time.sleep_ms(10)
        self._buf = b""
        self._last = time.ticks_ms()

    def poll(self):
        """คืน list ของข้อความที่อ่านครบบรรทัดแล้ว (อาจว่าง) — ไม่บล็อก"""
        out = []
        n = self.uart.any()
        if n:
            d = self.uart.read(n)
            if d:
                self._buf += d
                self._last = time.ticks_ms()
        elif self._buf and time.ticks_diff(time.ticks_ms(), self._last) > STALE_MS:
            self._buf = b""          # เศษที่ไม่มีวันจบ — ทิ้ง
            return out

        # โมดูลปิดท้ายด้วย CR แต่รับ LF ด้วยเผื่อมีคนไปตั้งค่าไว้
        while True:
            i = -1
            for sep in (b"\r", b"\n"):
                j = self._buf.find(sep)
                if j >= 0 and (i < 0 or j < i):
                    i = j
            if i < 0:
                break
            line = self._buf[:i]
            self._buf = self._buf[i + 1:]
            if line:
                try:
                    out.append(line.decode())
                except Exception:
                    pass             # ไบต์ที่ไม่ใช่ ascii = สัญญาณกวน ข้ามไป
        if len(self._buf) > MAX_LINE:
            self._buf = b""          # ยาวผิดปกติ = ไม่ใช่ข้อมูลของเรา
        return out

    def poll_frames(self, gap_ms=150):
        """อ่านแบบ "ไบต์ดิบ" ตัดเฟรมด้วยช่วงเงียบ แทนการตัดที่ CR — ไม่บล็อก

        ใช้กับ QR ไบนารี (CompactSeedQR) ซึ่ง poll() ตัวบนใช้ไม่ได้:
        entropy สุ่มมีไบต์ 0x0D ปนอยู่ ~22% และมีไบต์เกิน 0x7F เกือบทุกครั้ง

        ✅ ยืนยันกับฮาร์ดแวร์จริง 14 ก.ย. 2026: ส่อง CompactSeedQR ทดสอบ
           (void come effort ที่มี CR ปนข้างใน) ได้ 14/14 เฟรม ยาว 33 ไบต์
           = entropy 32 + CR 1 ตรงทุกไบต์ -> โมดูลไม่แปลงข้อมูลไบนารี
           ที่ 9600 bps 33 ไบต์ใช้ ~35 ms ส่วนช่วงระหว่างการอ่านคือ 1000 ms
           ช่วงเงียบ 150 ms จึงแยกเฟรมได้ขาด
        คืน list ของ bytes (ยังไม่ตัดหาง CR — ให้ seedqr.frame_to_entropy ตัดเอง)
        """
        out = []
        n = self.uart.any()
        if n:
            d = self.uart.read(n)
            if d:
                self._buf += d
                self._last = time.ticks_ms()
        elif self._buf and time.ticks_diff(time.ticks_ms(), self._last) > gap_ms:
            out.append(self._buf)
            self._buf = b""
        if len(self._buf) > MAX_LINE:
            self._buf = b""
        return out

    def deinit(self, stop=True):
        if stop:
            self.set_scanning(False)     # ออกจากหน้าสแกน = หยุด (QR ตั้งค่าเครื่องอ่านไม่ได้นอกหน้าสแกน)
        try:
            self.uart.deinit()
        except Exception:
            pass


def boot_check():
    """เรียกครั้งเดียวตอนเปิดแอป: ตรวจค่าตั้ง (คืนค่าโรงงานถ้าโดนแก้) แล้วจอดไว้ที่โหมดรอคำสั่ง"""
    sc = Scanner(start=False)
    try:
        return sc.check()
    finally:
        sc.deinit(stop=True)

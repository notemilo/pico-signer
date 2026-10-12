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


class Scanner:
    """อ่านทีละบรรทัด แบบไม่บล็อก

        s = Scanner()
        for text in s.poll():
            ...
    """

    def __init__(self, uart_id=0, baud=BAUD, tx=TX_PIN, rx=RX_PIN):
        self.uart = UART(uart_id, baudrate=baud, bits=8, parity=None, stop=1,
                         tx=Pin(tx), rx=Pin(rx))
        self._buf = b""
        self._last = time.ticks_ms()
        self.flush()

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

    def deinit(self):
        try:
            self.uart.deinit()
        except Exception:
            pass

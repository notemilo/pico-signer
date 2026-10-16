# ui.py — หน้าจอและเมนูของเครื่องเซ็น
#
# ปุ่มที่ใช้ (Pico-LCD-1.3 มี 9 ปุ่ม):
#   จอย ขึ้น/ลง = เลื่อนรายการ · ซ้าย = ย้อนกลับ/ลบ · ขวา = ถัดไป
#   CTRL หรือ A = ตกลง · B = ยกเลิก/ออก
#   X, Y = ปุ่มเสริมแล้วแต่หน้า (บอกไว้ที่แถบล่างของทุกหน้า)
#
# 🔑 หลักที่ยึดในการออกแบบหน้าจอ:
#   1. **แถบล่างบอกเสมอว่าปุ่มไหนทำอะไร** — เครื่องนี้ใช้นาน ๆ ที ต้องไม่ต้องจำ
#   2. **ทุกขั้นตอนที่ป้อนข้อมูลต้องย้อนได้** — กดพลาด 1 ครั้งตอนใส่ 256 ค่า
#      แล้วต้องเริ่มใหม่ทั้งหมด = ผู้ใช้จะเลิกใช้เครื่อง
#   3. **ตอนทอยเต๋าต้องโชว์บิตกับคำที่ได้** เพื่อให้เทียบกับตารางกระดาษได้ทันที
#   4. **ถ้าใช้ seed ทดสอบ ต้องมีแถบเตือนค้างตลอด** ห้ามให้ลืม

import gc
import time

import lcd
import bip39
import bip32
import address as addr
import base58
import dice
import devseed
import qr
import bbqr
import seedqr
import ups
import hashes
# 🔴 15 ต.ค. 2026: โหลดโค้ดเซ็น PSBT ตั้งแต่เปิดเครื่อง (เดิม import ตอนกด Sign)
#    เครื่องค้างที่ "GOT 1/2" หลังสแกน PSBT จาก wallet — crash.txt: MemoryError ที่ `import psbt` ใน screen_sign
#    psbt.py ใหญ่ขึ้นใน 2.17.0 · MicroPython คอมไพล์ .py บนเครื่องต้องใช้แรมก้อนติดกัน
#    หลังใส่ seed + passphrase + สแกน แรมแตกเป็นเศษ หาก้อนไม่ได้ → ตอนเปิดเครื่องแรมยังว่างเป็นก้อนใหญ่
#    แลกกับแรมที่จองค้างไว้ ~32 KB (วัดบนเครื่อง) และเปิดเครื่องช้าขึ้น ~0.65 วิ
import psbt
import scanner
import addrverify

WL = "english.txt"

_ = None  # กัน linter บ่นเรื่อง import ที่ใช้ผ่าน getattr


# ชุดตัวอักษรสำหรับ passphrase — แบ่งเป็นกลุ่มเพื่อไม่ต้องเลื่อนผ่าน 90 ตัว
# BIP39 ยอมรับ UTF-8 ทุกตัว แต่บนเครื่องนี้จำกัดที่ ASCII พิมพ์ได้
# เพื่อให้พิมพ์ซ้ำบนเครื่องอื่นได้แน่นอน (อักขระไทย/emoji เสี่ยงเรื่อง normalize)
PASS_SETS = (
    ("abc", "abcdefghijklmnopqrstuvwxyz"),
    ("ABC", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ("123", "0123456789"),
    ("sym", " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"),
)
PASS_MAX = 64

# คีย์บอร์ดเต็มจอสำหรับ passphrase (16 ต.ค. 2026 · ผู้ใช้ ขอแบบ Jade classic: เห็นทุกตัว เลื่อนด้วยจอยสติ้ก)
# ผัง QWERTY เดียวกับคีย์บอร์ดทัชของเครื่องอื่นในโปรเจกต์ — 3 หน้า + แถวปุ่มควบคุม = ASCII 95 ตัวเท่า PASS_SETS
PASS_KB = (
    ("1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"),
    ("1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"),
    ("!\"#$%&'()*", "+,-./:;<=>", "?@[\\]^_`{|", "}~"),
)
PASS_CTRL = ("SHIFT", "SYM", "SPACE", "DEL", "DONE")
# ป้าย 3 ตัว = 48 พิกเซล · ถ้าแบ่ง 240/5 = 48 เท่ากันหมด ป้ายจะชนกันอ่านเป็น "ABC#+=SPCDEL" (เห็นในภาพจำลอง)
# → ปุ่มช่องว่างแคบลง (วาดเป็นกล่องเทาแทนคำ แบบเดียวกับที่ใช้แทนช่องว่างทั้งเครื่อง) ให้ที่เหลือมีขอบ
PASS_CTRL_W = (52, 52, 32, 52, 52)
KB_KEY_W = 24           # 240 / 10 ปุ่มต่อแถว · ตัวอักษร scale 2 กว้าง 16
KB_BG = 0x8631          # เทาเข้ม (48,48,48) = 0x3186 สลับไบต์แบบสีใน lcd.py

TITLE_COLS = 10         # เหลือที่ให้เปอร์เซ็นต์แบตมุมขวาบน (สูงสุด "100%" = 4 ตัว)
HINT_COLS = 15          # 240 พิกเซล / (8 พิกเซล x scale 2) = 15 ตัวพอดี
HINT_MAX_LINES = 2


def _kb_rows(page):
    """แถวของคีย์บอร์ดหน้านี้ [[(x, กว้าง, ค่า), ...], ...] · แถวสุดท้าย = ปุ่มควบคุม (ทุกหน้ามี 5 แถว)"""
    rows = []
    for row in PASS_KB[page]:
        x0 = (10 - len(row)) * KB_KEY_W // 2          # แถวสั้นวางกลาง แบบคีย์บอร์ดจริง
        rows.append([(x0 + c * KB_KEY_W, KB_KEY_W, ch) for c, ch in enumerate(row)])
    ctrl = []
    x = 0
    for k, w in zip(PASS_CTRL, PASS_CTRL_W):
        ctrl.append((x, w, k))
        x += w
    rows.append(ctrl)
    return rows


def _kb_move(rows, r, c, key):
    """เลื่อนตัวเลือก — ซ้าย/ขวาสุดแถวข้ามไปแถวก่อน/ถัดไป · ขึ้น/ลงวนบนล่าง ไปปุ่มที่ตรงแนวที่สุด"""
    if key == "RIGHT":
        c += 1
        if c >= len(rows[r]):
            r, c = (r + 1) % len(rows), 0
    elif key == "LEFT":
        c -= 1
        if c < 0:
            r = (r - 1) % len(rows)
            c = len(rows[r]) - 1
    else:
        x, w, _k = rows[r][c]
        mid = x + w // 2
        r = (r + (1 if key == "DOWN" else -1)) % len(rows)
        best = None
        for i, (x2, w2, _k2) in enumerate(rows[r]):
            dist = abs(x2 + w2 // 2 - mid)
            if best is None or dist < best:
                best, c = dist, i
    return r, c


def _kb_label(k, page):
    if k == "SHIFT":
        return "abc" if page == 1 else "ABC"
    if k == "SYM":
        return "abc" if page == 2 else "#+="
    if k == "SPACE":
        return ""               # วาดกล่องเทาแทน (ดู screen_passphrase)
    if k == "DONE":
        return "OK"
    return k


def _hint_lines(hint):
    """ตัดข้อความบอกปุ่มเป็นบรรทัดละไม่เกิน 15 ตัว สูงสุด 2 บรรทัด

    ตัดตามช่องว่างเสมอ ไม่หั่นกลางคำว่า 'B=CANCEL' ให้อ่านไม่รู้เรื่อง
    """
    lines = []
    cur = ""
    for w in str(hint).split():
        cand = w if not cur else cur + " " + w
        if len(cand) <= HINT_COLS:
            cur = cand
            continue
        if cur:
            lines.append(cur)
            if len(lines) == HINT_MAX_LINES:
                return lines
        cur = w[:HINT_COLS]
    if cur:
        lines.append(cur)
    return lines[:HINT_MAX_LINES]


def next_letters(words, prefix):
    """ตัวเลือกถัดไปจาก prefix นี้ — คืน list ของตัวอักษร

    🔑 สองเรื่องที่ต้องได้พร้อมกัน:
       1. **ข้ามตัวอักษรที่ไม่มีคำรองรับ** — เดิมวนครบ a-z ผู้ใช้ต้องกดผ่าน
          ตัวที่ตันเป็นสิบครั้งต่อหนึ่งคำ
       2. **คำที่เป็นคำนำหน้าของคำอื่นต้องเลือกได้** — BIP39 มี 49 คำแบบนี้
          (car, add, art, sun, you, ...) เดิมพอพิมพ์ 'car' ระบบบังคับให้เลือก
          ตัวถัดไปเสมอ จึงได้แต่ carbon/card/cargo ไม่มีทางหยุดที่ 'car'
          -> seed 24 คำมีโอกาส ~44% ที่จะใส่เข้าเครื่องไม่ได้เลย
       ใช้ "" เป็นตัวแทนของ "คำจบแค่ prefix นี้" และวางไว้ตัวแรก

    wordlist เรียงตามพจนานุกรมอยู่แล้ว ผลลัพธ์จึงเรียงตามไปด้วย
    """
    n = len(prefix)
    out = []
    exact = False
    # 15 ต.ค. 2026: รายการคำแบบก้อนเดียว (bip39.WordList) หาเฉพาะช่วงที่ขึ้นต้นด้วย prefix ได้เลย ไม่ต้องไล่ 2,048 คำทุกครั้งที่กดปุ่ม
    pool = words.with_prefix(prefix) if hasattr(words, "with_prefix") else words
    for w in pool:
        if not w.startswith(prefix):
            continue
        if len(w) == n:
            exact = True
        else:
            c = w[n]
            if not out or out[-1] != c:
                if c not in out:
                    out.append(c)
    if exact:
        out.insert(0, "")
    return out


def fmt_sat(v):
    """1234567 -> '1,234,567' — อ่านเลขยอดเงินผิดเพราะไม่มีตัวคั่นคือเรื่องใหญ่"""
    sign = "-" if v < 0 else ""
    t = str(abs(int(v)))
    out = ""
    while len(t) > 3:
        out = "," + t[-3:] + out
        t = t[:-3]
    return sign + t + out


def fmt_btc(v):
    """ซาโตชิ -> BTC ทศนิยม 8 ตำแหน่ง"""
    neg = v < 0
    v = abs(int(v))
    return ("-" if neg else "") + "%d.%08d" % (v // 100000000, v % 100000000)



# ── ปิดช่องสั่งงานทาง USB ตอนมี seed (เพิ่ม 12 ต.ค. 2026) ─────────────
# 🔴 USB ของ Pico = ไฟ + ช่อง REPL ที่สั่งรันโค้ดอะไรก็ได้ ถ้าเสียบเข้าคอมที่มีมัลแวร์ตอน seed อยู่ใน RAM
#    มัลแวร์สั่งอ่าน seed ออกไปได้ทันที (เขียนไว้ใน README ตั้งแต่แรก · Gemini จัดเป็นข้อร้ายแรงสุดตอนรีวิว)
# วิธี: เปิด "USB แบบกำหนดเอง" ที่ไม่มี interface อะไรเลย + ไม่เอา CDC ในตัว (BUILTIN_NONE)
#    → คอมมองไม่เห็นพอร์ตเลย · ไฟ USB ยังเข้า · ปิดเปิดเครื่อง/ถอดเสียบ = USB กลับมาปกติ
#    ทดลองบนเครื่องจริง 12 ต.ค. 2026: พอร์ตหายจากแมคภายใน 1 วิ · สั่งเปิดกลับด้วยโค้ดไม่ขึ้น → ไม่ทำทางกลับ
#    config() ต้องมี desc_strs ไม่งั้น TypeError
# seed ทดสอบไม่ปิด (เป็นเวกเตอร์สาธารณะ ไว้ดีบักผ่านสาย)
_USB_DEV = bytes([18, 1, 0x00, 0x02, 0, 0, 0, 64, 0x8A, 0x2E, 0x0F, 0x00, 0x00, 0x01, 0, 0, 0, 1])
_USB_CFG = bytes([9, 2, 9, 0, 0, 1, 0, 0x80, 50])      # configuration ที่ไม่มี interface


def ec_backend():
    """คณิตศาสตร์เส้นโค้งมาจากไหน — libsecp256k1 (โมดูล C ในเฟิร์มแวร์) หรือ python (ตัวสำรอง)"""
    import secp256k1
    return secp256k1.backend()


def usb_is_off():
    """boot.py ปิดช่องข้อมูล USB ไปแล้วหรือยัง (13 ต.ค. 2026: ปิดตั้งแต่บูต เว้นแต่กด B ค้าง)"""
    try:
        import machine
        u = machine.USBDevice()
        return bool(u.active()) and u.builtin_driver is u.BUILTIN_NONE
    except Exception:
        return False


def usb_data_off():
    """ปิดช่องข้อมูล USB ทั้งหมด — คืน True ถ้าปิดได้ (บนแมค/CPython ไม่มี machine = False)"""
    try:
        import machine
        u = machine.USBDevice()
        u.active(False)
        u.builtin_driver = u.BUILTIN_NONE
        u.config(_USB_DEV, _USB_CFG, [None])
        u.active(True)
        return True
    except Exception:
        return False


class App:
    def __init__(self):
        self.d = lcd.LCD()
        self.k = lcd.Keys()
        self.d.backlight(True)
        self._body_bottom = 218      # ขอบบนของแถบบอกปุ่ม อัปเดตทุกครั้งที่วาด
        self.passphrase = ""         # คำที่ 25 ตาม BIP39 (ว่าง = ไม่ใช้)
        self._bat = None             # (เปอร์เซ็นต์, โวลต์, mA, ข้อความ) หรือ None
        self._bat_t = -99999
        self.mnemonic = None
        self.root = None
        self.is_test = False
        self.account = 0             # BIP84 account ที่เลือกตอนโหลด seed (m/84h/0h/<n>h)
        self.usb_off = usb_is_off()  # ปิดช่องข้อมูล USB ไปแล้วไหม (boot.py ปิดให้ตั้งแต่บูต · กลับมาได้ทางเดียวคือปิดเปิดเครื่อง)

    # ── ระดับล่าง: อ่านปุ่มแบบกดทีละครั้ง ────────────────────────────
    def wait_key(self, allow=None, timeout_ms=None):
        """รอจนกดปุ่มแล้วปล่อย — คืนชื่อปุ่ม (กันเด้งซ้ำในตัว)"""
        t0 = time.ticks_ms()
        while True:
            now = self.k.any_pressed()
            if now:
                name = now[0]
                while self.k.any_pressed():
                    time.sleep_ms(10)
                time.sleep_ms(20)          # กันปุ่มเด้ง
                if allow is None or name in allow:
                    return name
            if timeout_ms and time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return None
            time.sleep_ms(15)

    # ── สถานะแบต ────────────────────────────────────────────────────
    def bat(self, max_age_ms=10000):
        """คืนสถานะแบต (แคชไว้ 10 วินาที) · None ถ้าไม่มี UPS ต่ออยู่

        ต้องไม่ทำให้โปรแกรมตายเมื่อถอด UPS ออก — เครื่องต้องใช้ได้เหมือนเดิม
        """
        now = time.ticks_ms()
        if self._bat is None or time.ticks_diff(now, self._bat_t) > max_age_ms:
            self._bat = ups.try_read()
            self._bat_t = now
        return self._bat

    # ── ชิ้นส่วนหน้าจอที่ใช้ซ้ำ ──────────────────────────────────────
    def _chrome(self, title, hint):
        """วาดหัวเรื่อง + แถบเตือน + แถบบอกปุ่มล่างจอ

        ⚠️ ฟอนต์ในตัวสูง 8 พิกเซล = 0.8 มม. บนจอ 23 มม. — เล็กเกินอ่านจริง
           เนื้อหาหลักจึงใช้ scale 2 (15 ตัวอักษร/บรรทัด) ส่วนแถบบอกปุ่ม
           ยังใช้ scale 1 เพราะเป็นข้อมูลอ้างอิง ไม่ต้องอ่านตลอดเวลา
        """
        top = 0
        if self.is_test:
            self.d.banner("TEST SEED - NO REAL FUNDS", 0)
            top = 13
        # หัวเรื่อง: พื้นขาว ตัวดำ = คอนทราสต์สูงสุด (พื้นเทาตัวดำอ่านยากมาก)
        self.d.fill_rect(0, top, 240, 22, lcd.WHITE)
        self.d.text_big(title[:TITLE_COLS], 4, top + 3, lcd.BLACK, 2)
        # เปอร์เซ็นต์แบตมุมขวาบน — ต้องเห็นทุกหน้า (ผู้ใช้ สั่ง 11 ก.ย. 2026)
        # 🔑 ตอนชาร์จใช้ "กลับสี" เป็นกรอบดำตัวขาว **ไม่ใช้สีบอก**
        #    เพื่อคนตาบอดสีเขียว-แดง สัญลักษณ์ต้องอ่านได้จากรูปร่าง ไม่ใช่สี
        b = self.bat()
        if b:
            txt = "%d%%" % b[0]
            bx = 240 - len(txt) * 16 - 2
            if b[3] == "CHARGING":
                self.d.fill_rect(bx - 4, top, 240 - bx + 4, 22, lcd.BLACK)
                self.d.text_big(txt, bx, top + 3, lcd.WHITE, 2)
            else:
                self.d.text_big(txt, bx, top + 3, lcd.BLACK, 2)
        # แถบบอกปุ่ม: ตัวขาวบนพื้นดำ **ขนาดเดียวกับเนื้อหา (scale 2)**
        # ผู้ใช้ อ่าน scale 1 (สูง 0.8 มม.) ไม่ออกจริง ๆ — แจ้งเอง 10 ก.ย. 2026
        # ยาวเกิน 15 ตัวก็ตัดลงบรรทัดที่สองให้เอง แถบจะสูงขึ้นตามและ
        # เนื้อหาด้านบนถูกบีบให้พอดีโดยอัตโนมัติ (ดู self._body_bottom)
        hl = _hint_lines(hint)
        bar_h = 4 + 18 * len(hl)
        bar_y = 240 - bar_h
        self.d.fill_rect(0, bar_y, 240, bar_h, lcd.BLACK)
        hy = bar_y + 2
        for ln in hl:
            self.d.text_big(ln, 2, hy, lcd.WHITE, 2)
            hy += 18
        self._body_bottom = bar_y
        return top + 28

    def message(self, title, lines, hint="A=OK", color=lcd.WHITE, scale=2):
        self.d.clear(lcd.BLACK)
        y = self._chrome(title, hint)
        step = 22 if scale > 1 else 16
        lim = 14 if scale > 1 else 29
        room = max(1, (self._body_bottom - y) // step)
        for ln in lines[:min(8, room)]:
            self.d.text_big(str(ln)[:lim], 6, y, color, scale)
            y += step
        self.d.show()

    def confirm(self, title, lines):
        self.message(title, lines, "A=OK  B=CANCEL")
        return self.wait_key(("A", "CTRL", "B")) in ("A", "CTRL")

    def menu(self, title, items, hint="A=SELECT  B=BACK"):
        """เมนูเลื่อนขึ้นลง — คืน index หรือ None ถ้ากดออก"""
        sel = 0
        top = 0
        while True:
            self.d.clear(lcd.BLACK)
            y = self._chrome(title, hint)
            visible = 7
            if sel < top:
                top = sel
            elif sel >= top + visible:
                top = sel - visible + 1
            for i in range(top, min(len(items), top + visible)):
                mark = ">" if i == sel else " "
                col = lcd.YELLOW if i == sel else lcd.WHITE
                self.d.text_big("%s%s" % (mark, str(items[i])[:13]), 4, y, col, 2)
                y += 24
            if len(items) > visible:
                self.d.text("%d/%d" % (sel + 1, len(items)), 200, 210, lcd.GREY)
            self.d.show()
            # ⚠️ ต้องมี timeout ไม่งั้นหน้าเมนูจะค้างภาพเดิมตลอด
            #    เลขแบตบนหัวเรื่องจะไม่ขยับเลยจนกว่าจะกดปุ่ม (เจอจริง 11 ก.ย. 2026)
            key = self.wait_key(timeout_ms=15000)
            if key is None:
                continue                      # หมดเวลา = วาดใหม่ ค่าแบตอัปเดตเอง
            if key == "UP":
                sel = (sel - 1) % len(items)
            elif key == "DOWN":
                sel = (sel + 1) % len(items)
            elif key in ("A", "CTRL", "RIGHT"):
                return sel
            elif key in ("B", "LEFT"):
                return None

    # ── สร้าง seed จากลูกเต๋า ────────────────────────────────────────
    # ── New seed: ทอยเต๋านอกเครื่อง แล้วกรอกผล ─────────────────────────
    def screen_new_seed(self):
        """New Seed — เลือก 12/24 คำ แล้วทอยเต๋ากรอกผล เครื่องหาคำสุดท้ายให้เอง

        (ผู้ใช้ ออกแบบ 14 ก.ย. 2026: แยก New / Existing ให้ชัด · seed ทุกทางเป็น temporary)
        """
        j = self.menu("NEW SEED", ["24 words", "12 words"])
        if j == 0:
            self.screen_dice(24)
        elif j == 1:
            self.screen_dice(12)

    def screen_dice(self, count=24):
        """ป้อนผลทอยเต๋าทีละครั้ง — A = คี่(1,3,5) · B = คู่(2,4,6)

        ใช้คี่/คู่เพราะตรงกับใบตารางกระดาษที่ ผู้ใช้ ใช้อยู่พอดี
        (คี่=1 คู่=0) จะได้ไม่ต้องแปลงในหัวอีกชั้น
        24 คำ = 23x11 + 3 = 256 ทอย · 12 คำ = 11x11 + 7 = 128 ทอย
        """
        last_rolls = dice.LAST_ROLLS[count]
        NEED = dice.need_rolls(count)
        FIRST = count - 1
        bits = []
        words = bip39.wordlist(WL)
        while len(bits) < NEED:
            n = len(bits)
            widx = n // 11
            inword = n % 11
            self.d.clear(lcd.BLACK)
            y = self._chrome("D %d/%d" % (n + 1, NEED),
                             "A=135 B=246 X=DEL Y=QUIT")
            # ⚠️ scale 2 = 14 ตัวอักษรต่อบรรทัดเท่านั้น ข้อความต้องสั้นกว่านั้นเสมอ
            #    "WORD 23 R11/11" = 14 พอดี · "WORD 24 R1/3" = 12 · "WORD 12 R7/7" = 12
            if widx < FIRST:
                self.d.text_big("WORD %d R%d/11" % (widx + 1, inword + 1),
                                6, y, lcd.WHITE, 2)
            else:
                self.d.text_big("WORD %d R%d/%d" % (count, inword + 1, last_rolls),
                                6, y, lcd.ORANGE, 2)
            y += 24
            # บิตของคำที่กำลังทำ — โชว์เพื่อเทียบกับตารางกระดาษ
            cur = "".join(str(b) for b in bits[widx * 11:])
            # ⚠️ ห้ามใช้ str.ljust() — MicroPython ไม่มีเมธอดนี้ (CPython มี)
            #    เคยพังจริงบนเครื่อง 10 ก.ย. 2026 · ดู tests/test_micropython_compat.py
            width = 11 if widx < FIRST else last_rolls
            self.d.text_big(cur + "_" * (width - len(cur)), 6, y, lcd.YELLOW, 2)
            y += 28
            # คำที่ได้ครบแล้ว 3 คำหลังสุด
            done = len(bits) // 11
            self.d.text_big("DONE %d/%d" % (min(done, FIRST), FIRST), 6, y, lcd.GREY, 2)
            y += 24
            if done:
                start = max(0, min(done, FIRST) - 3)
                for i in range(start, min(done, FIRST)):
                    w = words[int("".join(str(b) for b in bits[i * 11:(i + 1) * 11]), 2)]
                    self.d.text_big("%2d %s" % (i + 1, w), 8, y, lcd.GREEN, 2)
                    y += 24
            self.d.show()

            key = self.wait_key(("A", "B", "X", "LEFT", "Y"))
            if key == "A":
                bits.append(1)
            elif key == "B":
                bits.append(0)
            elif key in ("X", "LEFT"):     # X = ปุ่มที่มีชื่อพิมพ์บนบอร์ด
                if bits:                   # LEFT = โยกจอยไปซ้าย (ของเดิม)
                    bits.pop()
            elif key == "Y":
                if self.confirm("QUIT?", ["ROLLS WILL BE", "LOST", "", "ARE YOU SURE?"]):
                    return
        # แปลงเป็นคำ — ใช้เส้นทางเดียวกับที่เทียบตารางกระดาษไว้แล้ว
        rolls = [1 if b else 2 for b in bits]
        mn, cands = dice.build_mnemonic(rolls, WL)
        parts = mn.split()
        pick = cands.index(parts[-1])
        if len(cands) <= 8:
            # ⚠️ message() วาดได้สูงสุด 8 บรรทัด — 8 ตัวเลือกกินครบพอดี
            #    คำที่เครื่องเลือกจึงต้องแยกไปอีกหน้า ห้ามยัดรวม (เคยพลาดตรงนี้มาแล้ว)
            #    12 คำมี 128 ตัวเลือก โชว์ทั้งหมดไม่ได้ -> ข้ามหน้านี้ ไปหน้าบอกผลเลย
            # 🔑 เลขหน้าคำนับ 1-8 ตรงกับใบกระดาษ dice-worksheet (ทอย 000→ลำดับที่ 1 … 111→8)
            #    เดิมนับ 0-7 → คำถูกแต่เลขคลาดกับใบหนึ่งช่อง ผู้ใช้ เจอเองตอนทำ seed (15 ก.ย. 2026)
            self.message("WORD %d" % count, ["%s%d %s" % (">" if i == pick else " ", i + 1, w)
                                             for i, w in enumerate(cands)], "A=NEXT")
            self.wait_key(("A", "CTRL"))
        rolled = "".join(str(b) for b in bits[-last_rolls:])
        self.message("WORD %d" % count, ["ROLL " + rolled, "PICK #%d" % (pick + 1),
                                         "OF 1-%d" % len(cands), "",
                                         parts[-1], "", "CHECK PAPER"], "A=NEXT", lcd.YELLOW)
        self.wait_key(("A", "CTRL"))
        # 🔑 ดูคำซ้ำได้ไม่จำกัด "เฉพาะตอนนี้" — ก่อนกดใช้งาน seed นี้ยังไม่มีเงินผูกอยู่
        #    แต่พอกดใช้แล้วปิดถาวร เพราะเครื่องไม่มี PIN — ถ้าเปิดให้ดูตลอด
        #    ใครหยิบเครื่องที่เปิดค้างอยู่ไปก็อ่าน seed ได้ทันที
        #    (ผู้ใช้ เลือกแนวทางนี้เอง 11 ก.ย. 2026 · ทางเลือกอื่นคือดูไม่ได้เลย / ดูได้ตลอด)
        while True:
            self.show_words(parts)
            j = self.menu("SEED READY", ["Show again", "USE SEED", "Discard"], "A=SELECT")
            if j == 0:
                continue
            if j == 1:
                if self.confirm("USE SEED?", ["WROTE ALL %d" % count, "WORDS ON PAPER?", "",
                                              "LAST CHANCE"]):
                    # 🔑 15 ต.ค. 2026 (SeedSigner SeedWordsBackupTestView): ทดสอบกระดาษก่อนใช้ — B ข้ามได้
                    #    ตอบผิด/กดหยุด = กลับไปดูคำใหม่ ยังไม่โหลด seed
                    if self.confirm("CHECK?", ["QUIZ EACH WORD", "AGAINST YOUR", "PAPER", "",
                                               "B = SKIP"]):
                        if not self.quiz_words(parts):
                            continue
                    self.load_mnemonic(mn, is_test=False)
                    return
                continue
            # Discard หรือกดถอยออก
            if self.confirm("DISCARD?", ["THROW AWAY", "THESE %d WORDS" % count, "",
                                         "CANNOT UNDO"]):
                return

    def quiz_words(self, parts):
        """ทดสอบว่าคำบนกระดาษตรงกับ seed ครบทุกคำ ทีละคำตามลำดับ — คืน True ถ้าผ่านครบ

        🔑 15 ต.ค. 2026 (SeedSigner SeedWordsBackupTestView): สำรองผิดคือทางเสียเงินที่ไม่มีใครช่วยได้
           SeedSigner สุ่มลำดับคำ + สุ่มคำหลอกด้วย random — **เครื่องนี้ตั้งใจไม่มีโค้ดสุ่มเลย** จึงใช้แบบกำหนดได้:
           ถามเรียงจากคำที่ 1 · คำหลอก = คำข้าง ๆ ในรายการ BIP39 (หน้าตาคล้าย เช่น zero/zone/zoo บังคับให้อ่านจริง)
           ตำแหน่งคำจริง = ลำดับคำ BIP39 mod 4 (เปลี่ยนไปทุกคำ ไม่ต้องสุ่ม)
        """
        wl = bip39.wordlist(WL)
        n = len(parts)
        i = 0
        while i < n:
            w = parts[i]
            idx = wl.index(w)
            decoys = [wl[(idx + d) % 2048] for d in (-1, 1, 2)]
            pos = idx % 4
            opts = decoys[:pos] + [w] + decoys[pos:]
            j = self.menu("WORD %d?" % (i + 1), opts, "A=PICK  B=STOP")
            if j is None:
                return False
            if opts[j] == w:
                i += 1
                continue
            self.message("WRONG", ["WORD %d IS" % (i + 1), "NOT", opts[j], "", "CHECK PAPER"],
                         "A=RETRY B=WORDS", lcd.RED)
            if self.wait_key(("A", "CTRL", "B")) == "B":
                return False
        self.message("PAPER OK", ["ALL %d WORDS" % n, "MATCH", "", "KEEP IT SAFE"], "A=NEXT", lcd.GREEN)
        self.wait_key(("A", "CTRL"))
        return True

    def show_words(self, parts):
        """โชว์คำทีละ 6 คำ ให้จดลงกระดาษ (24 คำ = 4 หน้า · 12 คำ = 2 หน้า)"""
        pages = (len(parts) + 5) // 6
        page = 0
        while True:
            self.d.clear(lcd.BLACK)
            y = self._chrome("PG %d/%d" % (page + 1, pages), "L/R=PAGE   A=DONE")
            for i in range(page * 6, min(len(parts), page * 6 + 6)):
                self.d.text_big("%2d %s" % (i + 1, parts[i]), 14, y, lcd.WHITE, 2)
                y += 30
            self.d.show()
            key = self.wait_key(("LEFT", "RIGHT", "A", "CTRL"))
            if key == "RIGHT":
                page = (page + 1) % pages
            elif key == "LEFT":
                page = (page - 1) % pages
            else:
                return

    def confirm_word(self, idx, count, word):
        """ถามยืนยันคำที่เพิ่งได้ ก่อนไปคำถัดไป

        🔑 ทำไมต้องมี: ระบบเติมคำให้เองทันทีที่เหลือตัวเลือกเดียว แล้วข้าม
           ไปคำถัดไปเลย ถ้าไม่มีด่านนี้ผู้ใช้จะไม่มีทางรู้ว่าเครื่องเติมคำอะไร
           และรู้ตัวอีกทีตอนครบ 24 คำแล้ว (ผู้ใช้ สั่งเพิ่ม 11 ก.ย. 2026)

        คืน True = ใช่ ไปคำถัดไป · False = พิมพ์คำนี้ใหม่
        """
        self.d.clear(lcd.BLACK)
        y = self._chrome("W %d/%d" % (idx, count), "A=YES  B=NO")
        self.d.text_big("THIS WORD?", 6, y, lcd.WHITE, 2)
        y += 36
        # scale 3 = 24 พิกเซล/ตัว -> คำยาวสุดใน BIP39 คือ 8 ตัว = 192 ลงจอพอดี
        self.d.text_big(word, 8, y, lcd.GREEN, 3)
        self.d.show()
        return self.wait_key(("A", "CTRL", "B", "X", "LEFT")) in ("A", "CTRL")

    # ── ใส่คำที่มีอยู่แล้ว ───────────────────────────────────────────
    def screen_existing_seed(self):
        """Existing Seed — มี seed อยู่แล้ว: พิมพ์ 24 / 12 คำ หรือสแกน Compact SeedQR"""
        j = self.menu("EXISTING", ["Type 24 words", "Type 12 words", "Scan SeedQR"])
        if j == 0:
            self.screen_type_words(24)
        elif j == 1:
            self.screen_type_words(12)
        elif j == 2:
            self.screen_load_seedqr()

    def screen_type_words(self, count):
        """ถามก่อนว่ามีคำสุดท้ายแล้วไหม — ไม่มี = เผื่อไว้ให้เครื่องหาให้ (แบบ Jade Calculate)"""
        j = self.menu("WORD %d?" % count, ["I have all %d" % count, "Find word %d" % count])
        if j == 0:
            self.screen_enter_words(count)
        elif j == 1:
            self.screen_find_last(count)

    def _type_words(self, n, count):
        """พิมพ์ n คำ (หัวเรื่องนับเป็น W i/count) — คืน list หรือ None ถ้ากดเลิก

        BIP39 ออกแบบมาให้ **4 ตัวอักษรแรกไม่ซ้ำกันเลย** จึงพิมพ์ไม่เกิน 4 ตัว
        แล้วส่วนใหญ่จะเหลือคำเดียวให้เลือก
        """
        words = bip39.wordlist(WL)
        got = []
        while len(got) < n:
            prefix = ""
            letters = next_letters(words, prefix)
            li = 0
            while True:
                ch = letters[li]
                if ch == "":                       # เลือก "คำจบแค่ prefix นี้"
                    matches = [prefix]
                    shown = prefix + "<"
                else:
                    matches = (words.with_prefix(prefix + ch) if hasattr(words, "with_prefix")
                               else [w for w in words if w.startswith(prefix + ch)])
                    shown = prefix + ch.upper()
                self.d.clear(lcd.BLACK)
                y = self._chrome("W %d/%d" % (len(got) + 1, count),
                                 "UD=LETTER A=OK X=DEL B=QUIT")
                self.d.text_big(shown, 6, y, lcd.YELLOW, 3)
                y += 32
                self.d.text("%d of %d choices  %d words"
                            % (li + 1, len(letters), len(matches)), 6, y, lcd.GREY)
                y += 18
                for w in matches[:4]:
                    self.d.text_big(w, 10, y, lcd.WHITE if len(matches) > 1 else lcd.GREEN, 2)
                    y += 22
                self.d.show()
                key = self.wait_key()
                if key == "UP":
                    li = (li - 1) % len(letters)
                elif key == "DOWN":
                    li = (li + 1) % len(letters)
                elif key in ("A", "CTRL", "RIGHT"):
                    if len(matches) == 1:
                        if self.confirm_word(len(got) + 1, count, matches[0]):
                            got.append(matches[0])
                            break
                        prefix = ""            # ตอบว่าไม่ใช่ = พิมพ์คำนี้ใหม่
                        letters = next_letters(words, prefix)
                        li = 0
                        continue
                    prefix += ch               # ตัวเลือกทุกตัวมีคำรองรับเสมอ
                    letters = next_letters(words, prefix)
                    li = 0
                elif key in ("X", "LEFT"):
                    if prefix:
                        prefix = prefix[:-1]
                        letters = next_letters(words, prefix)
                        li = 0
                    elif got:
                        got.pop()
                        break
                elif key == "B":
                    if self.confirm("QUIT?", ["WORDS WILL BE", "LOST"]):
                        return None
        return got

    def screen_enter_words(self, count=24):
        """มีครบทุกคำแล้ว — พิมพ์ทีละคำ ตรวจทาน แล้วตรวจ checksum"""
        got = self._type_words(count, count)
        if got is None:
            return
        # 🔴 ให้ตรวจทานครบทุกคำก่อน — นี่คือด่านสุดท้ายก่อนเครื่องเอา seed ไปใช้
        #    ถ้าใส่ผิดสักคำแล้วปล่อยผ่าน เงินจะไปอยู่กระเป๋าที่ไม่มีใครถือกุญแจ
        self.show_words(got)
        if not self.confirm("CHECK %d" % count, ["ALL WORDS", "CORRECT?", "", "B = START OVER"]):
            return
        mn = " ".join(got)
        if not bip39.is_valid(mn, WL):
            self.message("ERROR", ["CHECKSUM BAD", "", "WORD IS WRONG", "OR ORDER WRONG"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        self.load_mnemonic(mn, is_test=devseed.is_test_mnemonic(mn))

    def screen_find_last(self, count):
        """มีคำไม่ครบ (เช่นทอยเต๋าจดมาเอง 23/11 คำ) — พิมพ์ count-1 คำ แล้วเครื่องหาคำสุดท้าย

        🔴 บัค D (15 ก.ย. 2026): เดิม 24 คำให้เลื่อนเลือกเองจาก 8 คำ เคอร์เซอร์เริ่ม #1
           กด A ทันที = ได้คำ #1 ไม่ได้สุ่ม (เสีย entropy 3 บิต) และขัดกับใบกระดาษที่เขียนว่า
           "อย่าเลือกเอง ทอยเต๋าอีก 3 ครั้ง" → ตอนนี้ทั้ง 12/24 คำต้องทอยเต๋า
           24 คำ ทอย 3 ครั้ง แล้วโชว์ครบ 8 คำพร้อม > ให้เทียบกับใบ · 12 คำ ทอย 7 ครั้ง
        """
        got = self._type_words(count - 1, count)
        if got is None:
            return
        cands = bip39.last_word_candidates(" ".join(got), WL)
        last = self._pick_by_dice(cands, count)
        if last is None:
            return
        parts = got + [last]
        self.show_words(parts)
        if not self.confirm("CHECK %d" % count, ["ALL WORDS", "CORRECT?", "", "B = START OVER"]):
            return
        mn = " ".join(parts)
        if not bip39.is_valid(mn, WL):      # ไม่ควรเกิด — คำมาจาก last_word_candidates เอง
            self.message("ERROR", ["CHECKSUM BAD"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        self.load_mnemonic(mn, is_test=devseed.is_test_mnemonic(mn))

    def _pick_by_dice(self, cands, count):
        """ทอยเต๋าเลือกคำสุดท้าย — A = คี่ · B = คู่ เหมือนหน้า New seed

        ลำดับ cands (a->z) = ลำดับค่า entropy พอดี (ดู dice.last_word_from_rolls) -> ไม่มี bias
        """
        k = dice.LAST_ROLLS[count]
        bits = []
        while len(bits) < k:
            cur = "".join(str(b) for b in bits)
            # 🔑 แถบปุ่มต้องเขียนเหมือนหน้า New seed ทุกตัวอักษร ("A=135 B=246 X=DEL Y=QUIT")
            #    เดิมหน้านี้เขียน "A=ODD B=EVEN" ในเนื้อความ + แถบปุ่มมีแค่ X/Y → ผู้ใช้ งง (15 ก.ย. 2026)
            self.message("WORD %d" % count, ["ROLL %d/%d" % (len(bits) + 1, k), "",
                                             cur + "_" * (k - len(bits))],
                         "A=135 B=246 X=DEL Y=QUIT")
            key = self.wait_key(("A", "B", "X", "LEFT", "Y"))
            if key == "A":
                bits.append(1)
            elif key == "B":
                bits.append(0)
            elif key in ("X", "LEFT"):
                if bits:
                    bits.pop()
            elif key == "Y":
                if self.confirm("QUIT?", ["ROLLS WILL BE", "LOST"]):
                    return None
        idx = 0
        for b in bits:
            idx = (idx << 1) | b
        w = cands[idx]
        if len(cands) <= 8:
            # โชว์ครบ 8 คำ > ชี้คำที่ทอยได้ นับ 1-8 ตรงกับใบกระดาษ (message วาดได้ 8 บรรทัดพอดี)
            self.message("WORD %d" % count, ["%s%d %s" % (">" if k == idx else " ", k + 1, c)
                                             for k, c in enumerate(cands)], "A=NEXT")
            self.wait_key(("A", "CTRL"))
        self.message("WORD %d" % count, ["ROLL " + "".join(str(b) for b in bits),
                                         "PICK #%d" % (idx + 1), "OF 1-%d" % len(cands), "", w],
                     "A=NEXT", lcd.YELLOW)
        self.wait_key(("A", "CTRL"))
        return w

    # ── โหลด seed เข้าเครื่อง ────────────────────────────────────────
    def load_mnemonic(self, mn, is_test, passphrase="", keep_account=False):
        self.message("DERIVING", ["TAKES ~10 SEC", "", "DO NOT UNPLUG"], "")
        gc.collect()
        t0 = time.ticks_ms()
        # 🔴 บัค H (15 ก.ย. 2026): เดิมใส่ passphrase แล้ว account กลับเป็น 0 เงียบ ๆ
        #    seed เดิม + เปลี่ยน passphrase = คง account ที่เลือกไว้ · seed ใหม่ = เริ่ม 0
        #    และหน้า READY โชว์ ACCT ทุกครั้ง ผู้ใช้เห็นเสมอว่ากำลังใช้ account ไหน
        same_seed = keep_account and mn == self.mnemonic
        # 🔑 15 ต.ค. 2026 (SeedSigner หน้า passphrase โชว์ "FP เดิม >> FP ใหม่"): เปลี่ยน passphrase บน seed เดิม
        #    = โชว์ทั้งสองค่า ให้เห็นว่ากระเป๋าเปลี่ยนจริง และเทียบกับที่จดไว้ได้ทั้งคู่
        #    ใช้ root เดิมที่โหลดอยู่ ไม่ต้องคำนวณ seed ใหม่อีกรอบ (PBKDF2 ~10 วิบน Pico)
        old_fp = None
        if same_seed and self.root is not None and passphrase != self.passphrase:
            old_fp = self.root.my_fingerprint().hex().upper()
        sd = bip39.seed(mn, passphrase)
        self.root = bip32.HDKey.from_seed(sd)
        self.mnemonic = mn
        self.passphrase = passphrase
        self.is_test = is_test
        if not same_seed:
            self.account = 0
        dt = time.ticks_diff(time.ticks_ms(), t0)
        # 🔑 15 ต.ค. 2026: ใส่ seed เสร็จแล้วไม่ต้องใช้รายการคำ (68 KB) — ปล่อยคืนให้ขั้นเซ็น/ทำ QR
        #    (ฟังก์ชันที่ต้องใช้จะเรียก bip39.wordlist() โหลดใหม่เอง)
        bip39.release_wordlist()
        gc.collect()
        fp = self.root.my_fingerprint().hex().upper()
        self.message("READY", [
            "FP " + fp,
            ("WAS " + old_fp) if old_fp else "took %d ms" % dt,
            "",
            "TEST SEED!" if is_test else "REAL SEED",
            "WITH PASSPHRASE" if passphrase else "",
            "ACCT %d" % self.account,
        ], "A=NEXT", lcd.ORANGE if is_test else lcd.GREEN)
        self.wait_key(("A", "CTRL"))

    def pick_account(self):
        """เลือก BIP84 account (m/84h/0h/<n>h) จากเมนู Wallet — ใช้ร่วม Export xpub / Verify addr / Sign

        ผู้ใช้ ออกแบบเอง (14 ก.ย. 2026): แบบ Jade เลือก account ในเมนู Wallet
        ไม่บังคับถามทันทีหลังใส่ seed · ค่าเริ่มต้น 0 · โหลด seed ใหม่ = กลับเป็น 0
        seed เดียวใช้หลายเครื่อง แต่ละเครื่องคนละ account = กระเป๋าคนละใบ
        """
        a = self.account
        while True:
            self.message("ACCOUNT", ["%d" % a, "", "m/84h/0h/%dh" % a, "",
                                     "UD = +1 / -1", "LR = +10 / -10"], "A=OK")
            key = self.wait_key(("UP", "DOWN", "LEFT", "RIGHT", "A", "CTRL"))
            if key == "UP":
                a = (a + 1) % 100
            elif key == "DOWN":
                a = (a - 1) % 100
            elif key == "RIGHT":
                a = (a + 10) % 100
            elif key == "LEFT":
                a = (a - 10) % 100
            else:
                self.account = a
                return

    # ── CompactSeedQR — สำรอง seed ด้วยการวาดลงกระดาษเอง ─────────────
    def screen_seedqr(self):
        """สร้าง SeedQR แล้วโชว์เป็นตารางให้วาดตามลงกระดาษ (เลือก Compact / Standard)

        🔑 ทำไมต้อง "วาดเอง" ไม่ใช่พิมพ์:
           seed จะไม่เคยผ่านเครื่องพิมพ์ ไม่เคยเป็นไฟล์ มีแค่ลายมือบนกระดาษ
           (ไอเดียเดียวกับ Jade — ผู้ใช้ ขอแบบนี้เอง 12 ก.ย. 2026)

        สเปก CompactSeedQR ของ SeedSigner: entropy ดิบ (ตัด checksum ออก)
        โหมดไบนารี ECC ระดับ L -> 24 คำได้ 25x25 · 12 คำได้ 21x21
        ทำตามสเปกเป๊ะเพื่อให้กระเป๋าเจ้าอื่นอ่านกระดาษแผ่นเดียวกันได้

        🔴 passphrase **ไม่ได้อยู่ใน QR** — ใครได้ QR ไปได้แค่ 24 คำ
           ถ้าใช้ passphrase ต้องเก็บแยกต่างหากเสมอ
        """
        if not self.mnemonic:
            self.message("NO SEED", ["NO SEED LOADED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        if self.is_test:
            if not self.confirm("TEST SEED", ["THIS IS A TEST", "SEED - QR IS",
                                              "NOT USEFUL", "", "GO ON?"]):
                return
        # 🔑 2 รูปแบบ (ผู้ใช้ เลือกเองตอนสำรอง) — เนื้อ seed เดียวกัน ต่างที่วิธีเก็บ
        #    Compact  = entropy ดิบ ตารางเล็กกว่า แต่สแกนเนอร์บางตัวอ่านไบนารีไม่ได้
        #               (สแกนเนอร์ U173 ทำไบต์พังเป็น FF — วัดจริง 16 ก.ย. 2026)
        #    Standard = เลขลำดับคำ 4 หลัก เป็นตัวเลขล้วน เครื่องไหนก็อ่านได้ + มี checksum
        # ⚠️ เมนู Pico ตัดที่ 13 ตัวอักษร — ชื่อยาวกว่านี้จะโดนตัดเงียบ ๆ
        j = self.menu("SEED QR", ["Compact 25x25", "Standard num"], "A=SELECT")
        if j is None:
            return
        self.message("SEED QR", ["BUILDING..."], "")
        gc.collect()
        try:
            if j == 0:
                data = bip39.mnemonic_to_entropy(self.mnemonic, WL)
            else:
                data = seedqr.mnemonic_to_standard_digits(self.mnemonic, WL)
            m = qr.encode(data, qr.EC_L)
        except Exception as e:
            self.message("QR FAILED", [str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        n = len(m)
        del data
        gc.collect()
        self.message("SEED QR", ["%dx%d SQUARES" % (n, n), "",
                                 "DRAW ON PAPER", "NOT ON PHONE", "",
                                 "LEAVE 4 SQUARE", "WHITE BORDER"],
                     "A=NEXT", lcd.ORANGE)
        self.wait_key(("A", "CTRL"))
        self.show_qr_grid(m)
        del m
        gc.collect()
        self.check_seedqr_paper()

    def check_seedqr_paper(self):
        """วาด SeedQR เสร็จแล้ว ให้สแกนกระดาษเทียบกับ seed ที่โหลดอยู่ทันที

        🔑 15 ต.ค. 2026 (SeedSigner SeedTranscribeSeedQRConfirmScanView):
           วาดผิดช่องเดียว Compact อาจอ่านได้เป็น "กระเป๋าคนละใบ" แบบไม่มี error (ไม่มี checksum)
           เดิมต้องไปเมนู Load SeedQR แล้วเทียบ FP เอง → ตอนนี้เทียบชุดคำให้เลย ไม่แตะ seed ที่โหลดอยู่
        """
        if not self.confirm("CHECK QR?", ["SCAN THE PAPER", "YOU JUST DREW", "TO CHECK IT", "",
                                          "B = SKIP"]):
            return
        mn = self._scan_seedqr()
        if mn is None:
            return
        same = mn == self.mnemonic
        del mn
        gc.collect()
        if same:
            self.message("QR OK", ["PAPER MATCHES", "THIS SEED", "", "KEEP IT SAFE"], "A=OK", lcd.GREEN)
        else:
            self.message("QR WRONG", ["PAPER IS A", "DIFFERENT SEED", "", "FIX OR REDRAW", "DO NOT USE IT"],
                         "A=OK", lcd.RED)
        self.wait_key(("A", "CTRL", "B"))

    def show_qr_grid(self, m):
        """โชว์ QR ทีละบล็อก 5x5 ตาราง ตั้งชื่อ A1-E5 แบบเดียวกับที่วงการใช้

        🔑 ทำไมต้อง 5x5: วาด QR 25x25 ลงกระดาษคือระบาย 625 ช่อง ถ้าไม่แบ่งเป็นบล็อก
           จะนับหลงแน่นอน แบ่งเป็นตาราง 5x5 บล็อก (บล็อกละ 5x5 ช่อง) แล้วเรียกชื่อ
           A1 ถึง E5 ทำให้รู้เสมอว่าอยู่ตรงไหนและวาดถึงไหนแล้ว
           (มาตรฐานเดียวกับ SeedSigner — ผู้ใช้ แก้ให้ 12 ก.ย. 2026 ของเดิมผมแบ่ง 4 ส่วน ใช้จริงไม่ไหว)

        จอ 240 พิกเซล: บล็อกใหญ่ 5 ช่อง x 32 = 160 · เหลือ 72 ให้แผนที่ย่อทางขวา
        """
        B = 5
        n = len(m)
        nb = (n + B - 1) // B          # 25 -> 5 บล็อก · 21 -> 5 บล็อก (บล็อกท้ายไม่เต็ม)
        ROWS = "ABCDEFGH"
        br = bc = 0
        while True:
            label = "%s%d" % (ROWS[br], bc + 1)
            r0, c0 = br * B, bc * B
            rows = min(B, n - r0)
            cols = min(B, n - c0)
            self.d.clear(lcd.BLACK)
            y0 = self._chrome("BLOCK " + label, "UDLR=MOVE A=ALL B=BACK")

            # ⚠️ ต้องคำนวณขนาดช่องจากพื้นที่ที่เหลือจริง ห้ามล็อกตายตัว
            #    แถบเตือน TEST SEED กินไป 13 พิกเซล ทำให้บล็อกล้นไปทับแถบปุ่มล่าง
            #    (_body_bottom = ขอบบนของแถบปุ่ม อัปเดตทุกครั้งที่ _chrome วาด)
            gx, gy = 8, y0 + 4
            avail = self._body_bottom - gy - 4
            cell = max(8, min(32, avail // rows, (168 - gx) // cols))
            gw, gh = cols * cell, rows * cell
            self.d.fill_rect(gx - 2, gy - 2, gw + 4, gh + 4, lcd.WHITE)
            for r in range(rows):
                for c in range(cols):
                    if m[r0 + r][c0 + c]:
                        self.d.fill_rect(gx + c * cell, gy + r * cell, cell, cell, lcd.BLACK)
            # เส้นตาราง — วาดทับท้ายสุด สีเทาจึงเห็นได้ทั้งบนช่องขาวและช่องดำ
            # จำเป็นมากตอนวาดลงกระดาษ ไม่มีเส้นจะนับช่องหลงทันที
            for c in range(cols + 1):
                self.d.fill_rect(gx + c * cell, gy, 1, gh, lcd.GREY)
            for r in range(rows + 1):
                self.d.fill_rect(gx, gy + r * cell, gw, 1, lcd.GREY)

            # แผนที่ย่อทางขวา — บอกว่าบล็อกนี้อยู่ตรงไหนของ QR ทั้งใบ
            # ⚠️ ขนาดต้องคำนวณจากจำนวนบล็อก ห้ามล็อกตายตัว
            #    Standard SeedQR 29x29 มี 6 บล็อก/แถว (Compact 25x25 มี 5)
            #    เดิมล็อก ms=11 mx=180 -> 180+66 = 246 ล้นจอ 240 (เจอจากรูปถ่าย 16 ก.ย. 2026)
            ms = max(6, min(11, (240 - 176) // nb))
            mx, my = 240 - nb * ms - 4, gy + 4
            for r in range(nb):
                for c in range(nb):
                    on = (r == br and c == bc)
                    self.d.fill_rect(mx + c * ms, my + r * ms, ms - 1, ms - 1,
                                     lcd.YELLOW if on else lcd.GREY)
            self.d.text("of %s%d" % (ROWS[nb - 1], nb), mx, my + nb * ms + 5, lcd.WHITE)
            self.d.show()

            key = self.wait_key(("UP", "DOWN", "LEFT", "RIGHT", "A", "CTRL", "B"))
            if key == "RIGHT":
                bc += 1
                if bc >= nb:
                    bc = 0
                    br = (br + 1) % nb
            elif key == "LEFT":
                bc -= 1
                if bc < 0:
                    bc = nb - 1
                    br = (br - 1) % nb
            elif key == "DOWN":
                br = (br + 1) % nb
            elif key == "UP":
                br = (br - 1) % nb
            elif key in ("A", "CTRL"):
                lcd.draw_qr(self.d, m)
                self.d.fill_rect(0, 228, 240, 12, lcd.WHITE)
                self.d.text("WHOLE QR - ANY KEY BACK", 2, 230, lcd.BLACK)
                self.d.show()
                self.wait_key()
            else:
                return

    # ── passphrase (คำที่ 25 ตาม BIP39) ─────────────────────────────
    def screen_passphrase(self, current=""):
        """พิมพ์ passphrase — คืนข้อความ หรือ None ถ้ายกเลิก

        🔑 passphrase ทำให้ 24 คำชุดเดียวเปิดได้หลายกระเป๋า
           ใครเจอกระดาษ 24 คำแต่ไม่รู้ passphrase ก็เปิดกระเป๋าจริงไม่ได้
        🔴 แต่ **ลืม passphrase = เงินหายเท่ากับลืม seed** ไม่มีทางกู้
        ⚠️ พิมพ์ผิดไปตัวเดียวจะได้กระเป๋าคนละใบ "โดยไม่มี error"
           จึงต้องโชว์ fingerprint หลังใส่เสมอ ให้ผู้ใช้เทียบว่าตรงกับที่เคยได้ไหม
        """
        # 🔑 16 ต.ค. 2026 (ผู้ใช้ ขอแบบ Jade classic): เดิมเห็นทีละตัว เลื่อนขึ้นลงไล่ตัวอักษร
        #    → เปลี่ยนเป็นคีย์บอร์ดเต็มจอ จอยสติ้ก 4 ทิศเลื่อน ซ้าย/ขวาสุดแถวข้ามบรรทัดได้
        #    ปุ่ม X/Y เป็นทางลัด DEL/DONE · กดจอยสติ้กลง (CTRL) = A
        txt = current
        page, r, c = 0, 1, 0                      # เริ่มที่ q
        # สร้างผังปุ่มครั้งเดียวต่อการเข้าหน้านี้ (~150 tuple) — ไม่สร้างใหม่ทุกครั้งที่กดปุ่ม
        # เพราะ 2.17.2 เจอแรมแตกเป็นเศษหลังพิมพ์ passphrase ยาว ๆ
        pages = [_kb_rows(i) for i in range(len(PASS_KB))]
        while True:
            rows = pages[page]
            self.d.clear(lcd.BLACK)
            y = self._chrome("PASS %d" % len(txt), "A=TYPE X=DEL Y=DONE B=QUIT")
            if txt:
                shown = txt[-14:]
                self.d.text_big(shown, 6, y, lcd.WHITE, 2)
                # ช่องว่างวาดเป็นกล่องเทา แบบหน้า CONFIRM — ไม่งั้นมองไม่เห็นว่าเผลอเว้นวรรค
                for j in range(len(shown)):
                    if shown[j] == " ":
                        self.d.fill_rect(6 + j * 16 + 3, y + 4, 10, 10, lcd.GREY)
            else:
                self.d.text_big("(empty)", 6, y, lcd.GREY, 2)
            top = y + 24
            kh = (self._body_bottom - top) // len(rows)
            for ri in range(len(rows)):
                ky = top + ri * kh
                for ci, (x, w, k) in enumerate(rows[ri]):
                    on = ri == r and ci == c
                    # ตัวที่เลือก = กลับสีทั้งปุ่ม (พื้นเหลืองตัวดำ) ไม่ใช่แค่เปลี่ยนสีตัวอักษร — คนตาบอดสี
                    self.d.fill_rect(x + 1, ky + 1, w - 2, kh - 2, lcd.YELLOW if on else KB_BG)
                    lab = _kb_label(k, page)
                    if k == "SPACE":
                        self.d.fill_rect(x + (w - 12) // 2, ky + (kh - 12) // 2, 12, 12,
                                         lcd.BLACK if on else lcd.GREY)
                    else:
                        self.d.text_big(lab, x + (w - len(lab) * 16) // 2, ky + (kh - 17) // 2,
                                        lcd.BLACK if on else lcd.WHITE, 2)
            self.d.show()
            key = self.wait_key()
            if key in ("UP", "DOWN", "LEFT", "RIGHT"):
                r, c = _kb_move(rows, r, c, key)
                continue
            if key == "B":
                if self.confirm("QUIT?", ["DISCARD THIS", "PASSPHRASE?"]):
                    return None
                continue
            if key == "X":
                k = "DEL"
            elif key == "Y":
                k = "DONE"
            elif key in ("A", "CTRL"):
                k = rows[r][c][2]
            else:
                continue
            if k == "DONE":
                return txt
            if k == "DEL":
                txt = txt[:-1]
            elif k == "SHIFT":
                page = 0 if page == 1 else 1      # ตัวเลือกยังอยู่ที่ปุ่มเดิม กดซ้ำ = กลับ
            elif k == "SYM":
                page = 0 if page == 2 else 2
            elif len(txt) < PASS_MAX:
                txt += " " if k == "SPACE" else k

    def screen_set_passphrase(self):
        """เพิ่ม/แก้ passphrase ของ seed ที่โหลดอยู่"""
        if not self.mnemonic:
            self.message("NO SEED", ["NO SEED LOADED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        pw = self.screen_passphrase(self.passphrase)
        if pw is None:
            return
        # ยืนยันสิ่งที่พิมพ์ก่อนเอาไปใช้ — พิมพ์ผิดจะได้กระเป๋าคนละใบเงียบ ๆ
        self.d.clear(lcd.BLACK)
        y = self._chrome("CONFIRM", "A=USE  B=BACK")
        self.d.text_big("PASSPHRASE %d:" % len(pw), 6, y, lcd.WHITE, 2)
        y += 26
        if pw:
            for i in range(0, len(pw), 14):
                seg = pw[i:i + 14]
                self.d.text_big(seg, 6, y, lcd.YELLOW, 2)
                # 🔑 15 ต.ค. 2026 (SeedSigner แทนช่องว่างด้วยบล็อก ▉): ช่องว่างมองไม่เห็นบนจอ
                #    เผลอเว้นวรรคท้าย/ซ้อน = กระเป๋าคนละใบแบบไม่มี error → วาดกล่องเทาทุกช่องว่าง
                #    ช่องละ 16 พิกเซล (ฟอนต์ 8 x scale 2) · ฟอนต์ไม่มีตัวอักษรนอก ASCII ให้ใช้แทน
                for j in range(len(seg)):
                    if seg[j] == " ":
                        self.d.fill_rect(6 + j * 16 + 3, y + 4, 10, 10, lcd.GREY)
                y += 22
            if " " in pw:
                self.d.text("GREY BOX = SPACE", 6, y + 2, lcd.GREY)
        else:
            self.d.text_big("(none)", 6, y, lcd.GREY, 2)
            y += 22
        self.d.show()
        if self.wait_key(("A", "CTRL", "B")) == "B":
            return
        self.load_mnemonic(self.mnemonic, self.is_test, pw, keep_account=True)

    # ── แสดงที่อยู่ / xpub ───────────────────────────────────────────
    def draw_addr(self, a, x, y, per_line=3, step=24):
        """วาดที่อยู่แบ่งกลุ่มละ 4 ตัว แบบเดียวกับ wallet

        🔑 ทำไมต้องแบ่งกลุ่ม: ที่อยู่ยาว 42 ตัวอักษรไล่ทีละตัวเทียบสองจอไม่ไหว
           แบ่ง 4 แล้วเน้นกลุ่มแรก/กลุ่มสุดท้าย ทำให้เทียบได้เร็วและพลาดยาก
           wallet ใช้วิธีเดียวกัน -> สองจอหน้าตาตรงกัน เทียบได้ทันที

        ⚠️ ใช้ "ความสว่าง" แยกกลุ่ม ไม่ใช้คู่สีเขียว-แดง (คนตาบอดสีแยกไม่ออก)
           กลุ่มกลางเป็นสีขาวหมดเพื่อให้อ่านง่ายที่สุด ต่างจาก wallet ที่สลับสีเทา
           เพราะจอนี้เล็กและสีเทาจางเกินอ่านสบาย

        3 กลุ่ม/บรรทัด = 14 ตัวอักษรพอดีกับที่ scale 2 รับได้
        คืนค่า y ของบรรทัดถัดไป
        """
        groups = [a[i:i + 4] for i in range(0, len(a), 4)]
        last = len(groups) - 1
        for n, g in enumerate(groups):
            col = lcd.YELLOW if (n == 0 or n == last) else lcd.WHITE
            self.d.text_big(g, x + (n % per_line) * 80, y + (n // per_line) * step, col, 2)
        return y + ((len(groups) + per_line - 1) // per_line) * step

    def screen_export_xpub(self):
        """ส่งกุญแจสาธารณะระดับบัญชีออกไปให้ wallet เป็น QR

        🔑 wallet รับทางกล้องได้รูปแบบเดียว: **Coldcard Generic JSON ห่อใน BBQr**
           มันหยิบ `_pub` (zpub) ก่อน แล้วเดา script type จาก prefix ได้เอง
           และแปลง "h" ใน deriv เป็น "'" ให้เอง

        🔴 ส่งออกเฉพาะส่วน public เท่านั้น — to_public() ตัด private key ทิ้งก่อนเสมอ
           ถ้าหลุด private key ออกไป = เงินหายทั้งกระเป๋า
        """
        if not self.root:
            self.message("NO SEED", ["NO SEED LOADED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        self.message("XPUB", ["BUILDING..."], "")
        gc.collect()
        path = "m/84h/0h/%dh" % self.account
        acct = self.root.derive(path).to_public()
        raw = acct.serialize()
        xpub = base58.encode_check(raw)
        # zpub = xpub ก้อนเดียวกัน แค่เปลี่ยน version 4 ไบต์แรกเป็น 0x04B24746
        zpub = base58.encode_check(b"\x04\xb2\x47\x46" + raw[4:])
        xfp = self.root.my_fingerprint().hex()
        j = ('{"xfp":"%s","bip84":{"deriv":"%s",'
             '"xpub":"%s","_pub":"%s"}}') % (xfp, path, xpub, zpub)
        self.message("XPUB", ["FP " + xfp.upper(), "ACCT %d" % self.account, zpub[:14], zpub[14:28] + "..",
                              "", "A=SHOW QR"], "A=NEXT")
        self.wait_key(("A", "CTRL"))
        self.show_bbqr(j.encode(), "J", "XPUB")

    def show_qr(self, text, title="QR"):
        self.message(title, ["BUILDING QR..."], "")
        gc.collect()
        try:
            m = qr.encode(text, qr.EC_M)
        except Exception as e:
            self.message("QR FAILED", [str(e)[:28]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        lcd.draw_qr(self.d, m)
        self.d.show()
        self.wait_key()
        gc.collect()

    # ระดับความหนาแน่นของ QR — เลือกได้ตอนโชว์
    #
    # 🔴 บทเรียนที่วัดจริงบนบอร์ด (2026-09-09): จอกว้างแค่ 23.4 มม.
    #    chunk 600 (ค่าที่ลอกจาก wallet ซึ่งโชว์บนจอมือถือ 6 นิ้ว) ทำให้ได้
    #    QR 77x77 ช่อง → ขยายได้แค่ 2 เท่า → **1 ช่องกว้าง 0.19 มม.**
    #    กล้องอ่านไม่ออกเลย · เฟรมที่อ่านออกจริงคือเฟรมเล็ก ช่อง 0.78 มม.
    #    → ต้องหั่นชิ้นให้เล็กลง ยอมเฟรมเยอะขึ้นแลกกับช่องใหญ่ขึ้น
    #    (ตรงกับที่ wallet เคยเจอกับ Jade แล้วแก้ด้วยวิธีเดียวกัน)
    DENSITY = (
        ("BIG",  60),   # ช่องใหญ่สุด เฟรมเยอะสุด — ใช้เมื่อสแกนไม่ติด
        ("MID",  80),   # ค่าเริ่มต้น — ช่อง ~0.58 มม.
        ("SMALL", 150),  # เฟรมน้อย แต่ช่องเล็ก ~0.49 มม.
    )

    def show_bbqr(self, data, type_="P", title="PSBT", level=1):
        """โชว์ข้อมูลก้อนใหญ่เป็น QR หลายเฟรม วนซ้ำจนกว่าจะกดออก

        ปุ่มระหว่างโชว์: X = ช่องใหญ่ขึ้น (เฟรมเยอะขึ้น) · Y = ช่องเล็กลง
                        LEFT/RIGHT = เลื่อนเฟรมเอง · A/B = ออก
        """
        while True:
            name, chunk = self.DENSITY[level]
            gc.collect()
            parts = bbqr.encode(data, type_, chunk)
            frames = []
            for idx, p in enumerate(parts):
                self.message(title, ["DENS %s" % name,
                                     "FRAME %d/%d" % (idx + 1, len(parts))], "")
                gc.collect()
                # 🔴 เก็บแบบบีบเสมอ (qr.pack) — เดิมเก็บ list ซ้อน list ทุกเฟรม
                #    xpub 7 เฟรม ~73KB · PSBT ที่เซ็นแล้ว 12 เฟรม ~125KB
                #    → MemoryError ตอนเฟรมท้าย ๆ และช้าลงเรื่อย ๆ (gc กวาดทุกครั้งที่ขอแรม)
                #    แบบบีบ 12 เฟรมรวมไม่ถึง 3KB · ข้อมูลใน QR เท่าเดิมทุกช่อง
                frames.append(qr.pack(qr.encode(p, qr.EC_M)))
                gc.collect()
            i = 0
            manual = False
            newlevel = None
            while newlevel is None:
                m = frames[i]
                sc, _x, _y = lcd.qr_layout(lcd.qr_size(m))
                lcd.draw_qr(self.d, m)
                # แถบล่าง: บอกเฟรมและขนาดช่อง เพื่อให้รู้ว่ากำลังดูระดับไหน
                self.d.fill_rect(0, 228, 240, 12, lcd.WHITE)
                # ⚠️ แถบนี้นอนอยู่ในขอบขาวของ QR ขยายตัวอักษรไม่ได้
                #    (ต้องย่อ QR ลง แล้วกล้องจะอ่านยากขึ้น — ไม่คุ้ม)
                #    ยาวได้ 29 ตัวเท่านั้น · เดิม 32 ตัวจึงหลุดขอบ "B=EXIT" เหลือ "B=EX"
                self.d.text("%d/%d   X/Y=SIZE   B=EXIT"
                            % (i + 1, len(frames)), 2, 230, lcd.BLACK)
                self.d.show()
                key = self.wait_key(timeout_ms=None if manual else 900)
                if key in ("B", "A", "CTRL"):
                    return
                elif key == "X":
                    newlevel = max(0, level - 1)
                elif key == "Y":
                    newlevel = min(len(self.DENSITY) - 1, level + 1)
                elif key == "RIGHT":
                    manual = True
                    i = (i + 1) % len(frames)
                elif key == "LEFT":
                    manual = True
                    i = (i - 1) % len(frames)
                elif key is None:
                    i = (i + 1) % len(frames)      # หมดเวลา = เลื่อนเฟรมอัตโนมัติ
            if newlevel == level:
                return
            level = newlevel

    # ── หน้าสถานะเครื่อง ─────────────────────────────────────────────

    # ── เซ็น PSBT ────────────────────────────────────────────────────
    #
    # 🔴 นี่คือหน้าจอที่สำคัญที่สุดของเครื่องทั้งเครื่อง
    #    บั๊กตรงนี้ = ผู้ใช้กดยืนยันโดยเห็นตัวเลขชุดหนึ่ง แต่เซ็นอีกชุดหนึ่ง
    #    หลักที่ยึด: **แสดงทุกอย่างที่กระทบเงิน และปฏิเสธเมื่อไม่มั่นใจ**
    def screen_sign(self, src):
        if not self.root:
            self.message("NO SEED", ["NO SEED LOADED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        # 🔑 15 ต.ค. 2026: เครื่องค้างที่ "GOT 1/2" หลังสแกน PSBT จาก wallet (seed + passphrase · ทำซ้ำบนโต๊ะไม่ได้)
        #    ต้นเหตุ (crash.txt): MemoryError ตอน import psbt → แก้ด้วยการโหลดตั้งแต่เปิดเครื่อง (หัวไฟล์)
        #    จอยังบอกขั้น DECODING (ถอด QR) → READING (ตรวจ PSBT) ไว้ เผื่อมีอาการแบบนี้อีกจะรู้ว่าค้างขั้นไหน
        P = psbt                      # โหลดไว้ตั้งแต่เปิดเครื่องแล้ว (ดูหัวไฟล์)
        self.message("PSBT", ["READING..."], "")
        gc.collect()
        try:
            if isinstance(src, (bytes, bytearray)):
                ps = P.PSBT.parse(bytes(src))
            else:
                ps = P.PSBT.from_base64(src)
            info = ps.describe(self.root, account=self.account)
        except P.PSBTLie:
            # 🔴 15 ต.ค. 2026 (แนวคิดจาก SeedSigner): PSBT โกหกเรื่องกุญแจของ seed นี้ = ไม่ใช่ไฟล์เสีย
            #    บอกผู้ใช้ตรง ๆ ว่าฝั่งที่สร้าง PSBT (คอม/wallet) อาจโดนเจาะ — ไม่ใช่แค่ BAD PSBT
            self.message("PSBT LIES", ["KEY INFO FOR", "THIS SEED IS", "FAKE", "",
                                       "WALLET OR PC", "MAY BE HACKED", "", "NOT SIGNED"],
                         "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        except Exception as e:
            self.message("BAD PSBT", [str(type(e).__name__)[:14], str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return

        # ปฏิเสธก่อนถ้าข้อมูลไม่พอจะตัดสินใจ
        # ไม่รู้ยอด input = คำนวณค่าธรรมเนียมไม่ได้ = อาจโดนดูดเงินไปเป็นค่าธรรมเนียม
        # (ช่องโหว่ "high fee attack" ที่ hardware wallet ต้องกันให้ได้)
        if info["fee"] is None:
            # 🔴 12 ต.ค. 2026: ยอด input เชื่อได้เฉพาะจาก tx เก่าทั้งใบ (กัน CVE-2020-14199 · ดู psbt._prev_out)
            self.message("REFUSED", ["NO PREV TX FOR", "%d INPUT(S)" % info["inputs_unknown_amount"], "",
                                     "CANT VERIFY", "AMOUNT + FEE"],
                         "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        if info["fee"] < 0:
            self.message("REFUSED", ["OUTPUTS EXCEED", "INPUTS"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        # 🔑 15 ต.ค. 2026 (SeedSigner PSBTSeedCannotSignView): seed นี้เซ็น input ไหนไม่ได้เลย
        #    = เลือก seed/passphrase ผิด → บอกตั้งแต่ตอนนี้ ไม่ต้องให้กดผ่านหน้ารีวิวแล้วค่อยเจอ NOT SIGNED
        #    (อยู่หลังด่าน "ไม่มี tx เก่า" เพราะไม่รู้ script ของ input ก็นับไม่ได้ว่าเซ็นได้ไหม)
        if not info["inputs_signable"]:
            self.message("NOT YOURS", ["NO INPUT CAN", "BE SIGNED BY", "THIS SEED", "",
                                       "WRONG SEED OR", "PASSPHRASE?"], "A=BACK", lcd.ORANGE)
            self.wait_key(("A", "CTRL"))
            return
        # 🔴 12 ต.ค. 2026: ค่าธรรมเนียมเกินเพดาน (ดู psbt.MAX_FEE_PCT) = ไม่เซ็น ไม่ใช่แค่เตือน
        if info["fee_over_cap"]:
            self.message("REFUSED", ["FEE OVER %d%%" % P.MAX_FEE_PCT, "OF TOTAL OUT", "",
                                     "FEE %s" % fmt_sat(info["fee"]), "", "NOT SIGNED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return

        # 🔴 บัค F (15 ก.ย. 2026): input อยู่นอก account ที่เลือก → ไม่เซ็น ให้ไปเปลี่ยน account ก่อน
        #    ถ้าใช้ seed เดียวหลายเครื่อง แต่ละเครื่องคนละ account = กระเป๋าคนละใบ
        #    เซ็นข้าม account เงียบ ๆ = จ่ายเงินจากกระเป๋าที่ผู้ใช้ไม่ได้ตั้งใจ
        if info["inputs_wrong_account"]:
            accs = ",".join("?" if a is None else str(a) for a in info["input_accounts"])
            if len(accs) > 14:
                accs = accs[:12] + ".."
            self.message("WRONG ACCT", ["INPUT ACCT", accs, "YOU USE ACCT" , "%d" % self.account,
                                        "SWITCH ACCOUNT", "IN WALLET MENU", "", "NOT SIGNED"],
                         "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return

        fee = info["fee"]
        send = info["sending"]
        # ⚠️ รวมเหรียญเข้ากระเป๋าตัวเองล้วน ๆ send=0 — เดิมใส่ 999 ทำให้ขึ้น "FEE 999%"
        #    สีแดงทั้งที่ค่าธรรมเนียมปกติ (พบตอนไล่บั๊ก 11 ก.ย. 2026)
        #    เทียบกับยอดที่ขยับจริง (ส่งออก หรือถ้าไม่มีก็เงินทอน) แทน
        base = send if send else info["change"]
        pct = (fee * 100 // base) if base else 999
        lines = [
            "SEND %s" % fmt_sat(send),
            " %s" % fmt_btc(send),
            "FEE  %s" % fmt_sat(fee),
            "CHG  %s" % fmt_sat(info["change"]),
            # 🔑 15 ต.ค. 2026: มี input ของคนอื่นปน (payjoin/coinjoin) ต้องเห็น — SEND อาจรวมเงินที่คนอื่นจ่าย
            ("IN   %d" % info["inputs"]) if info["inputs_mine"] == info["inputs"]
            else ("IN %d MINE %d" % (info["inputs"], info["inputs_mine"])),
            "ACCT %d" % self.account,
        ]
        if pct >= 10:
            lines.append("! FEE %d%% !" % pct)
        self.message("REVIEW", lines, "A=NEXT  B=CANCEL",
                     lcd.RED if pct >= 10 else lcd.WHITE)
        if self.wait_key(("A", "CTRL", "B")) == "B":
            return

        # ดูปลายทางทีละรายการ — ต้องกดผ่านให้ครบทุกอัน
        # 🔴 locktime: ถ้าไม่บอก ผู้ใช้จะเซ็นแล้วส่งไม่ออกโดยไม่รู้สาเหตุ (เพิ่ม 12 ก.ย. 2026)
        if info["locktime"]:
            if info["locktime_no_effect"]:
                body = ["LOCKTIME SET", "BUT NO EFFECT", "", "ODD - CHECK", "WHO MADE THIS"]
            elif info["locktime_is_time"]:
                body = ["CANNOT SPEND", "UNTIL UNIX TIME", "", str(info["locktime"])]
            else:
                body = ["CANNOT SPEND", "UNTIL BLOCK", "", fmt_sat(info["locktime"])]
            self.message("LOCKTIME", body, "A=NEXT  B=CANCEL", lcd.ORANGE)
            if self.wait_key(("A", "CTRL", "B")) == "B":
                return

        dests = [o for o in info["outputs"] if not o["is_change"]]
        # 🔴 รวมเหรียญเข้ากระเป๋าตัวเองล้วน ๆ -> dests ว่าง -> เดิมข้ามหน้าที่อยู่ทั้งหมด
        #    ผู้ใช้จะกดเซ็นโดย **ไม่เคยเห็นที่อยู่ปลายทางสักตัว** (พบจากรีวิวภายนอก 11 ก.ย. 2026)
        #    ต้องโชว์ที่อยู่เสมอ ไม่ว่าเงินจะไปไหน — นั่นคือหน้าที่เดียวของหน้าจอนี้
        head = "TO"
        if not dests:
            dests = info["outputs"]
            head = "SELF"
        for i, o in enumerate(dests):
            a = o["address"] or "(odd script)"
            self.d.clear(lcd.BLACK)
            title = ("SELF %d/%d" if head == "SELF" else "TO %d/%d") % (i + 1, len(dests))
            y = self._chrome(title, "A=NEXT  B=CANCEL")
            self.d.text_big("%s SAT" % fmt_sat(o["value"]), 6, y, lcd.YELLOW, 2)
            y += 24
            if o.get("odd_owned"):
                self.d.text_big("! ODD PATH !", 6, y, lcd.ORANGE, 2)
                y += 22
                self.d.text((o["path"] or "")[:29], 6, y, lcd.GREY)
                y += 14
            elif head == "SELF":
                self.d.text_big("BACK TO SELF", 6, y, lcd.ORANGE, 2)
                y += 22
            else:
                y += 6
            self.draw_addr(a, 6, y)
            self.d.show()
            if self.wait_key(("A", "CTRL", "B")) == "B":
                return

        if not self.confirm("SIGN?", ["SIGN THIS TX", "WITH YOUR KEY", "",
                                      "CHECK ADDRESS"]):
            return

        self.message("SIGNING", ["PLEASE WAIT..."], "")
        gc.collect()
        t0 = time.ticks_ms()
        try:
            n = ps.sign(self.root, account=self.account)
        except Exception as e:
            self.message("SIGN FAIL", [str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        dt = time.ticks_diff(time.ticks_ms(), t0)
        # เซ็นได้ไม่ครบทุก input ที่ประกาศว่าเป็นของเรา = มีอะไรไม่ตรง (เส้นทางโกหก/คนละ account)
        # ธุรกรรมที่เซ็นไม่ครบใช้ไม่ได้อยู่แล้ว แต่ห้ามโชว์ QR ให้เข้าใจผิดว่าเสร็จ
        if 0 < n < info["inputs_mine"]:
            self.message("SIGN ERROR", ["SIGNED %d/%d" % (n, info["inputs_mine"]), "", "SOME INPUTS",
                                        "NOT VERIFIED", "", "DO NOT USE"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        if n == 0:
            self.message("NOT SIGNED", ["NO INPUT IS", "FROM THIS SEED", "",
                                        "WRONG SEED?"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        self.message("SIGNED", ["%d input(s)" % n, "took %d ms" % dt, "",
                                "SHOW QR NEXT"], "A=SHOW QR")
        self.wait_key(("A", "CTRL"))
        # 🔑 15 ต.ค. 2026: ส่งกลับแบบตัด tx เก่า/derivation ออก (psbt.export_signed) — เฟรม QR น้อยลงราวครึ่ง
        #    เทสไขว้: bitcoinjs (ตัวเดียวกับ wallet) finalize ใบที่ตัดแล้วได้ txid เดียวกับใบเต็ม
        out = ps.export_signed()
        del ps
        gc.collect()
        self.show_bbqr(out, "P", "SIGNED PSBT")

    # ── รับ PSBT จากสแกนเนอร์ ────────────────────────────────────────
    def screen_scan(self):
        """สแกน QR หลายเฟรม (BBQr) จากจอ wallet แล้วส่งต่อไปหน้าเซ็น

        สแกนเนอร์อยู่ในโหมด continuous ยิงเองทุก ๆ ~1 วินาที
        เราแค่คอยเก็บบรรทัดที่เข้ามาแล้วโยนให้ bbqr.Decoder เรียงเอง
        เฟรมซ้ำไม่เป็นไร — Decoder ตัดซ้ำให้อยู่แล้ว
        """
        SC = scanner
        try:
            sc = SC.Scanner()
        except Exception as e:
            self.message("NO SCANNER", ["UART FAILED", str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return

        dec = bbqr.Decoder()
        drawn = -1
        t_last = time.ticks_ms()
        raw_b64 = None
        try:
            while True:
                for text in sc.poll():
                    # PSBT ใบเดียวจบที่ไม่ได้ห่อ BBQr มา (base64 ขึ้นต้นด้วย cHNidP)
                    if text.startswith("cHNidP"):
                        raw_b64 = text
                        break
                    if dec.add(text):
                        t_last = time.ticks_ms()
                if raw_b64 or dec.done:
                    break
                # 13 ต.ค. 2026: QR ชุดใหญ่เกินเพดาน (bbqr.Decoder.MAX_TOTAL_CHARS) — บอกเลย ไม่ต้องรอหมดเวลา
                if dec.too_big and not dec.have:
                    self.message("REFUSED", ["QR TOO BIG", "", "MAX %d KB" % (dec.MAX_TOTAL_CHARS * 5 // 8 // 1024),
                                             "", "NOT A NORMAL", "PSBT"], "A=BACK", lcd.RED)
                    self.wait_key(("A", "CTRL", "B"))
                    return

                have = dec.have
                if have != drawn:
                    drawn = have
                    if dec.total:
                        body = ["GOT %d/%d" % (have, dec.total), "", "KEEP POINTING"]
                    else:
                        body = ["WAITING...", "", "POINT AT", "THE QR CODE"]
                    self.message("SCAN QR", body, "B=CANCEL",
                                 lcd.YELLOW if dec.total else lcd.WHITE)

                if self.k.any_pressed():
                    if self.wait_key() in ("B", "LEFT"):
                        return
                if time.ticks_diff(time.ticks_ms(), t_last) > 120000:
                    self.message("TIMEOUT", ["NOTHING", "SCANNED", "", "CHECK CABLE"],
                                 "A=BACK", lcd.RED)
                    self.wait_key(("A", "CTRL", "B"))
                    return
                time.sleep_ms(30)
        finally:
            sc.deinit()
            del sc
            gc.collect()

        if raw_b64:
            self.screen_sign(raw_b64)
            return

        self.message("SCAN QR", ["GOT %d/%d" % (dec.have, dec.total), "", "DECODING..."], "")
        try:
            res = dec.result()
        except MemoryError:
            # 13 ต.ค. 2026 (รีวิวภายนอก ข้อ 6): แรมไม่พอถอด = ปฏิเสธ ไม่ใช่ค้าง/CRASH
            res = None
            del dec
            gc.collect()
            self.message("REFUSED", ["OUT OF MEMORY", "DECODING QR", "", "PSBT TOO BIG"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return
        if res is None:
            self.message("BAD QR", ["FRAMES OK BUT", "DECODE FAILED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return
        data, typ = res
        del dec
        gc.collect()
        if typ != "P":
            self.message("NOT A PSBT", ["TYPE", "'%s'" % str(typ)[:12], "", "EXPECTED 'P'"],
                         "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return
        self.screen_sign(data)

    def guard_usb(self):
        """ปิดช่องข้อมูล USB ครั้งแรกที่เริ่มใส่ seed แล้วบอกผู้ใช้ครั้งเดียว"""
        if self.usb_off:
            return
        if usb_data_off():
            self.usb_off = True
            self.message("USB OFF", ["NO COMPUTER", "ACCESS NOW", "", "CHARGING OK", "",
                                          "POWER OFF TO", "RESTORE USB"], "A=OK")
        else:
            self.message("USB ON!", ["COULD NOT", "TURN OFF USB", "", "DO NOT PLUG", "INTO A", "COMPUTER"],
                         "A=OK", lcd.ORANGE)
        self.wait_key(("A", "CTRL"))

    def screen_status(self):
        gc.collect()
        lines = [
            "SHA512 " + str(hashes.sha512_backend()),
            "EC " + ("LIBSECP" if ec_backend() == "libsecp256k1" else "PYTHON"),
            "RAM %d" % gc.mem_free(),
            "SEED " + ("LOADED" if self.root else "NONE"),
            "PASS " + ("YES" if self.passphrase else "no"),
            "USB DATA " + ("OFF" if self.usb_off else "ON"),
        ]
        if self.root:
            lines.append("FP " + self.root.my_fingerprint().hex().upper())
            lines.append("ACCT %d" % self.account)
        b = self.bat(max_age_ms=0)          # หน้านี้ขออ่านสด ไม่เอาค่าแคช
        if b:
            pct, v, ma, note = b
            short = {"CHARGING": "CHG", "ON BATTERY": "BATT"}.get(note, "IDLE")
            lines += ["BAT %d%% %s" % (pct, short),
                      "%.2fV %dmA" % (v, ma)]
        else:
            lines.append("NO UPS FOUND")
        # message() วาดได้ 8 บรรทัด — หน้าแรกเต็มพอดีตอนมี seed จึงแยกเฟิร์มแวร์ไปหน้า 2
        self.message("Status", lines, "A=MORE B=BACK")
        if self.wait_key(("A", "CTRL", "B")) == "B":
            return
        v = firmware_info()
        fw = ["VER " + v["VERSION"],
              "GIT " + v["COMMIT"][:10],
              "BLD " + v["BUILD_SHA"][:8],
              "CORE " + v["CORE_SHA"][:8],
              "DEV " + v["DEVICE"],
              "SHA512 " + str(hashes.sha512_backend()),
              "RAM %d" % gc.mem_free()]
        if hashes.sha512_backend() == "python":
            fw.append("! SLOW SHA512")
        self.message("Firmware", fw, "A=BACK")
        self.wait_key(("A", "CTRL", "B"))

    # ── โหลด seed จาก CompactSeedQR ─────────────────────────────────
    def _scan_seedqr(self):
        """เปิดสแกนเนอร์ อ่าน SeedQR (Compact/Standard) จนได้ชุดคำตรงกันครบ 3 ครั้ง — คืนชุดคำ หรือ None ถ้ายกเลิก/ผิดพลาด

        แยกออกมา 15 ต.ค. 2026 ให้ใช้ร่วม Load SeedQR และ "ตรวจกระดาษ" หลังวาด SeedQR
        """
        SC = scanner
        import seedqr

        try:
            sc = SC.Scanner()
        except Exception as e:
            self.message("NO SCANNER", ["UART FAILED", str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return None

        col = seedqr.Collector()
        mn = None
        drawn = -1
        t0 = time.ticks_ms()
        try:
            while mn is None:
                for fr in sc.poll_frames():
                    got = col.add(fr, WL)      # คืน "ชุดคำ" แล้ว รับได้ทั้ง Compact และ Standard
                    if got is not None:
                        mn = got
                        break
                if col.count != drawn:
                    drawn = col.count
                    if col.count:
                        body = ["READ %d/%d" % (col.count, col.need), "", "HOLD STILL"]
                    else:
                        body = ["POINT AT", "SEEDQR PAPER"]
                    self.message("SCAN SEED", body, "B=CANCEL", lcd.WHITE)
                if self.k.any_pressed():
                    if self.wait_key() in ("B", "LEFT"):
                        return None
                if time.ticks_diff(time.ticks_ms(), t0) > 120000:
                    self.message("TIMEOUT", ["NO SEEDQR", "READ"], "A=BACK", lcd.RED)
                    self.wait_key(("A", "CTRL", "B"))
                    return None
                time.sleep_ms(30)
        finally:
            sc.deinit()
            del sc
            gc.collect()
        return mn

    def screen_load_seedqr(self):
        """สแกน CompactSeedQR (กระดาษที่วาดจากเมนู Seed QR) แล้วโหลดเป็น seed

        🔴 Compact ไม่มี checksum -> ไบต์เพี้ยน = กระเป๋าคนละใบ ไม่มี error
           กัน 2 ชั้น: อ่านได้ไบต์ตรงกันติดกัน 3 ครั้ง (seedqr.Collector)
           แล้วบังคับให้ผู้ใช้ตอบว่า fingerprint ตรงกับที่จดบนกระดาษ
           ตอบไม่ตรง = ล้าง seed ทิ้งทันที
        🔴 QR ไม่มี passphrase อยู่ในนั้น — ถ้าใช้ต้องใส่เองทีหลังที่เมนู Passphrase
        """
        if self.mnemonic and not self.confirm("REPLACE?", ["A SEED IS", "LOADED NOW", "",
                                                           "REPLACE IT?"]):
            return
        if not self.confirm("LOAD QR", ["UNPLUG USB", "USE BATTERY", "",
                                            "NO PASSPHRASE", "IN THE QR", "", "GO ON?"]):
            return

        mn = self._scan_seedqr()
        if mn is None:
            return
        gc.collect()

        # ถ้าเป็น seed ทดสอบสาธารณะในรายการ ให้ติดป้าย TEST เหมือนเมนู Test seed
        is_test = False
        for name in devseed.names():
            if devseed.get(name)[0] == mn:
                is_test = True
                break

        self.load_mnemonic(mn, is_test=is_test)
        del mn
        gc.collect()

        fp = self.root.my_fingerprint().hex().upper()
        if not self.confirm("CHECK FP", ["FP " + fp, "", "SAME AS YOUR", "PAPER?"]):
            # ไม่ตรง = อาจอ่านเพี้ยนหรือกระดาษวาดผิด ห้ามใช้ต่อ
            self._clear_seed()
            self.message("CLEARED", ["FP NOT SAME", "", "REDRAW OR", "RESCAN"],
                         "A=OK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return

    # ── ตรวจที่อยู่รับเงิน (แบบที่ ผู้ใช้ ใช้กับ Jade) ─────────────────
    VERIFY_BATCH = 20     # ~0.45 วิ/ที่อยู่บน Pico · รับ+ทอน 20 เลข ≈ 18 วิต่อรอบ

    def screen_verify_addr(self):
        """สแกน QR ที่อยู่รับเงินจาก wallet แล้วค้นว่ามาจาก seed + account นี้จริงไหม

        🔑 wallet อยู่บนเครื่องที่ต่อเน็ต ถูกเจาะแล้วโชว์ที่อยู่คนร้ายได้
           เครื่องนี้คำนวณเองจาก seed = ตัวยืนยันก่อนส่งที่อยู่ให้คนโอน
        ค้นทีละ VERIFY_BATCH เลข สลับ รับ/ทอน · ไม่เจอถามว่าค้นช่วงถัดไปไหม (แบบ Jade)
        🔑 ไม่เจอ ≠ โดนโกงเสมอ: อาจเป็น account อื่นหรือเลขสูงกว่าที่ค้น
        """
        SC = scanner
        AV = addrverify
        if not self.root:
            self.message("NO SEED", ["NO SEED LOADED"], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return
        try:
            sc = SC.Scanner()
        except Exception as e:
            self.message("NO SCANNER", ["UART FAILED", str(e)[:14]], "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL"))
            return

        text = None
        t0 = time.ticks_ms()
        self.message("VERIFY", ["POINT AT", "ADDRESS QR", "", "ACCT %d" % self.account],
                     "B=CANCEL")
        try:
            while text is None:
                for t in sc.poll():
                    text = t
                    break
                if self.k.any_pressed():
                    if self.wait_key() in ("B", "LEFT"):
                        return
                if time.ticks_diff(time.ticks_ms(), t0) > 120000:
                    self.message("TIMEOUT", ["NOTHING READ"], "A=BACK", lcd.RED)
                    self.wait_key(("A", "CTRL", "B"))
                    return
                time.sleep_ms(30)
        finally:
            sc.deinit()
            del sc
            gc.collect()

        try:
            spk, clean = AV.parse(text)
        except AV.AddressError as e:
            why = {
                AV.BAD_EMPTY: ["EMPTY QR"],
                AV.BAD_NOT_ADDRESS: ["NOT A BITCOIN", "ADDRESS"],
                AV.BAD_WRONG_NET: ["NOT MAINNET"],
                AV.BAD_NOT_P2WPKH: ["NOT A BC1Q", "ADDRESS", "", "WALLET USES", "BC1Q ONLY"],
            }.get(e.reason, [str(e.reason)[:14]])
            self.message("CANT CHECK", why, "A=BACK", lcd.RED)
            self.wait_key(("A", "CTRL", "B"))
            return

        self.message("CHECKING", ["DERIVING", "ACCT %d" % self.account], "")
        gc.collect()
        chains = AV.chain_nodes(AV.account_node(self.root, self.account))
        B = self.VERIFY_BATCH
        start = 0
        found = None
        while found is None:
            for chain, i, cand in AV.candidates(chains, start, B):
                self.message("CHECKING", ["ACCT %d" % self.account,
                                          "#%d-%d" % (start, start + B - 1),
                                          "NOW #%d" % i], "B=CANCEL")
                if self.k.any_pressed():
                    if self.wait_key() in ("B", "LEFT"):
                        return
                if cand == spk:
                    found = (chain, i)
                    break
            if found is None:
                if not self.confirm("NOT FOUND", ["ACCT %d" % self.account,
                                                  "#0-%d" % (start + B - 1), "",
                                                  "SEARCH NEXT", "%d?" % B]):
                    self.message("UNVERIFIED", ["NOT FOUND IN", "ACCT %d #0-%d" % (self.account, start + B - 1),
                                                "", "OTHER ACCT OR", "HIGHER INDEX?"],
                                 "A=BACK", lcd.RED)
                    self.wait_key(("A", "CTRL", "B"))
                    return
                start += B

        chain, i = found
        kind = "RECEIVE" if chain == AV.RECEIVE else "CHANGE"
        self.d.clear(lcd.BLACK)
        y = self._chrome("VERIFIED", "A=OK")
        self.d.text_big("%s #%d" % (kind, i), 6, y, lcd.GREEN, 2)
        y += 24
        self.d.text_big("ACCT %d" % self.account, 6, y, lcd.WHITE, 2)
        y += 24
        self.d.text(AV.path_str(self.account, chain, i), 6, y, lcd.GREY)
        y += 16
        self.draw_addr(clean, 6, y)
        self.d.show()
        self.wait_key(("A", "CTRL", "B"))

    # ── เมนูหลัก ─────────────────────────────────────────────────────
    def screen_test_seed(self):
        names = devseed.names()
        j = self.menu("TEST SEED", names)
        if j is not None:
            mn, _desc = devseed.get(names[j])
            self.load_mnemonic(mn, is_test=True)

    def _clear_seed(self):
        """ล้างสถานะ seed ทุกค่า — ทางเดียวที่ใช้ล้าง (Unload · FP ไม่ตรงตอน Load SeedQR)

        🔴 บัค B (15 ก.ย. 2026): เดิมแต่ละที่ล้างเอง ลืมบางค่า (ตอน FP ไม่ตรงไม่ได้รีเซ็ต account)
           รวมไว้ที่เดียว เพิ่มค่าใหม่เมื่อไหร่แก้ที่นี่ที่เดียว
        """
        self.root = None
        self.mnemonic = None
        self.passphrase = ""
        self.is_test = False
        self.account = 0
        gc.collect()

    def screen_unload(self):
        """ล้าง seed ออก กลับหน้าแรก โดยไม่ต้องปิดเปิดเครื่อง (ผู้ใช้ ขอ 14 ก.ย. 2026)

        ⚠️ MicroPython ไม่มีทางลบข้อความในหน่วยความจำให้เป็นศูนย์ได้จริง
           ตัดการอ้างอิงทิ้งแล้วเก็บขยะ = โปรแกรมเข้าถึงไม่ได้แล้ว แต่เศษอาจค้างจนถูกเขียนทับ
           ล้างจริงคือปิดเครื่อง (RAM ไม่มีไฟ = หาย)
        """
        if not self.confirm("UNLOAD?", ["CLEAR SEED", "FROM MEMORY", "", "PAPER BACKUP", "IS SAFE?"]):
            return
        self._clear_seed()
        self.message("UNLOADED", ["SEED CLEARED", "", "POWER OFF =", "FULL WIPE"], "A=OK")
        self.wait_key(("A", "CTRL", "B"))

    def run(self):
        """เมนู 2 ชั้นแบบ Jade (ผู้ใช้ ออกแบบ 14 ก.ย. 2026)

        ยังไม่มี seed: New seed / Existing seed / Test seed / Status
        มี seed แล้ว (Wallet): Account · Export xpub · Verify addr · Sign PSBT ·
                              Passphrase · SeedQR backup · Status · Unload seed
        ตัดออกแล้ว: Addresses (ใช้ Verify addr แทน — ให้ wallet สร้างที่อยู่ เครื่องแค่ยืนยัน)
                    Sign PSBT > From file (ใช้ทดสอบก่อนมีสแกนเนอร์)
        seed ทุกทางเป็น temporary — เครื่องไม่เก็บลงแฟลช
        """
        while True:
            if self.root is None:
                sel = self.menu("START", ["New seed", "Existing seed", "Test seed", "Status"],
                                "A=SELECT")
                if sel in (0, 1):
                    # ปิด USB ก่อนเริ่มทอยเต๋า/พิมพ์คำ/สแกน — คำอยู่ใน RAM ตั้งแต่ตอนกรอก ไม่ใช่แค่ตอนโหลดเสร็จ
                    self.guard_usb()
                if sel == 0:
                    self.screen_new_seed()
                elif sel == 1:
                    self.screen_existing_seed()
                elif sel == 2:
                    self.screen_test_seed()
                elif sel == 3:
                    self.screen_status()
            else:
                items = ["Account: %d" % self.account, "Export xpub", "Verify addr",
                         "Sign PSBT", "Passphrase", "SeedQR backup", "Status", "Unload seed"]
                sel = self.menu("WALLET", items, "A=SELECT")
                if sel == 0:
                    self.pick_account()
                elif sel == 1:
                    self.screen_export_xpub()
                elif sel == 2:
                    self.screen_verify_addr()
                elif sel == 3:
                    self.screen_scan()
                elif sel == 4:
                    self.screen_set_passphrase()
                elif sel == 5:
                    self.screen_seedqr()
                elif sel == 6:
                    self.screen_status()
                elif sel == 7:
                    self.screen_unload()


def firmware_info():
    """เลขรุ่นที่ deploy.sh เขียนไว้ใน coreid.py — ไม่มีไฟล์/ฟิลด์ (ส่งด้วย deploy รุ่นเก่า) = "?" """
    out = {}
    try:
        import coreid
    except Exception:
        coreid = None
    for k in ("VERSION", "COMMIT", "BUILD_SHA", "CORE_SHA", "DEVICE"):
        out[k] = str(getattr(coreid, k, "?")) if coreid is not None else "?"
    return out


def splash(app, seconds=5):
    """หน้าเปิดเครื่อง — โชว์ชื่อเครื่องก่อนเข้าเมนู

    กดปุ่มไหนก็ข้ามได้ทันที ไม่ต้องรอครบ
    scale 4 = 32 พิกเซลต่อตัวอักษร -> "SIGNER" 6 ตัว = 192 กว้าง เหลือขอบข้างละ 24
    """
    d = app.d
    d.clear(lcd.BLACK)
    d.text_big("PICO", 56, 66, lcd.WHITE, 4)
    d.text_big("SIGNER", 24, 106, lcd.YELLOW, 4)
    # เลขรุ่นใต้ชื่อ — เห็นทุกครั้งที่เปิดเครื่องว่ารันรุ่นไหน (เพิ่ม 15 ก.ย. 2026)
    ver = "v" + firmware_info()["VERSION"]
    d.text_big(ver[:14], max(0, (240 - len(ver[:14]) * 16) // 2), 156, lcd.GREY, 2)
    b = app.bat()
    if b:
        d.text_big("BAT %d%% %s" % (b[0], "CHG" if b[3] == "CHARGING" else ""),
                   6, 196, lcd.GREY, 2)
    d.show()
    app.wait_key(timeout_ms=seconds * 1000)


APP = None      # main.py ใช้จอของแอปนี้วาดหน้า CRASH (จองจอใหม่ 115 KB ตอนแรมหมดไม่ได้ — 15 ต.ค. 2026)


def main():
    global APP
    APP = App()
    splash(APP)
    APP.run()

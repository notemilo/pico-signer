"""เดินเมนูใหม่ของ Pico ด้วยการกดปุ่มจำลอง — จับบั๊กตอนรันก่อนขึ้นเครื่องที่มี seed

🔑 ทำไมต้องมี (14 ก.ย. 2026 จัดเมนูใหม่แบบ Jade):
   เทสอื่นเทสแค่ตรรกะล้วน (dice/psbt/addrverify) แต่หน้าจอใหม่ต่อสายกันเยอะ
   ส่งผิดชื่อ/ผิดจำนวนอาร์กิวเมนต์ = พังตอนกดบนเครื่องจริง
   จอ ปุ่ม สแกนเนอร์ แบต เป็นตัวหลอกทั้งหมด · ตรรกะ seed/psbt/ที่อยู่เป็นของจริง
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)
os.chdir(SRC)

# ── ตัวหลอกฮาร์ดแวร์ (แบบเดียวกับ test_word_entry.py) ─────────────────
_m = types.ModuleType("machine")
_m.Pin = type("Pin", (), {"__init__": lambda s, *a, **k: None, "IN": 0, "OUT": 1, "PULL_UP": 2,
                          "value": lambda s, *a: 1, "__call__": lambda s, *a: None})
_m.SPI = type("SPI", (), {"__init__": lambda s, *a, **k: None, "write": lambda s, *a: None})
_m.I2C = type("I2C", (), {"__init__": lambda s, *a, **k: None, "scan": lambda s: [],
                          "readfrom_mem": lambda s, *a: b"\x00\x00"})
_m.UART = type("UART", (), {"__init__": lambda s, *a, **k: None, "any": lambda s: 0,
                            "read": lambda s, *a: b"", "deinit": lambda s: None})
sys.modules["machine"] = _m
_f = types.ModuleType("framebuf")
_f.FrameBuffer = type("FrameBuffer", (), {"__init__": lambda s, *a, **k: None})
_f.MONO_HLSB = 0
_f.RGB565 = 1
sys.modules["framebuf"] = _f
# MicroPython time API ที่ CPython ไม่มี
time.ticks_ms = lambda: int(time.monotonic() * 1000)
time.ticks_diff = lambda a, b: a - b
time.ticks_add = lambda a, b: a + b
time.sleep_ms = lambda ms: None
# MicroPython gc API ที่ CPython ไม่มี (หน้า Status เรียก — เจอตอนเพิ่มเทส Status 15 ก.ย. 2026)
import gc as _gc
_gc.mem_free = lambda: 123456

import bip39, bip32, address as addr, devseed, seedqr  # noqa: E402
import lcd, ups  # noqa: E402

LOG = []


OUT_OF_SCREEN = []


class FakeLCD:
    width = 240
    height = 240

    def __init__(self, *a, **k):
        pass

    def fill_rect(self, x, y, w, h, *a, **k):
        # 🔴 วาดเลยขอบจอ = มองไม่เห็นบนเครื่องจริง (แผนที่ย่อของ SeedQR ล้นขอบขวา 16 ก.ย. 2026)
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            OUT_OF_SCREEN.append((x, y, w, h))

    def text(self, s, *a, **k):
        LOG.append(str(s))

    def text_big(self, s, *a, **k):
        LOG.append(str(s))

    def banner(self, s, *a, **k):
        LOG.append(str(s))

    def __getattr__(self, name):          # clear / fill_rect / show / backlight / pixel ...
        return lambda *a, **k: None


class FakeKeys:
    def any_pressed(self):
        return []


lcd.LCD = FakeLCD
lcd.Keys = FakeKeys
ups.try_read = lambda *a, **k: None

import ui  # noqa: E402


class Exhausted(BaseException):
    """ปุ่มในสคริปต์หมด — ใช้ BaseException ไม่ให้โค้ด ui ที่ดัก Exception กลืนไป"""


Q = []


def fake_wait_key(self, allow=None, timeout_ms=None):
    if not Q:
        raise Exhausted()
    k = Q.pop(0)
    if allow is not None and k not in allow:
        raise AssertionError("กด %r แต่หน้านี้รับแค่ %r · จอล่าสุด: %r" % (k, allow, LOG[-6:]))
    return k


ui.App.wait_key = fake_wait_key

# ปิด USB ตอนเริ่มใส่ seed (12 ต.ค. 2026) — สคริปต์ปุ่มเดิมไม่มีหน้านี้ จึงแทนด้วยตัวนับ
# แล้วเทสหน้าจริงแยกไว้ท้ายไฟล์ (หัวข้อ USB)
GUARD_CALLS = []
_REAL_GUARD = ui.App.guard_usb
ui.App.guard_usb = lambda self: GUARD_CALLS.append(1)

# ── สแกนเนอร์หลอก ───────────────────────────────────────────────────
SCAN_TEXT = []      # สิ่งที่ poll() จะคืน (ข้อความ)
SCAN_FRAMES = []    # สิ่งที่ poll_frames() จะคืน (ไบต์ดิบ)
_sc = types.ModuleType("scanner")


class FakeScanner:
    def __init__(self, *a, **k):
        pass

    def poll(self):
        return [SCAN_TEXT.pop(0)] if SCAN_TEXT else []

    def poll_frames(self, gap_ms=150):
        return [SCAN_FRAMES.pop(0)] if SCAN_FRAMES else []

    def flush(self):
        pass

    def deinit(self):
        pass


_sc.Scanner = FakeScanner
sys.modules["scanner"] = _sc
ui.scanner = _sc        # 15 ต.ค. 2026: ui import scanner ตั้งแต่โหลดโมดูล (กันแรมไม่พอตอนสแกน) → ต้องแทนในตัว ui ด้วย

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


def seen(sub):
    return any(sub in line for line in LOG)


def drive(fn, keys):
    """กดปุ่มตามสคริปต์จนหมด — คืนจำนวนปุ่มที่เหลือ (0 = ใช้ครบพอดี)"""
    LOG.clear()
    Q[:] = list(keys)
    try:
        fn()
    except Exhausted:
        pass
    return len(Q)


def new_app():
    a = ui.App()
    return a


WORDS = bip39.wordlist()
WL_PATH = "english.txt"
t0 = time.time()

# ═══ 1. New seed 12 คำ ═══
print("── 1. START → New seed → 12 words → ทอย 128 ครั้ง")
import random
rng = random.Random(1409)
bits = [rng.randint(0, 1) for _ in range(128)]
app = new_app()
keys = ["A",            # START: New seed
        "DOWN", "A"]    # NEW SEED: 12 words
keys += ["A" if b else "B" for b in bits]
keys += ["A",           # หน้า ROLLED (12 คำไม่มีหน้า 8 ตัวเลือก)
         "A",           # show_words
         "DOWN", "A",   # SEED READY: USE SEED
         "A",           # USE SEED? ยืนยัน
         "B",           # CHECK? (ทดสอบกระดาษ) — ข้าม · ทดสอบจริงอยู่หัวข้อ 16
         "A"]           # READY (FP)
left = drive(app.run, keys)
ent = int("".join(map(str, bits)), 2).to_bytes(16, "big")
check("ปุ่มใช้ครบพอดี แล้วค้างที่เมนู WALLET", left == 0 and seen("WALLET"))
check("ได้ 12 คำ และ entropy = บิตที่ทอยทุกบิต",
      app.mnemonic is not None and len(app.mnemonic.split()) == 12
      and bip39.mnemonic_to_entropy(app.mnemonic) == ent)
check("โชว์ PICK #n / OF 1-128 (นับ 1 ตรงกับใบกระดาษ)", seen("OF 1-128") and seen("PICK #%d" % (int("".join(map(str, bits[-7:])), 2) + 1)))
check("account เริ่มที่ 0 และไม่ถามหลังโหลด", app.account == 0 and not seen("ACCOUNT"))

# ═══ 1b. New seed 24 คำ · ทอยคำสุดท้าย 111 (ตัวอย่างของ ผู้ใช้) ═══
print("── 1b. New seed 24 → ทอยคำสุดท้าย 111 = ลำดับที่ 8 ตามใบกระดาษ")
bits24 = [rng.randint(0, 1) for _ in range(253)] + [1, 1, 1]
app = new_app()
keys = ["A", "A"] + ["A" if b else "B" for b in bits24] + ["A", "A", "A", "DOWN", "A", "A", "B", "A"]
left = drive(app.run, keys)
first23w = app.mnemonic.split()[:23] if app.mnemonic else []
c8 = bip39.last_word_candidates(" ".join(first23w)) if first23w else []
check("ปุ่มใช้ครบ · ได้ 24 คำ", left == 0 and len(first23w) == 23)
check("คำที่ 24 = คำลำดับที่ 8 (ตัวสุดท้ายของรายการ)", c8 and app.mnemonic.split()[23] == c8[7])
check("จอ: > ชี้เลข 8 · ROLL 111 · PICK #8 · OF 1-8",
      c8 and seen(">8 %s" % c8[7]) and seen("ROLL 111") and seen("PICK #8") and seen("OF 1-8"))

# ═══ 2. Existing → 24 → Find word 24 (เลือกจาก 8 หน้าเดียว) ═══
print("── 2. Existing → Type 24 → Find word 24 → ทอย 101 = ลำดับที่ 6 จาก 8 (บัค D)")
first23 = ["abandon"] * 23
cands = bip39.last_word_candidates(" ".join(first23))
app = new_app()
app._type_words = lambda n, count: list(first23) if (n, count) == (23, 24) else None
keys = ["DOWN", "A",            # START: Existing seed
        "A",                    # EXISTING: Type 24 words
        "DOWN", "A",            # WORD 24?: Find word 24
        "A", "B", "A",          # ทอยเต๋า 3 ครั้ง 101 = ตัวเลือกที่ 5 (นับ 0) = ลำดับที่ 6
        "A",                    # หน้า 8 คำพร้อม >
        "A",                    # หน้า ROLL/PICK
        "A",                    # show_words
        "A",                    # CHECK 24
        "A"]                    # READY
left = drive(app.run, keys)
check("ปุ่มใช้ครบ", left == 0)
check("คำที่ 24 = ตัวเลือกที่ 5 · checksum ถูก",
      app.mnemonic == " ".join(first23 + [cands[5]]) and bip39.is_valid(app.mnemonic))
check("หน้าเลือกโชว์ครบทั้ง 8 ตัวเลือก นับ 1-8", all(seen(" %d %s" % (i + 1, w)) or seen(">%d %s" % (i + 1, w))
                                                  for i, w in enumerate(cands)))
check("> ชี้บรรทัดที่ 6 (เลข 6) ตอนเลือกตัวเลือกที่ 5 นับจาก 0", seen(">6 %s" % cands[5]))
check("บัค D: หน้าทอยเต๋าโผล่ (ROLL 101 · PICK #6) ไม่ใช่เลื่อนเลือกเอง", seen("ROLL 101") and seen("PICK #6"))

# ═══ 3. Existing → 12 → Find word 12 (ทอย 7 ครั้ง) ═══
print("── 3. Existing → Type 12 → Find word 12 → ทอย 1011001")
first11 = [WORDS[rng.randrange(2048)] for _ in range(11)]
c128 = bip39.last_word_candidates(" ".join(first11))
app = new_app()
app._type_words = lambda n, count: list(first11) if (n, count) == (11, 12) else None
roll = [1, 0, 1, 1, 0, 0, 1]
keys = ["DOWN", "A",            # START: Existing
        "DOWN", "A",            # EXISTING: Type 12 words
        "DOWN", "A"]            # WORD 12?: Find word 12
keys += ["A" if b else "B" for b in roll]
keys += ["A",                   # ROLLED
         "A",                   # show_words
         "A",                   # CHECK 12
         "A"]                   # READY
left = drive(app.run, keys)
idx = int("".join(map(str, roll)), 2)
check("ปุ่มใช้ครบ", left == 0)
check("คำที่ 12 = ตัวเลือกที่ %d จาก 128" % idx, app.mnemonic == " ".join(first11 + [c128[idx]]))
check("  แถบปุ่มหน้าทอยคำที่ 12 เขียนเหมือนหน้า New seed (A=135 B=246)", seen("A=135 B=246") and not seen("A=ODD"))
check("  จอโชว์ ROLL 1011001 · PICK #%d · OF 1-128" % (idx + 1),
      seen("ROLL 1011001") and seen("PICK #%d" % (idx + 1)) and seen("OF 1-128"))
app2 = new_app()
Q[:] = ["A", "X", "B", "B", "B", "B", "B", "B", "B", "A"]
LOG.clear()
w = app2._pick_by_dice(c128, 12)
check("ทอยผิดแล้วกด X ลบได้: A, X, B x7 = ตัวเลือกที่ 0", w == c128[0])

# ═══ 4. Existing → 12 → I have all 12 · checksum ถูก/ผิด ═══
print("── 4. Existing → Type 12 → I have all 12")
v12 = devseed.get("vector-12")[0].split()
app = new_app()
app._type_words = lambda n, count: list(v12) if (n, count) == (12, 12) else None
left = drive(app.run, ["DOWN", "A", "DOWN", "A", "A", "A", "A", "A"])
check("โหลดได้ + รู้ว่าเป็น test seed", left == 0 and app.mnemonic == " ".join(v12) and app.is_test)
bad = v12[:-1] + ["zoo"]
app = new_app()
app._type_words = lambda n, count: list(bad)
left = drive(app.run, ["DOWN", "A", "DOWN", "A", "A", "A", "A", "A"])
check("checksum ผิด = ERROR ไม่โหลด", app.root is None and seen("CHECKSUM BAD"))

# ═══ 5. Wallet: Account + Verify addr ═══
print("── 5. Test seed vector-24 → Account 1 → Verify addr")
v24 = devseed.get("vector-24")[0]
root24 = bip32.HDKey.from_seed(bip39.seed(v24))
a13 = addr.script_to_address(addr.p2wpkh_script(root24.derive("m/84h/0h/1h/0/3").pubkey))
app = new_app()
SCAN_TEXT[:] = [a13]
keys = ["DOWN", "DOWN", "A",     # START: Test seed
        "DOWN", "A",             # TEST SEED: vector-24
        "A",                     # READY
        "A",                     # WALLET: Account: 0
        "UP", "A",               # ACCOUNT -> 1
        "DOWN", "DOWN", "A",     # WALLET: Verify addr
        "A"]                     # VERIFIED
left = drive(app.run, keys)
check("ปุ่มใช้ครบ", left == 0)
check("account = 1 และเมนูโชว์ Account: 1", app.account == 1)
check("VERIFIED · RECEIVE #3 · ACCT 1", seen("VERIFIED") and seen("RECEIVE #3") and seen("ACCT 1"))

print("── 6. Verify addr ที่อยู่ account 1 แต่เลือก account 0 → ไม่เจอ")
app.account = 0
app.VERIFY_BATCH = 5
SCAN_TEXT[:] = [a13]
left = drive(app.screen_verify_addr, ["B", "A"])   # NOT FOUND: ไม่ค้นต่อ · UNVERIFIED: ตกลง
check("NOT FOUND แล้ว UNVERIFIED", left == 0 and seen("NOT FOUND") and seen("UNVERIFIED")
      and not seen("VERIFIED ") and not any(l == "VERIFIED" for l in LOG))
SCAN_TEXT[:] = ["bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusxg3297"]
left = drive(app.screen_verify_addr, ["A"])
check("ที่อยู่ taproot = CANT CHECK", seen("CANT CHECK") and seen("NOT A BC1Q"))

# ═══ 7. Sign PSBT (test.psbt ของ vector-24 account 0) ═══
print("── 7. Sign PSBT จากสแกนเนอร์")
app.account = 0
SCAN_TEXT[:] = [open("../test.psbt").read().strip()]
left = drive(app.screen_scan, ["A"] * 12)
check("ผ่าน REVIEW → SIGNED", seen("REVIEW") and seen("ACCT 0") and seen("SIGNED"))

# ═══ 8. Export xpub ═══
print("── 8. Export xpub (account 1)")
app.account = 1
left = drive(app.screen_export_xpub, ["A", "A"])
check("โชว์ ACCT 1", seen("ACCT 1"))

# ═══ 9. Load SeedQR ═══
print("── 9. Existing → Scan SeedQR (void come effort) → FP ตรง/ไม่ตรง")
import json
rows = json.load(open("../vectors/bip39_vectors.json"))["english"]
void = [r for r in rows if r[1].startswith("void come effort")][0]
frame = bytes.fromhex(void[0]) + b"\r"
app = new_app()
SCAN_FRAMES[:] = [frame, frame, frame]
keys = ["DOWN", "A",        # START: Existing
        "DOWN", "DOWN", "A",  # EXISTING: Scan SeedQR
        "A",                # LOAD QR เตือน
        "A",                # READY
        "A"]                # CHECK FP: ตรง
left = drive(app.run, keys)
fp = app.root.my_fingerprint().hex().upper() if app.root else None
check("โหลดได้ FP F57F296D · account 0", left == 0 and fp == "F57F296D" and app.account == 0)
app = new_app()
SCAN_FRAMES[:] = [frame, frame, frame]
left = drive(app.screen_load_seedqr, ["A", "A", "B", "A"])
check("ตอบว่า FP ไม่ตรง = ล้าง seed", app.root is None and seen("CLEARED"))

import seedqr as _sq
_dig = _sq.mnemonic_to_standard_digits(void[1], WL_PATH).encode()
app = new_app()
SCAN_FRAMES[:] = [_dig, _dig, _dig]
left = drive(app.screen_load_seedqr, ["A", "A", "A"])      # LOAD QR · READY · CHECK FP
check("Pico อ่าน Standard SeedQR (ตัวเลข) ได้ด้วย",
      left == 0 and app.root is not None and app.root.my_fingerprint().hex().upper() == "F57F296D")
app = new_app()
SCAN_FRAMES[:] = [b"\xff" * 32] * 6
left = drive(app.screen_load_seedqr, ["A", "A"])
check("Pico ปฏิเสธเฟรมขยะ FF 32 ตัว", app.root is None and not seen("READ 1/3"))

# ═══ 10. Unload ═══
print("── 10. WALLET → Unload seed")
app = new_app()
Q[:] = ["A"]
app.load_mnemonic(v24, is_test=True)
app.account = 3
keys = ["DOWN"] * 7 + ["A",   # WALLET: Unload seed
                       "A",   # UNLOAD? ยืนยัน
                       "A"]   # UNLOADED
left = drive(app.run, keys)
check("กลับหน้า START · ล้าง seed/account", left == 0 and app.root is None and app.mnemonic is None
      and app.account == 0 and seen("START"))

# ═══ 12. บัค F: เลือก account 1 แต่ PSBT เป็นของ account 0 → ไม่เซ็น ═══
print("── 12. บัค F: Sign PSBT ข้าม account ต้องถูกปฏิเสธ")
app = new_app()
Q[:] = ["A"]
app.load_mnemonic(v24, is_test=True)
app.account = 1
SCAN_TEXT[:] = [open("../test.psbt").read().strip()]
left = drive(app.screen_scan, ["A"] * 6)
check("ขึ้น WRONG ACCT · ไม่ถึงหน้า REVIEW · ไม่มีหน้า SIGNED",
      seen("WRONG ACCT") and any(l == "INPUT ACCT" for l in LOG) and any(l == "0" for l in LOG) and any(l == "YOU USE ACCT" for l in LOG) and any(l == "1" for l in LOG)
      and not seen("REVIEW") and not any(l == "SIGNED" for l in LOG))

# ═══ 13. บัค H: ใส่ passphrase แล้ว account ต้องคงเดิม · READY โชว์ ACCT ═══
print("── 13. บัค H: Passphrase คง account")
app = new_app()
drive(lambda: app.load_mnemonic(v24, True), ["A"])
check("โหลด seed ใหม่ READY โชว์ ACCT 0", app.account == 0 and seen("ACCT 0"))
app.account = 3
app.screen_passphrase = lambda current="": "abc"
left = drive(app.screen_set_passphrase, ["A", "A"])     # CONFIRM · READY
check("ใส่ passphrase: account ยัง 3 · passphrase abc · READY โชว์ ACCT 3",
      left == 0 and app.account == 3 and app.passphrase == "abc" and seen("ACCT 3"))
drive(lambda: app.load_mnemonic(devseed.get("vector-12")[0], True), ["A"])
check("เปลี่ยนเป็น seed อื่น: account กลับ 0 · READY โชว์ ACCT 0", app.account == 0 and seen("ACCT 0"))

# ═══ 14. บัค B: ล้าง seed ต้องล้างครบทุกค่า ═══
print("── 14. บัค B: _clear_seed ล้างครบ · ใช้ทั้ง Unload และ FP ไม่ตรง")
app = new_app()
app.root, app.mnemonic, app.passphrase, app.is_test, app.account = object(), "x", "pw", True, 9
app._clear_seed()
check("root/mnemonic/passphrase/is_test/account ถูกล้างครบ",
      app.root is None and app.mnemonic is None and app.passphrase == "" and app.is_test is False
      and app.account == 0)
app = new_app()
drive(lambda: app.load_mnemonic(v24, True), ["A"])
app.account, app.passphrase = 4, "pw"
SCAN_FRAMES[:] = [frame, frame, frame]
left = drive(app.screen_load_seedqr, ["A", "A", "A", "B", "A"])   # REPLACE · LOAD QR · READY · CHECK FP=ไม่ตรง · CLEARED
check("Load SeedQR แล้วตอบ FP ไม่ตรง: ล้างครบ account 0 passphrase ว่าง",
      left == 0 and app.root is None and app.account == 0 and app.passphrase == "" and seen("CLEARED"))
import ui as _ui_src
check("Unload กับ FP ไม่ตรง เรียก _clear_seed (ไม่ล้างเองแยก)",
      open(_ui_src.__file__).read().count("self._clear_seed()") >= 2)

# ═══ 10b. หน้าตาราง SeedQR ต้องไม่วาดเลยขอบจอ (ทั้ง Compact และ Standard) ═══
print("── 10b. SeedQR backup: ตารางและแผนที่ย่อต้องอยู่ในจอ")
app = new_app()
Q[:] = ["A"]
app.load_mnemonic(v24, is_test=True)
for label, keys in (("Compact", ["A", "A", "A"] + ["RIGHT"] * 26 + ["B"]),
                    ("Standard", ["A", "DOWN", "A", "A"] + ["RIGHT"] * 37 + ["B"])):
    OUT_OF_SCREEN.clear()
    left = drive(app.screen_seedqr, keys)
    check("%s: ไล่ทุกบล็อกแล้วไม่มีอะไรวาดเลยขอบจอ %s" % (label, OUT_OF_SCREEN[:2]),
          left == 0 and not OUT_OF_SCREEN)
check("Standard โชว์บล็อกถึง F6", seen("BLOCK F6"))

# ═══ 11. Status 2 หน้า + เลขรุ่น ═══
print("── 11. Status → A (หน้าเฟิร์มแวร์)")
app = new_app()
cid = types.ModuleType("coreid")
cid.VERSION, cid.COMMIT, cid.BUILD_SHA, cid.CORE_SHA, cid.DEVICE = "2.0.0", "6c88921", "1234abcd5678ef90", "bd5e9d1a2b7de757", "pico"
sys.modules["coreid"] = cid
left = drive(app.screen_status, ["A", "A"])
check("หน้า 2 โชว์ VER 2.0.0 · GIT · BLD · CORE · DEV", left == 0 and seen("VER 2.0.0") and seen("GIT 6c88921")
      and seen("BLD 1234abcd") and seen("CORE bd5e9d1a") and seen("DEV pico"))
left = drive(app.screen_status, ["B"])
check("หน้าแรกกด B ออกเลย ไม่ไปหน้า 2", left == 0 and not seen("VER "))
del sys.modules["coreid"]
check("ไม่มี coreid → โชว์ ? ไม่พัง", ui.firmware_info()["VERSION"] == "?")

# ═══ 12. ปิด USB ตอนเริ่มใส่ seed (12 ต.ค. 2026) ═══
print("── 12. USB: New/Existing seed สั่งปิด · Test seed ไม่สั่ง · หน้าจอสำเร็จ/ล้มเหลว")
for label, keys, want in (("New seed", ["A"], 1), ("Existing seed", ["DOWN", "A"], 1),
                          ("Test seed", ["DOWN", "DOWN", "A"], 0)):
    GUARD_CALLS.clear()
    drive(new_app().run, keys)
    check("%s → สั่งปิด USB %d ครั้ง (ได้ %d)" % (label, want, len(GUARD_CALLS)), len(GUARD_CALLS) == want)
real_off = ui.usb_data_off
try:
    ui.usb_data_off = lambda: True
    app = new_app()
    left = drive(lambda: _REAL_GUARD(app), ["A"])
    check("ปิดได้ → หน้า USB OFF + usb_off=True + Status ขึ้น USB DATA OFF",
          left == 0 and app.usb_off and seen("NO COMPUTER") and seen("POWER OFF TO"))
    drive(app.screen_status, ["B"])
    ok_status = seen("USB DATA OFF")
    left = drive(lambda: _REAL_GUARD(app), [])
    check("ปิดแล้ว เรียกซ้ำไม่ถามอีก · Status ถูก", left == 0 and not LOG and ok_status)
    ui.usb_data_off = lambda: False
    app = new_app()
    left = drive(lambda: _REAL_GUARD(app), ["A"])
    check("ปิดไม่ได้ → เตือน DO NOT PLUG + usb_off=False", left == 0 and not app.usb_off and seen("DO NOT PLUG"))
finally:
    ui.usb_data_off = real_off
check("บนแมค (ไม่มี machine) usb_data_off คืน False ไม่พัง", ui.usb_data_off() is False)
# 13 ต.ค. 2026: boot.py ปิด USB ตั้งแต่บูต → App ต้องรู้ตั้งแต่เริ่ม และไม่ถามซ้ำ
real_is_off = ui.usb_is_off
try:
    ui.usb_is_off = lambda: True
    app = new_app()
    left = drive(lambda: _REAL_GUARD(app), [])
    check("boot ปิด USB แล้ว → usb_off=True ตั้งแต่เริ่ม · guard ไม่ขึ้นหน้าซ้ำ", app.usb_off and left == 0 and not LOG)
finally:
    ui.usb_is_off = real_is_off
check("บนแมค usb_is_off คืน False ไม่พัง", ui.usb_is_off() is False)

# ═══ 16. 15 ต.ค. 2026 — สิ่งที่ยืมแนวคิดจาก SeedSigner ═══
print("── 16. SeedQR ตรวจกระดาษ · passphrase ช่องว่าง/FP เดิม · PSBT LIES · NOT YOURS")
_keys_qr = ["A",    # TEST SEED ยืนยัน
            "A",    # เมนู SEED QR: Compact
            "A",    # หน้า SEED QR (วิธีวาด)
            "B"]    # ออกจากตาราง
# ⚠️ seed ทดสอบ abandon...art มี entropy เป็นศูนย์ล้วน — ตัวอ่าน Compact ปฏิเสธเฟรมไบต์ซ้ำทั้งก้อน (กันอ่านขยะ)
#    จึงใช้ seed "void come effort…" (เวกเตอร์ทางการ) เป็นตัวที่โหลด · กระดาษผิด = Standard ของ abandon…art
app = new_app()
drive(lambda: app.load_mnemonic(void[1], True), ["A"])
SCAN_FRAMES[:] = [frame] * 3
left = drive(app.screen_seedqr, _keys_qr + ["A", "A"])     # CHECK QR? ใช่ · QR OK
check("วาดเสร็จ → สแกนกระดาษที่ตรง = QR OK · seed เดิมยังโหลดอยู่",
      left == 0 and seen("CHECK QR?") and seen("PAPER MATCHES") and app.mnemonic == void[1])
SCAN_FRAMES[:] = [_sq.mnemonic_to_standard_digits(v24, WL_PATH).encode()] * 3
left = drive(app.screen_seedqr, _keys_qr + ["A", "A"])
check("สแกนกระดาษ seed อื่น = QR WRONG · seed ที่โหลดไม่ถูกแตะ",
      left == 0 and seen("DIFFERENT SEED") and not seen("PAPER MATCHES") and app.mnemonic == void[1])
SCAN_FRAMES[:] = []
left = drive(app.screen_seedqr, _keys_qr + ["B"])
check("กด B ข้ามการตรวจได้", left == 0 and seen("CHECK QR?") and not seen("SCAN SEED"))

app = new_app()
drive(lambda: app.load_mnemonic(v24, True), ["A"])
fp0 = app.root.my_fingerprint().hex().upper()
app.screen_passphrase = lambda current="": "a b "
left = drive(app.screen_set_passphrase, ["A", "A"])         # CONFIRM · READY
fp1 = app.root.my_fingerprint().hex().upper()
check("passphrase มีช่องว่าง: บอกความยาว + คำอธิบายกล่องเทา · READY โชว์ FP เดิม (WAS)",
      left == 0 and seen("PASSPHRASE 4:") and seen("GREY BOX = SPACE")
      and seen("FP " + fp1) and seen("WAS " + fp0) and fp0 != fp1)
app.screen_passphrase = lambda current="": "a b "
drive(app.screen_set_passphrase, ["A", "A"])
check("ใส่ passphrase เดิมซ้ำ = ไม่โชว์ WAS (กระเป๋าไม่เปลี่ยน)", not seen("WAS "))

import base64 as _b64
import psbt as _P
_raw = _b64.b64decode(open("../test.psbt").read().strip())
_ps = _P.PSBT.parse(_raw)
for _m in _ps.outputs:
    for _i, (_k, _v) in enumerate(_m.items_):
        if _k[0] == _P.OUT_BIP32_DERIVATION:
            _m.items_[_i] = (bytes([_k[0]]) + b"\x02" + b"\x55" * 32, _v)     # pubkey ปลอม + fingerprint เรา
app = new_app()
drive(lambda: app.load_mnemonic(v24, True), ["A"])
SCAN_TEXT[:] = [_b64.b64encode(_ps.serialize()).decode()]
left = drive(app.screen_scan, ["A"] * 4)
check("PSBT โกหกเรื่องกุญแจ → จอ PSBT LIES · ไม่ถึงหน้า REVIEW",
      seen("PSBT LIES") and seen("MAY BE HACKED") and not seen("REVIEW"))

app = new_app()
drive(lambda: app.load_mnemonic(devseed.get("vector-alt")[0], True), ["A"])
SCAN_TEXT[:] = [open("../test.psbt").read().strip()]
left = drive(app.screen_scan, ["A"] * 4)
check("seed ผิด → NOT YOURS ก่อนหน้ารีวิว (ไม่ต้องกดผ่านรีวิว)",
      seen("NOT YOURS") and seen("WRONG SEED OR") and not seen("REVIEW"))

app = new_app()
drive(lambda: app.load_mnemonic(v24, True), ["A"])
SCAN_TEXT[:] = [open("../test.psbt").read().strip()]
drive(app.screen_scan, ["A"])
check("PSBT ปกติ (input ของเราทั้งหมด) หน้า REVIEW ขึ้น 'IN   1' ไม่มีคำว่า MINE",
      seen("REVIEW") and seen("IN   1") and not seen("MINE"))

# ทดสอบกระดาษหลังสร้าง seed (ไม่มีตัวสุ่ม: คำหลอก = คำข้าง ๆ · ตำแหน่งคำจริง = ลำดับ BIP39 mod 4)
_q = void[1].split()
def _ans(w):
    return ["DOWN"] * (WORDS.index(w) % 4) + ["A"]
app = new_app()
keys = []
for w in _q:
    keys += _ans(w)
keys += ["A"]                                               # PAPER OK
res = []
left = drive(lambda: res.append(app.quiz_words(_q)), keys)
check("ตอบถูกครบ 24 คำ = PAPER OK คืน True", left == 0 and res == [True] and seen("ALL 24 WORDS"))
check("คำหลอกเป็นคำข้าง ๆ (หน้าตาคล้าย) ไม่ใช่สุ่ม",
      seen(WORDS[(WORDS.index(_q[0]) + 1) % 2048]) and seen(WORDS[(WORDS.index(_q[0]) - 1) % 2048]))
wrong_pos = (WORDS.index(_q[0]) % 4 + 1) % 4
res = []
left = drive(lambda: res.append(app.quiz_words(_q)), ["DOWN"] * wrong_pos + ["A", "B"])
check("ตอบผิดคำแรก แล้วกด B = WRONG · คืน False (ยังไม่โหลด seed)",
      left == 0 and res == [False] and seen("WORD 1 IS") and seen("CHECK PAPER"))
res = []
left = drive(lambda: res.append(app.quiz_words(_q)), _ans(_q[0]) + ["B"])
check("กด B กลางทาง = หยุด คืน False", left == 0 and res == [False])

print("\n(ใช้เวลา %.1f วิ)" % (time.time() - t0))
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_ui_flows ผ่านครบ")

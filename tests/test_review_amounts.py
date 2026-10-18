"""หน้ารีวิวก่อนเซ็น: ยอดเงินต้องไม่ถูกตัด · ปลายทางแปลกต้องไม่เซ็น · บอก relative timelock / เลขที่อยู่เงินทอน

🔴 17 ต.ค. 2026 — รีวิวภายนอก (GHSA-334h-x4f4-34h3 · รายงานส่วนตัวจาก kkdao):
   message() ตัดทุกบรรทัดที่ 14 ตัว → "FEE  " + เลขซาโตชิ เหลือที่ให้ตัวเลขแค่ 9 ตัว
   ค่าธรรมเนียม 10 BTC ขึ้นจอเป็น "FEE  1,000,000" (ดูเหมือน 0.01 BTC) แล้วเครื่องก็เซ็นให้
   เทสนี้เดินหน้าจอจริง (ui.screen_sign) ด้วยจอหลอกที่จดทุกบรรทัด แล้วเทียบยอดบนจอกับยอดจริงทีละซาโตชิ
   สร้าง PSBT/คีย์เองทั้งหมด (ไม่ได้ใช้สคริปต์ของผู้รายงาน)
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
os.chdir(os.path.join(HERE, "..", "src"))

# ── ตัวหลอกฮาร์ดแวร์ ───────────────────────────────────────────────
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
time.ticks_ms = lambda: int(time.monotonic() * 1000)
time.ticks_diff = lambda a, b: a - b
time.sleep_ms = lambda ms: None
import gc as _gc  # noqa: E402
_gc.mem_free = lambda: 123456

import lcd, ups  # noqa: E402
import bip32, address as addr, psbt as P, tx as txmod  # noqa: E402
from psbt_fixture import attach_prev  # noqa: E402

FRAMES = []
CUR = []
OFF = []


class FakeLCD:
    width = 240
    height = 240

    def __init__(self, *a, **k):
        pass

    def clear(self, *a):
        CUR.clear()

    def text_big(self, s, x, y, color=None, scale=2):
        s = str(s)
        CUR.append((s, x, y, scale))
        # แถบบอกปุ่ม (y >= 200) ใช้ 15 ตัวที่ x=2 = 242 พิกเซล มาตั้งแต่แรก (ช่องสุดท้ายของฟอนต์ว่าง) — ไม่นับ
        if x + len(s) * 8 * scale > 240 and y < 200:
            OFF.append((s, x, y))

    def text(self, s, x, y, *a, **k):
        CUR.append((str(s), x, y, 1))
        if x + len(str(s)) * 8 > 240:
            OFF.append((str(s), x, y))

    def show(self):
        FRAMES.append(list(CUR))

    def __getattr__(self, name):
        return lambda *a, **k: None


lcd.LCD = FakeLCD
lcd.Keys = type("K", (), {"any_pressed": lambda s: []})
ups.try_read = lambda *a, **k: None
_sc = types.ModuleType("scanner")
_sc.Scanner = object
sys.modules["scanner"] = _sc

import ui  # noqa: E402

H = P.HARDENED
ROOT = bip32.HDKey.from_seed(bytes(range(32)))
FP = ROOT.my_fingerprint()
OTHER = bip32.HDKey.from_seed(b"someone else's wallet seed 1234")

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


def node(path):
    n = ROOT
    for i in path:
        n = n.derive_child(i)
    return n


def apath(chain, idx):
    return (84 + H, H, H, chain, idx)


def origin(path):
    return FP + b"".join(i.to_bytes(4, "little") for i in path)


def build(ins, outs, version=2, sequence=0xFFFFFFFD, wu_tail=b""):
    """ins: [(chain, idx, sat)] · outs: [(spk, sat, path or None)]"""
    p = P.PSBT()
    p.tx = txmod.Transaction(version=version)
    for n, (chain, idx, value) in enumerate(ins):
        p.tx.vin.append(txmod.TxInput(bytes([n + 1]) * 32, 0, sequence=sequence))
        m = P.KVMap()
        if chain == "other":                       # input ของคนอื่น (payjoin/coinjoin) — fp ของเขา
            k = OTHER.derive_child(idx)
            m.put(bytes([P.IN_WITNESS_UTXO]), txmod.TxOutput(value, addr.p2wpkh_script(k.pubkey)).serialize())
            m.put(bytes([P.IN_BIP32_DERIVATION]) + k.pubkey, OTHER.my_fingerprint() + idx.to_bytes(4, "little"))
        else:
            pth = apath(chain, idx)
            pub = node(pth).pubkey
            m.put(bytes([P.IN_WITNESS_UTXO]), txmod.TxOutput(value, addr.p2wpkh_script(pub)).serialize())
            m.put(bytes([P.IN_BIP32_DERIVATION]) + pub, origin(pth))
        p.inputs.append(m)
    for spk, value, pth in outs:
        p.tx.vout.append(txmod.TxOutput(value, spk))
        m = P.KVMap()
        if pth is not None:
            m.put(bytes([P.OUT_BIP32_DERIVATION]) + node(pth).pubkey, origin(pth))
        p.outputs.append(m)
    q = attach_prev(p)
    if wu_tail:
        for m in q.inputs:
            m.items_ = [(k, v + wu_tail if k[0] == P.IN_WITNESS_UTXO else v) for k, v in m.items_]
    return q.serialize()


def ext(i=0):
    return addr.p2wpkh_script(OTHER.derive_child(i).pubkey)


def chg(idx, value, chain=1):
    pth = apath(chain, idx)
    return (addr.p2wpkh_script(node(pth).pubkey), value, pth)


def run(raw, is_test=False):
    """เดิน screen_sign กด A ทุกหน้า — คืน (frames, signed_raw หรือ None)"""
    FRAMES.clear()
    OFF.clear()
    app = ui.App()
    app.root = ROOT
    app.account = 0
    app.is_test = is_test
    app.wait_key = lambda *a, **k: "A"
    out = []
    app.show_bbqr = lambda raw, *a: out.append(raw)
    app.screen_sign(raw)
    return list(FRAMES), (out[0] if out else None)


def titles(frames):
    return [f[0][0] for f in frames if f]


def body(frames, title_prefix):
    """บรรทัดเนื้อความ (scale 2 ที่ x=6) ของทุกหน้าที่หัวเรื่องขึ้นต้นด้วย title_prefix ต่อกัน"""
    out = []
    for f in frames:
        if f and f[0][0].startswith(title_prefix):
            out += [t for t, x, y, sc in f[1:] if x == 6 and sc == 2]
    return out


def parse_amt(label, val, nxt=None):
    """แปลงยอดบนจอกลับเป็นซาโตชิ — หน่วยอยู่ท้ายบรรทัดยอด ท้ายหัวข้อ หรือบรรทัดถัดไป (10 BTC ขึ้นไป)"""
    if val.endswith(" SAT"):
        return int(val[:-4].replace(",", ""))
    if val.endswith(" BTC"):
        val = val[:-4]
    else:
        assert label.endswith(" BTC") or nxt == "BTC", (label, val, nxt)
    whole, frac = val.split(".")
    assert len(frac) == 8
    return int(whole) * 100000000 + int(frac)


def review_amount(lines, key):
    """หาบรรทัดหัวข้อที่ขึ้นต้นด้วย key แล้วอ่านยอดบรรทัดถัดไป"""
    for i, ln in enumerate(lines):
        if ln.lstrip("! ").startswith(key):
            return parse_amt(ln, lines[i + 1], lines[i + 2] if i + 2 < len(lines) else None)
    raise AssertionError("ไม่เจอ %s ใน %r" % (key, lines))


def main():
    print("── 1. amt_lines: ทุกยอดพอดี 14 ตัว และแปลงกลับได้ตรงทุกซาโตชิ (ไม่ถูกตัด)")
    vals = [0, 1, 999, 1000, 99_999_999, 100_000_000, 123_456_789, 999_999_999, 1_000_000_000,
            11_100_000_000, 999_999_999_999, 1_000_000_000_000, 9_999_999_999_999]
    ok = True
    for v in vals:
        for label in ("SEND", "FEE 9.9%", "CHG 1/150", "CHG 1/99200"):
            ln = ui.amt_lines(label, v)
            if any(len(x) > 14 for x in ln) or parse_amt(ln[0], ln[1], ln[2] if len(ln) > 2 else None) != v:
                ok = False
                print("     ผิด", label, v, ln)
    check("%d ยอด x 4 หัวข้อ ตั้งแต่ 0 ถึง 99,999.99999999 BTC" % len(vals), ok)
    try:
        ui.amt_lines("SEND", 10_000_000_000_000)
        check("100,000 BTC ขึ้นไป = AmountTooBig (ไม่ตัด)", False)
    except ui.AmountTooBig:
        check("100,000 BTC ขึ้นไป = AmountTooBig (ไม่ตัด)", True)

    print("── 2. เคสในรายงาน: เข้า 111 BTC · ส่ง 101 BTC · ค่าธรรมเนียม 10 BTC")
    raw = build([(0, 5, 11_100_000_000)], [(ext(), 10_100_000_000, None)])
    fr, signed = run(raw)
    rv = body(fr, "REVIEW")
    fee = review_amount(rv, "FEE")
    check("จอบอกค่าธรรมเนียม %d sat = ยอดจริง 1,000,000,000 · ส่ง %d" % (fee, review_amount(rv, "SEND")),
          fee == 1_000_000_000 and review_amount(rv, "SEND") == 10_100_000_000)
    check("บอกเป็นร้อยละ (9.9%) ด้วย", any("9.9%" in x for x in rv))
    check("ไม่มีข้อความเกินขอบจอสักหน้า %r" % OFF[:2], not OFF)
    check("ทุกบรรทัดเนื้อความ <= 14 ตัว (message ไม่ต้องตัด)",
          all(len(t) <= 14 for f in fr for t, x, y, sc in f[1:] if x == 6 and sc == 2))
    to = body(fr, "TO 1/1")
    check("หน้า TO: ยอด 101 BTC เต็ม (เลขบรรทัดหนึ่ง BTC อีกบรรทัด) %r" % to[:2],
          to[:2] == ["101.00000000", "BTC"])
    check("ยังเซ็นได้ (ค่าธรรมเนียมไม่เกินเพดาน 10%)", signed is not None)

    print("── 3. ยอดเล็ก ๆ ปกติ: จอยังอ่านง่าย (SAT) และมีเลขที่อยู่เงินทอน")
    raw = build([(0, 5, 1_000_000)], [(ext(), 300_000, None), chg(150, 699_000)])
    fr, signed = run(raw)
    rv = body(fr, "REVIEW")
    check("REVIEW: %r" % rv,
          rv[:2] == ["SEND", "300,000 SAT"] and rv[3] == "1,000 SAT" and "CHG 1/150" in rv
          and "699,000 SAT" in rv and rv[-1] == "IN 1  ACCT 0")
    check("หน้าเดียวพอ (ไม่ต้องกดเพิ่ม)", titles(fr).count("REVIEW") == 1)
    fr, _ = run(raw, is_test=True)
    check("มีแถบ TEST SEED: บรรทัดครบเท่าเดิม", body(fr, "REVIEW") == rv)
    FRAMES.clear()
    app = ui.App()
    app.is_test = True
    app.wait_key = lambda *a, **k: "A"
    eight = ["L%d" % i for i in range(9)]
    ok = app.message_pages("REVIEW", eight)
    check("message_pages: 9 บรรทัดบนจอ 8 บรรทัด → REVIEW 1/2 + 2/2 ไม่ทิ้งบรรทัด",
          ok and titles(FRAMES) == ["REVIEW 1/2", "REVIEW 2/2"] and body(FRAMES, "REVIEW") == eight)
    app.wait_key = lambda *a, **k: "B"
    check("กด B หน้าแรก = คืน False", app.message_pages("REVIEW", eight) is False)

    print("── 4. ไม่มีเงินทอน / input คนอื่นปน")
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)])
    rv = body(run(raw)[0], "REVIEW")
    check("CHG  NONE", "CHG  NONE" in rv)

    print("── 5. ปลายทางที่จอแสดงไม่ได้ (P2PK) → ไม่เซ็น")
    p2pk = b"\x21" + OTHER.pubkey + b"\xac"
    raw = build([(0, 5, 1_000_000)], [(p2pk, 999_000, None)])
    fr, signed = run(raw)
    check("REFUSED · CANNOT SHOW · ไม่ถึงหน้า REVIEW · ไม่เซ็น",
          signed is None and "REFUSED" in titles(fr) and "REVIEW" not in titles(fr)
          and "CANNOT SHOW" in body(fr, "REFUSED"))
    raw = build([(0, 5, 1_000_000)], [(b"\x6a\x04test", 0, None), (ext(), 999_000, None)])
    fr, signed = run(raw)
    check("OP_RETURN ยังเซ็นได้ (โชว์ OP_RETURN 5B)", signed is not None)

    print("── 6. relative timelock (BIP68)")
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)], sequence=144)
    fr, signed = run(raw)
    rl = body(fr, "REL LOCK")
    check("nSequence 144 · tx v2 → หน้า REL LOCK บอก 144 BLOCKS %r" % rl, "144 BLOCKS" in rl)
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)], sequence=0x00400000 | 10)
    rl = body(run(raw)[0], "REL LOCK")
    check("แบบเวลา 10 x 512 วินาที → 85 MINUTES %r" % rl, "85 MINUTES" in rl)
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)], version=1, sequence=144)
    check("tx version 1 → ไม่มีผล ไม่ขึ้นหน้า", "REL LOCK" not in titles(run(raw)[0]))
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)])
    check("RBF ปกติ (0xFFFFFFFD) → ไม่ขึ้นหน้า", "REL LOCK" not in titles(run(raw)[0]))

    print("── 7. witness_utxo มีไบต์เกินท้าย → ปฏิเสธ · ข้อความ error เป็นอังกฤษ ตัดบรรทัด")
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)], wu_tail=b"\xde\xad")
    fr, signed = run(raw)
    bad = body(fr, "BAD PSBT")
    check("BAD PSBT · ไม่เซ็น · %r" % bad, signed is None and "WITNESS UTXO" in " ".join(bad))
    check("ไม่มีอักษรไทยบนจอ (ฟอนต์วาดไม่ได้)",
          not any(any("฀" <= ch <= "๿" for ch in t) for f in fr for t, *_ in f))

    print("── 8. sign() ตรง ๆ เมื่อ input อื่นไม่มี tx เก่า → ไม่เซ็น")
    q = P.PSBT.parse(build([(0, 5, 1_000_000), (0, 6, 1_000_000)], [(ext(), 1_999_000, None)]))
    q.inputs[1].items_ = [(k, v) for k, v in q.inputs[1].items_ if k[0] != P.IN_NON_WITNESS_UTXO]
    try:
        q.sign(ROOT, account=0)
        check("ต้อง PSBTError", False)
    except P.PSBTError as e:
        check("PSBTError: %s" % e, "NO PREV TX" in str(e))

    print("── 8b. PSBT_GLOBAL_VERSION (BIP174): 0 ผ่าน · อื่น ๆ ปฏิเสธ")
    base = P.PSBT.parse(build([(0, 5, 1_000_000)], [(ext(), 999_000, None)]))
    res = []
    for v in (b"\x00\x00\x00\x00", b"\x02\x00\x00\x00", b"\x00"):
        q = P.PSBT.parse(base.serialize())
        q.g.put(bytes([P.GLOBAL_VERSION]), v)
        try:
            P.PSBT.parse(q.serialize())
            res.append("ok")
        except P.PSBTError:
            res.append("refused")
    check("v0 ผ่าน · v2 ปฏิเสธ · ยาวผิดปฏิเสธ %r" % res, res == ["ok", "refused", "refused"])

    print("── 10. 18 ต.ค. 2026 แนวคิดจาก ShieldSigner: OP_RETURN มีเงิน · ฝุ่น · ค่าธรรมเนียมต่อไบต์ · ยอดรวม")
    raw = build([(0, 5, 1_000_000)], [(b"\x6a\x04test", 1000, None), (ext(), 998_000, None)])
    fr, signed = run(raw)
    check("OP_RETURN แนบ 1,000 sat → REFUSED · BURNS · ไม่เซ็น",
          signed is None and "OUTPUT BURNS" in body(fr, "REFUSED") and "REVIEW" not in titles(fr))
    try:
        P.PSBT.parse(raw).sign(ROOT, account=0)
        check("sign() ตรง ๆ ก็ไม่เซ็น", False)
    except P.PSBTError as e:
        check("sign() ตรง ๆ ก็ไม่เซ็น: %s" % e, "OP_RETURN" in str(e))
    raw = build([(0, 5, 1_000_000)], [(ext(), 500, None), (ext(1), 998_000, None)])
    fr, signed = run(raw)
    td = body(fr, "TINY OUT")
    check("output 500 sat → TINY OUT เตือน (ยังเซ็นได้) %r" % td,
          "500 SAT" in td and "BELOW 546 SAT" in td and signed is not None)
    raw = build([(0, 5, 1_000_000)], [(ext(), 546, None), (ext(1), 998_000, None)])
    check("546 sat พอดี → ไม่เตือน", "TINY OUT" not in titles(run(raw)[0]))
    q = P.PSBT.parse(build([(0, 5, 1_000_000)], [(ext(), 300_000, None), chg(6, 699_000)]))
    vs = P.estimate_vsize(q.tx, [q.input_script_pubkey(0)])
    check("ขนาดโดยประมาณ 1 in 2 out p2wpkh = %d vB (จริง 141 — bitcoinjs ในรายงาน kkdao)" % vs, vs == 141)
    info = q.describe(ROOT, account=0)
    check("fee_rate = 1000 // 141 = %r" % info["fee_rate"], info["fee_rate"] == 7)
    raw = build([(0, 5, 1_000_000)], [(ext(), 920_000, None)])         # ค่าธรรมเนียม 80,000 / ~110 vB
    fr, signed = run(raw)
    rate = body(fr, "FEE RATE")
    check("ค่าธรรมเนียม 80,000 sat ใน ~110 vB → FEE RATE เตือน (ยังไม่เกินเพดาน 10%%) %r" % rate,
          "727" in rate and "SAT/VB" in rate and signed is not None)
    raw = build([(0, 5, 1_000_000)], [(ext(), 999_000, None)])
    check("ค่าธรรมเนียมปกติ → ไม่มี FEE RATE / TINY OUT",
          not {"FEE RATE", "TINY OUT"} & set(titles(run(raw)[0])))

    print("── 11. 18 ต.ค. 2026 แนวคิดจาก Specter-DIY: หน้า INPUTS · มี input คนอื่นปน = ไม่ซ่อนเงินทอน")
    raw = build([(0, 5, 1_000_000)], [(ext(), 300_000, None), chg(6, 699_000)])
    check("input เดียวของเรา → ไม่มีหน้า INPUTS (ไม่เพิ่มหน้าให้กด)", "INPUTS" not in titles(run(raw)[0]))
    raw = build([(0, 5, 1_000_000), (1, 3, 250_000_000)], [(ext(), 300_000, None), chg(6, 250_699_000)])
    fr, signed = run(raw)
    il = body(fr, "INPUTS")
    check("2 input → หน้า INPUTS ยอดทีละก้อน + เลขที่อยู่ %r" % il,
          il == ["#1 0/5", "1,000,000 SAT", "#2 1/3", "2.50000000 BTC"] and signed is not None)
    raw = build([(0, 5, 1_000_000), ("other", 7, 2_000_000)],
                [(ext(), 1_500_000, None), (ext(1), 800_000, None), chg(6, 699_000)])
    fr, signed = run(raw)
    rv = body(fr, "REVIEW")
    to = [t for f in fr if f and f[0][0].startswith("TO ") for t, *_ in f]
    check("input คนอื่นปน → CHG NONE · เงินทอนขึ้นหน้า TO ป้าย YOUR ADDRESS · INPUTS บอก #2 OTHER",
          "CHG  NONE" in rv and "YOUR ADDRESS" in to and "TO 3/3" in titles(fr)
          and "#2 OTHER" in body(fr, "INPUTS") and "IN 2 MINE 1" in rv)
    info = P.PSBT.parse(raw).describe(ROOT, account=0)
    check("describe: own_unhidden=True · is_change=False · ไม่ใช่ ODD PATH",
          [(o["own_unhidden"], o["is_change"], o["odd_owned"]) for o in info["outputs"]][2] == (True, False, False))

    print("── 9. หน้า TO ที่อยู่ยาวสุด (bc1p) + ยอด 2 บรรทัด + แถบ TEST SEED ไม่ล้นแถบปุ่ม")
    tr = b"\x51\x20" + bytes(range(32))
    raw = build([(0, 5, 2_000_000_000)], [(tr, 1_999_000_000, None)])
    fr, _ = run(raw, is_test=True)
    to = [f for f in fr if f and f[0][0].startswith("TO ")]
    ys = [y for t, x, y, sc in to[0][1:] if sc == 2 and t not in ("A=NEXT B=CANCEL",) and y < 210]
    check("ข้อความล่างสุด y=%d + สูง 17 <= แถบปุ่ม 218" % max(ys), max(ys) + 17 <= 218)

    print()
    if fails:
        print("❌ ไม่ผ่าน %d ข้อ" % fails)
        sys.exit(1)
    print("✅ test_review_amounts ผ่านครบ")


main()

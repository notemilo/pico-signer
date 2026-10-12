"""PSBT ที่จงใจทำร้ายเครื่อง — ต้องไม่ค้าง และต้องไม่หลอกให้เซ็นผิด

🔑 พบ 11 ก.ย. 2026 ตอนไล่บั๊กก่อนใส่ seed :
   PSBT ระบุเส้นทางกุญแจได้ยาวไม่จำกัด เครื่องไล่ตามทุกชั้น (~0.9 วิ/ชั้นบน Pico)
   path 300 ชั้น = ค้าง 4.5 นาทีบนหน้า READING กดยกเลิกไม่ได้ ต้องถอดแบต
   ไม่เสียเงิน แต่ QR ใบเดียวทำเครื่องใบ้ได้ — และถ้าคิดว่า "เครื่องพัง" อาจไปทำอย่างอื่นที่เสี่ยงกว่า
"""

import os
import sys
import time
import base64

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import psbt, bip39, bip32, devseed

RAW = base64.b64decode(open("../test.psbt").read().strip())
mn, _ = devseed.get("vector-24")
ROOT = bip32.HDKey.from_seed(bip39.seed(mn))
FP = ROOT.my_fingerprint()
IN_DERIV, OUT_DERIV = 0x06, 0x02


def with_deriv(where, value, extra_entries=0):
    """คืน PSBT ที่แก้ derivation ของ input หรือ output ทุกตัวเป็น value
    extra_entries > 0 = เพิ่มรายการปลอมอีก N รายการ (pubkey สุ่ม) ที่อ้าง fingerprint เรา"""
    ps = psbt.PSBT.parse(RAW)
    maps = ps.outputs if where == "out" else ps.inputs
    tag = OUT_DERIV if where == "out" else IN_DERIV
    for m in maps:
        for i, (k, v) in enumerate(m.items_):
            if k[0] == tag:
                m.items_[i] = (k, value)
        for n in range(extra_entries):
            fake_pub = b"\x02" + bytes([(n * 7 + 1) & 0xFF]) * 32
            m.items_.append((bytes([tag]) + fake_pub, value))
    return ps.serialize()


def timed(fn):
    t0 = time.time(); r = fn(); return r, time.time() - t0


def main():
    fails = 0

    # 1) path ลึก 300 ชั้นที่ output — ต้องจบเร็ว และต้องไม่ถูกนับเป็นเงินทอน
    deep = FP + b"".join((5).to_bytes(4, "little") for _ in range(300))
    info, dt = timed(lambda: psbt.PSBT.parse(with_deriv("out", deep)).describe(ROOT))
    ok = dt < 0.2 and all(not o["is_change"] for o in info["outputs"])
    fails += not ok
    print("1. path 300 ชั้นที่ output  : %.3fs · ทุก output ถูกมองเป็น 'ส่งออก' = %s  %s"
          % (dt, all(not o["is_change"] for o in info["outputs"]), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 2) path ลึก 300 ชั้นที่ input — sign() ต้องจบเร็ว และต้องไม่เซ็น
    n, dt = timed(lambda: psbt.PSBT.parse(with_deriv("in", deep)).sign(ROOT))
    ok = dt < 0.2 and n == 0
    fails += not ok
    print("2. path 300 ชั้นที่ input   : %.3fs · เซ็นไป %d input  %s" % (dt, n, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 3) รายการปลอม 50 รายการต่อ output ลึก 8 ชั้น (พอดีเพดาน) — งบรวมต้องหยุดมัน
    p8 = FP + b"".join((5).to_bytes(4, "little") for _ in range(8))
    def many():
        return psbt.PSBT.parse(with_deriv("out", p8, extra_entries=50)).describe(ROOT)
    try:
        info, dt = timed(many)
        ok = dt < 1.0
        note = "ดูแค่ %d รายการต่อ map" % psbt.MAX_DERIV_PER_MAP
    except psbt.PSBTError as e:
        dt = 0; ok = True; note = "ปฏิเสธ: %s" % e
    fails += not ok
    print("3. 50 รายการปลอมต่อ output  : %.3fs · %s  %s" % (dt, note, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 4) ของจริงยังทำงานปกติ — path ปกติ 5 ชั้น เงินทอนต้องถูกจับได้ และเซ็นได้
    info = psbt.PSBT.parse(RAW).describe(ROOT)
    n = psbt.PSBT.parse(RAW).sign(ROOT)
    ok = info["change"] > 0 and n == 1
    fails += not ok
    print("4. PSBT ปกติ               : เงินทอน %d · เซ็นได้ %d input  %s"
          % (info["change"], n, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 5) map ที่มีคีย์เยอะมาก (5,000 คีย์ไม่รู้จัก) — parse ต้องไม่ช้าแบบ n^2
    ps = psbt.PSBT.parse(RAW)
    for i in range(5000):
        ps.outputs[0].items_.append((b"\xfc" + i.to_bytes(2, "big"), b"x"))
    big = ps.serialize()
    _, dt = timed(lambda: psbt.PSBT.parse(big))
    ok = dt < 1.0
    fails += not ok
    print("5. map 5,000 คีย์            : parse %.3fs  %s" % (dt, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 6) เงินทอนบนเส้นทางแปลก (บัญชีอื่นของ seed เดียวกัน) ต้องไม่ถูกซ่อนเป็น CHG
    #    เดิม: จอขึ้น SEND 0 ผู้ใช้นึกว่าไม่มีอะไรออก แต่เงินไปบัญชีที่กระเป๋าไม่ได้เฝ้าดู
    #    ต้องสมจริง: ที่อยู่ปลายทางเป็นของกุญแจเราจริง ๆ บนบัญชี 999 (ไม่ใช่แค่แปะเส้นทางปลอม
    #    เพราะด่านที่ 3 ของ _owned_keys จับสคริปต์ไม่ตรงกุญแจได้อยู่แล้ว)
    import address as addr
    H = psbt.HARDENED
    odd_path = (84 + H, 0 + H, 999 + H, 0, 0)
    node = ROOT
    for idx in odd_path:
        node = node.derive_child(idx)
    ps = psbt.PSBT.parse(RAW)
    for n, o in enumerate(ps.tx.vout):
        m = ps.outputs[n]
        if any(k[0] == OUT_DERIV for k, _ in m.items_):        # output ที่เดิมเป็นเงินทอน
            o.script_pubkey = addr.p2wpkh_script(node.pubkey)   # ชี้ไปบัญชี 999 จริง ๆ
            m.items_ = [(k, v) for k, v in m.items_ if k[0] != OUT_DERIV]
            m.items_.append((bytes([OUT_DERIV]) + node.pubkey,
                             FP + b"".join(v.to_bytes(4, "little") for v in odd_path)))
    # serialize() เขียน self.g ตรง ๆ ไม่ได้แปลง self.tx กลับ -> ต้องยัด tx ที่แก้แล้วเข้าไปเอง
    ps.g.items_ = [(k, v) for k, v in ps.g.items_ if k[0] != psbt.GLOBAL_UNSIGNED_TX]
    ps.g.items_.insert(0, (bytes([psbt.GLOBAL_UNSIGNED_TX]), ps.tx.serialize(with_witness=False)))
    info = psbt.PSBT.parse(ps.serialize()).describe(ROOT)
    hidden = [o for o in info["outputs"] if o["is_change"]]
    flagged = [o for o in info["outputs"] if o.get("odd_owned")]
    ok = not hidden and flagged
    fails += not ok
    print("6. เงินทอน m/84h/0h/999h/0/0  : ถูกซ่อนเป็น CHG %d · ติดธงเตือน %d  %s"
          % (len(hidden), len(flagged), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 7) เส้นทางเงินทอนปกติต้องยังทำงาน (กันแก้แล้วพัง)
    info = psbt.PSBT.parse(RAW).describe(ROOT)
    ch = [o for o in info["outputs"] if o["is_change"]]
    ok = len(ch) == 1 and ch[0]["path"] == "m/84h/0h/0h/1/0"
    fails += not ok
    print("7. เงินทอน m/84h/0h/0h/1/0    : นับเป็น CHG %d รายการ · path %s  %s"
          % (len(ch), ch[0]["path"] if ch else "-", "ผ่าน" if ok else "ไม่ผ่าน"))

    # 8) รวมเหรียญเข้าตัวเองล้วน -> ต้องยังมีที่อยู่ให้ผู้ใช้ดู
    #    (จำลองตรรกะเดียวกับ ui.screen_sign: ถ้าไม่มีปลายทางนอกกระเป๋า ต้องถอยไปโชว์ทุก output)
    fake = dict(info)
    fake["outputs"] = [dict(o, is_change=True) for o in info["outputs"]]
    dests = [o for o in fake["outputs"] if not o["is_change"]] or fake["outputs"]
    ok = len(dests) == len(fake["outputs"]) and all(o["address"] for o in dests)
    fails += not ok
    print("8. รวมเหรียญเข้าตัวเองล้วน    : จอจะโชว์ที่อยู่ %d รายการ  %s"
          % (len(dests), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 9) เงินทอนเลขไกลเกิน gap — ยังเป็นกุญแจเราแต่กระเป๋าจะหาไม่เจอ ต้องไม่ซ่อนเป็น CHG
    import address as addr
    H = psbt.HARDENED
    far = (84 + H, 0 + H, 0 + H, 1, 999999)
    node = ROOT
    for idx in far:
        node = node.derive_child(idx)
    ps = psbt.PSBT.parse(RAW)
    for n, o in enumerate(ps.tx.vout):
        m = ps.outputs[n]
        if any(k[0] == OUT_DERIV for k, _ in m.items_):
            o.script_pubkey = addr.p2wpkh_script(node.pubkey)
            m.items_ = [(k, v) for k, v in m.items_ if k[0] != OUT_DERIV]
            m.items_.append((bytes([OUT_DERIV]) + node.pubkey,
                             FP + b"".join(v.to_bytes(4, "little") for v in far)))
    ps.g.items_ = [(k, v) for k, v in ps.g.items_ if k[0] != psbt.GLOBAL_UNSIGNED_TX]
    ps.g.items_.insert(0, (bytes([psbt.GLOBAL_UNSIGNED_TX]),
                           ps.tx.serialize(with_witness=False)))
    info = psbt.PSBT.parse(ps.serialize()).describe(ROOT)
    hidden = [o for o in info["outputs"] if o["is_change"]]
    flagged = [o for o in info["outputs"] if o.get("odd_owned")]
    ok = not hidden and flagged
    fails += not ok
    print("9. เงินทอน .../1/999999      : ถูกซ่อนเป็น CHG %d · ติดธงเตือน %d  %s"
          % (len(hidden), len(flagged), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 10) locktime ต้องถูกอ่านออกมา ไม่ใช่เงียบ
    ps = psbt.PSBT.parse(RAW)
    ps.tx.locktime = 900000
    ps.g.items_ = [(k, v) for k, v in ps.g.items_ if k[0] != psbt.GLOBAL_UNSIGNED_TX]
    ps.g.items_.insert(0, (bytes([psbt.GLOBAL_UNSIGNED_TX]),
                           ps.tx.serialize(with_witness=False)))
    info = psbt.PSBT.parse(ps.serialize()).describe(ROOT)
    ok = info["locktime"] == 900000 and not info["locktime_is_time"] and info["locktime_no_effect"]
    fails += not ok
    print("10. locktime บล็อก 900,000   : อ่านได้ %d · รู้ว่าไม่มีผล %s  %s"
          % (info["locktime"], info["locktime_no_effect"], "ผ่าน" if ok else "ไม่ผ่าน"))

    # 11) เงินทอนเส้นทางถูกแต่เป็นที่อยู่ 1... (p2pkh ของกุญแจเดียวกัน) ต้องไม่ถูกซ่อนเป็น CHG
    #     พบ 11 ต.ค. 2026: เดิมนับเป็นเงินทอน จอไม่โชว์ที่อยู่ แต่กระเป๋า BIP84 ไม่เฝ้าที่อยู่ 1...
    ps = psbt.PSBT.parse(RAW)
    for n, o in enumerate(ps.tx.vout):
        for k, _ in ps.outputs[n].items_:
            if k[0] == OUT_DERIV:
                o.script_pubkey = addr.p2pkh_script(k[1:])
    ps.g.items_ = [(k, v) for k, v in ps.g.items_ if k[0] != psbt.GLOBAL_UNSIGNED_TX]
    ps.g.items_.insert(0, (bytes([psbt.GLOBAL_UNSIGNED_TX]),
                           ps.tx.serialize(with_witness=False)))
    info = psbt.PSBT.parse(ps.serialize()).describe(ROOT)
    hidden = [o for o in info["outputs"] if o["is_change"]]
    shown = [o for o in info["outputs"] if o["address"].startswith("1") and o.get("odd_owned")]
    ok = not hidden and len(shown) == 1 and info["sending"] == sum(o["value"] for o in info["outputs"])
    fails += not ok
    print("11. เงินทอนเป็นที่อยู่ 1...   : ถูกซ่อนเป็น CHG %d · โชว์เป็นปลายทาง %d  %s"
          % (len(hidden), len(shown), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 12-14) CVE-2020-14199: ยอด input ต้องมาจาก tx เก่าทั้งใบที่แฮชตรง txid เท่านั้น (แก้ 12 ต.ค. 2026)
    #     คนร้ายโกหกยอดใน witness utxo ทีละรอบ แต่ละรอบจอโชว์ค่าธรรมเนียมปกติ แล้วรวมลายเซ็น 2 รอบ
    IN_WU, IN_NWU = psbt.IN_WITNESS_UTXO, psbt.IN_NON_WITNESS_UTXO
    def strip_nwu():
        ps = psbt.PSBT.parse(RAW)
        for m in ps.inputs:
            m.items_ = [(k, v) for k, v in m.items_ if k[0] != IN_NWU]
        return psbt.PSBT.parse(ps.serialize())
    p = strip_nwu()
    info = p.describe(ROOT)
    try:
        n = p.sign(ROOT); signed = n
    except psbt.PSBTError:
        signed = 0
    ok = info["fee"] is None and info["inputs_unknown_amount"] == 1 and signed == 0
    fails += not ok
    print("12. มีแค่ witness utxo        : ค่าธรรมเนียม %s · เซ็นไป %d  %s"
          % (info["fee"], signed, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 13) witness utxo โกหกยอดให้ต่ำกว่า tx เก่าจริง → ปฏิเสธทั้งใบ
    ps = psbt.PSBT.parse(RAW)
    m = ps.inputs[0]
    wu = m.get(bytes([IN_WU]))
    m.items_ = [(k, v) if k[0] != IN_WU else (k, (1).to_bytes(8, "little") + wu[8:]) for k, v in m.items_]
    try:
        psbt.PSBT.parse(ps.serialize()).describe(ROOT); ok = False; why = "ไม่จับ"
    except psbt.PSBTError as e:
        ok = True; why = str(e)
    fails += not ok
    print("13. witness utxo โกหกยอด      : %s  %s" % (why, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 14) tx เก่าที่แนบมาไม่ใช่ใบที่ input อ้าง (แก้ยอดใน tx เก่า → แฮชไม่ตรง txid)
    ps = psbt.PSBT.parse(RAW)
    m = ps.inputs[0]
    nwu = bytearray(m.get(bytes([IN_NWU])))
    nwu[-12] ^= 0x01                      # แตะไบต์ในยอดของ output สุดท้าย
    m.items_ = [(k, v) if k[0] != IN_NWU else (k, bytes(nwu)) for k, v in m.items_]
    try:
        psbt.PSBT.parse(ps.serialize()).describe(ROOT); ok = False; why = "ไม่จับ"
    except psbt.PSBTError as e:
        ok = True; why = str(e)
    fails += not ok
    print("14. tx เก่าถูกแก้ (txid ไม่ตรง) : %s  %s" % (why, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 15) คำอธิบาย output ที่ไม่ใช่ที่อยู่ต้องเป็น ASCII — ฟอนต์บนเครื่องไม่มีภาษาไทย (เดิมขึ้นจอเป็น ????)
    labels = [addr.script_to_address(b"\x6a" + bytes(10)),
              addr.script_to_address(b"\x51\x01\x00"),
              addr.script_to_address(bytes(7))]
    ok = all(all(32 <= ord(c) < 127 for c in t) for t in labels)
    fails += not ok
    print("15. ข้อความ output แปลก ASCII : %s  %s" % (" | ".join(labels), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 16) verify-after-sign: ถ้าการเซ็นคำนวณผิด (จำลองด้วยการเปลี่ยน s) ต้องไม่มีลายเซ็นหลุดออกไป
    import secp256k1 as ec
    real_sign = ec.sign
    try:
        ec.sign = lambda d, k: (lambda rs: (rs[0], (rs[1] + 1) % ec.N))(real_sign(d, k))
        ps = psbt.PSBT.parse(RAW)
        try:
            ps.sign(ROOT); caught = False
        except psbt.PSBTError:
            caught = True
        leaked = any(k[0] == psbt.IN_PARTIAL_SIG for m in ps.inputs for k, _ in m.items_)
    finally:
        ec.sign = real_sign
    ok = caught and not leaked
    fails += not ok
    print("16. ลายเซ็นคำนวณผิด          : จับได้ %s · ลายเซ็นหลุด %s  %s"
          % (caught, leaked, "ผ่าน" if ok else "ไม่ผ่าน"))

    # 17) ค่าธรรมเนียมเกิน 10% ของยอดรวม output = ไม่เซ็น (เดิมแค่เตือน) · ปกติยังเซ็นได้
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from psbt_fixture import attach_prev
    ps = psbt.PSBT.parse(RAW)
    # เพิ่มยอด input ใน witness utxo ให้ค่าธรรมเนียมพุ่ง แล้วสร้าง tx เก่าใหม่ให้ตรง
    m = ps.inputs[0]
    wu = m.get(bytes([IN_WU]))
    total_out = sum(o.value for o in ps.tx.vout)
    big_in = total_out * 2                       # ค่าธรรมเนียม = 100% ของ output
    m.items_ = [(k, v) if k[0] != IN_WU else (k, big_in.to_bytes(8, "little") + wu[8:])
                for k, v in m.items_ if k[0] != IN_NWU]
    hi = attach_prev(ps)
    info = hi.describe(ROOT)
    try:
        hi.sign(ROOT); refused = False
    except psbt.PSBTError:
        refused = True
    normal = psbt.PSBT.parse(RAW).describe(ROOT)["fee_over_cap"]
    ok = info["fee_over_cap"] and refused and not normal
    fails += not ok
    print("17. ค่าธรรมเนียม 100%%        : ติดเพดาน %s · ไม่เซ็น %s · ใบปกติติดเพดาน %s  %s"
          % (info["fee_over_cap"], refused, normal, "ผ่าน" if ok else "ไม่ผ่าน"))
    # ขอบเพดาน: 10% พอดีผ่าน · เกินนิดเดียวไม่ผ่าน
    ok = (not psbt.fee_over_cap(100, 1000)) and psbt.fee_over_cap(101, 1000) and psbt.fee_over_cap(1, 0) \
        and not psbt.fee_over_cap(None, 1000)
    fails += not ok
    print("    ขอบเพดาน 10%%             : %s" % ("ผ่าน" if ok else "ไม่ผ่าน"))

    # 18) input ซ้ำ (outpoint เดียวกัน 2 ครั้ง) = BAD PSBT
    ps = psbt.PSBT.parse(RAW)
    ps.tx.vin.append(ps.tx.vin[0])
    ps.inputs.append(ps.inputs[0])
    ps.g.items_ = [(k, v) for k, v in ps.g.items_ if k[0] != psbt.GLOBAL_UNSIGNED_TX]
    ps.g.items_.insert(0, (bytes([psbt.GLOBAL_UNSIGNED_TX]), ps.tx.serialize(with_witness=False)))
    try:
        psbt.PSBT.parse(ps.serialize()); ok = False; why = "ไม่จับ"
    except psbt.PSBTError as e:
        ok = True; why = str(e)
    fails += not ok
    print("18. input ซ้ำ                 : %s  %s" % (why, "ผ่าน" if ok else "ไม่ผ่าน"))

    print()
    if fails:
        print("ไม่ผ่าน %d ข้อ" % fails); sys.exit(1)
    print("ผ่านทั้งหมด")


if __name__ == "__main__":
    main()

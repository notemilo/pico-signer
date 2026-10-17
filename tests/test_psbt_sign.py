"""เทสการเซ็นจริง + เทส "การโจมตี" ที่ด่านตรวจต้องกันได้

ส่วนที่สำคัญที่สุดของทั้งโปรเจค — บั๊กตรงนี้คือบั๊กที่ทำให้เงินหาย
โดยที่หน้าจอยังโชว์ว่าถูกต้อง
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import address as addr  # noqa: E402
import bip32  # noqa: E402
import bip39  # noqa: E402
import psbt as P  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from psbt_fixture import attach_prev  # noqa: E402
from tx import Transaction, TxInput, TxOutput, ser_varbytes  # noqa: E402

WL = os.path.join(ROOT, "src", "english.txt")
MNEMONIC = ("abandon abandon abandon abandon abandon abandon "
            "abandon abandon abandon abandon abandon about")

MY_PATH = "m/84h/0h/0h/0/0"
CHANGE_PATH = "m/84h/0h/0h/1/0"


def build(root, out_scripts, change_index=None, change_deriv_path=CHANGE_PATH,
          fake_deriv_on=None, fake_pubkey=None, in_amount=91_000):
    # 12 ต.ค. 2026: เดิม 100,000 → ค่าธรรมเนียม 10,000 = 11% ของ output ติดเพดาน 10% (psbt.MAX_FEE_PCT) → ใช้ 91,000 ค่าธรรมเนียม 1,000 แทน
    """สร้าง PSBT ทดสอบ 1 input (p2wpkh ของเรา) + outputs ตามที่กำหนด"""
    my = root.derive(MY_PATH)
    my_spk = addr.p2wpkh_script(my.pubkey)
    fp = root.my_fingerprint()

    tx = Transaction(version=2)
    tx.vin.append(TxInput(bytes(range(32)), 0))
    for spk, val in out_scripts:
        tx.vout.append(TxOutput(val, spk))

    p = P.PSBT()
    p.tx = tx
    p.g.put(bytes([P.GLOBAL_UNSIGNED_TX]), tx.serialize(with_witness=False))

    def deriv_value(path):
        idxs = bip32.parse_path(path)
        return fp + b"".join(i.to_bytes(4, "little") for i in idxs)

    m = P.KVMap()
    m.put(bytes([P.IN_WITNESS_UTXO]),
          in_amount.to_bytes(8, "little") + ser_varbytes(my_spk))
    m.put(bytes([P.IN_BIP32_DERIVATION]) + my.pubkey, deriv_value(MY_PATH))
    p.inputs.append(m)

    for i in range(len(tx.vout)):
        om = P.KVMap()
        if i == change_index:
            ch = root.derive(change_deriv_path)
            om.put(bytes([P.OUT_BIP32_DERIVATION]) + ch.pubkey,
                   deriv_value(change_deriv_path))
        if i == fake_deriv_on:
            # ผู้โจมตีแปะ derivation ที่ใช้ fingerprint ของเรา ลงบน output ของเขาเอง
            om.put(bytes([P.OUT_BIP32_DERIVATION]) + (fake_pubkey or bytes(33)),
                   deriv_value(CHANGE_PATH))
        p.outputs.append(om)
    return attach_prev(p)   # แนบ tx เก่าทั้งใบแบบ wallet (psbt ไม่เชื่อ witness utxo อย่างเดียว)


def run():
    fails = []
    seed = bip39.seed(MNEMONIC, "")
    root = bip32.HDKey.from_seed(seed)
    my = root.derive(MY_PATH)
    change = root.derive(CHANGE_PATH)

    stranger_spk = addr.p2wpkh_script(bytes.fromhex(
        "0379be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"))
    change_spk = addr.p2wpkh_script(change.pubkey)

    # ===== 1. เคสปกติ: จ่ายออก 60,000 + ทอน 30,000 จาก input 100,000 =====
    p = build(root, [(stranger_spk, 60_000), (change_spk, 30_000)], change_index=1)
    d = p.describe(root)
    if d["sending"] != 60_000:
        fails.append("ยอดที่จ่ายออกควรเป็น 60,000 ได้ %d" % d["sending"])
    if d["change"] != 30_000:
        fails.append("ยอดทอนควรเป็น 30,000 ได้ %d" % d["change"])
    if d["fee"] != 1_000:
        fails.append("ค่าธรรมเนียมควรเป็น 1,000 ได้ %s" % d["fee"])
    if not d["outputs"][1]["is_change"] or d["outputs"][0]["is_change"]:
        fails.append("ระบุ change/ไม่ใช่ change ผิด")

    n = p.sign(root)
    if n != 1:
        fails.append("ควรเซ็นได้ 1 input ได้ %d" % n)
    sig = p.inputs[0].get(bytes([P.IN_PARTIAL_SIG]) + my.pubkey)
    if not sig:
        fails.append("ไม่พบลายเซ็นหลังเซ็น")
    else:
        # ตรวจว่าลายเซ็นใช้ได้จริง ไม่ใช่แค่มีไบต์อยู่
        import secp256k1 as ec
        digest = p.tx.sighash_segwit_v0(
            0, addr.p2wpkh_script_code(my.pubkey), 91_000, sig[-1])
        if not ec.verify(digest, ec.parse_der(sig[:-1]), my.pubkey):
            fails.append("🔴 ลายเซ็นตรวจไม่ผ่าน")
        # เซ็นซ้ำต้องได้ผลเดิม (RFC6979)
        if ec.sign(digest, my.key) != ec.parse_der(sig[:-1]):
            fails.append("🔴 เซ็นซ้ำได้ผลไม่เหมือนเดิม")

    # ที่อยู่ต้องตรงกับมาตรฐาน BIP84 ของ mnemonic ทดสอบตัวนี้
    if addr.script_to_address(addr.p2wpkh_script(my.pubkey)) != \
            "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu":
        fails.append("ที่อยู่ BIP84 ไม่ตรงมาตรฐาน")

    # ===== 2. โจมตี: แปะ derivation ปลอมบน output ของคนแปลกหน้า =====
    p2 = build(root, [(stranger_spk, 90_000)], fake_deriv_on=0,
               fake_pubkey=change.pubkey)
    # 15 ต.ค. 2026: PSBT ที่โกหกแบบนี้ต้องถูกปฏิเสธทั้งใบ (PSBTLie) — เดิมแค่ไม่นับเป็นเงินทอน
    try:
        d2 = p2.describe(root)
        if d2["outputs"][0]["is_change"]:
            fails.append("🔴 ถูกหลอก: นับ output ของคนอื่นเป็นเงินทอน")
        fails.append("🔴 derivation ปลอมบน output คนแปลกหน้า ต้องเป็น PSBTLie")
    except P.PSBTLie:
        pass

    # ===== 3. โจมตี: path ถูก แต่ scriptPubKey เป็นของคนอื่น =====
    p3 = build(root, [(stranger_spk, 90_000)], change_index=0)
    try:
        d3 = p3.describe(root)
        if d3["outputs"][0]["is_change"]:
            fails.append("🔴 ถูกหลอก: path ของเราแต่สคริปต์เป็นของคนอื่น กลับนับเป็นเงินทอน")
        fails.append("🔴 path ของเราแต่จ่ายคนอื่น ต้องเป็น PSBTLie")
    except P.PSBTLie:
        pass

    # ===== 4. โจมตี: input ที่ไม่ใช่ของเรา ต้องไม่เซ็น =====
    p4 = build(root, [(stranger_spk, 90_000)])
    p4.inputs[0] = P.KVMap()
    p4.inputs[0].put(bytes([P.IN_WITNESS_UTXO]),
                     (100_000).to_bytes(8, "little") + ser_varbytes(stranger_spk))
    # 17 ต.ค. 2026: input ไม่มี tx เก่า → sign() ปฏิเสธทั้งใบ (PSBTError) ก็นับว่าไม่เซ็น
    try:
        if p4.sign(root) != 0:
            fails.append("🔴 เซ็น input ที่ไม่ใช่ของเรา")
    except P.PSBTError:
        pass

    # ===== 5. ยอดขาออกมากกว่าขาเข้า ต้องถูกจับได้ =====
    p5 = build(root, [(stranger_spk, 200_000)])
    try:
        p5.fee()
        fails.append("🔴 ไม่จับกรณียอดออก > ยอดเข้า")
    except P.PSBTError:
        pass

    print("เคสปกติ  : จ่ายออก %s · ทอน %s · ค่าธรรมเนียม %s ซาโตชิ · เซ็น %d input"
          % (d["sending"], d["change"], d["fee"], n))
    print("           ไปที่ %s" % d["outputs"][0]["address"])
    print("           ทอนกลับ %s (%s)" % (d["outputs"][1]["address"], d["outputs"][1]["path"]))
    print("เทสโจมตี : derivation ปลอม · path/สคริปต์ไม่ตรง · input คนอื่น · ยอดเกิน")

    if fails:
        print("ไม่ผ่าน %d:" % len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(run())

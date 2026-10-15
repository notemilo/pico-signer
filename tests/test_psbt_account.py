"""เลือก BIP84 account ได้ (เพิ่ม 14 ก.ย. 2026)

ตัวอย่างการใช้: seed เดียวกับหลายเครื่อง แต่ละเครื่องคนละ account = กระเป๋าคนละใบ
สิ่งที่ต้องไม่พัง:
  - ของเดิม (account 0) ทำงานเหมือนเดิมทุกอย่าง
  - เงินทอนนับได้เฉพาะใน account ที่ผู้ใช้เลือก
  - account ไม่ตรง = ไม่นับเป็นเงินทอน โผล่เป็นปลายทางให้เห็น (fail-safe เดิม)
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

MNEMONIC = ("abandon abandon abandon abandon abandon abandon "
            "abandon abandon abandon abandon abandon about")
root = bip32.HDKey.from_seed(bip39.seed(MNEMONIC))
fp = root.my_fingerprint()
STRANGER = addr.p2wpkh_script(bip32.HDKey.from_seed(bytes(32)).derive("m/0").pubkey)

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    if not ok:
        fails += 1


def deriv_value(path):
    return fp + b"".join(i.to_bytes(4, "little") for i in bip32.parse_path(path))


def build(in_path, change_path):
    """1 input ของเรา (in_path) · output 0 = คนแปลกหน้า · output 1 = เงินทอน (change_path)"""
    my = root.derive(in_path)
    ch = root.derive(change_path)
    tx = Transaction(version=2)
    tx.vin.append(TxInput(bytes(range(32)), 0))
    tx.vout.append(TxOutput(60_000, STRANGER))
    tx.vout.append(TxOutput(39_000, addr.p2wpkh_script(ch.pubkey)))
    p = P.PSBT()
    p.tx = tx
    p.g.put(bytes([P.GLOBAL_UNSIGNED_TX]), tx.serialize(with_witness=False))
    m = P.KVMap()
    m.put(bytes([P.IN_WITNESS_UTXO]),
          (100_000).to_bytes(8, "little") + ser_varbytes(addr.p2wpkh_script(my.pubkey)))
    m.put(bytes([P.IN_BIP32_DERIVATION]) + my.pubkey, deriv_value(in_path))
    p.inputs.append(m)
    p.outputs.append(P.KVMap())
    om = P.KVMap()
    om.put(bytes([P.OUT_BIP32_DERIVATION]) + ch.pubkey, deriv_value(change_path))
    p.outputs.append(om)
    # ผ่าน serialize/parse จริง + แนบ tx เก่าทั้งใบแบบ wallet
    return attach_prev(p)


def summary(d):
    o = d["outputs"][1]
    return o["is_change"], o["odd_owned"], d["sending"], d["change"], d["fee"]


print("── 1. ของเดิม account 0 ต้องเหมือนเดิม")
p0 = build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0")
d_default = p0.describe(root)
d_zero = p0.describe(root, account=0)
check("describe() ไม่ใส่ account = ใส่ account=0 ทุกค่า", d_default == d_zero)
check("เงินทอน account 0 ถูกนับเป็นเงินทอน", summary(d_zero)[:4] == (True, False, 60_000, 39_000))
check("ค่าธรรมเนียมถูก (100000-60000-39000 = 1000)", d_zero["fee"] == 1000)

print("── 2. กระเป๋า account 1 (เช่นเครื่องที่ 2)")
p1 = build("m/84h/0h/1h/0/0", "m/84h/0h/1h/1/0")
d1 = p1.describe(root, account=1)
check("เลือก account 1: เงินทอน account 1 นับเป็นเงินทอน", summary(d1)[:4] == (True, False, 60_000, 39_000))
check("เซ็น input ของ account 1 ได้ 1 ตัว", build("m/84h/0h/1h/0/0", "m/84h/0h/1h/1/0").sign(root) == 1)

print("── 3. account ไม่ตรง = fail-safe (เงินทอนโผล่เป็นปลายทาง ไม่ถูกซ่อน)")
d_wrong = p1.describe(root, account=0)
c, odd, sending, change, _ = summary(d_wrong)
check("PSBT account 1 แต่เลือก 0: ไม่นับเป็นเงินทอน", c is False)
check("  ติดธง odd_owned ให้จอเตือน", odd is True)
check("  ยอดส่งออกรวมเงินทอนก้อนนั้น (60000+39000)", sending == 99_000 and change == 0)
d_wrong2 = p0.describe(root, account=1)
check("PSBT account 0 แต่เลือก 1: ไม่นับเป็นเงินทอนเช่นกัน",
      summary(d_wrong2)[0] is False and summary(d_wrong2)[1] is True)

print("── 4. account 3 และเลขสูง")
p3 = build("m/84h/0h/3h/0/5", "m/84h/0h/3h/1/7")
check("account 3 เงินทอนนับถูก", summary(p3.describe(root, account=3))[0] is True)
p99 = build("m/84h/0h/99h/0/0", "m/84h/0h/99h/1/0")
check("account 99 เงินทอนนับถูก", summary(p99.describe(root, account=99))[0] is True)

print("── 5. ค่า account ผิดรูป ต้องปฏิเสธ")
for bad in (-1, 2 ** 31, "1", 1.0, None):
    try:
        P.change_account(bad)
        ok = False
    except ValueError:
        ok = True
    check("ปฏิเสธ account=%r" % (bad,), ok)
check("change_account(2) = (84h, 0h, 2h)",
      P.change_account(2) == (84 + P.HARDENED, P.HARDENED, 2 + P.HARDENED))

print("── 6. บัค F: input จาก account อื่นต้องรู้และไม่ถูกเซ็นเมื่อระบุ account")


def build_multi(in_paths, change_path):
    """หลาย input ของเรา (คนละ account ได้) · output 0 = คนแปลกหน้า · output 1 = เงินทอน"""
    ch = root.derive(change_path)
    tx = Transaction(version=2)
    for i, _ in enumerate(in_paths):
        tx.vin.append(TxInput(bytes([i + 1]) * 32, 0))
    tx.vout.append(TxOutput(50_000, STRANGER))
    tx.vout.append(TxOutput(100_000 * len(in_paths) - 51_000, addr.p2wpkh_script(ch.pubkey)))
    p = P.PSBT()
    p.tx = tx
    p.g.put(bytes([P.GLOBAL_UNSIGNED_TX]), tx.serialize(with_witness=False))
    for ip in in_paths:
        my = root.derive(ip)
        m = P.KVMap()
        m.put(bytes([P.IN_WITNESS_UTXO]),
              (100_000).to_bytes(8, "little") + ser_varbytes(addr.p2wpkh_script(my.pubkey)))
        m.put(bytes([P.IN_BIP32_DERIVATION]) + my.pubkey, deriv_value(ip))
        p.inputs.append(m)
    p.outputs.append(P.KVMap())
    om = P.KVMap()
    om.put(bytes([P.OUT_BIP32_DERIVATION]) + ch.pubkey, deriv_value(change_path))
    p.outputs.append(om)
    return attach_prev(p)


d = build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0").describe(root, account=1)
check("PSBT account 0 แต่เลือก 1: รู้ว่า input มาจาก account 0",
      d["inputs_mine"] == 1 and d["input_accounts"] == [0] and d["inputs_wrong_account"] == 1)
d = build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0").describe(root, account=0)
check("PSBT account 0 และเลือก 0: ไม่มี input ผิด account",
      d["inputs_mine"] == 1 and d["inputs_wrong_account"] == 0)
check("sign(account=1) บน PSBT ของ account 0: เซ็น 0 input",
      build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0").sign(root, account=1) == 0)
check("sign(account=0) บน PSBT ของ account 0: เซ็น 1 input",
      build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0").sign(root, account=0) == 1)
check("sign() ไม่ระบุ account (ของเดิม): ยังเซ็น 1 input เหมือนเดิม",
      build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0").sign(root) == 1)
mix = ["m/84h/0h/0h/0/0", "m/84h/0h/1h/0/0"]
d = build_multi(mix, "m/84h/0h/1h/1/0").describe(root, account=1)
check("input ปน 2 account เลือก 1: inputs_mine 2 · account [0,1] · ผิด 1",
      d["inputs_mine"] == 2 and sorted(d["input_accounts"]) == [0, 1] and d["inputs_wrong_account"] == 1)
check("input ปน 2 account: sign(account=1) เซ็นแค่ของ account 1 = 1",
      build_multi(mix, "m/84h/0h/1h/1/0").sign(root, account=1) == 1)
d = build("m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0")
for m in d.inputs:
    for i, (k, v) in enumerate(m.items_):
        if k[0] == P.IN_BIP32_DERIVATION:
            m.items_[i] = (k, deriv_value("m/49h/0h/0h/0/0"))
# 15 ต.ค. 2026: เส้นทางที่ประกาศไม่ตรงกับ pubkey จริง = PSBT โกหก → ปฏิเสธทั้งใบ (เดิม: ผ่านแต่นับเป็นผิด account)
try:
    P.PSBT.parse(d.serialize()).describe(root, account=0)
    lied = False
except P.PSBTLie:
    lied = True
check("input ประกาศเส้นทาง 49h ที่ไม่ตรง pubkey จริง: ปฏิเสธเป็น PSBTLie", lied)
# เส้นทางแปลกแต่ "จริง" (กุญแจ m/49h จริง จ่ายแบบ p2wpkh) ต้องยังผ่าน แค่นับเป็นผิด account
dd = build("m/49h/0h/0h/0/0", "m/84h/0h/0h/1/0").describe(root, account=0)
check("input เส้นทางแปลกแต่จริง (49h): account = ? และนับเป็นผิด account",
      dd["input_accounts"] == [None] and dd["inputs_wrong_account"] == 1)

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_psbt_account ผ่านครบ")

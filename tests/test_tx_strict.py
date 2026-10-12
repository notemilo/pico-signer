"""ตัวอ่านธุรกรรมแบบเข้ม — ขาด/เกิน/varint ไม่สั้นสุด ต้องโดนปฏิเสธทุกกรณี (13 ต.ค. 2026)

มาจากรีวิวภายนอก 2 ฉบับ (ข้อ 7 / F-01): เดิมอ่านด้วย slicing ข้อมูลขาดได้ 0 เงียบ ๆ
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
os.chdir(os.path.join(HERE, "..", "src"))
import psbt  # noqa: E402
import tx as txmod  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


def rejects(fn):
    try:
        fn()
        return False
    except (txmod.TxError, psbt.PSBTError, ValueError):
        return True


RAW = base64.b64decode(open("../test.psbt").read().strip())
P = psbt.PSBT.parse(RAW)
UNSIGNED = P.g.get(bytes([psbt.GLOBAL_UNSIGNED_TX]))
PREV = P.inputs[0].get(bytes([psbt.IN_NON_WITNESS_UTXO]))

# ธุรกรรม segwit จริง (มี witness) — สร้างจาก tx เดิม + witness ปลอม แล้วต้องอ่านกลับได้เท่าเดิม
seg = txmod.Transaction.parse(PREV)
seg.vin[0].witness = [b"\x30" * 71, b"\x02" * 33]
SEGWIT = seg.serialize(with_witness=True)

for name, raw in (("unsigned tx", UNSIGNED), ("prev tx", PREV), ("segwit tx", SEGWIT)):
    check("%s อ่านได้และ serialize กลับได้ไบต์เดิม" % name,
          txmod.Transaction.parse(raw).serialize(with_witness=True) == raw)
    bad = [n for n in range(len(raw)) if not rejects(lambda n=n: txmod.Transaction.parse(raw[:n]))]
    check("%s ตัดทิ้งท้ายทุกตำแหน่ง (%d แบบ) → ปฏิเสธหมด" % (name, len(raw)), not bad)
    check("%s มีไบต์เกินท้าย → ปฏิเสธ" % name, rejects(lambda: txmod.Transaction.parse(raw + b"\x00")))

# varint ไม่สั้นสุด: จำนวน input 1 เขียนแบบ 0xFD 0x01 0x00
u = bytearray(UNSIGNED)
noncanon = bytes(u[:4]) + b"\xfd\x01\x00" + bytes(u[5:])
check("varint ไม่สั้นสุด (1 เขียนเป็น FD 01 00) → ปฏิเสธ", rejects(lambda: txmod.Transaction.parse(noncanon)))
check("read_varint ข้อมูลขาด → TxError", rejects(lambda: txmod.read_varint(b"\xfe\x01\x02", 0)))
check("read_varint สั้นสุดถูกต้อง 253 = FD FD 00", txmod.read_varint(b"\xfd\xfd\x00", 0) == (253, 3))

# segwit flag ที่ไม่มี witness จริง (Bitcoin Core ก็ปฏิเสธ)
empty_wit = UNSIGNED[:4] + b"\x00\x01" + UNSIGNED[4:-4] + b"\x00" * len(P.tx.vin) + UNSIGNED[-4:]
check("segwit flag แต่ witness ว่างทุกตัว → ปฏิเสธ", rejects(lambda: txmod.Transaction.parse(empty_wit)))

# จำนวน input เกินขนาดข้อมูล (กันจองหน่วยความจำ/วนนาน)
huge = UNSIGNED[:4] + b"\xfe\xff\xff\xff\x00" + UNSIGNED[5:]
check("ประกาศ input 16 ล้านตัวในข้อมูลไม่กี่ร้อยไบต์ → ปฏิเสธทันที", rejects(lambda: txmod.Transaction.parse(huge)))

# ผ่านชั้น PSBT: prev tx ที่ถูกตัด/มีไบต์เกิน → BAD PSBT ไม่ถึงขั้นเซ็น
for label, mod in (("ตัด 1 ไบต์", PREV[:-1]), ("เกิน 1 ไบต์", PREV + b"\x00")):
    q = psbt.PSBT.parse(RAW)
    q.inputs[0].items_ = [(k, v) if k[0] != psbt.IN_NON_WITNESS_UTXO else (k, mod) for k, v in q.inputs[0].items_]
    check("PSBT ที่ prev tx %s → ปฏิเสธ" % label,
          rejects(lambda q=q: psbt.PSBT.parse(q.serialize()).describe(__import__("bip32").HDKey.from_seed(b"\x01" * 32))))

if fails:
    print("❌ test_tx_strict ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_tx_strict ผ่านครบ")

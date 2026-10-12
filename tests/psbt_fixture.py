"""แนบ tx เก่าทั้งใบ (non-witness utxo) ให้ PSBT ที่เทสสร้างขึ้น

🔑 12 ต.ค. 2026: psbt เชื่อยอด input เฉพาะจาก tx เก่าที่แฮชตรง txid (กัน CVE-2020-14199)
   PSBT ในเทสเดิมมีแค่ witness utxo → ต้องสร้าง tx เก่าปลอมที่จ่ายเข้า script/ยอดเดียวกัน
   แล้วชี้ input ไปที่ txid ของมัน แบบเดียวกับที่ wallet แนบมาจริง
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import psbt as P  # noqa: E402
import tx as txmod  # noqa: E402
from tx import Transaction, TxInput, TxOutput  # noqa: E402


def prev_tx(spk, value, vout=0, tag=0):
    """tx เก่าปลอมที่ output ลำดับ vout จ่าย value เข้า spk — คืน (txid แบบในสาย, raw)"""
    t = Transaction(version=2)
    t.vin.append(TxInput(bytes([tag & 0xFF]) * 32, tag))
    for i in range(vout):
        t.vout.append(TxOutput(1000 + i, b"\x6a"))           # output อื่นที่ไม่เกี่ยว
    t.vout.append(TxOutput(value, spk))
    raw = t.serialize(with_witness=False)
    return txmod.dsha256(raw), raw


def _set(m, key, val):
    m.items_ = [(k, v) for k, v in m.items_ if k != key]
    m.items_.append((key, val))


def attach_prev(p, keep_witness_utxo=True):
    """ทุก input ที่มี witness utxo → สร้าง tx เก่าตามนั้น ชี้ input ไปหา แล้วแนบ non-witness utxo

    คืน PSBT ที่ผ่าน serialize/parse แล้ว (เส้นทางเดียวกับที่เครื่องใช้)
    """
    for n, m in enumerate(p.inputs):
        wu = m.get(bytes([P.IN_WITNESS_UTXO]))
        if wu is None:
            continue
        spk, _ = txmod.read_varbytes(wu, 8)
        value = int.from_bytes(wu[:8], "little")
        vin = p.tx.vin[n]
        txid, raw = prev_tx(spk, value, vin.vout, tag=n + 1)
        vin.txid = txid
        _set(m, bytes([P.IN_NON_WITNESS_UTXO]), raw)
        if not keep_witness_utxo:
            m.items_ = [(k, v) for k, v in m.items_ if k != bytes([P.IN_WITNESS_UTXO])]
    gkey = bytes([P.GLOBAL_UNSIGNED_TX])
    p.g.items_ = [(k, v) for k, v in p.g.items_ if k != gkey]
    p.g.items_.insert(0, (gkey, p.tx.serialize(with_witness=False)))
    return P.PSBT.parse(p.serialize())

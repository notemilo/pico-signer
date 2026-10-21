"""scriptPubKey -> ที่อยู่ที่คนอ่านได้ + สร้าง scriptPubKey จาก pubkey

ใช้ทั้งตอนแสดงผลให้ผู้ใช้ยืนยัน และตอนตรวจว่า output เป็นของเราจริงไหม
"""

import base58
import bech32
from hashes import sha256
from ripemd160 import ripemd160

MAINNET = {"p2pkh": 0x00, "p2sh": 0x05, "bech32": "bc"}
TESTNET = {"p2pkh": 0x6F, "p2sh": 0xC4, "bech32": "tb"}


def hash160(b):
    return ripemd160(sha256(b))


# ---------- สร้าง scriptPubKey ----------

def p2wpkh_script(pubkey):
    """OP_0 <20-byte-hash>"""
    return b"\x00\x14" + hash160(pubkey)


def p2pkh_script(pubkey):
    """OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG"""
    return b"\x76\xa9\x14" + hash160(pubkey) + b"\x88\xac"


def p2sh_script(script):
    """OP_HASH160 <20> OP_EQUAL"""
    return b"\xa9\x14" + hash160(script) + b"\x87"


def p2wpkh_script_code(pubkey):
    """scriptCode ที่ BIP143 ต้องใช้ตอนคำนวณ sighash ของ p2wpkh"""
    return b"\x76\xa9\x14" + hash160(pubkey) + b"\x88\xac"


# ---------- แปลงเป็นที่อยู่ ----------

def witness_program(spk):
    """(เวอร์ชัน, program) ถ้า spk มีรูปแบบ witness program ตาม BIP141 · ไม่ใช่ = (None, None)

    รูปแบบ: <OP_0 หรือ OP_1..OP_16> <push 2-40 ไบต์> แล้วจบพอดี
    """
    if 4 <= len(spk) <= 42:
        ver = spk[0]
        if ver == 0x00 or 0x51 <= ver <= 0x60:
            prog = spk[2:]
            if spk[1] == len(prog) and 2 <= len(prog) <= 40:
                return (0 if ver == 0 else ver - 0x50), prog
    return None, None


def is_unassigned_witness(spk):
    """witness program ที่ยังไม่มีกฎการใช้จ่าย = ใครก็หยิบเงินไปได้ (เท่ากับเผาทิ้ง)

    🔴 21 ต.ค. 2026 (ตรวจโค้ดเอง): เดิมจอโชว์เป็นที่อยู่ bc1z… / bc1p… ดูปกติ และเครื่องยอมเซ็น
       ทั้งที่ OP_RETURN ที่มีเงินแนบ (เผาเงินแบบเดียวกัน) เราปฏิเสธอยู่แล้ว
       v0 ต้องยาว 20/32 ไบต์ — ยาวอื่นเป็น script ผิดรูป ตกไปเป็น UNKNOWN SCRIPT อยู่แล้ว
       v1 32 ไบต์ = taproot (ใช้งานจริง) · v1 ยาวอื่น และ v2-v16 = ยังไม่มีเจ้าของ (BIP141/BIP341)
       รวมถึง P2A (v1 2 ไบต์ "bc1pfeessrawgf") ที่ตั้งใจให้ใครก็ใช้ได้
    """
    ver, prog = witness_program(spk)
    if ver is None or ver == 0:
        return False
    return not (ver == 1 and len(prog) == 32)


def script_to_address(spk, testnet=False):
    """คืนที่อยู่ หรือคำอธิบายถ้าเป็นสคริปต์ที่ไม่รู้จัก"""
    net = TESTNET if testnet else MAINNET

    # p2pkh: 76 a9 14 <20> 88 ac
    if (len(spk) == 25 and spk[0] == 0x76 and spk[1] == 0xA9 and spk[2] == 0x14
            and spk[23] == 0x88 and spk[24] == 0xAC):
        return base58.encode_check(bytes([net["p2pkh"]]) + spk[3:23])

    # p2sh: a9 14 <20> 87
    if len(spk) == 23 and spk[0] == 0xA9 and spk[1] == 0x14 and spk[22] == 0x87:
        return base58.encode_check(bytes([net["p2sh"]]) + spk[2:22])

    # segwit: <version> <push len> <program>
    witver, prog = witness_program(spk)
    if witver is not None and not (witver == 0 and len(prog) not in (20, 32)):
        return bech32.encode_segwit(net["bech32"], witver, prog)

    # ⚠️ ข้อความนี้ขึ้นจอเครื่องเซ็นตรง ๆ — ต้องเป็น ASCII (ฟอนต์บนเครื่องไม่มีภาษาไทย ขึ้นเป็น ???)
    #    แก้ 12 ต.ค. 2026 · เดิมเป็นภาษาไทย ผู้ใช้จะเห็นแค่ ???? บนหน้า TO
    if spk[:1] == b"\x6a":
        return "OP_RETURN %dB" % (len(spk) - 1)
    return "UNKNOWN SCRIPT %dB" % len(spk)

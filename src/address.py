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
    if 4 <= len(spk) <= 42:
        ver = spk[0]
        if ver == 0x00 or 0x51 <= ver <= 0x60:
            witver = 0 if ver == 0 else ver - 0x50
            plen = spk[1]
            prog = spk[2:]
            if plen == len(prog) and 2 <= len(prog) <= 40:
                if witver == 0 and len(prog) not in (20, 32):
                    pass
                else:
                    return bech32.encode_segwit(net["bech32"], witver, prog)

    # ⚠️ ข้อความนี้ขึ้นจอเครื่องเซ็นตรง ๆ — ต้องเป็น ASCII (ฟอนต์บนเครื่องไม่มีภาษาไทย ขึ้นเป็น ???)
    #    แก้ 12 ต.ค. 2026 · เดิมเป็นภาษาไทย ผู้ใช้จะเห็นแค่ ???? บนหน้า TO
    if spk[:1] == b"\x6a":
        return "OP_RETURN %dB" % (len(spk) - 1)
    return "UNKNOWN SCRIPT %dB" % len(spk)

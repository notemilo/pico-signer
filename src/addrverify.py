# addrverify.py — ตรวจว่าที่อยู่รับเงิน (สแกนจาก QR ของ wallet) มาจาก seed นี้จริงไหม
#
# ทำไมต้องมี (ผู้ใช้ ขอ 14 ก.ย. 2026 — แบบที่เคยใช้กับ Jade):
#   wallet อยู่บนเครื่องที่ต่อเน็ต ถ้าถูกเจาะ มันแสดงที่อยู่ของคนร้ายเป็น QR ได้
#   เครื่องเซ็นที่ไม่ต่อเน็ตคำนวณที่อยู่เองจาก seed แล้วเทียบ = ยืนยันก่อนส่งให้คนโอน
#
# ขอบเขต: เฉพาะ p2wpkh (bc1q… 42 ตัว) บน m/84h/0h/<account>h/<0|1>/<index>
#   ตรงกับที่เครื่องนี้ส่ง xpub ให้ wallet · ที่อยู่แบบอื่นตอบว่า "ไม่ใช่แบบของกระเป๋านี้"
#
# 🔑 หาไม่เจอ ≠ โดนโกงเสมอไป (Jade เตือนแบบเดียวกัน): อาจเป็น account อื่น หรือเลขที่อยู่สูงกว่าที่ค้น
#
# ไฟล์นี้เป็น core (ไม่แตะฮาร์ดแวร์) ใช้ร่วมได้ทุกบอร์ด · เทสบนแมคได้

import bech32
import address as addr

HARDENED = 0x80000000
RECEIVE, CHANGE = 0, 1

# เหตุผลที่ parse ไม่ผ่าน (ให้ UI แปลเป็นข้อความสั้นตามขนาดจอเอง)
BAD_EMPTY = "empty"
BAD_NOT_ADDRESS = "not_address"      # ถอดไม่ได้ / checksum ผิด
BAD_WRONG_NET = "wrong_net"          # tb1… / bcrt1…
BAD_NOT_P2WPKH = "not_p2wpkh"        # bc1p… taproot, bc1q ยาว 62 (p2wsh), 1… / 3…


class AddressError(ValueError):
    def __init__(self, reason):
        ValueError.__init__(self, reason)
        self.reason = reason


def parse(text):
    """ข้อความจาก QR -> (scriptPubKey, ที่อยู่ตัวเล็ก)

    รับได้ทั้ง "bc1q…", "BC1Q…" (QR มักใช้ตัวใหญ่), "bitcoin:bc1q…?amount=…"
    """
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode()
        except Exception:
            raise AddressError(BAD_NOT_ADDRESS)
    s = (text or "").strip()
    if not s:
        raise AddressError(BAD_EMPTY)
    if s[:8].lower() == "bitcoin:":
        s = s[8:]
    q = s.find("?")
    if q >= 0:
        s = s[:q]
    s = s.strip()
    low = s.lower()
    if low.startswith("tb1") or low.startswith("bcrt1"):
        raise AddressError(BAD_WRONG_NET)
    if not low.startswith("bc1"):
        # 1… (p2pkh) / 3… (p2sh) หรือข้อความอื่น
        if low[:1] in ("1", "3") and 26 <= len(s) <= 35:
            raise AddressError(BAD_NOT_P2WPKH)
        raise AddressError(BAD_NOT_ADDRESS)
    ver, prog = bech32.decode_segwit("bc", s)
    if ver is None:
        raise AddressError(BAD_NOT_ADDRESS)
    if ver != 0 or len(prog) != 20:
        raise AddressError(BAD_NOT_P2WPKH)
    return b"\x00\x14" + prog, low


def account_node(root, account):
    """m/84h/0h/<account>h — hardened ต้องใช้กุญแจส่วนตัว ทำครั้งเดียวแล้วเก็บไว้ใช้ทุกช่วง"""
    if not isinstance(account, int) or account < 0 or account >= HARDENED:
        raise ValueError("account ต้องอยู่ในช่วง 0..2^31-1")
    return root.derive("m/84h/0h/%dh" % account).to_public()


def chain_nodes(acct_node):
    """(receive, change) — อนุพันธ์จาก xpub ได้ ไม่ต้องแตะกุญแจส่วนตัวอีก"""
    return acct_node.derive_child(RECEIVE), acct_node.derive_child(CHANGE)


def candidates(chains, start, count):
    """ไล่ที่อยู่ช่วง [start, start+count) สลับ รับ/ทอน ทีละเลข
    (สลับกันเพื่อให้ที่อยู่เลขต่ำของทั้งสองช่องเจอเร็ว)
    yield (chain, index, scriptPubKey)"""
    recv, chg = chains
    for i in range(start, start + count):
        yield RECEIVE, i, addr.p2wpkh_script(recv.derive_child(i).pubkey)
        yield CHANGE, i, addr.p2wpkh_script(chg.derive_child(i).pubkey)


def path_str(account, chain, index):
    return "m/84h/0h/%dh/%d/%d" % (account, chain, index)

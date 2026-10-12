"""Bech32 / Bech32m (BIP-173, BIP-350) — ใช้ทำที่อยู่ segwit

จำเป็นสำหรับ "แสดงให้ผู้ใช้ดูว่าเงินจะไปไหน" ซึ่งเป็นด่านความปลอดภัยสุดท้าย
"""

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M_CONST = 0x2BC830A3


def _polymod(values):
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _hrp_expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _create_checksum(hrp, data, const):
    values = _hrp_expand(hrp) + data
    polymod = _polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _verify_checksum(hrp, data):
    c = _polymod(_hrp_expand(hrp) + data)
    if c == 1:
        return "bech32"
    if c == BECH32M_CONST:
        return "bech32m"
    return None


def _convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def encode_segwit(hrp, witver, witprog):
    """witver 0 -> bech32, witver 1+ -> bech32m"""
    data = [witver] + _convertbits(list(witprog), 8, 5)
    const = 1 if witver == 0 else BECH32M_CONST
    combined = data + _create_checksum(hrp, data, const)
    return hrp + "1" + "".join(CHARSET[d] for d in combined)


def decode_segwit(hrp, addr):
    """คืน (witver, witprog) หรือ (None, None) ถ้าไม่ถูกต้อง"""
    if addr.lower() != addr and addr.upper() != addr:
        return None, None
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return None, None
    if addr[:pos] != hrp:
        return None, None
    try:
        data = [CHARSET.index(c) for c in addr[pos + 1:]]
    except ValueError:
        return None, None
    spec = _verify_checksum(hrp, data)
    if spec is None:
        return None, None
    decoded = _convertbits(data[1:-6], 5, 8, False)
    if decoded is None or not (2 <= len(decoded) <= 40):
        return None, None
    witver = data[0]
    if witver > 16:
        return None, None
    if witver == 0 and len(decoded) not in (20, 32):
        return None, None
    if (spec == "bech32") != (witver == 0):
        return None, None
    return witver, bytes(decoded)

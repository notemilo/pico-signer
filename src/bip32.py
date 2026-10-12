"""BIP32 — กุญแจลูกแบบลำดับชั้น (HD wallet)

รองรับทั้งฝั่ง private (xprv) และ public อย่างเดียว (xpub)
เขียนให้ยกไปวางบน MicroPython ได้ตรง ๆ
"""

import base58
import secp256k1 as ec
from hashes import sha256, hmac_sha512
from ripemd160 import ripemd160

HARDENED = 0x80000000

# version bytes มาตรฐาน
VERSIONS = {
    "xprv": b"\x04\x88\xad\xe4",
    "xpub": b"\x04\x88\xb2\x1e",
    "tprv": b"\x04\x35\x83\x94",
    "tpub": b"\x04\x35\x87\xcf",
}


def hash160(data):
    return ripemd160(sha256(data))


def parse_path(path):
    """'m/84h/0h/0h/0/0' -> [84+H, 0+H, 0+H, 0, 0]  (รับทั้ง h, H และ ')"""
    path = path.strip()
    if path in ("m", "M", ""):
        return []
    parts = path.split("/")
    if parts[0] in ("m", "M"):
        parts = parts[1:]
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        hard = p[-1] in ("h", "H", "'")
        if hard:
            p = p[:-1]
        n = int(p)
        if not (0 <= n < HARDENED):
            raise ValueError("index เกินช่วง: %s" % p)
        out.append(n + HARDENED if hard else n)
    return out


class HDKey:
    def __init__(self, key, chain_code, depth=0, fingerprint=b"\x00\x00\x00\x00",
                 child_number=0, private=True, testnet=False):
        self.key = key                  # 32 ไบต์ถ้า private, 33 ไบต์ถ้า public
        self.chain_code = chain_code
        self.depth = depth
        self.fingerprint = fingerprint  # fingerprint ของ "พ่อ"
        self.child_number = child_number
        self.private = private
        self.testnet = testnet

    # ---------- สร้าง ----------

    @classmethod
    def from_seed(cls, seed, testnet=False):
        I = hmac_sha512(b"Bitcoin seed", seed)
        il, ir = I[:32], I[32:]
        if not (0 < int.from_bytes(il, "big") < ec.N):
            raise ValueError("seed นี้ใช้ไม่ได้ (โอกาสเกิดต่ำมาก) ให้ลอง seed อื่น")
        return cls(il, ir, private=True, testnet=testnet)

    # ---------- คุณสมบัติ ----------

    @property
    def pubkey(self):
        """pubkey ของโหนดนี้ — คำนวณครั้งเดียวแล้วจำไว้

        🔑 EC point multiply เป็นงานหนักที่สุดในเครื่อง (~0.45 วิ/ครั้งบน Pico)
           derive_child เรียก pubkey 2 ครั้งต่อชั้น (ทำ data + ทำ fingerprint)
           ไม่จำไว้ = โหลด seed และเซ็นช้าลงเกือบเท่าตัวโดยเปล่าประโยชน์
           (วัดจริง 11 ก.ย. 2026: non-hardened 928 ms -> ครึ่งเดียวถ้าจำ)
        """
        if self.private:
            c = getattr(self, "_pub", None)
            if c is None:
                c = ec.privkey_to_pubkey(self.key)
                self._pub = c
            return c
        return self.key

    def my_fingerprint(self):
        return hash160(self.pubkey)[:4]

    def to_public(self):
        """ตัดส่วน private ออก เหลือแต่ xpub"""
        return HDKey(self.pubkey, self.chain_code, self.depth, self.fingerprint,
                     self.child_number, private=False, testnet=self.testnet)

    # ---------- อนุพันธ์ ----------

    def derive_child(self, index):
        if index >= HARDENED and not self.private:
            raise ValueError("xpub อนุพันธ์แบบ hardened ไม่ได้")

        idx = index.to_bytes(4, "big")
        if index >= HARDENED:
            data = b"\x00" + self.key + idx
        else:
            data = self.pubkey + idx

        I = hmac_sha512(self.chain_code, data)
        il, ir = I[:32], I[32:]
        if int.from_bytes(il, "big") >= ec.N:
            raise ValueError("index นี้ใช้ไม่ได้ ให้ข้ามไป index ถัดไป")

        parent_fp = self.my_fingerprint()
        if self.private:
            child = ec.tweak_add_private(self.key, il)
        else:
            child = ec.tweak_add_public(self.key, il)

        return HDKey(child, ir, self.depth + 1, parent_fp, index,
                     private=self.private, testnet=self.testnet)

    def derive(self, path):
        node = self
        for idx in parse_path(path):
            node = node.derive_child(idx)
        return node

    # ---------- ทำเป็นข้อความ ----------

    def serialize(self):
        if self.private:
            ver = VERSIONS["tprv" if self.testnet else "xprv"]
            keydata = b"\x00" + self.key
        else:
            ver = VERSIONS["tpub" if self.testnet else "xpub"]
            keydata = self.key
        return (ver + bytes([self.depth]) + self.fingerprint
                + self.child_number.to_bytes(4, "big") + self.chain_code + keydata)

    def to_base58(self):
        return base58.encode_check(self.serialize())

    @classmethod
    def from_base58(cls, s):
        raw = base58.decode_check(s)
        if len(raw) != 78:
            raise ValueError("ความยาวไม่ใช่ 78 ไบต์")
        ver = raw[:4]
        private = ver in (VERSIONS["xprv"], VERSIONS["tprv"])
        testnet = ver in (VERSIONS["tprv"], VERSIONS["tpub"])
        # ไบต์ 45:78 คือ key data — ถ้าเป็น private จะมี 0x00 นำหน้า 1 ไบต์
        keydata = raw[46:] if private else raw[45:]
        return cls(keydata, raw[13:45],
                   depth=raw[4], fingerprint=raw[5:9],
                   child_number=int.from_bytes(raw[9:13], "big"),
                   private=private, testnet=testnet)

    def __repr__(self):
        return "<HDKey %s depth=%d>" % (self.to_base58()[:12] + "...", self.depth)

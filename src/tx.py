"""ธุรกรรมบิตคอยน์ — อ่าน/เขียน และ sighash แบบ BIP143

รองรับ legacy และ segwit v0 (พอสำหรับ p2wpkh / p2wsh)
"""

from hashes import sha256


def dsha256(b):
    return sha256(sha256(b))


# ---------- varint ----------

def read_varint(b, i):
    """คืน (ค่า, ตำแหน่งถัดไป)"""
    n = b[i]
    if n < 0xFD:
        return n, i + 1
    if n == 0xFD:
        return int.from_bytes(b[i + 1:i + 3], "little"), i + 3
    if n == 0xFE:
        return int.from_bytes(b[i + 1:i + 5], "little"), i + 5
    return int.from_bytes(b[i + 1:i + 9], "little"), i + 9


def ser_varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def read_varbytes(b, i):
    n, i = read_varint(b, i)
    return b[i:i + n], i + n


def ser_varbytes(b):
    return ser_varint(len(b)) + b


# ---------- โครงสร้าง ----------

class TxInput:
    def __init__(self, txid, vout, script_sig=b"", sequence=0xFFFFFFFF):
        self.txid = txid            # 32 ไบต์ เรียงแบบ internal (little-endian)
        self.vout = vout
        self.script_sig = script_sig
        self.sequence = sequence
        self.witness = []

    def serialize(self):
        return (self.txid + self.vout.to_bytes(4, "little")
                + ser_varbytes(self.script_sig) + self.sequence.to_bytes(4, "little"))

    @property
    def txid_hex(self):
        """txid แบบที่คนอ่าน (กลับด้าน)"""
        return bytes(reversed(self.txid)).hex()


class TxOutput:
    def __init__(self, value, script_pubkey):
        self.value = value          # หน่วยซาโตชิ
        self.script_pubkey = script_pubkey

    def serialize(self):
        return self.value.to_bytes(8, "little") + ser_varbytes(self.script_pubkey)


class Transaction:
    def __init__(self, version=2, vin=None, vout=None, locktime=0):
        self.version = version
        self.vin = vin if vin is not None else []
        self.vout = vout if vout is not None else []
        self.locktime = locktime
        self.segwit = False

    # ---------- อ่าน ----------

    @classmethod
    def parse(cls, b):
        tx = cls()
        i = 0
        tx.version = int.from_bytes(b[i:i + 4], "little"); i += 4

        # ตรวจ marker+flag ของ segwit
        segwit = b[i] == 0x00 and b[i + 1] == 0x01
        if segwit:
            tx.segwit = True
            i += 2

        n, i = read_varint(b, i)
        for _ in range(n):
            txid = b[i:i + 32]; i += 32
            vout = int.from_bytes(b[i:i + 4], "little"); i += 4
            script, i = read_varbytes(b, i)
            seq = int.from_bytes(b[i:i + 4], "little"); i += 4
            tx.vin.append(TxInput(txid, vout, script, seq))

        n, i = read_varint(b, i)
        for _ in range(n):
            val = int.from_bytes(b[i:i + 8], "little"); i += 8
            spk, i = read_varbytes(b, i)
            tx.vout.append(TxOutput(val, spk))

        if segwit:
            for inp in tx.vin:
                cnt, i = read_varint(b, i)
                items = []
                for _ in range(cnt):
                    it, i = read_varbytes(b, i)
                    items.append(it)
                inp.witness = items

        tx.locktime = int.from_bytes(b[i:i + 4], "little"); i += 4
        return tx

    # ---------- เขียน ----------

    def serialize(self, with_witness=True):
        has_wit = with_witness and any(inp.witness for inp in self.vin)
        out = self.version.to_bytes(4, "little")
        if has_wit:
            out += b"\x00\x01"
        out += ser_varint(len(self.vin)) + b"".join(i.serialize() for i in self.vin)
        out += ser_varint(len(self.vout)) + b"".join(o.serialize() for o in self.vout)
        if has_wit:
            for inp in self.vin:
                out += ser_varint(len(inp.witness))
                for it in inp.witness:
                    out += ser_varbytes(it)
        out += self.locktime.to_bytes(4, "little")
        return out

    def txid(self):
        """txid (ไม่รวม witness) แบบที่คนอ่าน"""
        return bytes(reversed(dsha256(self.serialize(with_witness=False)))).hex()

    # ---------- sighash ----------

    def sighash_segwit_v0(self, index, script_code, amount, sighash_type=1):
        """คำนวณ sighash ตาม BIP143 สำหรับ segwit v0

        script_code สำหรับ p2wpkh คือ 0x1976a914{20-byte-pkh}88ac
        """
        hash_prevouts = dsha256(b"".join(
            i.txid + i.vout.to_bytes(4, "little") for i in self.vin))
        hash_sequence = dsha256(b"".join(
            i.sequence.to_bytes(4, "little") for i in self.vin))
        hash_outputs = dsha256(b"".join(o.serialize() for o in self.vout))

        inp = self.vin[index]
        preimage = (
            self.version.to_bytes(4, "little")
            + hash_prevouts
            + hash_sequence
            + inp.txid + inp.vout.to_bytes(4, "little")
            + ser_varbytes(script_code)
            + amount.to_bytes(8, "little")
            + inp.sequence.to_bytes(4, "little")
            + hash_outputs
            + self.locktime.to_bytes(4, "little")
            + sighash_type.to_bytes(4, "little")
        )
        return dsha256(preimage)

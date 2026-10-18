"""PSBT ตาม BIP-174 — อ่าน, วิเคราะห์, เซ็น

ออกแบบให้ "ตรวจก่อนเซ็น" เป็นหน้าที่หลัก ไม่ใช่แค่เซ็นให้ผ่าน ๆ
"""

import base64_min as b64
import bip32
import secp256k1 as ec
import tx as txmod
from tx import Transaction, read_varint, ser_varint, ser_varbytes

MAGIC = b"psbt\xff"

# --- คีย์ฝั่ง global ---
GLOBAL_UNSIGNED_TX = 0x00
GLOBAL_XPUB = 0x01
GLOBAL_VERSION = 0xFB

# --- คีย์ฝั่ง input ---
IN_NON_WITNESS_UTXO = 0x00
IN_WITNESS_UTXO = 0x01
IN_PARTIAL_SIG = 0x02
IN_SIGHASH_TYPE = 0x03
IN_REDEEM_SCRIPT = 0x04
IN_WITNESS_SCRIPT = 0x05
IN_BIP32_DERIVATION = 0x06
IN_FINAL_SCRIPTSIG = 0x07
IN_FINAL_SCRIPTWITNESS = 0x08

# --- คีย์ฝั่ง output ---
OUT_REDEEM_SCRIPT = 0x00
OUT_WITNESS_SCRIPT = 0x01
OUT_BIP32_DERIVATION = 0x02


# 🔴 กันโจมตีแบบทำเครื่องค้าง (พบ 11 ก.ย. 2026)
#    PSBT ระบุเส้นทางกุญแจได้ยาวไม่จำกัด และใส่กี่รายการก็ได้ ถ้าเราไล่ตามหมด
#    path 300 ชั้น = เครื่องค้าง 4.5 นาทีบนหน้า READING โดยกดยกเลิกไม่ได้
#    วิธีกัน: (ก) ไม่ไล่ path ที่ลึกกว่าของจริงที่เป็นไปได้ (ข) ไม่ดูเกิน N รายการต่อ map
#             (ค) มีงบรวมทั้ง PSBT — เกินแล้วปฏิเสธทั้งใบพร้อมบอกเหตุผล ดีกว่าค้างเงียบ
#    เส้นทางจริง: m/84h/0h/0h/1/5 = 5 ชั้น · multisig m/48h/0h/0h/2h/0/5 = 6 ชั้น
MAX_DERIV_DEPTH = 8        # ชั้น
MAX_DERIV_PER_MAP = 4      # รายการที่อ้าง fingerprint เราต่อ input/output (15 ต.ค. 2026: _check_claims ปฏิเสธช่องที่มีเกิน 1 ไปก่อนแล้ว · คงไว้เป็นด่านสำรอง)
MAX_DERIV_STEPS = 1200     # ชั้นรวมทั้ง PSBT (~ 100 input x 5 ชั้น ไล่ทั้งตอนหาช่วงทอน + output · ขยายจาก 600 เมื่อ 12 ต.ค. 2026)

# 🔴 เงินทอนต้องอยู่บนเส้นทางที่ "เครื่องนี้" ใช้จริงเท่านั้น (แก้ 11 ก.ย. 2026)
#    เดิมนับเป็นเงินทอนถ้าพิสูจน์ได้ว่าเป็นกุญแจเราล้วน ๆ โดยไม่สนเส้นทาง
#    คนร้ายจึงสร้าง PSBT ที่ระบุเงินทอนเป็น m/84h/0h/999h/0/0 ได้
#    -> จอขึ้น "SEND 0" เหมือนไม่มีอะไรออกจากกระเป๋า แต่เงินไปอยู่บัญชีที่
#       กระเป๋าฝั่งคอมไม่ได้เฝ้าดู เจ้าของต้องไปไล่หาเองถึงจะเจอ
#    ยังเป็นกุญแจเราอยู่ (ไม่ถูกขโมย) แต่ "หายไปจากสายตา" ซึ่งอันตรายพอกัน
#    วิธีกัน: เส้นทางไหนไม่ตรงแบบนี้ ไม่นับเป็นเงินทอน -> ไปโผล่เป็นปลายทางให้ผู้ใช้เห็นที่อยู่
#    (fail-safe: แย่สุดคือผู้ใช้ต้องกดยืนยันที่อยู่เพิ่มหนึ่งหน้า ดีกว่าถูกซ่อน)
HARDENED = 0x80000000
CHANGE_ACCOUNT = (84 + HARDENED, 0 + HARDENED, 0 + HARDENED)   # ค่าเริ่มต้น = account 0

# 🔑 เลือก account ได้ (เพิ่ม 14 ก.ย. 2026 — ผู้ใช้ เลือกแบบ "มีเมนูเลือก" ให้ยืดหยุ่นแบบกระเป๋าทั่วไป)
#    ตัวอย่างการใช้: seed เดียวกับหลายเครื่อง แต่ละเครื่องใช้คนละ account = กระเป๋าคนละใบ
#    เงินทอนต้องอยู่ใน account ที่ผู้ใช้เลือกไว้เท่านั้น — account อื่นแม้เป็นกุญแจเรา
#    ก็ไม่นับเป็นเงินทอน (โผล่เป็นปลายทางให้เห็น) ตามหลัก fail-safe เดิม
def _bip84_account(path):
    """เลข account จากเส้นทางแบบ m/84h/0h/<n>h/<chain>/<index> · ไม่ใช่รูปแบบนี้ = None"""
    if (len(path) == CHANGE_DEPTH and path[0] == 84 + HARDENED and path[1] == 0 + HARDENED
            and path[2] >= HARDENED):
        return path[2] - HARDENED
    return None


def change_account(account=0):
    """(84h, 0h, <account>h) — ส่วนหัวของเส้นทางที่นับเป็นเงินทอนได้"""
    if not isinstance(account, int) or account < 0 or account >= HARDENED:
        raise ValueError("ACCOUNT OUT OF RANGE")
    return (84 + HARDENED, 0 + HARDENED, account + HARDENED)
CHANGE_CHAINS = (0, 1)        # 0 = ช่องรับ · 1 = ช่องเงินทอน (กระเป๋าบางตัวทอนเข้า 0)
CHANGE_DEPTH = 5              # m/84h/0h/0h/<chain>/<index>

# 🔴 เพดานเลขที่อยู่ของเงินทอน (เพิ่ม 12 ก.ย. 2026 — ได้ไอเดียจาก Coldcard)
#    เช็คแค่ "เส้นทางถูกแบบ" ยังไม่พอ เงินทอนที่ไป m/84h/0h/0h/1/999999
#    ยังเป็นกุญแจเราก็จริง แต่กระเป๋าฝั่งคอมสแกนหาแค่ ~20 ที่อยู่แรก จะมองไม่เห็นเงินก้อนนั้น
#    Coldcard แก้ด้วยการดูว่า input ที่กำลังจะเซ็นใช้เลขอะไร แล้วให้เงินทอนอยู่ใกล้ ๆ กัน
#    เราทำแบบเดียวกัน: เลขเงินทอนต้องไม่เกิน (เลขสูงสุดของ input + CHANGE_GAP)
CHANGE_GAP = 200
CHANGE_INDEX_CAP = 100000     # เพดานเด็ดขาด เผื่อกรณีไม่รู้เลขของ input เลย


# 🔴 เพดานค่าธรรมเนียม (เพิ่ม 12 ต.ค. 2026) — เกินแล้ว "ไม่เซ็น" ไม่ใช่แค่เตือน
#    คิดแบบ Coldcard: ค่าธรรมเนียม ÷ ยอดรวมทุก output (รวมเงินทอน) · Coldcard เดิมล็อก 10% ตายตัว
#    (blog.coinkite.com/coldcard-v110 · สูตรตาม commit ของ Sparrow ที่ทำให้ตรง Coldcard)
#    จอยังเตือน "! FEE n% !" แบบเดิม (เทียบกับยอดส่งออก) ซึ่งเข้มกว่า — อันนี้คือด่านปฏิเสธ
MAX_FEE_PCT = 10


# 🔑 18 ต.ค. 2026 (แนวคิดจาก ShieldSigner psbt_parser.py · fork ของ SeedSigner โดย 3rdIteration/Crypto Guide)
#    ค่าเดียวกับเขา: output ต่ำกว่า 546 sat = ฝุ่น (อาจไม่คุ้มค่าธรรมเนียมที่จะใช้ต่อ / ใช้ติดตามกระเป๋า)
#    ค่าธรรมเนียมต่อไบต์ 500 sat/vB ขึ้นไป = เตือน (ค่าสำรองของเขาตอนไม่รู้สภาพเครือข่าย — เครื่องเราไม่ต่อเน็ต จึงใช้ค่าคงที่)
DUST_SAT = 546
HIGH_FEE_RATE = 500


def estimate_vsize(tx, in_spks):
    """ขนาดธุรกรรมหลังเซ็น (vbyte) โดยประมาณ — in_spks = script ของ input ทุกตัว (จาก tx เก่า)

    witness ของ p2wpkh = 1 + (1+72) + (1+33) = 108 WU · taproot key path = 1 + 1 + 64 = 66 WU
    p2pkh ใส่ scriptSig ~107 ไบต์ในส่วน non-witness · ชนิดอื่นเดาแบบ p2wpkh (ประมาณการ ไม่ใช่ค่าจริง)
    """
    base = len(tx.serialize(with_witness=False))
    wu = base * 4
    seg = False
    for spk in in_spks:
        if len(spk) == 25 and spk[:3] == b"\x76\xa9\x14":          # p2pkh
            wu += 107 * 4
        elif len(spk) == 34 and spk[:2] == b"\x51\x20":            # p2tr
            wu += 66
            seg = True
        else:
            wu += 108
            seg = True
    if seg:
        wu += 2                                                    # segwit marker + flag
    return (wu + 3) // 4


def fee_over_cap(fee, total_out):
    """ค่าธรรมเนียมเกินเพดานไหม (ไม่รู้ค่าธรรมเนียม = ตัดสินที่นี่ไม่ได้ คืน False ให้ด่านอื่นปฏิเสธ)"""
    if fee is None:
        return False
    if total_out <= 0:
        return fee > 0
    return fee * 100 > MAX_FEE_PCT * total_out


class PSBTError(Exception):
    pass


class PSBTLie(PSBTError):
    """PSBT อ้างข้อมูลกุญแจของ seed นี้แล้ว "พิสูจน์ได้ว่าเท็จ" — ไม่ใช่ไฟล์เสีย แต่เป็นการโกหก

    🔴 15 ต.ค. 2026 (แนวคิดจาก SeedSigner psbt_parser.py · PSBT[Input|Output]OwnershipClaimError
       / PSBTOutputOwnershipContradictionError):
       เดิมเจอรายการที่อ้าง fingerprint เราแต่ derive แล้วไม่ตรง เรา "ข้ามเงียบ ๆ"
       ไม่เสียเงิน (output ไปโผล่เป็นปลายทาง) แต่ผู้ใช้ไม่มีทางรู้ว่าคอม/กระเป๋าฝั่งออนไลน์กำลังโกหก
       ตอนนี้ปฏิเสธทั้งใบ + จอบอกตรง ๆ ว่าอาจโดนเจาะ
       และปิดทั้งตระกูลช่อง "แอบรายการปลอมไว้ข้างรายการจริง" (ช่องที่ผู้รีวิวภายนอกเจอ 12 ต.ค.) ตั้งแต่ทางเข้า
    """
    pass


ZERO_FP = b"\x00\x00\x00\x00"    # กระเป๋าบางตัวใส่ fingerprint เป็น 0 เมื่อไม่รู้ = "ไม่ระบุ" ไม่ใช่ "ของคนอื่น"
DCACHE_MAX = 32                  # เก็บ node ระดับกลาง (ไม่ใช่ปลายทาง) ที่ derive แล้ว ต่อการเรียก 1 ครั้ง


class KVMap:
    """key-value map ที่รักษาลำดับเดิมไว้ (MicroPython ไม่รับประกันลำดับของ dict)"""

    def __init__(self):
        self.items_ = []

    def get(self, key, default=None):
        for k, v in self.items_:
            if k == key:
                return v
        return default

    def put(self, key, val):
        self.items_.append((key, val))

    def keys(self):
        return [k for k, _ in self.items_]

    def items(self):
        return list(self.items_)

    def __contains__(self, key):
        return self.get(key) is not None

    def __len__(self):
        return len(self.items_)


# ชนิดคีย์ที่ "ห้ามมีข้อมูลต่อท้าย" (keydata ต้องว่าง)
_BARE = {
    "g": (GLOBAL_UNSIGNED_TX, GLOBAL_VERSION),
    "i": (IN_NON_WITNESS_UTXO, IN_WITNESS_UTXO, IN_SIGHASH_TYPE, IN_REDEEM_SCRIPT,
          IN_WITNESS_SCRIPT, IN_FINAL_SCRIPTSIG, IN_FINAL_SCRIPTWITNESS),
    "o": (OUT_REDEEM_SCRIPT, OUT_WITNESS_SCRIPT),
}
# ชนิดคีย์ที่ keydata ต้องเป็น pubkey (33 หรือ 65 ไบต์)
_PUBKEY = {
    "g": (),
    "i": (IN_PARTIAL_SIG, IN_BIP32_DERIVATION),
    "o": (OUT_BIP32_DERIVATION,),
}


def _check_key(key, scope):
    """ตรวจว่าคีย์ที่รู้จักมีความยาวถูกต้อง — คีย์ที่ไม่รู้จักปล่อยผ่าน (สเปกอนุญาต)"""
    t = key[0]
    data = key[1:]
    if t in _BARE[scope]:
        if data:
            raise PSBTError("KEY 0x%02x HAS %d EXTRA BYTES" % (t, len(data)))
    elif t in _PUBKEY[scope]:
        if len(data) not in (33, 65):
            raise PSBTError("KEY 0x%02x BAD PUBKEY LEN %d"
                            % (t, len(data)))
    elif scope == "g" and t == GLOBAL_XPUB:
        if len(data) != 78:
            raise PSBTError("GLOBAL XPUB BAD LEN %d" % len(data))


def _parse_map(b, i, scope):
    """อ่าน key-value map หนึ่งชุด จนเจอ key ยาว 0 -> คืน (KVMap, ตำแหน่งถัดไป)"""
    m = KVMap()
    seen = set()          # ⚠️ ต้องเป็น set — list ทำให้ map ใหญ่ ๆ ช้าแบบ n^2
    while True:
        if i >= len(b):
            raise PSBTError("TRUNCATED - MAP NOT CLOSED")
        klen, i = read_varint(b, i)
        if klen == 0:
            return m, i
        key = b[i:i + klen]
        if len(key) != klen:
            raise PSBTError("TRUNCATED KEY")
        i += klen
        vlen, i = read_varint(b, i)
        val = b[i:i + vlen]
        if len(val) != vlen:
            raise PSBTError("TRUNCATED VALUE")
        i += vlen
        if key in seen:
            raise PSBTError("DUPLICATE KEY IN MAP")
        seen.add(key)
        _check_key(key, scope)
        m.put(key, val)


def _ser_map(m):
    out = b""
    for k, v in m.items():
        out += ser_varint(len(k)) + k + ser_varbytes(v)
    return out + b"\x00"


def _parse_derivation(val):
    """ค่าใน BIP32_DERIVATION = fingerprint 4 ไบต์ + index ละ 4 ไบต์"""
    if len(val) < 4 or (len(val) - 4) % 4 != 0:
        raise PSBTError("BAD BIP32 DERIVATION LEN")
    fp = val[:4]
    path = [int.from_bytes(val[i:i + 4], "little") for i in range(4, len(val), 4)]
    return fp, path


def _last_index(ps):
    """'m/84h/0h/0h/1/150' -> 150"""
    return int(ps.rsplit("/", 1)[1])


def _chain_of(ps):
    """'m/84h/0h/0h/1/150' -> 1"""
    return int(ps.rsplit("/", 2)[1])


def path_str(path):
    out = "m"
    for i in path:
        if i >= bip32.HARDENED:
            out += "/%dh" % (i - bip32.HARDENED)
        else:
            out += "/%d" % i
    return out


class PSBT:
    def __init__(self):
        self._deriv_steps = 0
        self._dcache = {}       # path ระดับกลาง (tuple) -> node · ล้างทุกครั้งที่เริ่ม/จบ describe() และ sign()
        self._prev_cache = {}   # n -> (value, spk) ที่ตรวจกับ tx เก่าแล้ว
        self.tx = None
        self.g = KVMap()     # global map ดิบ
        self.inputs = []     # list ของ dict
        self.outputs = []

    # ---------- อ่าน / เขียน ----------

    @classmethod
    def parse(cls, raw):
        if raw[:5] != MAGIC:
            raise PSBTError("NOT A PSBT - BAD MAGIC")
        p = cls()
        i = 5
        p.g, i = _parse_map(raw, i, "g")

        # 🔑 17 ต.ค. 2026 (รีวิวภายนอก Crypto Guide F-006): BIP174 ให้ปฏิเสธ PSBT เวอร์ชันที่ไม่รู้จัก
        #    เดิมรู้จักคีย์ 0xFB แต่ไม่เคยอ่านค่า → เวอร์ชันอนาคต (ความหมายฟิลด์อาจเปลี่ยน) ผ่านไปแบบ v0
        ver = p.g.get(bytes([GLOBAL_VERSION]))
        if ver is not None and (len(ver) != 4 or int.from_bytes(ver, "little") != 0):
            raise PSBTError("PSBT VERSION %d NOT SUPPORTED" % int.from_bytes(ver[:4], "little"))

        raw_tx = p.g.get(bytes([GLOBAL_UNSIGNED_TX]))
        if raw_tx is None:
            raise PSBTError("NO UNSIGNED TX")
        p.tx = Transaction.parse(raw_tx)

        # unsigned tx ต้องเรียงแบบ legacy ห้ามมี marker/flag ของ segwit
        if p.tx.segwit:
            raise PSBTError("UNSIGNED TX HAS SEGWIT FLAG")

        # 🔴 input ซ้ำ (outpoint เดียวกัน 2 ครั้ง) = ธุรกรรมใช้ไม่ได้ และทำให้ยอดขาเข้า/ค่าธรรมเนียมบนจอเพี้ยน (12 ต.ค. 2026)
        seen_op = set()
        for inp in p.tx.vin:
            op = bytes(inp.txid) + inp.vout.to_bytes(4, "little")
            if op in seen_op:
                raise PSBTError("DUPLICATE INPUT - same coin used twice")
            seen_op.add(op)

        # unsigned tx ต้องไม่มีลายเซ็นติดมา
        for inp in p.tx.vin:
            if inp.script_sig or inp.witness:
                raise PSBTError("UNSIGNED TX HAS SCRIPTSIG")

        for _ in range(len(p.tx.vin)):
            m, i = _parse_map(raw, i, "i")
            p.inputs.append(m)
        for _ in range(len(p.tx.vout)):
            m, i = _parse_map(raw, i, "o")
            p.outputs.append(m)

        if i != len(raw):
            raise PSBTError("EXTRA BYTES AFTER PSBT")
        return p

    @classmethod
    def from_base64(cls, s):
        return cls.parse(b64.b64decode(s))

    def serialize(self):
        out = MAGIC + _ser_map(self.g)
        for m in self.inputs:
            out += _ser_map(m)
        for m in self.outputs:
            out += _ser_map(m)
        return out

    def to_base64(self):
        return b64.b64encode(self.serialize())

    def export_signed(self):
        """PSBT ที่เซ็นแล้วแบบตัดของที่ฝั่งรับไม่ต้องใช้ — ไว้ทำ QR ส่งกลับ (เฟรมน้อยลง สแกนเร็วขึ้น)

        🔑 15 ต.ค. 2026 (SeedSigner `PSBTParser.trim()` โชว์เฉพาะลายเซ็นก่อนทำ QR):
           ก้อนใหญ่สุดใน PSBT คือ tx เก่าทั้งใบ (non-witness utxo) ที่เราใช้ "ตรวจ" ยอด — ตรวจเสร็จแล้วไม่ต้องส่งกลับ
           ตัด: non-witness utxo (เฉพาะ input ที่มี witness utxo) · BIP32 derivation ทั้ง input/output · global xpub
           เก็บ: unsigned tx · witness utxo · ลายเซ็น · sighash · script · คีย์ที่ไม่รู้จัก
        ⚠️ ต่างจาก SeedSigner ที่ตัดเหลือแค่ลายเซ็น: wallet เอา PSBT ใบนี้ไป finalize เองโดยไม่รวมกับใบเดิม
           (server.js finalizeAllInputs) และ bitcoinjs ต้องมี witness utxo → จึงต้องเก็บไว้
           (เทสไขว้ test_signing_interop ข้อ 4: bitcoinjs finalize ใบที่ตัดแล้วได้ txid เดียวกับใบเต็ม)
        """
        out = MAGIC
        g = KVMap()
        for k, v in self.g.items():
            if k[0] != GLOBAL_XPUB:
                g.put(k, v)
        out += _ser_map(g)
        for m in self.inputs:
            has_wu = m.get(bytes([IN_WITNESS_UTXO])) is not None
            t = KVMap()
            for k, v in m.items():
                if k[0] == IN_BIP32_DERIVATION or (k[0] == IN_NON_WITNESS_UTXO and has_wu):
                    continue
                t.put(k, v)
            out += _ser_map(t)
        for m in self.outputs:
            t = KVMap()
            for k, v in m.items():
                if k[0] != OUT_BIP32_DERIVATION:
                    t.put(k, v)
            out += _ser_map(t)
        return out

    # ---------- ดึงข้อมูลที่ใช้ตัดสินใจ ----------

    def _prev_out(self, n):
        """(จำนวนซาโตชิ, scriptPubKey) ของ input ที่ n ที่ "พิสูจน์แล้ว" — None ถ้าไม่มี tx เก่าแนบมา

        🔴 เชื่อเฉพาะ tx เก่าทั้งใบ (non-witness utxo) ที่แฮชแล้วตรง txid ที่ input อ้าง (แก้ 12 ต.ค. 2026)
           เดิมเชื่อยอดใน witness utxo ตรง ๆ → เปิดช่อง CVE-2020-14199:
           คนร้ายโกหกยอดของ input ทีละใบในการเซ็น 2 รอบ แต่ละรอบจอโชว์ค่าธรรมเนียมปกติ
           แต่เอาลายเซ็นที่ใช้ได้จากทั้ง 2 รอบมารวมกัน = ค่าธรรมเนียมก้อนใหญ่ที่ผู้ใช้ไม่เคยเห็น
           ลายเซ็น segwit ผูกยอดของ input ตัวเองเท่านั้น ไม่ผูกยอดของ input อื่น จึงกันด้วยลายเซ็นไม่ได้
           แต่ txid ผูกทั้งใบ → ยอดที่อ่านจาก tx ที่แฮชตรง txid โกหกไม่ได้
           wallet แนบ tx เก่าให้ทุก input อยู่แล้ว (server.js "Always include nonWitnessUtxo")
        ถ้ามี witness utxo มาด้วยต้องตรงกันทุกไบต์ ไม่ตรง = มีคนแก้ PSBT → ปฏิเสธทั้งใบ
        """
        c = self._prev_cache.get(n)
        if c is not None:
            return c
        m = self.inputs[n]
        nwu = m.get(bytes([IN_NON_WITNESS_UTXO]))
        if nwu is None:
            return None
        prev = Transaction.parse(nwu)
        vin = self.tx.vin[n]
        # เทียบ bytes ตรง ๆ (txid() คืน hex กลับด้าน · vin.txid เก็บแบบ little-endian ตามที่อยู่ในสาย)
        if bytes(reversed(bytes.fromhex(prev.txid()))) != vin.txid:
            raise PSBTError("INPUT %d PREV TX DOES NOT MATCH TXID" % n)
        if vin.vout >= len(prev.vout):
            raise PSBTError("INPUT %d SPENDS MISSING OUTPUT %d" % (n, vin.vout))
        out = prev.vout[vin.vout]
        wu = m.get(bytes([IN_WITNESS_UTXO]))
        if wu is not None:
            spk, end = txmod.read_varbytes(wu, 8)
            # 🔑 17 ต.ค. 2026 (รีวิวภายนอก): เดิมไบต์เกินท้าย script ผ่านได้ — README บอกว่าตรวจทุกไบต์ จึงต้องไม่มีส่วนเกิน
            if end != len(wu) or int.from_bytes(wu[:8], "little") != out.value or spk != out.script_pubkey:
                raise PSBTError("INPUT %d WITNESS UTXO DOES NOT MATCH PREV TX" % n)
        c = (out.value, out.script_pubkey)
        self._prev_cache[n] = c
        del prev
        return c

    def input_amount(self, n):
        """จำนวนซาโตชิของ input ที่ n ที่พิสูจน์แล้ว — None ถ้าไม่มี tx เก่าแนบมา (ไม่เชื่อ witness utxo อย่างเดียว)"""
        c = self._prev_out(n)
        return None if c is None else c[0]

    def input_script_pubkey(self, n):
        c = self._prev_out(n)
        return None if c is None else c[1]

    def derivations(self, m, prefix):
        """ดึง {pubkey: (fingerprint, path)} จาก map ที่ให้มา"""
        out = {}
        for k, v in m.items():
            if k and k[0] == prefix:
                out[k[1:]] = _parse_derivation(v)
        return out

    def fee(self):
        """ค่าธรรมเนียม = ผลรวม input - ผลรวม output (None ถ้าข้อมูล input ไม่ครบ)"""
        total_in = 0
        for n in range(len(self.tx.vin)):
            a = self.input_amount(n)
            if a is None:
                return None
            total_in += a
        total_out = sum(o.value for o in self.tx.vout)
        if total_out > total_in:
            raise PSBTError("OUTPUTS EXCEED INPUTS")
        return total_in - total_out

    # ---------- ตรวจความเป็นเจ้าของ (ด่านความปลอดภัยหลัก) ----------

    def _derive(self, root, path):
        """derive ตาม path จาก root — คืน node หรือ None ถ้าลึกเกินจริง / derive ไม่ได้

        นับงบ MAX_DERIV_STEPS เฉพาะชั้นที่ derive จริง
        🔑 15 ต.ค. 2026 (แนวคิดจาก SeedSigner `_derive_with_cache_via_indices`):
           ทุก path ในกระเป๋าเดียวกันขึ้นต้นเหมือนกัน (m/84h/0h/0h/...) และเราไล่ซ้ำหลายรอบ
           (ตรวจคำอ้าง → หาช่วงทอน → ดู output) จึงเก็บ node ระดับกลางไว้ใช้ซ้ำ
           key = path เต็มจาก root เดียวกัน (ไม่ใช้ fingerprint เป็น key — คนร้ายบังคับให้ 4 ไบต์ชนได้)
           ไม่เก็บ node ปลายทาง (มีได้หลายร้อยตัว กินแรม) · เพดาน DCACHE_MAX ตัว
        """
        if len(path) > MAX_DERIV_DEPTH:
            return None
        node = root
        start = 0
        for i in range(len(path) - 1, 0, -1):        # หา prefix ที่ยาวสุดที่มีในแคช
            c = self._dcache.get(tuple(path[:i]))
            if c is not None:
                node, start = c, i
                break
        try:
            for i in range(start, len(path)):
                self._deriv_steps += 1
                if self._deriv_steps > MAX_DERIV_STEPS:
                    raise PSBTError("PSBT TOO BIG (over %d key steps)" % MAX_DERIV_STEPS)
                node = node.derive_child(path[i])
                if i < len(path) - 1 and len(self._dcache) < DCACHE_MAX:
                    self._dcache[tuple(path[:i + 1])] = node
        except PSBTError:
            raise
        except Exception:
            return None
        return node

    def _check_claims(self, root, fp_root):
        """ตรวจทุกรายการ derivation ก่อนเชื่ออะไรใน PSBT — โกหก = ปฏิเสธทั้งใบ (PSBTLie)

        🔴 15 ต.ค. 2026 (แนวคิดจาก SeedSigner `_verify_claimed_derivation_paths` + ตาราง 2x2 ใน `_parse_outputs`)
        1. ช่องเดียวมี derivation เกิน 1 รายการ = ปฏิเสธ (PSBTError)
           เครื่องนี้ single-sig p2wpkh อย่างเดียว · wallet ใส่ช่องละ 1 รายการ
           (SeedSigner: PSBTSurplusDerivationPathsError) — ช่องที่ผู้รีวิวเจอ 12 ต.ค. อาศัยรายการที่ 2 พอดี
        2. อ้าง fingerprint เรา แต่ derive แล้ว pubkey ไม่ตรง (หรือ path ลึกผิดปกติ) = โกหก
           (เดิม: ข้ามเงียบ ๆ)
        3. output: อ้าง fingerprint เรา pubkey จริง แต่ scriptPubKey ไม่ได้จ่ายเข้ากุญแจนั้น = โกหก
           ("บอกว่าเป็นของเรา แต่เงินไปที่อื่น")
        4. output: อ้าง fingerprint คนอื่น แต่ path นั้น derive จาก seed เราได้ pubkey นั้นพอดี = โกหก
           ("จ่ายเข้าเรา แต่บอกว่าเป็นของคนอื่น") · fingerprint 0000 = "ไม่ระบุ" ไม่นับว่าโกหก
        ดู output ก่อน input — output โกหกน่าจะเป็นการโจมตี input โกหกแค่ทำให้เซ็นไม่ได้
        ⚠️ ข้อแลก (SeedSigner ยอมแบบเดียวกัน): fingerprint 4 ไบต์ชนกันได้ ~1 ใน 4 พันล้าน
           ถ้าคนอื่นในธุรกรรมเดียวกันบังเอิญมี fingerprint ตรงเรา จะถูกปฏิเสธเหมือนโกหก
        """
        import address as addr
        for kind, maps, prefix in (("OUT", self.outputs, OUT_BIP32_DERIVATION),
                                   ("IN", self.inputs, IN_BIP32_DERIVATION)):
            for n, m in enumerate(maps):
                ders = self.derivations(m, prefix)
                if len(ders) > 1:
                    raise PSBTError("%s %d HAS %d KEY PATHS - single-sig allows 1"
                                    % (kind, n, len(ders)))
                for pub, (fp, path) in ders.items():
                    if fp == fp_root:
                        node = self._derive(root, path)
                        if node is None or node.pubkey != pub:
                            raise PSBTLie("%s %d FAKE KEY PATH for this seed" % (kind, n))
                        if kind == "OUT":
                            spk = self.tx.vout[n].script_pubkey
                            if spk != addr.p2wpkh_script(pub) and spk != addr.p2pkh_script(pub):
                                raise PSBTLie("OUT %d CLAIMS THIS SEED but pays elsewhere" % n)
                    elif kind == "OUT" and fp != ZERO_FP:
                        node = self._derive(root, path)
                        if node is not None and node.pubkey == pub:
                            raise PSBTLie("OUT %d PAYS THIS SEED but claims another" % n)

    def _check_sighash(self):
        """PSBT ขอ sighash อื่นที่ไม่ใช่ ALL = ไม่เซ็น

        🔴 15 ต.ค. 2026 (embit `sign_with` ทำแบบนี้ · BIP174: signer ที่ไม่ยอมรับ sighash ที่ขอต้องปฏิเสธ)
           เดิมไม่อ่านช่องนี้เลย เซ็น ALL เสมอ — ไม่เสียเงิน แต่ได้ลายเซ็นที่คนขอไม่ได้ขอ
           (ตอบคำถามข้อ 4 ใน SECURITY_REVIEW.md)
        """
        for n, m in enumerate(self.inputs):
            v = m.get(bytes([IN_SIGHASH_TYPE]))
            if v is not None and (len(v) != 4 or int.from_bytes(v, "little") != 1):
                raise PSBTError("SIGHASH NOT ALL input %d - not signed" % n)

    def _owned_keys(self, m, prefix, spk, root, fp_root):
        """คืนรายการ (pubkey, path) ที่ 'พิสูจน์แล้ว' ว่าเป็นของเราจริง

        ตรวจ 3 ชั้น — ขาดชั้นไหนก็ถือว่าไม่ใช่ของเรา:
          1. fingerprint ตรงกับกุญแจแม่ของเรา
          2. อนุพันธ์ตาม path แล้วได้ pubkey ตรงกับที่ระบุในคีย์
             (กัน PSBT ปลอม path มั่ว ๆ มาหลอกว่าเป็นของเรา)
          3. scriptPubKey ตรงกับที่ pubkey นั้นสร้างได้จริง
             (กัน path ชี้ไป pubkey ที่ไม่ได้อยู่ในสคริปต์นั้นจริง)
        """
        found = []
        checked = 0
        for pub, (fp, path) in self.derivations(m, prefix).items():
            if fp != fp_root:
                continue
            # ── กันค้าง: ดูรายละเอียดที่หัวไฟล์ (MAX_DERIV_*)
            if len(path) > MAX_DERIV_DEPTH:
                continue                      # ลึกผิดปกติ = ไม่ใช่ของเรา (fail-closed)
            checked += 1
            if checked > MAX_DERIV_PER_MAP:
                break
            node = self._derive(root, path)
            if node is None:
                continue
            if node.pubkey != pub:               # ชั้นที่ 2
                continue
            if spk is not None:                  # ชั้นที่ 3
                import address as addr
                if spk != addr.p2wpkh_script(pub) and spk != addr.p2pkh_script(pub):
                    continue
            found.append((pub, path, node))
        return found

    def _check_not_presigned(self, fp_root):
        """ปฏิเสธ PSBT ที่มีลายเซ็นของกุญแจเรา (หรือ input ที่ปิดงานแล้ว) ติดมาตั้งแต่ต้น

        🔴 13 ต.ค. 2026 (ผู้รีวิวภายนอก ข้อ 4): sign() ใช้ put ต่อท้าย ไม่ลบของเดิม
           ถ้าคนสร้าง PSBT แปะ PARTIAL_SIG ปลอมของ pubkey เรามาก่อน ไฟล์ที่ส่งออกจะมีคีย์ซ้ำ (ผิด BIP174)
           และตัวอ่านหลายตัวหยิบตัวแรก = ลายเซ็นปลอม → "ดูเหมือนเซ็นแล้วแต่ใช้ไม่ได้"
           input ที่มี FINAL_SCRIPTSIG/FINAL_SCRIPTWITNESS แล้วก็ไม่ควรมาให้เซ็นอีก
        """
        for n, m in enumerate(self.inputs):
            ours = [pub for pub, (fp, _p) in self.derivations(m, IN_BIP32_DERIVATION).items()
                    if fp == fp_root]
            for k, _v in m.items():
                if not k:
                    continue
                if k[0] == IN_PARTIAL_SIG and k[1:] in ours:
                    raise PSBTError("ALREADY SIGNED input %d - signature for our key present" % n)
                if k[0] in (IN_FINAL_SCRIPTSIG, IN_FINAL_SCRIPTWITNESS) and ours:
                    raise PSBTError("ALREADY FINAL input %d - nothing to sign" % n)

    def _max_input_index(self, root, fp_root, acct=CHANGE_ACCOUNT):
        """เลขที่อยู่สูงสุดของ input ที่ "พิสูจน์แล้ว" ว่าเป็นของเรา — กำหนดช่วงที่เงินทอนควรอยู่

        🔴 แก้ 12 ต.ค. 2026 (ผู้รีวิวภายนอกเจอ + มี PoC · เทสข้อ 19):
           เดิมอ่านเลขจากเส้นทางที่ PSBT "ประกาศ" เฉย ๆ โดยเชื่อว่า sign() จะจับได้ถ้าโกหก
           แต่คนร้ายไม่ต้องแก้รายการจริง แค่ "เพิ่มรายการที่ 2" ใน input จริงของเรา
           (pubkey มั่ว + fingerprint เรา + m/84h/0h/0h/0/99999) → ช่วงเงินทอนถ่างไปถึง 100,000
           → เงินทอนที่ index 100,000 ถูกซ่อนเป็น CHG · sign() เจอรายการจริงก็เซ็นให้ครบ
           ตอนนี้: นับเฉพาะรายการที่ผ่าน _owned_keys (ไล่กุญแจแล้ว pubkey ตรง + script ตรง)
           ช้าขึ้นเพราะต้องไล่กุญแจของ input ด้วย (ใช้งบ MAX_DERIV_STEPS ร่วมกับ output)

        คืน (เลขสูงสุด, จำนวน input ที่ seed นี้เซ็นได้จริง)
        🔑 15 ต.ค. 2026: นับ "เซ็นได้จริง" (ไล่กุญแจแล้ว + เป็น p2wpkh) ไว้บอกผู้ใช้ตั้งแต่ก่อนหน้ารีวิว
           (SeedSigner `_reject_if_seed_cannot_sign`) · เดิมผู้ใช้กดผ่านรีวิวครบแล้วค่อยเจอ NOT SIGNED
        """
        import address as addr
        best = -1
        signable = 0
        for n, m in enumerate(self.inputs):
            spk = self.input_script_pubkey(n)
            if spk is None:
                continue
            owned = self._owned_keys(m, IN_BIP32_DERIVATION, spk, root, fp_root)
            if any(spk == addr.p2wpkh_script(pub) for pub, _p, _n in owned):
                signable += 1
            for _pub, path, _node in owned:
                if (len(path) == CHANGE_DEPTH and tuple(path[:3]) == acct
                        and path[3] in CHANGE_CHAINS and path[4] > best):
                    best = path[4]
        return best, signable

    def _is_change_path(self, path, max_in_idx, acct=CHANGE_ACCOUNT):
        """เส้นทางนี้เป็น "เงินทอนที่กระเป๋าจะหาเจอ" จริงไหม"""
        if len(path) != CHANGE_DEPTH:
            return False
        if tuple(path[:3]) != acct:
            return False
        if path[3] not in CHANGE_CHAINS:
            return False
        idx = path[4]
        if idx >= HARDENED or idx > CHANGE_INDEX_CAP:
            return False
        limit = (max_in_idx if max_in_idx >= 0 else 0) + CHANGE_GAP
        return idx <= limit

    def describe(self, root, testnet=False, account=0):
        """สรุปสิ่งที่ผู้ใช้ต้องยืนยันก่อนเซ็น

        account = BIP84 account ที่ผู้ใช้เลือกไว้ (m/84h/0h/<account>h) ใช้ตัดสินว่า output ไหนเป็นเงินทอน

        คืน dict: outputs (พร้อมธง is_change ที่พิสูจน์แล้ว), fee, ยอดที่ออกจากกระเป๋า
        """
        fp_root = root.my_fingerprint()
        self._check_not_presigned(fp_root)
        self._check_sighash()
        acct = change_account(account)
        self._deriv_steps = 0
        self._dcache = {}
        try:
            return self._describe(root, fp_root, acct, account, testnet)
        finally:
            self._dcache = {}              # node ในแคชมีกุญแจส่วนตัว — ไม่เก็บค้างหลังใช้

    def _describe(self, root, fp_root, acct, account, testnet):
        import address as addr

        self._check_claims(root, fp_root)
        max_in_idx, inputs_signable = self._max_input_index(root, fp_root, acct)
        total_in = 0
        unknown_in = 0
        # 🔴 input ของเรามาจาก account ไหน (แก้บัค F 15 ก.ย. 2026)
        #    เดิมเลือก account 1 อยู่ แต่ PSBT ใช้เหรียญของ account 0 ก็เซ็นให้เงียบ ๆ
        #    อ่านจากเส้นทางที่ PSBT ประกาศ (เร็ว ไม่ไล่กุญแจ) — ถ้าคนร้ายโกหกเส้นทาง
        #    sign(account=) จะไล่กุญแจจริงแล้วไม่เซ็นให้อยู่ดี
        inputs_mine = 0
        input_accounts = []
        inputs_wrong_account = 0
        inputs_detail = []
        for n in range(len(self.tx.vin)):
            a = self.input_amount(n)
            if a is None:
                unknown_in += 1
            else:
                total_in += a
            decl = [path for _pub, (fp, path) in self.derivations(self.inputs[n], IN_BIP32_DERIVATION).items()
                    if fp == fp_root]
            # 🔑 18 ต.ค. 2026 (แนวคิดจาก Specter-DIY หน้ารายละเอียด input): ยอดของแต่ละ input + ของเราไหม
            #    เส้นทางที่อ้าง fp เรา ผ่าน _check_claims มาแล้ว = จริง (โกหก = PSBTLie ไปก่อนถึงตรงนี้)
            inputs_detail.append({"index": n, "value": a, "path": path_str(decl[0]) if decl else None})
            if decl:
                inputs_mine += 1
                ia = _bip84_account(decl[0])
                if ia not in input_accounts:
                    input_accounts.append(ia)
                if ia != account:
                    inputs_wrong_account += 1

        outs = []
        sending = 0
        change = 0
        for n, o in enumerate(self.tx.vout):
            owned = self._owned_keys(self.outputs[n], OUT_BIP32_DERIVATION,
                                     o.script_pubkey, root, fp_root)
            # เป็นกุญแจเราอย่างเดียวยังไม่พอ — เส้นทางต้องอยู่ในช่วงที่กระเป๋าจะหาเจอด้วย
            # 🔴 และต้องเป็นที่อยู่แบบ bc1q (p2wpkh) เท่านั้น (แก้ 11 ต.ค. 2026 · ตรวจโค้ดหลังข่าว Ledger)
            #    _owned_keys ยอม p2pkh ด้วย → เงินทอนไปที่อยู่ "1..." ของกุญแจเดียวกันถูกนับเป็น CHG
            #    จอไม่โชว์ที่อยู่ แต่กระเป๋า BIP84 ไม่เฝ้าที่อยู่แบบ 1... = เงินหายไปจากสายตา
            #    แบบเดียวกับเส้นทางแปลก (11 ก.ย.) → ไม่นับเป็นเงินทอน ให้ไปโผล่เป็นปลายทางแทน
            is_change = any(self._is_change_path(pth, max_in_idx, acct)
                            and o.script_pubkey == addr.p2wpkh_script(_pub)
                            for _pub, pth, _node in owned)
            # 🔑 18 ต.ค. 2026 (แนวคิดจาก Specter-DIY UNVERIFIED_CHANGE_WARNING): มี input ที่ seed นี้เซ็นไม่ได้ปน
            #    (payjoin/coinjoin) = พิสูจน์ไม่ได้ว่าเป็น "เงินทอน" ในความหมายบัญชี → ไม่ซ่อน ให้ขึ้นจอพร้อมป้าย YOUR ADDRESS
            own_unhidden = False
            if is_change and inputs_signable < len(self.tx.vin):
                is_change = False
                own_unhidden = True
            # ของเราแต่เส้นทางแปลก = ถือเป็นการจ่ายออก แต่ติดธงไว้ให้จอเตือนได้
            odd_owned = bool(owned) and not is_change and not own_unhidden
            if is_change:
                change += o.value
            else:
                sending += o.value
            a = addr.script_to_address(o.script_pubkey, testnet)
            outs.append({
                "index": n,
                "address": a,
                # 🔑 17 ต.ค. 2026 (รีวิวภายนอก): ปลายทางที่แปลงเป็นที่อยู่ไม่ได้ จอขึ้นแค่ขนาด script
                #    = ปลายทางต่างกันแต่หน้าจอเหมือนกัน → UI ปฏิเสธไม่เซ็น
                "unknown_script": a.startswith("UNKNOWN SCRIPT"),
                "value": o.value,
                "is_change": is_change,
                "odd_owned": odd_owned,
                "own_unhidden": own_unhidden,
                "path": path_str(owned[0][1]) if owned else None,
            })

        fee = None if unknown_in else total_in - sum(o.value for o in self.tx.vout)
        # 🔑 18 ต.ค. 2026 (แนวคิดจาก ShieldSigner): ยอดทุกก้อนต้องรวมกันได้ยอดเข้าพอดี
        #    ตอนนี้ทุก output ตกเป็น CHG หรือ SEND อย่างเดียวเสมอ จึงจริงอยู่แล้ว — ใส่ไว้กันการแก้โค้ดวันหน้าทำให้ยอดหาย
        if fee is not None and sending + change + fee != total_in:
            raise PSBTError("AMOUNTS DO NOT ADD UP")
        # 🔑 18 ต.ค. 2026 (แนวคิดจาก ShieldSigner): OP_RETURN ใช้จ่ายต่อไม่ได้ เงินที่แนบไป = เผาทิ้ง
        #    output ฝุ่น (ต่ำกว่า 546 sat) = เตือน · ค่าธรรมเนียมต่อไบต์สูงผิดปกติ = เตือน
        op_return_sat = sum(o.value for o in self.tx.vout if o.script_pubkey[:1] == b"\x6a")
        dust = [o["index"] for o in outs
                if o["value"] < DUST_SAT and self.tx.vout[o["index"]].script_pubkey[:1] != b"\x6a"]
        fee_rate = None
        if fee is not None:
            vsize = estimate_vsize(self.tx, [self.input_script_pubkey(n) for n in range(len(self.tx.vin))])
            fee_rate = fee // vsize if vsize else None

        # 🔴 locktime: เดิมไม่เคยอ่านค่านี้เลย (เพิ่ม 12 ก.ย. 2026)
        #    ธุรกรรมระบุได้ว่า "ห้ามใช้ก่อนบล็อกที่ N" หรือ "ก่อนเวลา T"
        #    ถ้าไม่บอกผู้ใช้ เขาจะเซ็นแล้วส่งไม่ออกโดยไม่รู้สาเหตุ
        #    และถ้า nSequence ทุกช่องเป็น 0xffffffff -> locktime ไม่มีผลจริง (กับดักที่ Coldcard ดักไว้)
        lt = self.tx.locktime
        seqs = [i.sequence for i in self.tx.vin]
        # 🔑 17 ต.ค. 2026 (รีวิวภายนอก): relative timelock (BIP68) — tx version 2 ขึ้นไป + nSequence บิต 31 เป็น 0
        #    = เหรียญนั้นใช้ได้หลังยืนยันครบ N บล็อก (หรือ N x 512 วินาที ถ้าบิต 22 ตั้ง) · เดิมไม่บอกเลย
        rel_blocks = 0
        rel_secs = 0
        if self.tx.version >= 2:
            for q in seqs:
                if q & 0x80000000:
                    continue
                if q & 0x00400000:
                    rel_secs = max(rel_secs, (q & 0xFFFF) * 512)
                else:
                    rel_blocks = max(rel_blocks, q & 0xFFFF)
        # 🔑 17 ต.ค. 2026 (รีวิวภายนอก): เลขที่อยู่ของเงินทอนสูงสุด (สูงได้ถึง input+200) — จอ REVIEW ต้องบอก
        #    เพราะกู้กระเป๋าด้วยค่าตั้งต้น (Sparrow ค้น 20 ที่อยู่) อาจหาเงินทอนที่อยู่ไกลไม่เจอ
        chg_idx = None
        for o in outs:
            if o["is_change"]:
                k = _last_index(o["path"])
                if chg_idx is None or k > chg_idx[1]:
                    chg_idx = (_chain_of(o["path"]), k)
        return {
            "inputs": len(self.tx.vin),
            "inputs_mine": inputs_mine,                  # input ที่ประกาศว่าเป็นกุญแจเรา
            "inputs_signable": inputs_signable,          # input ที่ไล่กุญแจแล้วเซ็นได้จริง (0 = seed ผิด)
            "input_accounts": input_accounts,            # account ของ input เหล่านั้น (None = เส้นทางแปลก)
            "inputs_wrong_account": inputs_wrong_account,  # อยู่นอก account ที่ผู้ใช้เลือก
            "inputs_unknown_amount": unknown_in,
            "total_in": total_in,
            "outputs": outs,
            "sending": sending,     # ยอดที่ออกจากกระเป๋าจริง
            "change": change,
            "fee": fee,
            "locktime": lt,
            "locktime_is_time": lt >= 500000000,
            "locktime_no_effect": lt > 0 and all(q == 0xFFFFFFFF for q in seqs),
            "rbf": any(q < 0xFFFFFFFE for q in seqs),
            "inputs_detail": inputs_detail,   # [{index, value, path (str) หรือ None = ไม่ใช่ของเรา}]
            "rel_lock_blocks": rel_blocks,
            "rel_lock_secs": rel_secs,
            "change_index": chg_idx,          # (chain, index) ของเงินทอนที่ไกลที่สุด · None = ไม่มีเงินทอน
            "op_return_sat": op_return_sat,   # เงินที่แนบไปกับ OP_RETURN (> 0 = UI ไม่เซ็น)
            "dust_outputs": dust,             # index ของ output ที่ต่ำกว่า DUST_SAT
            "fee_rate": fee_rate,             # sat/vB โดยประมาณ (ปัดลง) · None = ไม่รู้ค่าธรรมเนียม
            "fee_over_cap": fee_over_cap(fee, sum(o.value for o in self.tx.vout)),
        }

    # ---------- เซ็น ----------

    def sign(self, root, sighash_type=1, account=None):
        """เซ็นทุก input ที่พิสูจน์ได้ว่าเป็นของเรา — คืนจำนวน input ที่เซ็นไป

        account = ถ้าระบุ เซ็นเฉพาะ input ที่ไล่กุญแจแล้วอยู่ใน m/84h/0h/<account>h เท่านั้น
                  (ชั้นที่ 2 ของการแก้บัค F — UI ปฏิเสธก่อนแล้ว ตัวเซ็นกันซ้ำอีกชั้น)

        รองรับ p2wpkh (native segwit) เท่านั้น
        input ชนิดอื่นจะข้ามไป ไม่เซ็นมั่ว
        """
        # ด่านซ้ำของเพดานค่าธรรมเนียม — UI ปฏิเสธก่อนแล้ว ตัวเซ็นกันอีกชั้น (fee() ไม่รู้ยอด = None ไปตกด่าน "ไม่มีจำนวนเงิน" ข้างล่าง)
        if fee_over_cap(self.fee(), sum(o.value for o in self.tx.vout)):
            raise PSBTError("FEE OVER %d%% - not signed" % MAX_FEE_PCT)
        # 🔑 18 ต.ค. 2026: เงินที่แนบไปกับ OP_RETURN = เผาทิ้ง → ไม่เซ็น (UI ปฏิเสธก่อนแล้ว ตัวเซ็นกันซ้ำ)
        for o in self.tx.vout:
            if o.script_pubkey[:1] == b"\x6a" and o.value > 0:
                raise PSBTError("OP_RETURN BURNS %d SAT - not signed" % o.value)
        # 🔑 17 ต.ค. 2026 (รีวิวภายนอก): เดิม sign() ที่ถูกเรียกตรง ๆ เซ็น input ของเราได้ แม้ input อื่นไม่มี tx เก่า
        #    (= ไม่รู้ค่าธรรมเนียมจริง) · UI ปฏิเสธก่อนแล้ว แต่ตัวเซ็นต้องไม่พึ่งว่าใครเรียกอะไรก่อน
        for n in range(len(self.tx.vin)):
            if self.input_amount(n) is None:
                raise PSBTError("INPUT %d HAS NO PREV TX - not signed" % n)

        fp_root = root.my_fingerprint()
        self._check_not_presigned(fp_root)
        self._check_sighash()
        acct_t = change_account(account) if account is not None else None
        self._deriv_steps = 0
        self._dcache = {}
        try:
            return self._sign(root, fp_root, acct_t, sighash_type)
        finally:
            self._dcache = {}

    def _sign(self, root, fp_root, acct_t, sighash_type):
        import address as addr

        self._check_claims(root, fp_root)       # ด่านซ้ำ — describe() ตรวจแล้ว แต่ sign() ต้องไม่พึ่งว่าใครเรียกอะไรก่อน
        signed = 0
        for n in range(len(self.tx.vin)):
            m = self.inputs[n]
            spk = self.input_script_pubkey(n)
            if spk is None:
                continue
            owned = self._owned_keys(m, IN_BIP32_DERIVATION, spk, root, fp_root)
            if not owned:
                continue
            pick = None
            for o in owned:
                if acct_t is None or tuple(o[1][:3]) == acct_t:
                    pick = o
                    break
            if pick is None:
                continue          # กุญแจเรา แต่อยู่นอก account ที่เลือก — ไม่เซ็น
            pub, path, node = pick

            if spk != addr.p2wpkh_script(pub):
                continue      # ยังไม่รองรับชนิดอื่น — ข้าม ดีกว่าเซ็นผิด

            amount = self.input_amount(n)
            if amount is None:
                raise PSBTError("INPUT %d HAS NO AMOUNT - not signed" % n)

            digest = self.tx.sighash_segwit_v0(
                n, addr.p2wpkh_script_code(pub), amount, sighash_type)
            r, s = ec.sign(digest, node.key)
            # 🔴 ตรวจลายเซ็นตัวเองก่อนส่งออก (verify-after-sign · เพิ่ม 12 ต.ค. 2026)
            #    nonce แบบ RFC6979 ได้ค่าเดิมทุกครั้ง → ถ้าการคำนวณพลาดแม้รอบเดียว (บั๊ก/ไฟกระตุก/ตั้งใจรบกวน)
            #    ลายเซ็นผิด 1 ใบ + ลายเซ็นถูกของ sighash เดียวกัน = แก้สมการหา private key ได้
            #    ตรวจด้วย pubkey ที่ derive ได้เอง ไม่ผ่าน = ไม่ใส่ลายเซ็น ทิ้งทั้งใบ
            #    (ช้าขึ้น ~2 การคูณจุดต่อ input · Coldcard/Jade ก็ตรวจแบบนี้ ตามที่ Gemini บอก ยังไม่ได้ยืนยันเอง)
            if not ec.verify(digest, (r, s), pub):
                raise PSBTError("SIG VERIFY FAIL input %d - not signed" % n)
            m.put(bytes([IN_PARTIAL_SIG]) + pub,
                  _der(r, s) + bytes([sighash_type]))
            signed += 1
        return signed


def _der(r, s):
    """เข้ารหัสลายเซ็นแบบ DER ตามที่บิตคอยน์ใช้"""
    def enc(v):
        b = v.to_bytes(32, "big").lstrip(b"\x00")
        if not b:
            b = b"\x00"
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b
    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body

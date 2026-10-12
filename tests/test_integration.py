"""เทสต่อกันทั้งสาย: mnemonic -> seed -> BIP32 -> xprv

ใช้ช่องที่ 4 ของ test vector Trezor ซึ่งเป็น xprv ที่ถูกต้อง
= ตรวจ BIP39 กับ BIP32 พร้อมกันในเทสเดียว
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import bip39  # noqa: E402
import bip32  # noqa: E402

WL = os.path.join(ROOT, "src", "english.txt")
VECTORS = json.load(open(os.path.join(ROOT, "vectors", "bip39_vectors.json")))["english"]


def run():
    fails = []
    for i, (_ent, mnemonic, _seed, xprv) in enumerate(VECTORS):
        seed = bip39.seed(mnemonic, "TREZOR")
        got = bip32.HDKey.from_seed(seed).to_base58()
        if got != xprv:
            fails.append("v%d xprv ไม่ตรง" % i)

    # เส้นทางจริงที่จะใช้งาน (Native SegWit บัญชีแรก ที่อยู่แรก)
    seed = bip39.seed(VECTORS[0][1], "")
    root = bip32.HDKey.from_seed(seed)
    t = time.time()
    node = root.derive("m/84h/0h/0h/0/0")
    dt = time.time() - t

    print("เทส %d ชุด: mnemonic -> seed -> master xprv" % len(VECTORS))
    print("  m/84h/0h/0h/0/0 -> pubkey %s" % node.pubkey.hex()[:24] + "...")
    print("  fingerprint ราก: %s" % root.my_fingerprint().hex())
    print("  เวลาไล่ 5 ชั้นบนแมค: %.0f ms" % (dt * 1000))
    if fails:
        print("ไม่ผ่าน %d: %s" % (len(fails), fails[:5]))
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(run())

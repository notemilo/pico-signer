"""เทส BIP39 กับ test vector ทางการของ Trezor (24 ชุด)"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import bip39  # noqa: E402

WL = os.path.join(ROOT, "src", "english.txt")
VECTORS = json.load(open(os.path.join(ROOT, "vectors", "bip39_vectors.json")))["english"]

# vector ทางการใช้ passphrase "TREZOR" ทุกชุด
PASSPHRASE = "TREZOR"


def run():
    fails = []
    for i, (entropy_hex, mnemonic, seed_hex, _xprv) in enumerate(VECTORS):
        entropy = bytes.fromhex(entropy_hex)

        got = bip39.mnemonic_from_entropy(entropy, WL)
        if got != mnemonic:
            fails.append("v%d entropy->mnemonic: ได้ %r" % (i, got))

        got_ent = bip39.mnemonic_to_entropy(mnemonic, WL)
        if got_ent != entropy:
            fails.append("v%d mnemonic->entropy: ได้ %s" % (i, got_ent.hex()))

        got_seed = bip39.seed(mnemonic, PASSPHRASE)
        if got_seed.hex() != seed_hex:
            fails.append("v%d seed: ได้ %s" % (i, got_seed.hex()))

    # checksum ผิดต้องถูกจับได้
    bad = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"
    if bip39.is_valid(bad, WL):
        fails.append("checksum ผิดแต่ผ่าน")

    # หาคำสุดท้ายจาก 23 คำ (เคสทอยเต๋า)
    full = next(v[1].split() for v in VECTORS if len(v[1].split()) == 24)
    cands = bip39.last_word_candidates(full[:23], WL)
    if full[23] not in cands:
        fails.append("last_word: ไม่มีคำจริงในผลลัพธ์")
    if len(cands) != 8:
        fails.append("last_word: ควรได้ 8 คำ ได้ %d" % len(cands))

    # 11 คำ -> คำที่ 12
    full12 = next(v[1].split() for v in VECTORS if len(v[1].split()) == 12)
    c12 = bip39.last_word_candidates(full12[:11], WL)
    if full12[11] not in c12:
        fails.append("last_word 12คำ: ไม่มีคำจริง")
    if len(c12) != 128:
        fails.append("last_word 12คำ: ควรได้ 128 คำ ได้ %d" % len(c12))

    print("เทส %d ชุด (entropy/mnemonic/seed) + checksum + คำสุดท้าย" % len(VECTORS))
    if fails:
        print("ไม่ผ่าน %d:" % len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(run())

"""เทส BIP32 กับ test vector ทางการจากตัวสเปก BIP-32 เอง"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import bip32  # noqa: E402

VECTORS = json.load(open(os.path.join(ROOT, "vectors", "bip32_vectors.json")))


def clean_path(p):
    # สเปกเขียน hardened เป็น <sub>H</sub> ในไฟล์ mediawiki
    return p.replace("<sub>H</sub>", "h").replace("H", "h").strip()


def run():
    fails = []
    n_chain = 0

    for vi, vec in enumerate(VECTORS):
        seed = bytes.fromhex(vec["seed"])
        master = bip32.HDKey.from_seed(seed)

        for ch in vec["chains"]:
            n_chain += 1
            path = clean_path(ch["path"])
            node = master.derive(path)

            if node.to_base58() != ch["xprv"]:
                fails.append("v%d %s xprv ไม่ตรง" % (vi + 1, path))
            if node.to_public().to_base58() != ch["xpub"]:
                fails.append("v%d %s xpub ไม่ตรง" % (vi + 1, path))

            # อนุพันธ์จาก xpub อย่างเดียวต้องได้ผลเท่ากัน (เฉพาะ path ที่ไม่มี hardened)
            idxs = bip32.parse_path(path)
            if idxs and all(i < bip32.HARDENED for i in idxs):
                pub_only = master.to_public()
                for i in idxs:
                    pub_only = pub_only.derive_child(i)
                if pub_only.to_base58() != ch["xpub"]:
                    fails.append("v%d %s อนุพันธ์จาก xpub ไม่ตรง" % (vi + 1, path))

            # อ่านกลับจาก base58 แล้วต้องได้ค่าเดิม
            if bip32.HDKey.from_base58(ch["xprv"]).to_base58() != ch["xprv"]:
                fails.append("v%d %s อ่าน xprv กลับไม่ตรง" % (vi + 1, path))
            if bip32.HDKey.from_base58(ch["xpub"]).to_base58() != ch["xpub"]:
                fails.append("v%d %s อ่าน xpub กลับไม่ตรง" % (vi + 1, path))

    # xpub ต้องอนุพันธ์แบบ hardened ไม่ได้
    m = bip32.HDKey.from_seed(bytes(32)).to_public()
    try:
        m.derive_child(bip32.HARDENED)
        fails.append("xpub ทำ hardened ได้ ทั้งที่ไม่ควรได้")
    except ValueError:
        pass

    print("เทส %d เวกเตอร์ / %d chain (xprv, xpub, อนุพันธ์จาก xpub, อ่านกลับ)"
          % (len(VECTORS), n_chain))
    if fails:
        print("ไม่ผ่าน %d:" % len(fails))
        for f in fails[:12]:
            print("  -", f)
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(run())

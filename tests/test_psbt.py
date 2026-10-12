"""เทส PSBT กับ test vector ทางการจากสเปก BIP-174

- valid 24 ชุด: ต้องอ่านได้ และ serialize กลับได้ไบต์เดิมเป๊ะ
- invalid 20 ชุด: ต้องถูกปฏิเสธ ไม่ใช่อ่านผ่านเงียบ ๆ
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from psbt import PSBT, PSBTError  # noqa: E402

V = json.load(open(os.path.join(ROOT, "vectors", "bip174_vectors.json")))
VALID = V["The following are valid PSBTs:"]
INVALID = V["The following are invalid PSBTs:"]


def run():
    fails = []

    # --- ชุดที่ถูกต้อง ---
    ok_parse = ok_roundtrip = 0
    psbts = [h for h in VALID["hex"] if h.startswith("70736274ff")]
    for i, h in enumerate(psbts):
        raw = bytes.fromhex(h)
        try:
            p = PSBT.parse(raw)
            ok_parse += 1
        except Exception as e:
            fails.append("valid[%d] อ่านไม่ได้: %s" % (i, e))
            continue
        if p.serialize() == raw:
            ok_roundtrip += 1
        else:
            fails.append("valid[%d] serialize กลับไม่ตรงไบต์เดิม" % i)

    # --- ชุดที่ต้องถูกปฏิเสธ ---
    ok_reject = 0
    for i, h in enumerate(INVALID["hex"]):
        raw = bytes.fromhex(h)
        try:
            PSBT.parse(raw)
            fails.append("invalid[%d] (%s) อ่านผ่าน ทั้งที่ควรถูกปฏิเสธ"
                         % (i, INVALID["cases"][i][:45] if i < len(INVALID["cases"]) else "?"))
        except Exception:
            ok_reject += 1

    print("valid   : อ่านได้ %d/%d · serialize ตรงไบต์เดิม %d/%d"
          % (ok_parse, len(psbts), ok_roundtrip, len(psbts)))
    print("invalid : ปฏิเสธถูกต้อง %d/%d" % (ok_reject, len(INVALID["hex"])))

    if fails:
        print("ไม่ผ่าน %d:" % len(fails))
        for f in fails[:12]:
            print("  -", f)
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(run())

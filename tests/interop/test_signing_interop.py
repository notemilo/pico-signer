"""เทสไขว้ส่วนเข้ารหัส: Pico (เขียนเอง) เทียบกับไลบรารีมาตรฐานที่ wallet ใช้จริง

ทำไมไฟล์นี้สำคัญที่สุดในโปรเจกต์:
โค้ดเข้ารหัสในโปรเจกต์นี้เขียนขึ้นใหม่ทั้งหมด (SHA512/HMAC/PBKDF2/RIPEMD160/
secp256k1/RFC6979) เพราะ MicroPython ไม่มีให้ ถ้ามันคำนวณผิดแม้แต่บิตเดียว
ผลคือเซ็นธุรกรรมออกไปแล้วเงินหาย โดยหน้าจอยังโชว์ว่าทุกอย่างถูกต้อง

การเทสตัวเองไม่พอ เพราะคนเขียนโค้ดกับคนเขียนเทสคือคนเดียวกัน
ไฟล์นี้จึงเทียบกับ bitcoinjs-lib / tiny-secp256k1 / bip32 / bip39
ซึ่งเป็นคนละคนเขียน คนละภาษา และมีคนใช้จริงทั้งวงการ

🔑 RFC6979 ทำให้ค่า nonce ไม่สุ่ม → ลายเซ็นของ input เดียวกันต้องออกมา
   "เหมือนกันทุกไบต์" ทั้งสองฝั่ง ไม่ใช่แค่ "ตรวจผ่านทั้งคู่"
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))

import address as addr        # noqa: E402
import bip32                  # noqa: E402
import bip39                  # noqa: E402
import psbt as P              # noqa: E402
import secp256k1 as ec        # noqa: E402

REF = os.path.join(HERE, "ref_bitcoin.js")


def js(fn, **kw):
    r = subprocess.run(["node", REF, json.dumps(dict(fn=fn, **kw))],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("node ล้มเหลว: " + r.stderr.strip()[:300])
    return json.loads(r.stdout)


fails = []


def check(name, ours, theirs, extra=""):
    ok = ours == theirs
    if not ok:
        fails.append(name)
    print("  %-42s %s%s" % (name, "ตรงกัน" if ok else "❌ ไม่ตรง", extra))
    if not ok:
        print("      Pico     : %s" % str(ours)[:110])
        print("      ของจริง  : %s" % str(theirs)[:110])
    return ok


# ─────────────────────────────────────────────────────────────────────────
print("── 1. BIP39: คำ → seed (ทดสอบ PBKDF2 + HMAC-SHA512 ที่เขียนเอง) ──")
M12 = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
M24 = ("legal winner thank year wave sausage worth useful legal winner thank yellow "
       "legal winner thank year wave sausage worth useful legal winner thank yellow")
for label, mn, pw in [
    ("12 คำ ไม่มี passphrase", M12, ""),
    ("12 คำ + passphrase", M12, "TREZOR"),
    ("24 คำ + passphrase ไทย", M24, "รหัสลับของผม"),
    ("24 คำ + passphrase ยาว", M24, "x" * 100),
]:
    ours = bip39.seed(mn, pw).hex()
    check(label, ours, js("seed", mnemonic=mn, passphrase=pw)["seed"])

# ─────────────────────────────────────────────────────────────────────────
print("\n── 2. BIP32: seed → กุญแจ/xpub/ที่อยู่ ตาม path ────────────────")
seed_hex = bip39.seed(M12, "").hex()
root = bip32.HDKey.from_seed(bytes.fromhex(seed_hex))
for path in ["m/84h/0h/0h/0/0", "m/84h/0h/0h/1/0", "m/84h/0h/5h/0/199", "m/0", "m/1h/2h/3h"]:
    node = root.derive(path)
    ref = js("derive", seed=seed_hex, path=path.replace("h", "'"))
    check("pubkey  %s" % path, node.pubkey.hex(), ref["pubkey"])
    check("xpub    %s" % path, node.to_public().to_base58(), ref["xpub"])
    check("xprv    %s" % path, node.to_base58(), ref["xprv"])
    check("ที่อยู่  %s" % path,
          addr.script_to_address(addr.p2wpkh_script(node.pubkey)), ref["address"])
check("master fingerprint", root.my_fingerprint().hex(),
      js("derive", seed=seed_hex, path="m/0")["masterFingerprint"])

# ─────────────────────────────────────────────────────────────────────────
print("\n── 3. ECDSA + RFC6979: ลายเซ็นต้องเหมือนกันทุกไบต์ ─────────────")
node = root.derive("m/84h/0h/0h/0/0")
digests = [
    ("digest ปกติ", bytes(range(32))),
    ("digest ศูนย์ล้วน", b"\x00" * 32),
    ("digest FF ล้วน", b"\xff" * 32),
    ("digest จาก sighash จริง", bytes.fromhex(
        "1c1b1a191817161514131211100f0e0d0c0b0a090807060504030201000f1e2d")),
]
def compact(rs):
    """(r, s) -> 64 ไบต์ แบบเดียวกับที่ tiny-secp256k1 คืนมา"""
    r, s_ = rs
    return (r.to_bytes(32, "big") + s_.to_bytes(32, "big")).hex()


for label, dg in digests:
    ours = compact(ec.sign(dg, node.key))
    ref = js("sign", digest=dg.hex(), privkey=node.key.hex())
    check(label + " (compact 64B)", ours, ref["compact"])
    v = js("verify", digest=dg.hex(), pubkey=node.pubkey.hex(), compact=ours)
    if not v["ok"]:
        fails.append(label + " verify")
    print("  %-42s %s" % (label + " → ไลบรารีมาตรฐานตรวจ",
                          "ยอมรับ" if v["ok"] else "❌ ปฏิเสธ"))

# ─────────────────────────────────────────────────────────────────────────
print("\n── 4. วงจรจริง: JS สร้าง PSBT → Pico เซ็น → JS ตรวจ+finalize ───")
DEST = "bc1q4h0ycu78h88wzldxc7e79vhw5xsde0n8jk4wl5"
made = js("make_psbt",
          seed=seed_hex, path="m/84'/0'/0'/0/0",
          prevTxid="a" * 64, prevVout=0, inValue=91000,
          outputs=[{"address": DEST, "value": 60000}],
          change={"path": "m/84'/0'/0'/1/0", "value": 30000})

p = P.PSBT.from_base64(made["psbt"])
d = p.describe(root)
print("  อ่าน PSBT ที่ bitcoinjs-lib สร้าง          จ่ายออก %d · ทอน %d · ค่าธรรมเนียม %d"
      % (d["sending"], d["change"], d["fee"]))
if (d["sending"], d["change"], d["fee"]) != (60000, 30000, 1000):
    fails.append("ตัวเลขใน describe ไม่ตรง")
if not d["outputs"][1]["is_change"] or d["outputs"][0]["is_change"]:
    fails.append("ระบุ change ผิดบน PSBT ที่ JS สร้าง")
    print("  ❌ ระบุ change ผิด")
else:
    print("  ระบุเงินทอนถูกต้อง (output ที่ 2 = ของเรา)")

n = p.sign(root)
print("  Pico เซ็นได้ %d input" % n)
if n != 1:
    fails.append("ควรเซ็นได้ 1 input")

res = js("validate_psbt", psbt=p.to_base64())
print("  bitcoinjs-lib ตรวจลายเซ็น                 %s"
      % ("ผ่าน" if res["signaturesValid"] else "❌ ไม่ผ่าน"))
if not res["signaturesValid"]:
    fails.append("ลายเซ็นจาก Pico ไลบรารีมาตรฐานไม่ยอมรับ")
print("  finalize เป็นธุรกรรมพร้อม broadcast       txid %s… (%d vbyte)"
      % (res["txid"][:20], res["vsize"]))
got_outs = [(o["address"], o["value"]) for o in res["outputs"]]
want_dest = (DEST, 60000)
if want_dest not in got_outs:
    fails.append("ปลายทาง/ยอดในธุรกรรมที่ออกมาไม่ตรงกับที่สั่ง")
    print("  ❌ ปลายทางไม่ตรง: %s" % got_outs)
else:
    print("  ปลายทางในธุรกรรมจริงตรงกับที่สั่ง        %s ← %d ซาโตชิ" % want_dest)

# ─────────────────────────────────────────────────────────────────────────
print("\n── 5. เซ็นซ้ำ 3 รอบต้องได้ผลเดิม (ไม่มีความสุ่มหลุดเข้ามา) ─────")
sigs = set()
for _ in range(3):
    q = P.PSBT.from_base64(made["psbt"])
    q.sign(root)
    sigs.add(q.to_base64())
ok = len(sigs) == 1
if not ok:
    fails.append("เซ็นซ้ำได้ผลไม่เหมือนเดิม")
print("  เซ็น PSBT เดิม 3 รอบ                      %s"
      % ("ได้ผลเดียวกันทุกรอบ" if ok else "❌ ได้ %d ผลต่างกัน" % len(sigs)))

print("\n%s" % ("✅ เทสไขว้ผ่านทั้งหมด — โค้ดที่เขียนเองตรงกับไลบรารีมาตรฐาน"
                if not fails else "❌ ไม่ผ่าน %d จุด: %s" % (len(fails), ", ".join(fails[:5]))))
sys.exit(1 if fails else 0)

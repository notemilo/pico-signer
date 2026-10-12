"""passphrase (คำที่ 25 ตาม BIP39) — seed ต้องตรงมาตรฐานเป๊ะ

🔴 ทำไมต้องเทสหนัก: พิมพ์ passphrase ผิดไปตัวเดียวจะได้กระเป๋าคนละใบ
   **โดยไม่มี error อะไรเตือนเลย** เงินที่โอนเข้าไปแล้วจะหาไม่เจอ
   ถ้าโค้ดเราคำนวณไม่ตรงมาตรฐาน = ย้ายไปเครื่องอื่นแล้วเปิดกระเป๋าไม่ได้ตลอดกาล

เทียบ 2 ทาง: เวกเตอร์ทางการของ BIP39 (passphrase "TREZOR") และไลบรารี bip39 ของ JS
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
os.chdir(os.path.join(HERE, "..", "src"))

import bip39, bip32

JS_DIR = os.path.join(HERE, "interop")
JS = os.path.join(JS_DIR, "_pp.js")

JS_SRC = """
const bip39 = require("bip39");
const [mn, pw] = [process.argv[2], process.argv[3] || ""];
console.log(bip39.mnemonicToSeedSync(mn, pw).toString("hex"));
"""


def main():
    fails = 0

    # 1) เวกเตอร์ทางการ BIP39 — ทุกตัวใช้ passphrase "TREZOR"
    vec = json.load(open(os.path.join(HERE, "..", "vectors", "bip39_vectors.json")))["english"]
    bad = 0
    for entropy, mn, want_seed, want_xprv in vec:
        got = bip39.seed(mn, "TREZOR").hex()
        if got != want_seed:
            bad += 1
            if bad == 1:
                print("   ตัวแรกที่ผิด:", mn[:40], "...")
        root = bip32.HDKey.from_seed(bytes.fromhex(got))
        if root.to_base58() != want_xprv:
            bad += 1
    fails += bool(bad)
    print("1. เวกเตอร์ทางการ %d ชุด (passphrase 'TREZOR')  ผิด %d  %s"
          % (len(vec), bad, "ผ่าน" if not bad else "ไม่ผ่าน"))

    # 2) passphrase ว่าง ต้องได้ผลเดิมกับตอนไม่ใส่เลย
    mn = "abandon " * 11 + "about"
    mn = mn.strip()
    ok = bip39.seed(mn, "") == bip39.seed(mn)
    fails += not ok
    print("2. passphrase ว่าง = ไม่ใส่เลย                    %s" % ("ผ่าน" if ok else "ไม่ผ่าน"))

    # 3) เทียบข้ามภาษากับ bip39 ของ JS — รวมอักขระพิเศษทุกกลุ่มที่เครื่องพิมพ์ได้
    try:
        with open(JS, "w") as f:
            f.write(JS_SRC)
        cases = ["", "TREZOR", "a", "Z9", " ", "  ", "hello world",
                 "!\"#$%&'()*+,-./", ":;<=>?@[\\]^_`{|}~",
                 "Correct Horse Battery Staple 42!", "x" * 64]
        bad = 0
        for pw in cases:
            mine = bip39.seed(mn, pw).hex()
            out = subprocess.run(["node", JS, mn, pw], cwd=JS_DIR,
                                 capture_output=True, text=True).stdout.strip()
            if mine != out:
                bad += 1
                print("   ไม่ตรงที่ passphrase %r" % pw)
        fails += bool(bad)
        print("3. เทียบ bip39 ของ JS %d แบบ                    ผิด %d  %s"
              % (len(cases), bad, "ผ่าน" if not bad else "ไม่ผ่าน"))
    finally:
        if os.path.exists(JS):
            os.remove(JS)

    # 4) เปลี่ยน passphrase ต้องได้คนละกระเป๋า (พิสูจน์ว่ามันมีผลจริง)
    a = bip32.HDKey.from_seed(bip39.seed(mn, "")).my_fingerprint().hex()
    b = bip32.HDKey.from_seed(bip39.seed(mn, "x")).my_fingerprint().hex()
    c = bip32.HDKey.from_seed(bip39.seed(mn, "X")).my_fingerprint().hex()
    ok = a != b and b != c and a != c
    fails += not ok
    print("4. ว่าง / 'x' / 'X' ได้คนละกระเป๋า  %s %s %s  %s"
          % (a.upper(), b.upper(), c.upper(), "ผ่าน" if ok else "ไม่ผ่าน"))

    # 5) อักขระนอก ASCII ต้องโดนปฏิเสธ — ทำ NFKD ไม่ได้บน MicroPython (รีวิวภายนอก F-02 · 13 ต.ค. 2026)
    mn12 = "abandon " * 11 + "about"
    rej = []
    for pp in ("caf\u00e9", "cafe\u0301", "\u0e17\u0e14\u0e2a\u0e2d\u0e1a", "a\nb", "a\tb"):
        try:
            bip39.seed(mn12, pp)
        except ValueError:
            rej.append(pp)
    try:
        ascii_ok = len(bip39.seed(mn12, " !~Az09")) == 64
    except ValueError:
        ascii_ok = False
    ok = len(rej) == 5 and ascii_ok
    fails += not ok
    print("5. นอก ASCII ปฏิเสธ %d/5 · ASCII ปกติ (รวมช่องว่าง/สัญลักษณ์) ผ่าน %s  %s"
          % (len(rej), ascii_ok, "ผ่าน" if ok else "ไม่ผ่าน"))

    print()
    if fails:
        print("ไม่ผ่าน %d ข้อ" % fails)
        sys.exit(1)
    print("ผ่านทั้งหมด")


if __name__ == "__main__":
    main()

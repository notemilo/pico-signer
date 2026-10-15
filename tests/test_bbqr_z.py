"""BBQr แบบบีบอัด ('Z' = deflate raw wbits 10 + base32) — อ่านได้ตั้งแต่ 2.17.0 (15 ต.ค. 2026)

ทำไม: กระเป๋าอื่น (Sparrow/Coldcard) ส่ง BBQr แบบ Z บ่อย · ถ้าวันไหนต้องใช้แทน wallet เครื่องต้องอ่านได้
แนวคิดจาก SeedSigner (decode_qr.py BBQRPsbtQrDecoder)

เฟรมตัวอย่าง FIXTURE_Z คัดลอกจากชุดเทสของ SeedSigner
(tests/test_decodepsbtqr.py::test_basic_1_in_2_out_bbqr_psbt_qr)
Copyright (c) SeedSigner contributors — MIT License (https://github.com/SeedSigner/seedsigner)
"""
import base64
import os
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import bbqr   # noqa: E402
import psbt   # noqa: E402

FIXTURE_Z = "B$ZP0100FMUE4KXZZ7EHBEUJQGAYDGMXLP2O34WEVGERCKNOQWTY3URDYXHGTXTTHOVHKW6YXZQYEVSN6UGQMEHYB4CP4RI3BJK43MVLSZ7ZRH5R5SB4527A5C6N3LL65GZRPNZZGU2NK332BFLVR7VVKSYTCILLOLCJZ5PGFQGCC2U37YW5J6CTXMW6NHMT533MMPJ3YXQQVGL2ZZ76AADRETFVNCV4MGOMY6GEPPPG5XSZFIOQ6PW2JUFQVDWX5FMIHLHCI3Y23V5WGPPK5OF5GSFOKZI576FTVA5FGM5NNACNMNSAQBLZQZY62PJQS7Q72PQGVTABGZRVEPB4HL5MGCB3SVONS5P7W7BGVVT557AFA33L63OW43GW5BAYVTCMNLH5XCUEDNRF4HXFFLMHCWV25FZM6VQNQFPW2PZWI5MXP3QKHGIKOPMXR6CZGOO6CFSQ42IKN3USTQ44OHX53YYXTSSX74XXZ7ZPFXMRMCDTBDJU3JIJ2Z6ZXJXOK3LD6YHA3NYV4PDUDFR2K2H6RIPZ4BI7V2YOXRXPQY5YJELSQ4EHNXBM6HQX74PC26NXEXI6B7UR6IQMH446CDUR36RHYRKV5DE5ZUUVS5FEIWNKJLGJXHGPK66WGP5YNX3PEW24ZRLTJYAOMEBNXIGEYT2OSSUTLGKFZX7M7VTZUGI5LH5GM6X6PC76XZOO3PM7WV67BCM3D5M3XMAEQBYPJAWRAJZQAMEQA"

fails = 0


def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1


def z_frames(data, type_="P", chunk=600):
    """ทำ BBQr แบบ Z เอง (ฝั่งเครื่องไม่มีตัวบีบ — ใช้ในเทสเท่านั้น)"""
    c = zlib.compressobj(9, zlib.DEFLATED, -10)
    raw = c.compress(data) + c.flush()
    return [p.replace("B$2", "B$Z", 1) for p in bbqr.encode(raw, type_, chunk)]


print("── BBQr Z")
r = bbqr.decode([FIXTURE_Z])
ok = r is not None and r[1] == "P" and r[0][:5] == b"psbt\xff"
check("เฟรม Z ของ SeedSigner ถอดได้เป็น PSBT (%s ไบต์)" % (len(r[0]) if r else "-"), ok)
if ok:
    try:
        p = psbt.PSBT.parse(r[0])
        check("PSBT ที่คลายแล้วผ่านตัวอ่านแบบเข้มของเรา (%d input · %d output)"
              % (len(p.tx.vin), len(p.tx.vout)), True)
    except psbt.PSBTError as e:
        check("PSBT ที่คลายแล้วผ่านตัวอ่านแบบเข้มของเรา: %s" % e, False)

raw = base64.b64decode(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test.psbt")).read().strip())
parts = z_frames(raw, chunk=80)
r = bbqr.decode(parts)
check("Z หลายเฟรม (%d เฟรม) ถอดกลับได้ไบต์ตรง" % len(parts), r is not None and r[0] == raw)
check("Z สั้นกว่า base32 ธรรมดา (%d vs %d เฟรม)" % (len(parts), len(bbqr.encode(raw, "P", 80))),
      len(parts) <= len(bbqr.encode(raw, "P", 80)))

bomb = z_frames(b"\x00" * (bbqr.MAX_INFLATED + 1))
check("zip bomb (%d ไบต์หลังคลาย ส่งมาแค่ %d ตัวอักษร) = ปฏิเสธ"
      % (bbqr.MAX_INFLATED + 1, sum(len(p) for p in bomb)), bbqr.decode(bomb) is None)
check("ขนาดพอดีเพดาน = ผ่าน", bbqr.decode(z_frames(b"\x01" * bbqr.MAX_INFLATED)) is not None)

bad = list(FIXTURE_Z)
bad[40] = "A" if bad[40] != "A" else "B"
r = bbqr.decode(["".join(bad)])
check("Z เสีย 1 ตัวอักษร = None หรือได้ข้อมูลคนละก้อน (ตัวอ่าน PSBT จะปฏิเสธต่อ) ไม่ crash",
      r is None or r[0] != bbqr.decode([FIXTURE_Z])[0])

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails)
    sys.exit(1)
print("✅ test_bbqr_z ผ่านครบ")

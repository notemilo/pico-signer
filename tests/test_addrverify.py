# test_addrverify.py — ตัวตรวจที่อยู่รับเงิน (src/addrverify.py)
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import addrverify as AV, address as addr, bech32, bip32, bip39

MN = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
root = bip32.HDKey.from_seed(bip39.seed(MN))
fails = 0

def check(name, ok):
    global fails
    print(("  ✅ " if ok else "  ❌ ") + name)
    fails += 0 if ok else 1

def expect_bad(text, reason):
    try:
        AV.parse(text)
        return False
    except AV.AddressError as e:
        return e.reason == reason

# ที่อยู่อ้างอิงคำนวณด้วยเส้นทางเต็มจากกุญแจแม่ (คนละวิธีกับตัวค้นที่อนุพันธ์จาก xpub)
def ref_addr(path):
    return addr.script_to_address(addr.p2wpkh_script(root.derive(path).pubkey))

a0 = ref_addr("m/84h/0h/0h/0/0")
print("── 1. อ่านรูปแบบ QR ต่าง ๆ")
spk, clean = AV.parse(a0)
check("ที่อยู่ล้วน", clean == a0 and addr.script_to_address(spk) == a0)
check("ตัวใหญ่ทั้งหมด (QR ชอบใช้)", AV.parse(a0.upper())[1] == a0)
check("bitcoin: URI", AV.parse("bitcoin:" + a0)[1] == a0)
check("BITCOIN: + ?amount=&label=", AV.parse("BITCOIN:" + a0.upper() + "?amount=0.001&label=x")[1] == a0)
check("มีช่องว่าง/ขึ้นบรรทัดหัวท้าย", AV.parse("  " + a0 + "\r\n")[1] == a0)
check("bytes จากสแกนเนอร์", AV.parse(a0.encode())[1] == a0)

print("── 2. ปฏิเสธที่อยู่ที่ไม่ใช่ของกระเป๋านี้")
check("ว่าง", expect_bad("", AV.BAD_EMPTY))
bad_ck = a0[:-1] + ("q" if a0[-1] != "q" else "p")
check("checksum ผิด 1 ตัวอักษร", expect_bad(bad_ck, AV.BAD_NOT_ADDRESS))
check("ตัวเล็กปนตัวใหญ่", expect_bad(a0[:10] + a0[10:].upper(), AV.BAD_NOT_ADDRESS))
check("testnet tb1", expect_bad(bech32.encode_segwit("tb", 0, bytes(20)), AV.BAD_WRONG_NET))
check("taproot bc1p", expect_bad(bech32.encode_segwit("bc", 1, bytes(32)), AV.BAD_NOT_P2WPKH))
check("p2wsh bc1q ยาว", expect_bad(bech32.encode_segwit("bc", 0, bytes(32)), AV.BAD_NOT_P2WPKH))
check("p2pkh 1…", expect_bad("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", AV.BAD_NOT_P2WPKH))
check("p2sh 3…", expect_bad("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", AV.BAD_NOT_P2WPKH))
check("ข้อความอื่น (PSBT)", expect_bad("cHNidP8BAHECAAAAA", AV.BAD_NOT_ADDRESS))

def find(target_addr, account, start=0, count=5):
    spk, _ = AV.parse(target_addr)
    chains = AV.chain_nodes(AV.account_node(root, account))
    for chain, i, cand in AV.candidates(chains, start, count):
        if cand == spk:
            return chain, i
    return None

print("── 3. ค้นหา (อนุพันธ์จาก xpub ต้องได้ตรงกับเส้นทางเต็ม)")
check("account 0 รับ #0", find(a0, 0) == (AV.RECEIVE, 0))
check("account 0 ทอน #3", find(ref_addr("m/84h/0h/0h/1/3"), 0) == (AV.CHANGE, 3))
check("account 1 รับ #4", find(ref_addr("m/84h/0h/1h/0/4"), 1) == (AV.RECEIVE, 4))
check("ที่อยู่ account 1 แต่ค้นใน account 0 = ไม่เจอ", find(ref_addr("m/84h/0h/1h/0/4"), 0) is None)
check("เลข 7 เกินช่วง 0-4 = ไม่เจอ", find(ref_addr("m/84h/0h/0h/0/7"), 0) is None)
check("ค้นช่วงถัดไป 5-9 เจอ #7", find(ref_addr("m/84h/0h/0h/0/7"), 0, start=5) == (AV.RECEIVE, 7))
check("path_str", AV.path_str(2, 1, 9) == "m/84h/0h/2h/1/9")

print()
if fails:
    print("❌ ไม่ผ่าน %d ข้อ" % fails); sys.exit(1)
print("✅ test_addrverify ผ่านครบ")

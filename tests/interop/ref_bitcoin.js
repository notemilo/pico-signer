// ตัวแทน "ของจริง" ฝั่ง JavaScript — ไลบรารีชุดเดียวกับที่ wallet ใช้
//   bitcoinjs-lib · bip32 · tiny-secp256k1 · bip39
// รับคำสั่งเป็น JSON ทาง argv แล้วคืน JSON ทาง stdout ให้ฝั่ง Python เทียบผล
//
// ⚠️ ไฟล์นี้ต้องไม่ import อะไรจากโปรเจกต์ Pico เลย ไม่งั้นไม่ใช่การเทียบข้าม
const bitcoin = require("bitcoinjs-lib");
const ecc = require("tiny-secp256k1");
const { BIP32Factory } = require("bip32");
const bip39 = require("bip39");

const bip32 = BIP32Factory(ecc);
bitcoin.initEccLib(ecc);

const a = JSON.parse(process.argv[2]);
let out;

switch (a.fn) {
  // BIP39: คำ 12/24 คำ (+ passphrase) -> seed 64 ไบต์
  case "seed":
    out = { seed: bip39.mnemonicToSeedSync(a.mnemonic, a.passphrase || "").toString("hex") };
    break;

  // BIP32: seed -> xprv/xpub ที่ path + ที่อยู่ p2wpkh + fingerprint แม่
  case "derive": {
    const root = bip32.fromSeed(Buffer.from(a.seed, "hex"));
    const node = root.derivePath(a.path);
    const { address } = bitcoin.payments.p2wpkh({ pubkey: node.publicKey });
    out = {
      pubkey: Buffer.from(node.publicKey).toString("hex"),
      xpub: node.neutered().toBase58(),
      xprv: node.toBase58(),
      address,
      masterFingerprint: Buffer.from(root.fingerprint).toString("hex"),
    };
    break;
  }

  // ECDSA: เซ็น digest 32 ไบต์ด้วย RFC6979 -> DER
  // (ทั้งสองฝั่งใช้ nonce แบบกำหนดค่าตายตัว ผลจึงต้องเหมือนกัน "ทุกไบต์")
  case "sign": {
    const sig = ecc.sign(Buffer.from(a.digest, "hex"), Buffer.from(a.privkey, "hex"));
    out = {
      compact: Buffer.from(sig).toString("hex"),
      der: Buffer.from(bitcoin.script.signature.encode(Buffer.from(sig), 1)).toString("hex"),
    };
    break;
  }

  // ตรวจลายเซ็นที่ฝั่ง Pico สร้าง ว่าไลบรารีมาตรฐานยอมรับไหม
  case "verify":
    out = {
      ok: ecc.verify(Buffer.from(a.digest, "hex"),
                     Buffer.from(a.pubkey, "hex"),
                     Buffer.from(a.compact, "hex")),
    };
    break;

  // อ่าน PSBT ที่ฝั่ง Pico เซ็นแล้ว -> ให้ bitcoinjs-lib ตรวจลายเซ็นเองทั้งหมด
  // นี่คือด่านชี้ขาด: ถ้าไลบรารีมาตรฐานบอกว่าลายเซ็นใช้ได้และ finalize ออกมาเป็น
  // ธุรกรรมที่ broadcast ได้ แปลว่าโค้ดที่เขียนเองทำงานถูกจริง
  case "validate_psbt": {
    const psbt = bitcoin.Psbt.fromBase64(a.psbt);
    const sigOk = psbt.validateSignaturesOfAllInputs(
      (pubkey, msghash, signature) => ecc.verify(msghash, pubkey, signature));
    psbt.finalizeAllInputs();
    const tx = psbt.extractTransaction();
    out = {
      signaturesValid: sigOk,
      txid: tx.getId(),
      txHex: tx.toHex(),
      vsize: tx.virtualSize(),
      outputs: tx.outs.map(o => ({
        value: o.value,
        address: (() => {
          try { return bitcoin.address.fromOutputScript(o.script); }
          catch { return null; }
        })(),
      })),
    };
    break;
  }

  // สร้าง PSBT ฝั่ง JS แล้วให้ Pico ไปเซ็น (ทิศทางกลับกัน)
  case "make_psbt": {
    const root = bip32.fromSeed(Buffer.from(a.seed, "hex"));
    const node = root.derivePath(a.path);
    const p2wpkh = bitcoin.payments.p2wpkh({ pubkey: node.publicKey });
    // tx เก่าทั้งใบแบบที่ wallet แนบ (nonWitnessUtxo) — Pico เชื่อยอดจากตรงนี้เท่านั้น (12 ต.ค. 2026)
    // output ก่อนหน้า prevVout เป็นของอื่นที่ไม่เกี่ยว · txid จริงคำนวณจาก tx นี้ (ไม่ใช้ a.prevTxid)
    const prev = new bitcoin.Transaction();
    prev.version = 2;
    prev.addInput(Buffer.from(a.prevTxid, "hex").reverse(), 0);
    for (let i = 0; i < a.prevVout; i++) prev.addOutput(Buffer.from("6a", "hex"), 1000 + i);
    prev.addOutput(p2wpkh.output, a.inValue);
    const psbt = new bitcoin.Psbt();
    psbt.addInput({
      hash: prev.getId(),
      index: a.prevVout,
      nonWitnessUtxo: prev.toBuffer(),
      witnessUtxo: { script: p2wpkh.output, value: a.inValue },
      bip32Derivation: [{
        masterFingerprint: Buffer.from(root.fingerprint),
        pubkey: Buffer.from(node.publicKey),
        path: a.path,
      }],
    });
    for (const o of a.outputs) psbt.addOutput({ address: o.address, value: o.value });
    if (a.change) {
      const ch = root.derivePath(a.change.path);
      const chp = bitcoin.payments.p2wpkh({ pubkey: ch.publicKey });
      psbt.addOutput({ address: chp.address, value: a.change.value });
      psbt.updateOutput(psbt.txOutputs.length - 1, {
        bip32Derivation: [{
          masterFingerprint: Buffer.from(root.fingerprint),
          pubkey: Buffer.from(ch.publicKey),
          path: a.change.path,
        }],
      });
    }
    out = { psbt: psbt.toBase64() };
    break;
  }

  default:
    throw new Error("ไม่รู้จักคำสั่ง " + a.fn);
}

process.stdout.write(JSON.stringify(out));

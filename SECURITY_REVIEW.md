# Security review guide

Thank you for looking. This is a hobby signer, but it is meant to hold real keys, so findings of any
size are welcome. Please report vulnerabilities privately (GitHub → Security → *Report a vulnerability*)
rather than in a public issue.

## What the device is

- Raspberry Pi Pico 2 (RP2350, no radio), MicroPython 1.29, custom firmware with two C modules
  (`firmware/usermod_sha512`, `firmware/usermod_secp256k1` → libsecp256k1 v0.8.0).
- **Stateless:** seed in RAM only, never written to flash. Power off = seed gone.
- Single-sig **BIP84 p2wpkh, mainnet only.** Account selectable (`m/84h/0h/<n>h`).
- All data in and out goes through **QR codes**: a UART barcode scanner reads BBQr (base32) frames
  from the online wallet's screen; the device shows BBQr frames back on its LCD.
- The online watch-only wallet is **assumed compromised**: it can send any PSBT, any address, any QR.

## Threat model

In scope:
1. A malicious PSBT that makes the ผู้ใช้ sign something other than what the screen shows
   (hidden outputs, hidden change, fee tricks, wrong account, unsigned-but-looks-signed, etc.).
2. A malicious QR (PSBT, address, SeedQR) that crashes, hangs, or corrupts device state.
3. Key/nonce leakage through faulty or non-deterministic signing.
4. A computer the device is plugged into while a seed is loaded.
5. Mistakes in BIP39 / BIP32 / SeedQR / dice-to-mnemonic that would produce a different wallet
   than the ผู้ใช้'s paper backup.

Out of scope / accepted:
- Physical attacker with lab equipment (power analysis, glitching, decapping). There is no secure element
  and no secure boot.
- Someone holding the device while it is on with a seed loaded (no PIN, by design).
- The barcode scanner module's own firmware.

## Where to look (highest value first)

| File | What it does |
|---|---|
| `src/psbt.py` | BIP174 parse, `describe()` (what the review screen shows), `sign()` |
| `src/ui.py` → `screen_sign`, `screen_scan` | refusal rules and what the ผู้ใช้ must confirm |
| `src/tx.py` | transaction parse/serialize, BIP143 sighash |
| `src/bip32.py`, `src/bip39.py`, `src/hashes.py` | key derivation, PBKDF2/HMAC |
| `src/dice.py`, `src/seedqr.py` | dice → mnemonic (1 bit per roll: odd/even), SeedQR Standard/Compact |
| `src/bbqr.py`, `src/scanner.py`, `src/addrverify.py` | QR input handling |
| `src/secp256k1.py` | routes to libsecp256k1 when present, pure-Python fallback otherwise |
| `firmware/usermod_secp256k1/secp256k1mod.c` | the C bridge (no curve math of its own) |

### Specific questions

1. **Change detection** (`PSBT._owned_keys`, `_is_change_path`, `describe`): can an output be hidden from
   the review (`is_change=True`) while paying anywhere the ผู้ใช้'s wallet will not find?
2. **Input amounts**: amounts come only from `non_witness_utxo` (hash-checked) and must equal
   `witness_utxo`. Any way around this, e.g. via parse quirks in `tx.Transaction.parse`?
3. **Fee cap**: refuse if `fee > 10 %` of total outputs (Coldcard's original formula). Edge cases?
4. **Sighash**: the device always signs `SIGHASH_ALL` and ignores the PSBT's sighash field. Is that enough?
5. **Parsing**: `tx.Transaction.parse` does little bounds checking and relies on Python slicing. Can a
   truncated/odd transaction make `describe()` and `sign()` see different data than a node would?
6. **Dice entropy**: 1 bit per roll from parity. Last word is chosen from the 2^k checksum-valid
   candidates by extra rolls (`dice.last_word_from_rolls`). Is there any bias?
7. **USB**: on entering a real seed, `ui.usb_data_off()` activates a runtime USB device with no
   interfaces and `BUILTIN_NONE`. Is there any remaining way to reach the REPL over USB?
8. **libsecp256k1 bridge**: context is preallocated and never randomized; illegal-argument callbacks are
   replaced so they return instead of aborting. Any misuse of the API?

## Known limitations (no need to report)

- No PIN, no secure boot, no secure element.
- MicroPython cannot reliably wipe immutable `bytes` from RAM; power-off is the real wipe.
- BBQr has no set ID, so frames from two different PSBTs with the same frame count could mix
  (the result fails to parse, or is shown in full on the review screen).
- Dust outputs and multiple change outputs are not warned about yet.
- Pure-Python BIP32/HMAC/PBKDF2 are not constant-time.

## How to run things

```sh
./run_tests.sh          # CPython; interop tests need node (cd tests/interop && npm ci)
```

`tests/test_psbt_attacks.py` lists the PSBT attacks already covered (18 cases).
Firmware build steps are in [README.md](README.md#firmware).

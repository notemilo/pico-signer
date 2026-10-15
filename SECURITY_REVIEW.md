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
1. A malicious PSBT that makes the owner sign something other than what the screen shows
   (hidden outputs, hidden change, fee tricks, wrong account, unsigned-but-looks-signed, etc.).
2. A malicious QR (PSBT, address, SeedQR) that crashes, hangs, or corrupts device state.
3. Key/nonce leakage through faulty or non-deterministic signing.
4. A computer the device is plugged into while a seed is loaded.
5. Mistakes in BIP39 / BIP32 / SeedQR / dice-to-mnemonic that would produce a different wallet
   than the owner's paper backup.

Out of scope / accepted:
- Physical attacker with lab equipment (power analysis, glitching, decapping). There is no secure element
  and no secure boot.
- Someone holding the device while it is on with a seed loaded (no PIN, by design).
- The barcode scanner module's own firmware.

## Where to look (highest value first)

| File | What it does |
|---|---|
| `src/psbt.py` | BIP174 parse, `describe()` (what the review screen shows), `sign()` |
| `src/ui.py` → `screen_sign`, `screen_scan` | refusal rules and what the owner must confirm |
| `src/tx.py` | transaction parse/serialize, BIP143 sighash |
| `src/bip32.py`, `src/bip39.py`, `src/hashes.py` | key derivation, PBKDF2/HMAC |
| `src/dice.py`, `src/seedqr.py` | dice → mnemonic (1 bit per roll: odd/even), SeedQR Standard/Compact |
| `src/bbqr.py`, `src/scanner.py`, `src/addrverify.py` | QR input handling |
| `src/secp256k1.py` | routes to libsecp256k1 when present, pure-Python fallback otherwise |
| `firmware/usermod_secp256k1/secp256k1mod.c` | the C bridge (no curve math of its own) |

### Specific questions

1. **Change detection** (`PSBT._check_claims`, `_owned_keys`, `_is_change_path`, `describe`): can an output be hidden from
   the review (`is_change=True`) while paying anywhere the owner's wallet will not find?
2. **Input amounts**: amounts come only from `non_witness_utxo` (hash-checked) and must equal
   `witness_utxo`. Any way around this, e.g. via parse quirks in `tx.Transaction.parse`?
3. **Fee cap**: refuse if `fee > 10 %` of total outputs (Coldcard's original formula). Edge cases?
4. **Sighash**: the device signs only `SIGHASH_ALL`; a PSBT that sets any other (or malformed) sighash type is refused (`PSBT._check_sighash`). Any case this misses?
5. **Parsing**: `tx.Transaction.parse` does little bounds checking and relies on Python slicing. Can a
   truncated/odd transaction make `describe()` and `sign()` see different data than a node would?
6. **Dice entropy**: 1 bit per roll from parity. Last word is chosen from the 2^k checksum-valid
   candidates by extra rolls (`dice.last_word_from_rolls`). Is there any bias?
7. **USB**: `boot.py` (runs before USB init) activates a runtime USB device with no interfaces and
   `BUILTIN_NONE` unless button B is held; `ui.usb_data_off()` does the same when a real seed is entered
   after a B-held boot. Is there any remaining way to reach the REPL over USB?
8. **libsecp256k1 bridge**: context is preallocated and never randomized; illegal-argument callbacks are
   replaced so they return instead of aborting. Any misuse of the API?

## Fixed after outside review (2026-10-13)

Thanks to the reviewers. Fixed, each with a regression test:

- **Hidden change via a fake extra BIP32 derivation on a real input** (high) — the change-index window now
  counts only input derivations proven by key derivation + script match (`test_psbt_attacks.py` #19).
- USB data now off from power-on via `boot.py` (hold B for dev mode).
- PSBT already carrying a signature for our key / finalized input → refused (#20).
- `crash.txt` no longer stores exception messages; BIP39 errors no longer echo the typed word.
- libsecp256k1 bridge checks the illegal-argument flag after every call; error callback never returns.
- Strict transaction parsing (bounds, canonical varints, no trailing bytes, exact round-trip) — `test_tx_strict.py`.
- BIP39 rejects non-ASCII mnemonic/passphrase (no NFKD available in MicroPython).
- BBQr total size cap (~39 KB) and out-of-memory handling.

## Changed after studying SeedSigner (2026-10-15)

Ideas taken from SeedSigner's `psbt_parser.py` and embit's `sign_with` (both MIT), rewritten for this code base:

- A PSBT that makes a provably false claim about this seed's keys is refused outright (`PSBTLie`) instead of
  the claim being skipped silently (`test_psbt_attacks.py` #21-24).
- One BIP32 derivation per input/output; non-`SIGHASH_ALL` refused (#19, #25).
- "This seed can sign nothing here" is reported before the review screens (#26).
- Per-call cache of intermediate derivation nodes, cleared when the call returns (#27).
- Signed PSBT is exported without non-witness UTXOs, derivations or global xpubs (#28); witness UTXOs are kept
  because the watch-only wallet finalizes this copy on its own (`tests/interop/test_signing_interop.py`).
- BBQr `Z` (raw deflate, wbits 10) is accepted, capped at 48,000 bytes after inflation (`tests/test_bbqr_z.py`).
- Backup quiz after creating a seed and a scan-to-check step after drawing a SeedQR. The quiz uses no randomness:
  decoys are the neighbouring BIP39 words, the answer position is the word index mod 4.

## Known limitations (no need to report)

- No PIN, no secure boot, no secure element.
- App code (`*.py`) lives on the filesystem, not in the firmware image, so the firmware hash does not
  cover it. Freezing the app into the firmware is a possible later step.
- MicroPython cannot reliably wipe immutable `bytes` from RAM; power-off is the real wipe.
- BBQr has no set ID, so frames from two different PSBTs with the same frame count could mix
  (the result fails to parse, or is shown in full on the review screen).
- App code is not frozen into the firmware (see above); someone with physical access and button B can change it.
- Dust outputs and multiple change outputs are not warned about yet.
- Pure-Python BIP32/HMAC/PBKDF2 are not constant-time.

## How to run things

```sh
./run_tests.sh          # CPython; interop tests need node (cd tests/interop && npm ci)
```

`tests/test_psbt_attacks.py` lists the PSBT attacks already covered (20 cases).
Firmware build steps are in [README.md](README.md#firmware).

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
- Someone who has the device while it is off: holding **B** at power-on (or BOOTSEL) gives USB access, and with a
  cable and a minute they can replace the app. The Status screen shows build metadata from `coreid.py`; it does not
  verify the installed app.
- The barcode scanner module's own firmware. It is trusted with the seed: scanning a SeedQR passes the whole seed
  through it. It also obeys its vendor's configuration QR codes (enabled by default; they cannot be disabled over
  UART). Since 2.20.0 the module is kept in command mode outside scan screens and its settings are checked at
  start-up (factory restore if changed), so a configuration QR can only act during a scan and is undone at the next
  start. No fund-loss path is known.

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
- RAM fixes found on hardware (2.17.2-2.17.4): `psbt`, `scanner` and `addrverify` are imported at boot instead of on first
  use (compiling `psbt.py` after a long passphrase entry raised `MemoryError`); the BIP39 word list is kept as one
  byte block plus an offset table (`bip39.WordList`, ~10 KB instead of 68 KB in 2,048 small strings) and released
  after a seed is loaded; the crash screen reuses the app's existing frame buffer. Measured on the board with a
  5.2 KB PSBT, a seed and a long passphrase: lowest free heap during scan → sign → QR was 227 KB.

## Fixed after outside review (2026-10-17, 2.18.1)

Reported privately through GitHub (GHSA-334h-x4f4-34h3) by **kkdao**, with reproductions. Each point was checked
against the code and has a regression test (`tests/test_review_amounts.py`, `tests/test_ui_flows.py`).

- **Review screen cut amounts.** Every body line was cut to 14 characters, so `FEE  ` left 9 digits: a 10 BTC fee
  showed as `FEE  1,000,000`. Amounts now always have a line of their own (sat below 1 BTC, BTC above), are
  checked to fit, and a review that still does not fit is split into pages instead of dropping lines. An amount
  that cannot be shown is refused. The fee also shows its percentage.
- **README install skipped `boot.py`**, so a device built from the README kept USB serial and the REPL from
  power-on. Fixed in the install command.
- **Unknown output scripts** showed only `UNKNOWN SCRIPT 35B`, so two different P2PK recipients looked identical.
  Now refused.
- **Change index**: the review screen shows the change path's chain and highest index (`CHG 1/150`), since change
  can be up to 200 addresses past the highest input and a default gap-limit recovery may not look that far.
- **USB isolation failed open**: if USB could not be switched off, the device warned and still allowed seed
  entry. Seed entry is now blocked.
- Relative timelocks (BIP68) are shown; `witness_utxo` with bytes after the script is refused; `sign()` refuses
  when any input has no previous transaction; PSBT error messages are English and wrapped on screen (they were
  Thai, which the font cannot draw).

An automated audit run (shared by Crypto Guide, on commit b0f909b) was also checked point by point. Fixed: unknown
`PSBT_GLOBAL_VERSION` is refused (2.18.2); relative timelocks (same as above). Not changed, with reasons: plain
`memset()` in the C bridge could be removed by the compiler (to be replaced with a volatile wipe at the next firmware
build; the seed also lives in the Python heap, so anyone with SWD access can read it anyway); SWD is not disabled
(physical access is out of scope, and disabling it on the RP2350 is permanent); RBF is not shown (only the key
holder can sign a replacement); the transaction version is not shown.

## Changed after reading ShieldSigner (2026-10-18, 2.19.0)

From [3rdIteration/seedsigner](https://github.com/3rdIteration/seedsigner) `psbt_parser.py` (read, not run): refuse
OP_RETURN outputs with value, warn on dust outputs (< 546 sat) and on fee rates of about 500 sat/vB or more, and
check that sent + change + fee equals the input total.

## Changed after reading Specter-DIY (2026-10-18, 2.20.0)

From [cryptoadvance/specter-diy](https://github.com/cryptoadvance/specter-diy) (read, not run): scanner control over
UART (settings check and command mode, see the threat model above), not hiding change when inputs this seed cannot
sign are present, and a per-input screen.

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

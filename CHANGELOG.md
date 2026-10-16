# Changelog

The version running on a device is shown on the boot screen and under **Status → A** (with the git commit and
file hashes). The current version is in [`VERSION`](VERSION). Versions: first number = menu or data format changes,
second = new features, third = fixes.

## 2.18.0 — 2026-10-16
- Passphrase entry is a full on-screen keyboard (QWERTY, three pages: `abc`, `ABC`, symbols) instead of one
  character at a time. The joystick moves in four directions; moving past the end of a row continues on the next
  row. A or joystick press types, X deletes, Y finishes, B quits. The selected key is drawn inverted, and the space
  key and typed spaces are drawn as grey boxes.

## 2.17.4 — 2026-10-15
RAM fix found on hardware: an occasional `MemoryError` while scanning a SeedQR right after boot.

- The BIP39 word list is kept as one byte block plus an offset table (`bip39.WordList`) instead of 2,048 separate
  strings: about 10 KB instead of 68 KB on the board, and no heap fragmentation. Lookups use binary search; the list
  is checked on load (2,048 words, sorted, no empty lines).
- Word entry uses the same prefix search instead of scanning all 2,048 words on every key press.
- Tests: `tests/test_wordlist.py`.

## 2.17.3 — 2026-10-15
- The word list is released once a seed is loaded.
- RAM measured on the board along the whole path (seed + long passphrase, 5.2 KB PSBT with a 150-output previous
  transaction): lowest free heap 227 KB.

## 2.17.2 — 2026-10-15
Fix: the device could look frozen after scanning a PSBT.

- Cause (from `crash.txt`): `MemoryError` while compiling `psbt.py` on first use, after a long passphrase entry had
  fragmented the heap. `psbt`, `scanner` and `addrverify` are now imported at boot.
- The crash screen reuses the app's frame buffer; before, it tried to allocate a new 115 KB one, failed silently and
  left the last screen on display.

## 2.17.1 — 2026-10-15
- After a QR set is complete the screen shows `DECODING...` then `READING...`.

## 2.17.0 — 2026-10-15
Ideas taken from reading SeedSigner (`models/psbt_parser.py`) and embit (`psbt.py`), both MIT, rewritten for this
code base.

- **A PSBT that makes a provably false claim about this seed's keys is refused** (`PSBT LIES`): a derivation with this
  seed's fingerprint whose key does not derive, an output that claims this seed but pays elsewhere, or an output that
  pays this seed while naming another fingerprint. Before, such entries were skipped silently.
- One BIP32 derivation per input/output (single-sig); more is refused.
- Only `SIGHASH_ALL` is signed; any other or malformed sighash type is refused.
- "No input can be signed by this seed" is reported before the review screens.
- Review screen shows `IN 3 MINE 1` when other people's inputs are mixed in.
- Backup quiz after creating a seed (word by word, no randomness: decoys are neighbouring BIP39 words).
- Scan-to-check after drawing a SeedQR.
- Passphrase confirmation draws spaces as grey boxes and shows the length; the ready screen shows the previous
  fingerprint when the passphrase changes.
- Signed PSBT is exported without non-witness UTXOs, derivations and global xpubs (about half the QR frames); the
  witness UTXOs stay so a wallet can finalize this copy alone.
- BBQr `Z` (raw deflate) is accepted, capped at 48,000 bytes after inflation.
- Per-call cache of intermediate derivation nodes, cleared when the call returns.

## 2.16.4 — 2026-10-13
Fixes after outside review (see [SECURITY_REVIEW.md](SECURITY_REVIEW.md#fixed-after-outside-review-2026-10-13)).

- Strict transaction parsing (bounds, canonical varints, no trailing bytes, exact round-trip).
- BIP39 accepts ASCII only (MicroPython has no NFKD).
- BBQr total size cap and out-of-memory handling.

## 2.16.3 — 2026-10-13
- USB data is off from power-on (`boot.py`); hold **B** while powering on for development access.

## 2.16.2 — 2026-10-13
- `crash.txt` stores file, line and exception type only (no messages).
- A PSBT already carrying a signature for this seed's key, or a finalized input, is refused.
- The libsecp256k1 bridge checks the illegal-argument flag after every call.

## 2.16.1 — 2026-10-12
- Fixed: change could be hidden with a fake second derivation on a real input (found by an outside reviewer with a
  proof of concept). The change index window now counts only derivations proven by key derivation and script match.

## 2.16.0 — 2026-10-12
- First public release. Elliptic-curve math moved to libsecp256k1 v0.8.0 (custom firmware).

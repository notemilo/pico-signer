# Making a seed with dice

Pico Signer never uses the chip's random number generator. Every bit of a new seed comes from a die you roll
yourself, and you can check every word by hand.

Thai version: [DICE.th.md](DICE.th.md)

## What you need

- One six-sided die
- A pen
- The roll sheet: [docs/dice-roll-sheet.html](docs/dice-roll-sheet.html) (print it on A4; page 1 is for 24 words,
  page 2 for 12 words)
- The word table: [docs/dice-word-table.html](docs/dice-word-table.html) (4 pages, printable) or
  [docs/dice-word-table.md](docs/dice-word-table.md) (searchable)

## How it works

Each roll gives one bit: **odd (1, 3, 5) = 1** and **even (2, 4, 6) = 0**. A fair die has three odd and three even
faces, so each bit is a fair coin flip.

Eleven rolls make one word. Written left to right, the 11 bits are the word's position in the BIP39 English word
list in binary: `00000000000` is word #1 `abandon` and `11111111111` is word #2048 `zoo`. Nothing is hashed or
changed on the way, which is why the paper table gives exactly the same words as the device.

| Seed | Rolls | How |
|---|---|---|
| 24 words | 256 | 23 words × 11 rolls, then 3 rolls for the last word |
| 12 words | 128 | 11 words × 11 rolls, then 7 rolls for the last word |

The last word also carries a checksum, so it cannot be any word: the device works out which words are valid and
your last rolls pick one of them. For 24 words there are 8 valid last words and your 3 rolls choose one
(`000` = #1 … `111` = #8). For 12 words there are 128, and your 7 rolls choose one.

## Step by step

1. On the device: **New seed** → **24 words** (or **12 words**). USB data is switched off before the first roll.
2. Roll the die. Press **A** if it shows 1, 3 or 5, and **B** if it shows 2, 4 or 6. Write the same digit (1 or 0)
   in the next box of the roll sheet. **X** deletes the last roll.
3. The screen shows the bits of the word you are on. After every 11 rolls the finished word appears under `DONE` (the last three words are shown).
   Look the 11 bits up in the word table and check it is the same word.
4. After the last rolls the device shows the last word and which choice your rolls picked
   (for 24 words it also lists all 8 choices). Check it against the roll sheet.
5. Write all the words on your backup in order. **Show again** lets you read them again before you continue.
6. Choose **USE SEED**. You can then take a short quiz that asks each word against your paper (B skips it).

## Keep it safe

- **The roll sheet is your seed.** Anyone who sees it can rebuild your wallet. Fill it in privately, never take a
  photo of it, and destroy it once the words are on your backup.
- After you choose USE SEED the device no longer lists the words (there is no PIN, so this keeps someone who picks
  up a running device from reading them; only the SeedQR backup screen remains). Write them down before that step.
- The device does not judge your rolls. Real dice, entered as rolled, are random.

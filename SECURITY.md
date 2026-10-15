# Security policy

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability**
(https://github.com/notemilo/pico-signer/security/advisories/new). Do not open a public issue for anything that
could cost someone funds.

Useful to include: the version (`VERSION`, also shown on the device under Status → A), the file and line, and a
PSBT or QR that reproduces it if you have one. Findings of any size are welcome, including "this looks wrong but I
am not sure".

This is a one-person hobby project, so there is no bug bounty and no fixed response time. Reports are read; fixes
go out as a new version with a regression test and are listed in [CHANGELOG.md](CHANGELOG.md).

## Supported versions

Only the latest release is supported. Older versions do not get fixes.

## Scope

What is in and out of scope, the threat model and the parts most worth reviewing are in
[SECURITY_REVIEW.md](SECURITY_REVIEW.md). Known limitations (no PIN, no secure boot, no secure element, app code
outside the firmware image) are listed there and do not need to be reported.

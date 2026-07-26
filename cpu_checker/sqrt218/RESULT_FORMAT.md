# Sqrt218 CPU result record

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

`sqrt218_cpu_checker_v2 CERTIFICATE RESULT` writes exactly one 120-byte result
record. The command reads the certificate completely into a private owned
allocation, closes the input, treats that allocation as immutable for the
entire validation, and invokes only `tg_sq218_validate_bytes_v2`. The result
buffer is separate from the input allocation. SHA-256 is computed directly
over that same allocation before it is freed; the command never reopens the
certificate path to obtain the digest.

The output path is created with exclusive-create semantics. The command never
overwrites an existing file, symlink, hard link, or the certificate path.
Exit status zero means both that the production-profile certificate was
accepted and that the complete result record was written and synchronized.
Exit status 2 means that a canonical rejection record was written. Every
other nonzero exit is an invocation or I/O failure and must be treated as no
result. If writing, synchronization, or close fails, the command unlinks the
newly created result path.

| Exit | Meaning |
|---:|---|
| 0 | accepted and synchronized 120-byte record written |
| 2 | rejected and synchronized 120-byte record written |
| 64 | command-line usage error |
| 65 | input snapshot/read error |
| 73 | exclusive output creation failed |
| 74 | output write, synchronization, or close failed |

All multi-byte integers are unsigned big-endian:

| Offset | Width | Field |
|---:|---:|---|
| 0 | 8 | magic `53 51 32 31 38 52 32 00` (`SQ218R2\0`) |
| 8 | 2 | result-format version, exactly `1` |
| 10 | 2 | record width, exactly `120` |
| 12 | 4 | exact `tg_sq218_status` returned by the byte-level checker |
| 16 | 8 | number of bytes in the owned input snapshot |
| 24 | 8 | final next-event index |
| 32 | 8 | final event value |
| 40 | 8 | weighted-upper accumulator, high limb |
| 48 | 8 | weighted-upper accumulator, low limb |
| 56 | 8 | psi-lower accumulator, high limb |
| 64 | 8 | psi-lower accumulator, low limb |
| 72 | 8 | endpoint-anchor slack, high limb |
| 80 | 8 | endpoint-anchor slack, low limb |
| 88 | 32 | SHA-256 of the exact owned input snapshot |

Status zero is `TG_SQ218_OK`; only then are the state and slack fields
populated. For every rejection status, bytes 24 through 87 are exactly zero.
Readers must reject records with the wrong magic, version, width, length, or
an unknown status. The SHA-256 field is populated for both acceptance and
rejection records.

The complete status encoding is:

| Value | Meaning |
|---:|---|
| 0 | accepted (`TG_SQ218_OK`) |
| 1 | bad wrapper/checker argument |
| 2 | malformed or wrong-profile certificate |
| 3 | record or section index outside its declared range |
| 4 | checked arithmetic overflow or underflow |
| 5 | mathematical certificate condition rejected |

This record deterministically binds the checker outcome to the digest of the
exact bytes the checker saw, but it is not itself an authenticated receipt.
The measured runner must commit these exact 120 bytes—without field
reserialization—together with the measured executable identity and
invocation/profile data in the signed confidential-compute receipt. The
receipt layer's canonical ASCII exact-hex envelope must therefore encode all
240 hexadecimal digits of this record. Receipt construction, signing, and
Lean registration are intentionally outside this narrowly scoped command.

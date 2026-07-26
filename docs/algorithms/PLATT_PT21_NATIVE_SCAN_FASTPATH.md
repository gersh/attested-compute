# PT21 qualification-only native packet-scan fast path

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

This component accelerates the two scalar Python loops at the start of the
PT21 native-record adapter. It does not replace the reference adapter, does
not change `PT21BLK1`, and does not establish any analytic fact. Selection is
explicit through `adapt_block_native_scan_fastpath`; manifest, shard, and
production entry points still call the ordinary Python `Fraction` path.

The fast path has two independently implemented halves:

- `reference/tg_platt_pt21_packet_scan_fastpath.cpp` validates one complete
  `PT21SGN1` packet, recomputes its two versioned wire checksums and every DD
  sign guard, scans all three source ranges, and emits `PT21FSC1`;
- `tg_verifier/platt_pt21_native_scan_fastpath.py` rechecks the fixed packet
  and certificate framing, SHA-256 commitments, every DD/sign relationship,
  both wire-checksum fields in its exported standalone validator, and the
  complete event/candidate lists with vectorized outward binary64 and exact
  `Fraction` fallback.

The version-1 checksum recurrence is exactly

```text
h[0]   = 0x14650fb0739d0383
h[i+1] = ((h[i] XOR byte[i]) * 0x00000100000001b3) mod 2^64
```

The field was historically named FNV-1a in the implementation, but its offset
basis is not the standard FNV-1a-64 basis. It is therefore a nonstandard,
versioned FNV-family wire checksum. It provides only redundant corruption
detection beside the complete SHA-256; it is not a cryptographic commitment.
Changing the basis or recurrence without introducing a new packet/certificate
wire version is forbidden.

The performance path may skip only the second, scalar-Python checksum pass in a
private helper after the certificate has been received directly from the
identity-pinned sealed scanner, which has already recomputed both fields. The
exported standalone validator always recomputes them. A forged-header KAT
updates every unkeyed SHA-256 in a certificate after changing one checksum
field and confirms that this strict validator still rejects it.

The Python adapter then uses the already rechecked lists only to avoid its two
O(25,741) scalar loops. Exact endpoint fractions, source-trace validation,
stationary-resolution binding, exact Turing arithmetic, the complete v2
artifact validation, source-height handling, and `PT21BLK1` encoding remain
the existing Python implementations.

## Why GMP is required

`__int128` cannot cover the accepted packet language:

| accepted value | exact rational size |
|---|---:|
| smallest positive binary64 subnormal | denominator `2^1074` (1,075-bit representation) |
| largest finite binary64 value | 1,024-bit integer numerator |

Moreover, stationary and Turing JSON fields accept canonical integers bounded
by file size rather than 64- or 128-bit magnitude. The native scanner does
not parse those JSON rationals; the exact Python Turing tail remains in place.
For packet comparisons the scanner uses outward binary64 first and GMP
`mpq_class` only for undecided triples. The independent checker uses NumPy
outward operations and Python `Fraction` for its own undecided triples.
Neither implementation assumes that intervals at different precisions nest.

`arithmetic_range_report()` exposes these bounds as a machine-readable audit.

## `PT21FSC1`

The nonterminal certificate begins with a 192-byte little-endian header:

| offset | bytes | field |
|---:|---:|---|
| 0 | 8 | magic `PT21FSC1` |
| 8 | 4 | version `1` |
| 12 | 4 | header bytes `192` |
| 16 | 4 | endian tag `0x01020304` |
| 20 | 4 | exact GMP fallback count |
| 24 | 8 | input packet bytes |
| 32 | 8 | source window center |
| 40 | 4 | sample count `25,741` |
| 44 | 4 | same-sign triple count |
| 48 | 12 | direct-event counts: main, left flank, right flank |
| 60 | 12 | stationary-candidate counts in the same order |
| 72 | 8 | body bytes |
| 80 | 8 | recomputed sample version-1 wire checksum |
| 88 | 8 | recomputed sign version-1 wire checksum |
| 96 | 32 | complete `PT21SGN1` SHA-256 |
| 128 | 32 | body SHA-256 |
| 160 | 32 | domain-separated header-prefix-plus-body SHA-256 |

The body contains signed 32-bit offsets, grouped first by all three direct
lists and then by all three stationary lists. Counts determine its exact
length. The checker rejects trailing data, non-increasing offsets, offsets
outside their fixed stream, any digest mismatch, or any difference from its
independent complete replay.

`--stream` adds ordered `PT21FSQ1` request and `PT21FSR1` response framing so
one pinned process can serve many packets. Request IDs, exact lengths, packet
SHA-256, response SHA-256, and EOF are checked on every transition.

## Executable identity and mutation resistance

The Python launcher:

1. opens the source path with `O_NOFOLLOW`;
2. hashes the bytes and compares the caller-supplied SHA-256;
3. copies exactly those bytes into a new `memfd`;
4. hashes the copied image independently;
5. applies `F_SEAL_WRITE`, `F_SEAL_GROW`, `F_SEAL_SHRINK`, and `F_SEAL_SEAL`;
6. executes `/proc/self/fd/N`, passing only that sealed descriptor.

Both the source-path digest and executed sealed-image digest are exposed in
`NativeScannerIdentity`. A known-answer test mutates the same source inode
after pinning and confirms that the sealed image remains executable and emits
the original certificate. Platforms without sealing fail closed; there is no
mutable-file fallback.

The scanner identity is not added to the unchanged 320-byte `PT21BLK1`.
Consequently this route remains qualification-only. A future production
integration would need to bind the scanner image and `PT21FSC1` version into
the measured execution recipe or retained receipt.

## Bounded verification and benchmark

Build and run:

```bash
cmake --build build/dgx-spark --target \
  sparkinterval-tg-platt-pt21-native-scan-fastpath

ctest --test-dir build/dgx-spark --output-on-failure \
  -R '^tg_platt_pt21_native_scan_fastpath_known_answers$'
```

Repeatable cold, one-shot, persistent, validation-only, and full-tail timing
is provided by:

```bash
python3 tools/benchmark_tg_platt_pt21_native_scan_fastpath.py \
  --required-sign-packet REQUIRED.bin \
  --stationary-trace STATIONARY.json \
  --turing-inputs TURING.json \
  --worker MEASURED_WORKER \
  --native-scanner \
    build/dgx-spark/sparkinterval-tg-platt-pt21-native-scan-fastpath \
  --expected-native-scanner-sha256 SCANNER_SHA256 \
  --iterations 13
```

The KAT covers byte-for-byte source trace, v2 artifact, and `PT21BLK1`
equivalence; all three stream boundaries; positive and negative stationary
cases; a half-ulp exact fallback; minimum subnormal and maximum finite inputs;
a greater-than-128-bit dyadic Turing tail; wrong executable identity;
symlinks; same-inode mutation; packet, sign, wire-checksum, body, digest,
length, and offset tampering; standalone forged-checksum certificates; and
repeated ordered persistent requests. The same suite passes AddressSanitizer
plus UndefinedBehaviorSanitizer.

On the local 20-core aarch64 DGX Spark CPU on 2026-07-26, 13 interleaved
repetitions of bounded block zero gave:

| measurement | median | min | max / p95 |
|---|---:|---:|---:|
| reference adapter, full artifact/Turing/`PT21BLK1` | 80.61 ms | 77.68 ms | 83.25 ms |
| one-shot fast path, full artifact/Turing/`PT21BLK1` | 8.30 ms | 6.60 ms | 10.46 ms |
| one-shot sealed copy + process + native certificate | 7.34 ms | 4.71 ms | 7.86 ms |
| persistent native certificate round trip | 3.37 ms | 3.30 ms | 3.43 ms |
| persistent private trusted-scanner semantic replay | 1.19 ms | 1.04 ms | 1.48 ms |
| strict standalone Python validation, including both checksum passes | 37.71 ms | 37.41 ms | 38.44 ms |
| persistent full artifact/Turing/`PT21BLK1` | 5.51 ms | 5.40 ms | 5.74 ms |

The measured cold one-shot path was 14.81 ms and persistent session startup
was 0.32 ms. The one-shot median speedup was 9.71x and the persistent full path
was 14.62x relative to the reference median. The full rows include exact
artifact and Turing reconstruction and final record encoding, not only packet
scanning. The 37.71-ms strict row quantifies the redundant scalar-Python
checksum cost paid by callers of the exported standalone validator; it is
deliberately not paid a second time by a certificate received directly from
the pinned sealed scanner. Isolated rows were measured in separate phases and
are not intended to sum to the separately interleaved end-to-end median.

These are qualification timings for repeated synthetic block zero, which has
no stationary resolutions. They show that the scalar adapter bottleneck can
be removed; they do not provide a valid PT21 campaign ETA. There is no H100
measurement, full-range run, analytic realization, source-scale receipt, or
production integration.

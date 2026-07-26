# Formulaic Dirichlet q-major target cursor

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

The optimized all-character transform needs every ordinate for one modulus
to remain contiguous in the `TGDQORD1` component-signature order. The source
Hurwitz lattice, however, is stored once in eight t-major archives. A
materialized interface would require 56,981,100 JSON controls and as many
per-target job and receipt paths before any analytic result was obtained.

`tg_verifier.dirichlet_formulaic_qmajor_cursor` replaces that control roster
with a deterministic cursor. Its complete state is:

- the externally hash-bound `TGDQORD1` manifest;
- the eight gap-free t-lane ranges;
- one execution-q index, lane index, and next ordinate;
- exact aggregate counters; and
- a streaming SHA-256 target chain.

For each scheduled modulus with `r` ordinates, the cursor emits consecutive
targets of at most 64 ordinates. A target never crosses an archive lane
boundary. Every internal source lane boundary is divisible by 64, so this
does not add partial batches. Compressed accounting independently sums the
same per-q/per-lane ceilings without enumerating the targets.

The exact primitive-V2 source result is:

| Quantity | Exact value |
|---|---:|
| scheduled primitive moduli | 292,500 |
| q/ordinate row references | 3,637,613,167 |
| bounded targets | 56,981,100 |
| serialized per-target controls required | 0 |

The per-lane target counts are

```text
4,095,000  3,510,000  4,095,000  3,510,000
4,387,802  5,051,668  8,203,438  24,128,192
```

These counts are pinned independently and checked by the full-source
accounting command:

```bash
python3 tools/tg_dirichlet_formulaic_qmajor_cursor.py \
  --pretty source-accounting
```

Tests expand bounded schedules and compare every `(q,t)` pair with a direct
oracle. They also reject gaps, overlaps, reordered lanes, internal boundaries
that split a canonical batch, target substitution, duplicate acceptance,
truncated finalization, and Boolean-as-integer values.

The independent C++20 implementation in
`gpu/include/sparkinterval/tg_dirichlet_formulaic_qmajor.hpp` is the reusable
cursor intended for the compiled executor. Its known-answer test uses the
same nonmonotone four-q schedule as Python and requires identical
little-endian target SHA-256 values and the identical final streaming chain.
It separately rejects substituted targets, truncation, duplicate
finalization, lane gaps, and misaligned boundaries.

`SparkInterval.Dirichlet.FormulaicQMajorCursor` proves without
`native_decide` that every in-range ordinate belongs to exactly one quotient
batch, every target is nonempty and at most 64 rows, the nonempty target
indices are exactly `0 .. ceil(rowCount/64)-1`, and aligned lane boundaries
cannot be crossed. The executable-byte/parser refinement remains separate.

On 2026-07-25, three C++20 runs expanded and hash-chained the complete
56,981,100-target source geometry in `40.8755`, `41.0562`, and `41.4225 s`
on the local 20-core AArch64 DGX Spark CPU, using one sequential thread. The
median is
`1.388 million targets/s`. The timing includes compressed-accounting
validation and a fresh SHA-256 link for every target; it performs no lattice,
factor, CUDA, FFT, or zero work and is therefore a cursor microbenchmark, not
campaign evidence. Even without parallelizing the cursor, its full-roster
cost is under one minute and is no longer a meaningful part of a multi-day
campaign estimate.

```bash
sparkinterval-tg-dirichlet-formulaic-qmajor-benchmark \
  /tmp/TGDQORD1-source.bin
```

## Bounded compiled integration

The seeded CUDA runner now has a descriptor-free bounded service mode:

```bash
sparkinterval-tg-dirichlet-largeq-seeded \
  --formulaic-qmajor-service \
  SEEDS SEED_SHA256 TGDQORD1 PLAN_SHA256 SUMMARY_JSON DEVICE \
  --allow-prefix-kat \
  < TGDQMS_STREAM > TGDAFFI1_STREAM
```

`--allow-prefix-kat` is a test-only concession for a structurally valid seed
prefix. Without it, the existing seeded runner still requires the complete
recovery-seed range. The compiled service accepts only a bounded `TGDQORD1`
classification. It independently parses the schedule, verifies primitive-V2
membership and canonical component-signature execution order, and rejects a
full-source schedule.

`tg_verifier.dirichlet_formulaic_qmajor_service` writes and independently
replays the compact stream. The version-1 wire is:

| Record | Magic | Fixed bytes | Contents |
|---|---|---:|---|
| service header | `TGDQMSH1` | 288 | bounds, lane count, exact fixed geometry, six source identities |
| lane | none | 16 | canonical lane index and half-open t range |
| target frame | `TGDQMSQ1` | 208 | actual q/t target, component/order/value geometry, three bindings |
| lattice row | `TGDLTMR1` | 64 + 1 MiB | exact t index, payload size, payload SHA-256, interval payload |
| factor | none | 32 per row | directed complex interval |
| Taylor tail | none | 8 per row | finite nonnegative radius |
| footer | `TGDQMSF1` | 168 | exact counts, target chain, frame-stream digest |

A frame contains from 1 through 64 consecutive rows and cannot cross a lane
boundary. No canonical CRT descriptor and no per-target JSON control occurs
on this wire. On an actual-q transition, the runner reconstructs the
canonical descriptors from q, verifies the expected group order, and caches
the device descriptor table. Consecutive targets for the same q reuse it.
The runner emits the unchanged `TGDAFFI1` framing expected by the existing
scheduled all-character CUDA service.

Plan identity is the SHA-256 of the exact Python canonical plan encoding, not
the hash of the raw schedule-manifest bytes. The compiled service reconstructs
that canonical encoding from its independently parsed schedule, lane table,
q slice, and batch bound, then requires the result to equal both the CLI pin
and the stream header. Python and C++ pin the fixed answer
`03b5f39b9dec5e9518c1283d9d46208f3a7464b16db084d96ae4e8c9c72854b1`
for their shared nonmonotone known-answer plan. They also pin target chain
`a53afecd88edf8d5502427d53945d41192de64a7d55c07cbdbf70311b7431e2b`.

Transport authentication deliberately keeps two different digests:

- `input_stream_sha256` covers every input byte, including the service header,
  lane table, frames, and footer;
- `frame_stream_sha256` covers only target headers, row records, factors, and
  tails, and is committed by the footer.

The row and sidecar binding domain strings include their terminating NUL in
both Python and C++. The pre-existing target and cursor-chain domain strings
exclude it. This distinction is pinned rather than left to language defaults.
Row and sidecar hashes authenticate transport relative to externally pinned
source identities; they are not signatures and do not establish the analytic
semantics of those sources.

## Bounded CUDA known answer

The real-CUDA KAT uses the nonmonotone execution order
`10080, 18480, 11088, 10001`, two ordinates per q, and one row per frame. It
checks all of the following:

- the operating-system pipeline from the formulaic seeded runner, through the
  bounded stream tee, into the existing scheduled all-character CUDA runner;
- exact schedule, plan, target-chain, raw-input, frame-stream, and output
  digests;
- four descriptor reconstructions/uploads for eight targets and zero
  descriptor input bytes;
- byte-for-byte equality with the concatenation of eight legacy one-shot
  `TGDLQB2` seeded outputs built from identical canonical descriptors,
  factors, rows, and tails;
- an independent exact-`Fraction` replay of selected directed binary64 CUDA
  outputs, optional pinned-Arb factor containment, and MPFR replay of every
  all-character output frame; and
- fail-closed q substitution, truncation, and externally pinned raw-stream
  mutation attacks.

These are bounded implementation known answers using synthetic lattice rows
and deliberately wide finite factors. They are not analytic or campaign
evidence.

## Scaling boundary

This service removes the 56,981,100 serialized controls and repeated CRT
descriptor transport, but q-major execution still rereads and transfers every
referenced physical row. A hypothetical source run would therefore reread and
upload exactly 3,637,613,167 one-MiB rows:

```text
3,637,613,167 × 1,048,576
  = 3,814,313,864,200,192 bytes
  ≈ 3.81 decimal PB
  ≈ 3.39 PiB
```

It does not preserve the current t-major path's one upload per physical row
and is not the economical production solution to reuse the roughly 125-GiB
source lattice cache. The bounded
[resident q-major phase](DIRICHLET_RESIDENT_QMAJOR_PHASE.md) now demonstrates
the one-upload seam for at most 64 unique rows and 64 active q targets. Scaling
that seam to the source still requires source-sized authenticated phase
transport, device qualification, and persistent downstream FFT/sign state.

A more concrete candidate keeps q-major result order while making t shards
resident across eight H100s. The unbatched-butterfly-balanced t cuts are

```text
0, 768, 1600, 2368, 3200, 4032, 5568, 9600,
49088, 88512, 127988
```

The earlier two-way split of the last slot had a known
payload-plus-buffer estimate of about 76.25 GiB. That left only about
3.75 GiB on an 80-GiB device before the CUDA context, fragmentation, and
downstream state, so it was not a defensible fit claim. The current
conservative candidate splits slot 7 into three sequential phases:
`[9600,49088)`, `[49088,88512)`, and `[88512,127988)`. This gives ten
phases, a maximum of 39,488 resident rows (38.5625 GiB of row payload), and
the same approximately 125-GiB total unique lattice. The canonical candidate
report SHA-256 is
`eae086771356cc3e2cc26780012686fdbc3a8097aa76a3417056fe74f5a32eb6`.
This remains a sizing/design candidate only: the bounded resident-phase seam
does not accept the source schedule or execute these source shards, and no
H100 source fit or run is claimed.

No source spool population or source-stream production operator is included;
the Python writer exposes bounded row/sidecar provider callbacks only. A
streaming stdout consumer may receive a prefix before a later frame or footer
failure, so a supervisor must discard every capture lacking a successful
terminal summary and must bind the input to an external writer-receipt hash.
Independent replay is intentionally bounded to 256 MiB.

All source-scale, production, attestation, completed-\(L\), zero-completeness,
Turing, and external-atom flags remain false. No source schedule was executed,
no source lattice archive was populated, and no theorem or external atom is
claimed by this integration.

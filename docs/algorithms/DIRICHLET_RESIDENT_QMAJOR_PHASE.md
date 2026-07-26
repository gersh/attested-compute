# Bounded resident q-major phase

`tg_verifier.dirichlet_resident_qmajor_phase` and the
`--resident-qmajor-phase` mode of
`sparkinterval-tg-dirichlet-largeq-seeded` implement a bounded executable
seam between the existing t-major row transport and formulaic q-major target
reconstruction. One contiguous t shard is authenticated, serialized, and
uploaded once. Every active scheduled q is then run against the resident
shard in the schedule's authenticated execution order.

This is a finite KAT component, not a source executor. It accepts only bounded
`TGDQORD1` schedules, at most 64 unique rows, at most 64 active targets, at
most 256 schedule records, at most \(2^{24}\) output values, and at most
80 MiB of input. The derived output cap is 536,875,520 bytes: \(2^{24}\)
complex intervals plus 64 output headers. Source execution, an H100
source-phase fit, production execution, attestation, completed-\(L\)
validation, zero completeness, and external-atom discharge are all
explicitly false.

## Formulaic target reconstruction

For execution record \(i\), with scheduled row count \(R_i\), phase range
\([a,b)\), and phase number \(p\), the Python writer, independent Python
replay, and C++ worker derive

```text
active_stop = min(R_i, b)
inactive    = active_stop <= a
target      = (i, q_i, p, a, active_stop, active_stop - a)
```

Inactive q values are omitted. Active targets appear once in canonical
execution-q order. A phase whose last row is unused by every selected q is
rejected. Canonical component orders, reduced residues, group order, and CRT
descriptors are reconstructed from the actual q; no descriptor or JSON
control roster is carried on the phase wire.

## Binary wire

All integers are little-endian. Fixed structure sizes are compile-time
asserted in C++ and import-time asserted in Python.

| Record | Magic | Bytes | Contents |
|---|---:|---:|---|
| Phase header | `TGDQRPH1` | 384 | bounds, phase/q/t geometry, exact sizes, and eight SHA-256 bindings |
| Row header | `TGDLTMR1` | 64 | contiguous t index, one-MiB payload size, and payload SHA-256 |
| Row payload | — | 1,048,576 | one canonical Hurwitz lattice row |
| Target header | `TGDQRPQ1` | 144 | reconstructed target identity, q geometry, exact sidecar sizes, target and sidecar hashes |
| Factors | — | 32 per active t | four finite ordered interval endpoints |
| Tails | — | 8 per active t | finite nonnegative Taylor-tail radius |
| Footer | `TGDQRPF1` | 216 | exact counts, upload counts, target chain, row/target stream hashes |

The exact file size is derived from the header, row count, target sidecars,
and footer, then checked against both the declared size and the 80-MiB cap.
The row payload occurs once even when several q targets reference it.

The phase-plan digest is

```text
SHA256(
  "TG_DIRICHLET_RESIDENT_QMAJOR_PHASE_PLAN_V1"
  || schedule_manifest_sha256
  || schedule_execution_order_sha256
  || LE64(start_q_index)
  || LE64(stop_q_index)
  || LE32(phase_index)
  || LE32(first_t_index)
  || LE32(t_index_stop_exclusive)
  || LE32(64)
  || LE32(64)
)
```

The domain above has no terminating NUL. Target identities retain the
formulaic-q-major target domain and packed
`<QIIIII>` identity. The target chain is seeded by the phase-plan digest and
advanced by each canonical target. Row and sidecar bindings include their
C++ string-literal NUL and bind, respectively:

```text
row binding:
  domain || lattice_source_sha256 || phase_plan_sha256
  || each (LE64(t_index) || row_payload_sha256)

sidecar binding:
  domain || sidecar_source_sha256 || phase_plan_sha256
  || packed_target || factors || tails
```

Separate row-stream, target-stream, and whole-input hashes bind exact wire
bytes. The CLI additionally requires external phase-plan and input SHA-256
pins.

## Fail-closed execution

The worker performs a complete file preflight before selecting CUDA or
writing output: regular-file and byte caps, external input hash, schedule and
seed bindings, independently recomputed phase plan, target reconstruction,
all row/sidecar validity and hashes, target chain, footer, exact accounting,
and absence of trailing bytes.

After device selection and before allocation, `cudaMemGetInfo` must satisfy

```text
known allocations + 512 MiB safety reserve <= free device memory
```

Known allocations include the recovery seeds, resident lattice, largest
descriptor table, factors, tails, and largest result buffer. The summary
records the measured free bytes and computed allocation bytes. Failure
creates neither output bytes nor a summary. During execution the worker
rehashes the entire input before publishing the terminal summary.

As with the other streaming modes, stdout can contain a valid prefix if a
late device or output failure occurs. A supervisor must accept a capture only
with a successfully published, independently replayed terminal summary.

## Known-answer equivalence

The real-CUDA KAT uses the nonmonotone execution order
`10080, 18480, 11088, 10001`, two shared rows, and four targets. It checks
three byte-identical output paths:

1. the resident phase;
2. the row-repeated formulaic q-major service;
3. four concatenated legacy `TGDLQB2` seeded executions.

The resident artifact is 2,098,776 bytes; the row-repeated formulaic artifact
is 8,390,744 bytes. Reusing the two rows saves exactly 6,291,968 bytes
(75.0%) in this fixture. A 2026-07-25 NVIDIA GB10 run measured 1,481,470 ns
for the resident kernels and 1,295,646 ns for the row-repeated kernels
(ratio 1.1434); these are one-run KAT observations, not an H100 measurement or
a speedup claim. The exact shared output SHA-256 was
`deb868eb9f3ced5e5275df24ca40bd0158e3b7b860c6165d5b4f3935ad6a041e`.
The pinned phase-plan SHA-256 is
`408b16760a74a8e95e1021e2a3758cbe1d2370865b7c6e3d8b4912b870140fed`,
and the pinned resident input SHA-256 is
`1e476abf96895db74abf6c04f9b70cc8491c605215320f1ef2c1040a6df5c2aa`.
Compiled attacks mutate a row, truncate the input, substitute q, and alter the
phase plan; each is rejected before stdout or summary creation.

## Source-plan boundary

The separately pinned conservative source candidate has ten phases with cuts

```text
0, 768, 1600, 2368, 3200, 4032, 5568, 9600,
49088, 88512, 127988
```

Slot 7 runs `[9600,49088)`, `[49088,88512)`, and `[88512,127988)`
sequentially. The maximum candidate shard is 39,488 rows. Its report SHA-256
is
`eae086771356cc3e2cc26780012686fdbc3a8097aa76a3417056fe74f5a32eb6`.
Those shards exceed this seam's 64-row cap. The candidate is resource
planning metadata for this bounded seam. A separate
[source-shaped stream candidate](DIRICHLET_RESIDENT_QMAJOR_STREAM.md) now
implements the larger wire/executor boundary, but has not executed a source
phase or integrated the semantic/sign reducer. No device-fit claim, H100
source run, zero closure, or source completion follows from either bounded
KAT.

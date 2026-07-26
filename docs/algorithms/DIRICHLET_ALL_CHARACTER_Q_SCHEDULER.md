# Primitive-V2 all-character q-order scheduler

Copyright (c) 2026 Gershon Bialer. All rights reserved.

## Purpose and trust boundary

The all-character transform for one modulus is independent of every other
modulus. The old persistent service nevertheless required increasing `q`.
That convention caused the exact 512-MiB split cache to regenerate
`5,153,638,792` order-specific directed enclosures after eviction.

The scheduler changes only the order in which complete q groups are sent to
the same transform. Every `TGDAFFI1` and `TGDAFFO1` frame still carries its
actual q, canonical component orders, exact ordinate, and value count. No q,
character, ordinate, or interval is renamed or merged.

This component proves operational coverage and cache accounting. It does not
prove that input intervals contain the intended analytic values, refine CUDA
to SASS, isolate zeros, establish a Turing count, or discharge Platt's
Theorem 7.1.

## Deterministic permutation

For q, form its canonical cyclic component orders, sort those orders from
largest to smallest, and pad the tuple with zeros to eight entries. Sort the
primitive-V2 modulus roster lexicographically by

```text
(descending component-order signature, actual q).
```

The q tie-breaker makes the ordering total. Component order inside the actual
mixed-radix transform is unchanged.

An exact replay over all 292,500 active source moduli gives:

| Quantity | Increasing q | Manifest order |
|---|---:|---:|
| order accesses | `816,177` | `816,177` |
| order hits | `532,611` | `782,177` |
| order misses | `283,566` | `34,000` |
| order enclosures prepared | `18,102,127,240` | `12,948,488,448` |
| root enclosures prepared | `4,194,258` | `4,194,258` |
| total enclosures prepared | `18,106,321,498` | `12,952,682,706` |

There are exactly 34,000 distinct component orders. A cold execution must
prepare each distinct order and each of the 19 radix-2 root arrays at least
once. The manifest order misses each one exactly once, so
`12,952,682,706` is not merely a heuristic improvement: it attains that
cold-cache preparation lower bound for the exact source roster under the
implemented split representation. The saved `5,153,638,792` enclosures are
28.46% of increasing-q preparation.

Three complete Python simulations of all 292,500 q on the local DGX Spark
took `4.401`, `4.403`, and `4.438` seconds (median `4.403` seconds). This
measures integer planning/cache replay only, not enclosure construction or
the transform.

At the deliberately conservative retained rate of 46,000 enclosures/s, the
new exact count is 78.2 serial preparation hours, or 9.78 ideal hours across
eight perfectly scaling hosts. This conversion is not an H100 or source-run
measurement.

## `TGDQORD1` manifest

`tools/tg_dirichlet_allchars_q_scheduler.py source-manifest PATH` creates a
2,340,112-byte binary manifest. Its header contains:

- format and primitive-roster version;
- bounded-KAT or full-source classification;
- source q range, q count, and exact total ordinate-row count;
- SHA-256 of `(q, row_count)` records in increasing source-q order; and
- SHA-256 of the same records in execution order.

The records themselves are fixed little-endian pairs
`(u32 q, u32 t_index_count)` in execution order. The full-source identity is:

| Binding | Exact value |
|---|---|
| q count | `292,500` |
| ordinate rows | `3,637,613,167` |
| increasing-roster SHA-256 | `d80a78ee36a82e2dab0d783b2c2407eff425a5978edb46585fba09d1ca7d5a2c` |
| execution-order SHA-256 | `34d633f0e3ed0d9cf3f684199fd2024a82e8027b4fc6733e48040a36007f3acd` |
| complete manifest SHA-256 | `a5ae1af2e4a9e944ccef559e169a13cd74f21c220ed882950ecd4491cbf13e93` |
| first / last execution q | `10,080 / 399,989` |

The manifest is generated, not checked in. Both Python and C++ independently:

1. reconstruct every canonical component signature;
2. require the canonical total permutation;
3. reject duplicate q or a modulus congruent to 2 modulo 4;
4. reconstruct the increasing source roster and every source height;
5. recompute both record digests; and
6. for a full-source manifest, compare the exact counts and digests above.

Thus a permutation is never inferred from nonmonotone input. It is an
explicit, versioned, hash-bound execution object.

## Scheduled CUDA service and replay

The optimized mode is:

```text
PRODUCER | sparkinterval-tg-dirichlet-allchars \
  --scheduled-multiq-framed-service \
  MAX_BATCH 512 SCHEDULE.bin SUMMARY.json DEVICE | CONSUMER
```

At every q transition, the CUDA process requires the next manifest record.
Within that q it requires `t = 0, 5/64, 10/64, ...` without a gap or overlap,
and it rejects EOF or transition until exactly the manifest row count has
been consumed. It also rejects trailing q groups, incomplete source coverage,
a noncanonical permutation, manifest tampering, or any cache budget other
than 512 MiB. This production command accepts only a full-source manifest.
The separately named
`--bounded-scheduled-multiq-framed-service` command is required for a bounded
KAT manifest, preventing a test schedule from being substituted at the
production CLI boundary.

The versioned summary binds the whole manifest, both roster digests, the
ordered cache-key chain, the root catalog, and complete input/output streams.
`validate_scheduled_multiq_framed_summary` independently parses every frame,
reconstructs every q plan and butterfly count, checks exact manifest
coverage, validates every interval shape, and separately simulates the split
cache. Production callers set `require_full_source=True`, which rejects a
bounded manifest before parsing any stream. The arithmetic payload still
requires the existing independent MPFR checker.

## Bounded DGX Spark evidence

A CUDA/MPFR KAT used q

```text
10001, 10080, 11088, 18480
```

with one ordinate each. The manifest execution order was

```text
10080, 18480, 11088, 10001.
```

For every q, the scheduled CUDA payload was byte-identical to a fresh
ordinary CUDA run and was contained by the independent 192-bit MPFR checker.
Negative tests rejected source-q order, a one-byte manifest mutation, and a
forged execution digest. Seven fresh scheduled runs on the local DGX Spark
had medians:

| Measurement | Median |
|---|---:|
| directed plan preparation | `0.03752 s` |
| GPU arithmetic | `0.001925 s` |
| process wall time | `0.4442 s` |

The bounded stream contained 602,400 input bytes. This is a conformance and
launch-overhead measurement, not a source-scale throughput result and not an
H100 calibration.

Reproduce the exact source accounting and the integrated CUDA KAT with:

```bash
python3 tools/tg_dirichlet_allchars_q_scheduler.py \
  --pretty source-inventory

python3 tools/tg_dirichlet_allchars_stage.py kat \
  --runner build/tg-production-kat/sparkinterval-tg-dirichlet-allchars \
  --checker build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr
```

## Receipt-preserving component-graph integration

`tg_verifier.dirichlet_scheduled_largeq_pipeline` now carries the same
manifest through the existing residue composer, scheduled CUDA service, and
completed-L consumer. The producer and consumer have explicit scheduled
modes; their old fixed-q behavior is unchanged.

The supervisor independently replays the composition and consumer controls
before launch. It requires:

- the exact manifest execution q at every q transition;
- t rows starting at zero on the exact 5/64 grid and complete per-q row
  coverage;
- the actual q in every `TGDAFFI1`, `TGDAFFO1`, root artifact, control row,
  and receipt;
- the manifest file hash, source-roster hash, and execution-order hash in
  producer, transform, consumer, and final supervisor receipts; and
- a root catalog whose increasing identity roster is exactly the same set of
  q labels as the manifest, even though artifacts are consumed in manifest
  order.

There is no increasing-q premise in the scheduled consumer. A q may occur
only in its one manifest group, and ordinates within that group remain
contiguous. The consumer seeds its frame fold with the immutable manifest
hash. Thus reordering, relabeling, truncating, or extending q/t work changes
or invalidates a receipt rather than silently changing cache behavior.

For a bounded KAT, two one-MiB, size-capped relays retain the exact input and
output streams while preserving OS-pipe backpressure. Any child or relay
failure cancels its siblings. Fresh replay:

1. reruns the actual residue composer and requires byte-identical
   `TGDAFFI1`;
2. validates the transform summary and every frame/coverage counter;
3. checks each `TGDAFFO1` frame with the independent MPFR executable; and
4. reruns the completed-L consumer with the authenticated per-q root
   catalog and requires byte-identical decisions.

The four-q KAT uses the complete active roster in `[10001,10005]` and
executes

```text
10005, 10004, 10001, 10003
```

rather than increasing q. It passes the complete replay, while tests reject
noncanonical control order, incomplete coverage, an oversized relay, child
failure without sibling cancellation, manifest tampering, and retained-stream
mutation.

Reproduce it with:

```bash
python3 -m unittest -v \
  tests.test_tg_dirichlet_scheduled_largeq_pipeline
```

The portable CUDA and strict `sm_90` all-character targets both build. The
strict binary was not executed on this DGX Spark because its GPU is not an
H100.

## Remaining source-scale work

The three component protocols accept the full-source manifest and do not need
to retain the many-petabyte transform streams. The integrated supervisor is
currently bounded-control tooling: it has not yet replaced its retained
composition/consumer control files with the formulaic source t-block
producer. That source launch seam, populated lattice/recovery/root inputs, an
Azure measured execution, compact source-scale zero-state transport,
independent streaming rather than retained-byte replay, exception refinement,
zero isolation, an accepted Turing count, and the final Lean evidence bridge
remain. There is no source-scale CUDA result, H100 timing/calibration,
attestation, completed-L/Turing closure, or discharge of Platt's Theorem 7.1.

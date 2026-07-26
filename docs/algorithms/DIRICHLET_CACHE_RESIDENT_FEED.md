# Authenticated cache-to-resident Dirichlet row feed

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Scope

`tg_verifier.dirichlet_cache_resident_feed` closes the bounded transport seam
between the `TGDLTCH1` unique t-major cache and the row artifact consumed by
`sparkinterval-tg-dirichlet-resident-qmajor-stream`. It does not regenerate a
q-major lattice. Each selected 1-MiB t row is copied once into the resident
artifact and is then reused for every target that references it.

This is qualification infrastructure, not a Platt Theorem 7.1 certificate.
No source cache has been populated, no source phase has run, and all
source/production/attestation/external-atom flags remain false.

## Fail-closed range admission

The caller supplies an external SHA-256 pin for the canonical cache catalog
and the exact resident phase plan. The adapter:

1. opens and validates the catalog without following symbolic links;
2. requires the requested half-open t range to lie inside the catalog;
3. opens only storage shards intersecting that range;
4. performs the cache reader's complete pre-hash and complete parse/hash pass
   for every touched shard;
5. parses every row and the footer of each touched shard, including
   unselected prefix or suffix rows at phase boundaries;
6. yields only the selected rows, in strictly increasing t order;
7. requires exactly the resident plan's row count; and
8. exhausts the range reader before atomically publishing the derived
   `TGDQSRH1`/`TGDLTMR1` row artifact.

Step 8 matters because the ten execution-phase cuts need not coincide with
the cache's 128-row storage-shard cuts. A corrupt unselected suffix or late
footer therefore prevents publication rather than leaving a seemingly valid
phase artifact.

For `R` selected rows and `P` physical rows in touched shards, the adapter
records:

```text
selected payload bytes        = R * 1,048,576
logical target references     = target_row_reference_count * 1,048,576
repeated lattice bytes avoided
  = (target_row_reference_count - R) * 1,048,576
authenticated cache file I/O  = two complete passes over touched shard files
```

The receipt binds the catalog file and semantic catalog hashes, cache plan,
`TGDQORD1` schedule and execution-order hashes, phase and lane-partition
hashes, touched shard identities, exact selected and physical row counts,
and the derived resident-row artifact hashes.

## Ordering and classifier boundary

The cache supplies only t-major Hurwitz rows. The resident plan separately
binds q execution order, lane order, target order, and increasing sample
order within each target. The CUDA worker reconstructs the canonical CRT
residue descriptors for the actual q and emits ordinary `TGDAFFI1` frames.
The existing all-character CUDA/MPFR KATs independently check CRT/Bluestein
frequency order; the completed-sign reducer's Arb differential qualification
checks directed sign classification.

`TGDBSPK1` must not be relabelled as the large-q result wire. Version 1 binds
the factored-small-q `TGDBSQP3` plan, its character batches and time-tail
control, and a t=0 full-span contract. The large-q path has distinct
CRT/root/completed-factor identities and its own same-device completed-L
reducer producing compact `TGDCSB03`-shaped phase state. Reusing the
small-q magic would erase material provenance instead of consolidating it.

## Bounded evidence

The structural tests establish byte-for-byte equality with a directly
generated resident row artifact. They reject:

- a wrong external catalog pin;
- a requested range outside the catalog;
- a reordered or omitted selected row;
- corruption in an unselected boundary-shard row;
- a late boundary footer failure; and
- publication before the range iterator has authenticated its final footer.

The CUDA integration KAT derives two shared rows from two one-row cache
shards, feeds the actual resident worker, and obtains the already pinned
four-target output:

```text
deb868eb9f3ced5e5275df24ca40bd0158e3b7b860c6165d5b4f3935ad6a041e
```

It also checks exactly two lattice uploads, four target records, four
descriptor uploads, and false external-atom discharge.

On 2026-07-26, a local five-repetition range replay selected rows `[1,31)`
from four eight-row synthetic shards. Its median was:

```text
selected payload per repetition          31,457,280 bytes
two-pass authenticated file I/O          67,115,584 bytes
median elapsed                            0.074999860 seconds
selected payload rate                     419,431,183 bytes/s
authenticated physical file rate          894,876,124 bytes/s
```

This is a page-cache-sensitive local I/O measurement, not an H100, Azure,
analytic-generation, or source-scale benchmark.

Run the bounded suite with:

```bash
python3 -m unittest -v \
  tests.test_tg_dirichlet_lattice_cache \
  tests.test_tg_dirichlet_cache_resident_feed

ctest --test-dir build/dgx-spark --output-on-failure \
  -R '^tg_dirichlet_resident_qmajor_stream_known_answers$'
```

## What is closed and what remains

Closed here:

- externally pinned cache-range admission;
- full authentication of phase-boundary storage shards;
- deterministic one-copy derivation of the resident row artifact;
- exact cache/schedule/phase/lane/order accounting; and
- bounded execution through the implemented resident CUDA worker.

Still open:

- populate and independently replay all 1,000 source cache shards;
- run an exact source phase through this admission path;
- connect the resident worker directly to the large-q all-character and
  completed-L phase accumulator without a petabyte-scale raw stream;
- produce and audit source root and completed-factor artifacts;
- prove enclosure usefulness, isolate zeros with multiplicity, and complete
  interpolation, exceptions, and reflected Turing closure;
- measure and attest the source Azure execution; and
- realize the accepted source evidence in Lean.


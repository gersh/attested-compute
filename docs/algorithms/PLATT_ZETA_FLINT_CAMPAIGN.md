# FLINT Platt campaign for zeta RH through `3000175332800`

Copyright (c) 2026 Gershon Bialer. All rights reserved.  
SPDX-License-Identifier: MIT

> **Preferred source-scale route.**  The fixed-index FLINT campaign documented
> below remains a useful independent replay and audit path, but its measured
> projection is years.  The pinned public windowed Arb/Turing implementation
> and its fail-closed campaign are now documented in
> [PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md](PLATT_PT21_WINDOWED_SOURCE_CAMPAIGN.md).
> That route has valid known-answer blocks and a much better cost model, but
> its complete H100 port, lower prefix, and Azure receipt are still unfinished.

This is the source-scale external verifier for
`platt-trudgian-rh-3e12`. It covers the exact statement used by the ternary
Goldbach project:

```text
N(3000175332800) = 12363153437138,
```

where `N(T)` counts nontrivial zeta zeros with multiplicity, and every such
zero is on `Re(s) = 1/2`. The height and count are those of Theorem 1 of
[Platt--Trudgian (2021)](https://doi.org/10.1112/blms.12460).

The implementation is external finite-computation evidence. It trusts the
reviewed FLINT implementation, compiler, operating system, and hardware. It
does not identify FLINT's zeta implementation with Mathlib's `riemannZeta`,
does not attest execution by itself, and does not discharge a Lean atom.

## Reviewed implementation

The following project-owned files implement the campaign:

- [`reference/tg_platt_zeta_shard.cpp`](../../reference/tg_platt_zeta_shard.cpp)
  is the bounded-memory native producer;
- [`tg_verifier/platt_zeta_campaign.py`](../../tg_verifier/platt_zeta_campaign.py)
  fixes the index geometry, validates receipts, builds the Merkle root, and
  replays a shard;
- [`tools/tg_platt_zeta_campaign.py`](../../tools/tg_platt_zeta_campaign.py)
  is the operator CLI; and
- [`specifications/FLINT_3_6_PLATT_UPSTREAM.json`](../../specifications/FLINT_3_6_PLATT_UPSTREAM.json)
  pins FLINT tag `v3.6.0`, commit
  `8d5454b96761fafe4d5a9da76a369a602f500f49`, its LGPL license files, public
  API declaration, implementation files, documentation, and example.

`tools/fetch_flint_platt.py` verifies the clean Git checkout, exact commit,
tag resolution, and the hashes of the reviewed files. It can also configure,
build, and install that checkout:

```bash
python3 tools/fetch_flint_platt.py build/upstream/flint-3.6 \
  --build --prefix build/upstream/flint-3.6-install --jobs 40 --pretty
```

Configure the native target with both the verified checkout and its install:

```bash
cmake -S . -B build/platt-zeta \
  -DSPARKINTERVAL_FLINT_PLATT_ROOT="$PWD/build/upstream/flint-3.6" \
  -DSPARKINTERVAL_FLINT_PLATT_PREFIX="$PWD/build/upstream/flint-3.6-install"
cmake --build build/platt-zeta --target \
  sparkinterval-tg-platt-zeta-shard -j40
ctest --test-dir build/platt-zeta -R tg_platt_zeta_shard_known_answers \
  --output-on-failure
```

## What the two Platt engines prove

FLINT 3.6 documents `acb_dirichlet_platt_zeta_zeros` as returning consecutive
Riemann-zeta zeros beginning at a requested index. Internally it uses Platt's
rigorous grid evaluation, isolates sign changes, applies a Turing count to
anchor the indices, and then refines every returned zero to an `acb` ball.

The runner exposes two related engines:

1. `platt-isolate` is the production engine. It calls FLINT's public
   `acb_dirichlet_platt_isolate_local_hardy_z_zeros` function. This runs the
   same rigorous grid and Turing-completeness machinery, but retains the open
   sign-change endpoints instead of refining every zero. It fails if a call
   returns no consecutive block, an interval is nonpositive or malformed,
   two open intervals overlap, an included terminal interval is not below
   the cutoff, or the `N+1` sentinel is not above it.
2. `platt-zeta-replay` calls
   `acb_dirichlet_platt_zeta_zeros` itself. The campaign uses this named API
   for bounded audit samples, checking exact real part `1/2`, positive finite
   imaginary balls, and strict disjointness.

The distinction is important. The public named API has no count-only mode and
pays to refine every zero. The local isolator avoids that refinement, but
FLINT's high-level heuristic still uses small local grids. This repository
does not claim to reproduce the much larger, more efficient production grid
used in the original Platt--Trudgian computation.

No simplicity conjecture is an input. `acb_dirichlet_zeta_nzeros` counts with
multiplicity. Each Platt interval is produced only after FLINT's Turing method
has established the corresponding consecutive index. If the multiplicity
count and the returned critical-line sequence cannot be reconciled, a call or
the final campaign fails; the code never silently collapses a repeated zero.

## Fixed source geometry

The full campaign always uses:

| item | fixed value |
|---|---:|
| exact height | `3000175332800` |
| multiplicity count | `12363153437138` |
| ordinary low-index prefix | `1..9999` |
| Platt range | `[10000, 12363153437140)` |
| last included index | `12363153437138` |
| first excluded sentinel | `12363153437139` |
| Platt shard span | `10000000` indices |
| number of Platt shards | `1236316` |
| local request size | `4096` |
| working precision | `96` bits |
| FLINT threads per process | `1` |

The formula for shard `i` is stored in `campaign.json`; no twelve-trillion-row
plan is materialized. Forty independent one-thread processes fit the 40-vCPU
host of one Azure `NCC40ads_H100_v5` node. The H100 is not used by FLINT's
host implementation.

Initialize and inspect the immutable plan:

```bash
RUNNER=build/platt-zeta/sparkinterval-tg-platt-zeta-shard
OUT=build/tg/platt-zeta-3e12
python3 tools/tg_platt_zeta_campaign.py --pretty init "$OUT" \
  --runner "$RUNNER"
python3 tools/tg_platt_zeta_campaign.py --pretty range "$OUT" 0
```

First record the exact multiplicity count and the small prefix:

```bash
python3 tools/tg_platt_zeta_campaign.py --pretty count "$OUT"
python3 tools/tg_platt_zeta_campaign.py --pretty prefix "$OUT"
```

Each scheduler task receives one immutable integer index:

```bash
python3 tools/tg_platt_zeta_campaign.py --pretty run-shard "$OUT" 0
python3 tools/tg_platt_zeta_campaign.py --pretty replay-shard "$OUT" 0
python3 tools/tg_platt_zeta_campaign.py --pretty replay-shard "$OUT" 0 \
  --refined
```

After every fixed shard exists:

```bash
python3 tools/tg_platt_zeta_campaign.py --pretty status "$OUT"
python3 tools/tg_platt_zeta_campaign.py --pretty finalize "$OUT"
```

Every receipt binds its exact range, working configuration, FLINT identity,
canonical FLINT interval-stream digest, first and last exact endpoints, and
cutoff checks. Replay discards elapsed time and requires an identical semantic
receipt. Finalization orders the exact-count receipt, prefix receipt, and all
`1236316` shard receipts, then builds a domain-separated SHA-256 Merkle tree.

## Exact Lean handoff

[`ZetaRHSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/ZetaRHSourceSemantics.lean)
states the exact positive-height, open-critical-strip claim at
`3000175332800`. Its `SourceEvidence` retains the generic chunked bracket
certificate, endpoint continuity/coverage, Hardy-Z zero equivalence and global
zero-count upper bound; the final specialization is an ordinary Lean theorem.

The closed `plattTrudgianFiniteRHProductionV1` trusted-compute invocation binds
the campaign ID, exact height and multiplicity count, pinned FLINT commit,
working precision, micro-batch size, shard span and shard count. It accepts
only Azure SEV-SNP CPU execution. A successful signed result can expose the
source claim through
[`RegisteredZetaRHCertificate.lean`](../../SparkInterval/Execution/RegisteredZetaRHCertificate.lean),
using exactly the repository's one accepted-run axiom.

This is a conditional vertical slice, not a completed certificate. The current
campaign artifacts do not construct `SourceEvidence`: the endpoint stream to
Lean chunk evidence, FLINT Hardy-Z semantics to Mathlib `riemannZeta`, and the
Turing/multiplicity count to the Lean upper-bound contract remain explicit.
There is also no source-scale materializer, full run, or attested success
receipt. The `platt-trudgian-rh-3e12` Azure semantic-binding row is deliberately
left disabled, but its exact invocation, conditional theorem, and
`${TG_RUN_ROOT}/platt-trudgian-rh-3e12/registered-result.txt` terminal contract
are staged for review. The finalizer creates literal `true` exclusively only
after complete source-scale finalization; these staged fields are not evidence.

## Measured performance and Azure projection

The following measurements were made on `2026-07-21` on the local DGX Spark
host (`aarch64`, 20 CPU cores, NVIDIA GB10). They use the pinned FLINT build,
96-bit working precision, and the actual source-height index.

| operation | records | threads | wall time | peak RSS | result |
|---|---:|---:|---:|---:|---|
| exact `N(T)` at source height | one count | 1 | `2.47 s` | `28 MB` | exact source count |
| named `platt_zeta_zeros` | 100 | 20 | `13.47 s` | `309 MB` | success |
| named `platt_zeta_zeros` | 4096 | 1 | `67.93 s` | `309 MB` | success |
| count-only local isolation | 4096 | 1 | `44.82 s` | `311 MB` | 3 rigorous local calls |
| terminal boundary isolation | 102 | 20 | `13.25 s` | `311 MB` | `gamma_N < T < gamma_(N+1)` |

The production measurement is `91.38` zeros/second/process. Straight scaling
of the complete Platt range therefore gives:

```text
37.58 million one-process CPU-hours
= 4,287 one-process years
= 117,440 ideal wall-hours on 320 independent CPU processes
= 13.40 ideal wall-years on eight 40-vCPU NCC nodes.
```

At the Azure East US 2 prices captured on `2026-07-21` by
`tools/tg_azure_production_sizing.py` (`$6.98` PAYG or `$1.419034` Spot per
NCC node-hour), that point projection is about `$6.56M` PAYG or `$1.33M` Spot.
It excludes storage, orchestration, retries, unavailable capacity, and the
risk of multi-year Spot eviction. CPU differences between the local ARM host
and Azure's Genoa host have not been measured, so this is a transparent
throughput transfer, not an Azure benchmark.

For context, the source paper reports roughly `7.5 million core-hours` for
its optimized production computation. Perfectly spreading that historical
work over 320 cores would still take about `2.67 years`, costing roughly
`$1.31M` PAYG or `$266k` Spot at the same rates. Thus this implementation is
source-range capable and independently replayable, but a complete Azure run
is not presently economical. An H100 port of the Platt multievaluation and
rigorous interval/Turing pipeline, or imported reviewed source artifacts, is
needed before scheduling the full campaign.

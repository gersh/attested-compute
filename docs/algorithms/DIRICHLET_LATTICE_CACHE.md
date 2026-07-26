# Authenticated t-major Hurwitz-lattice cache

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

This component removes a source-scale transport duplication in the optimized
large-`q` path for D. J. Platt,
[*Numerical computations concerning the GRH*](https://arxiv.org/abs/1305.3087v1).
It is a cache, sharding, and replay boundary. It is not a proof of Platt's
Theorem 7.1.

## Why the cache is t-major

At one source ordinate `t=5j/64`, every active modulus uses the same lattice

```text
zeta_M(1/2 + it + c, r/2048),
  r = 1,...,2048, c = 0,...,15, M = 4.
```

There are exactly `2048 * 16 = 32768` complex rectangles per ordinate. Each
rectangle has four binary64 endpoints, so one complete ordinate is exactly
`32768 * 32 = 1,048,576` bytes. The large-`q` main positive grid has 127,988
ordinates. Storing each row once therefore requires:

| quantity | exact value |
|---|---:|
| lattice cells | `4,193,910,784` |
| row payload | `1,048,576` bytes |
| complete payload | `134,205,145,088` bytes (`124.98828125 GiB`) |
| complete authenticated artifacts | `134,214,624,224` bytes |
| former descriptor-repeated non-lattice model | `41,279,640,994,288` bytes |
| former t-major compact model | `41,413,846,139,376` bytes (`41.414` TB) |
| direct primitive-only V2 `TGDLTMB1` binary input | `286,556,459,000` bytes (`286.556` GB) |

The former q-major compact schedule logically supplied
`5,139,124,740,685,824` lattice bytes. The t-major payload is smaller by
`38,293.053x`. The earlier t-major model still repeated canonical descriptor
tables and fell from `5,180,404,381,680,112` bytes to
`41,413,846,139,376` bytes. The newer
[`TGDLTMB1` component](DIRICHLET_TMAJOR_CUDA_BLOCK.md) reconstructs those
descriptors, generates factors/tails directly, and reduces the exact binary
input to `286,556,459,000` bytes. This is a host-supply model. It does not
remove the Taylor arithmetic or prove source-scale HBM/L2 behavior.

This cache does not contain the finer interpolation/exception points, endpoint
padding, shifted windows, or paired Turing windows. Those remain separate
inputs and are not hidden in the 125-GiB count.

## Fixed main-grid plan

[`dirichlet_lattice_cache.py`](../../tg_verifier/dirichlet_lattice_cache.py)
uses 1,000 immutable storage shards. The first 999 contain 128 consecutive
ordinates and the last contains 116. A full ordinary shard has a 128 MiB
payload. The canonical source plan hash is:

```text
b86872a3a389f3fb23c5ca0c82c02d0c2605726f245e309e04e3859d7319f98d
```

Storage sharding and execution assignment are separate. The default
eight-lane execution plan in this cache module is the retained all-modulus V1
plan, with boundaries chosen to balance 327,089,206,283,008 residue
reconstructions. It must not be silently presented as the V2 schedule. The
direct `TGDLTMB1` V2 component independently pins its 266,697,737,764,848
primitive-only reconstructions and new lane counts. Within one lane, an
implementation can load a row once and broadcast it across every active
modulus stream before advancing `t`. The last lane owns many more cache bytes
because relatively few moduli remain active at high ordinates; its Taylor
work is nevertheless comparable to the other lanes.

The execution-plan hash is:

```text
c64a0bd96bb446ae458a244e4cb37fada70be78870f08324a5764d1148bb6450
```

This assignment is implemented and tested. The
[`cache-to-resident feed`](DIRICHLET_CACHE_RESIDENT_FEED.md) now admits an
externally pinned half-open catalog range, fully authenticates every touched
storage shard, and publishes the exact row artifact consumed by the resident
q-major CUDA worker. A bounded cache-derived artifact has run through that
worker. Neither component has run at source scale or been connected to the
persistent multi-q transform/zero service.
The lane-local reader used by
[`DIRICHLET_SOURCE_SUPERVISOR.md`](DIRICHLET_SOURCE_SUPERVISOR.md) authenticates
only the shards assigned to that lane and permits at most one outstanding row
lease. The supervisor also exposes the distinct fixed-q FFT roster; it does
not claim that the existing q-major process graph can yet consume the t-major
order.

## Binary authentication and bounded memory

Each `TGDLTCH1` file binds:

- the complete storage-plan hash and its domain-separated shard descriptor;
- exact `M`, lattice dimensions, source step, t range, and producer kind;
- one `TGDLTCR1` header and domain-separated SHA-256 for each 1 MiB row; and
- a `TGDLTCF1` footer committing the raw row stream and ordered row-hash root.

The strict reader can require the complete file SHA-256 before parsing. It
opens the regular file without following symbolic links, hashes and parses the
same file descriptor, and checks the complete digest again during parsing. It
then buffers and authenticates exactly one 1 MiB row before exposing it.
Footer success is reported only after the iterator is exhausted. A separate
bounded decoder checks finite, ordered binary64 rectangles; the fast
transport reader deliberately does not run 4.19 billion Python-level interval
decodes.

A canonical catalog covers every shard exactly once, pins every artifact
hash, and rejects gaps, overlaps, substitutions, trailing bytes, changed
plans, and noncanonical filenames. A catalog satisfying
`--require-replayed` must also retain one pack receipt per shard. The catalog
states that those receipts are bound; it keeps execution attestation false.

## Analytic-input boundary

SHA-256 proves identity, not Hurwitz-zeta semantics. Synthetic shards are
therefore permanently labelled format KATs and cannot satisfy a
`--require-replayed` catalog audit.

The production repacker takes the stronger route:

1. accept exactly one existing
   [`TGDLATI1` certified bundle](DIRICHLET_LATTICE_CERTIFICATES.md) per planned
   ordinate;
2. invoke its independent higher-precision Arb replay, including every one of
   the 32,768 Hurwitz rectangles;
3. extract the canonical lattice payload only after replay succeeds; and
4. retain the certificate, replay, lattice-input, cache-row, artifact, and
   plan hashes in a canonical receipt.

Thus the cache does not weaken interval semantics. Full source population is
theoretically available through already implemented pinned-Arb replay, but no
source campaign has been run and the analytic generation rate has not been
measured on the intended Azure setup.

The canonical pack receipt is provenance, not a new trust oracle: it binds the
exact repacker module plus every input certificate and replay digest. An
auditor must rerun that module or authenticate its measured execution; a
self-hash alone is not evidence that arbitrary JSON claims are true.

## Operator commands

Inspect the fixed plans:

```bash
python3 tools/tg_dirichlet_lattice_cache.py --pretty plan
python3 tools/tg_dirichlet_lattice_cache.py --pretty broadcast-plan --lanes 8
```

Create and audit a three-row structural KAT:

```bash
ROOT=/tmp/tg-lattice-cache-kat
for I in 0 1 2; do
  python3 tools/tg_dirichlet_lattice_cache.py synthetic-shard \
    --t-index-stop 3 --t-indices-per-shard 1 "$ROOT" "$I"
done
python3 tools/tg_dirichlet_lattice_cache.py build-catalog \
  --t-index-stop 3 --t-indices-per-shard 1 --allow-synthetic \
  "$ROOT" "$ROOT/catalog.json"
python3 tools/tg_dirichlet_lattice_cache.py audit-catalog \
  "$ROOT" "$ROOT/catalog.json"
```

For a replayed production shard, pass certificate roots in exact t order:

```bash
python3 tools/tg_dirichlet_lattice_cache.py pack-replayed-shard \
  /work/cache/lattice-shard-0000.bin \
  /work/cache/lattice-shard-0000.receipt.json \
  0 /work/cert/t-000000 /work/cert/t-000001 ... /work/cert/t-000127
```

The command deliberately performs the expensive higher-precision replay
instead of trusting supplied digest strings.

## Local cache benchmark

On 2026-07-22, a retained local 32 MiB synthetic artifact was strictly read
twenty times. Counting both the mandatory full-file pre-hash and parser pass,
the local filesystem sustained:

```text
0.17316 GB/s physical file bytes
1,342,280,000 physical bytes
7.75169 seconds
```

Straight-line scaling gives about 1,550 seconds (25.8 minutes) for two complete
scans of the 125 GiB main-grid cache. Consecutive smaller runs varied from
0.108 to 1.004 GB/s, so filesystem caching and host contention plainly
dominate this microbenchmark. It is not an Azure durable-storage benchmark,
not host-to-H100 throughput, and does not time the remaining 41.280 TB logical
compact stream. It is not a Platt Theorem 7.1 ETA. The exact retained command
is:

```bash
python3 tools/tg_dirichlet_lattice_cache.py --pretty benchmark \
  --t-indices 32 --repetitions 20
```

The projection accepts a separately measured analytic-cell rate, but none is
recorded here: the pinned python-flint 0.9.0 / FLINT 3.6.0 environment was not
available during this cache benchmark.

The newer range-admission benchmark, which measures the exact
cache-to-resident reader rather than the whole-catalog reader, is recorded in
[`DIRICHLET_CACHE_RESIDENT_FEED.md`](DIRICHLET_CACHE_RESIDENT_FEED.md).

## Remaining boundary

The following are still open:

- populate and independently audit all 1,000 main-grid cache shards;
- measure and optimize Hurwitz-cell generation/replay on production hardware;
- run exact source phases through the cache-to-resident admission and
  integrate the worker output with the persistent multi-q all-character FFT
  and completed-L consumer without materializing the raw stream;
- demonstrate source-wide enclosure usefulness and exception handling;
- complete interpolation, zero-isolation, and reflected Turing closure;
- run and attest the complete Azure campaign; and
- realize the resulting source evidence in Lean.

Every report produced here keeps `external_atom_discharged=false`.

# Source-shaped resident q-major stream candidate

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status and claim boundary

`tg_verifier.dirichlet_resident_qmajor_stream` and
`sparkinterval-tg-dirichlet-resident-qmajor-stream` implement the
source-shaped arithmetic executor boundary for the pinned ten-phase resident
q-major plan. The wire accepts the authenticated full `TGDQORD1` source
schedule, represents all ten exact phase ranges, streams rows one at a time,
partitions q work into bounded lanes, and emits one bounded `TGDAFFI1` target
at a time. The
[`cache-to-resident feed`](DIRICHLET_CACHE_RESIDENT_FEED.md) now derives this
worker's exact row artifact from an externally pinned `TGDLTCH1` catalog
range, with full authentication of boundary storage shards before
publication. A bounded cache-derived CUDA KAT has completed.

This is still an arithmetic component, not a completed source zero
verification. No exact source phase has run. No H100 source-phase fit has
been measured. The separately implemented large-q all-character/completed-L
device reducer is not integrated into this source executor or its receipt;
zero isolation, Turing closure, attestation, and external-atom discharge are
also absent. Every corresponding capability and receipt flag remains false.

The largest projected raw phase output is
`1,093,526,631,178,952` bytes: more than one decimal petabyte. It is not a
disk artifact or a memory requirement. Full-source mode accepts stdout only
when it is a pipe or socket to a bounded consumer that applies backpressure;
regular files, terminals, and character devices are refused. The current
interface can feed such a consumer, but no
semantic/sign consumer is yet part of this executor or its claims.

## Exact geometry and bounded units

The candidate phase cuts are:

```text
0, 768, 1600, 2368, 3200, 4032, 5568, 9600,
49088, 88512, 127988
```

Bounded projections may select a contiguous subrange of one phase and only
use a bounded schedule. Exact candidate-phase mode requires both the full
source schedule and the whole canonical phase range. The fixed execution
bounds are:

| Unit | Bound |
|---|---:|
| Rows in one phase | 39,488 |
| q records in one lane | 64 |
| Targets in one lane | 39,488 |
| Lanes | 8,192 |
| t rows in one target | 64 |
| Group order | 400,000 |
| Values in one target | 25,600,000 |
| Lane sidecar wire | 128 MiB |
| Phase sidecar wire | 64 GiB |

An inactive q contributes no target. A contiguous lane may therefore contain
zero active q values; its authenticated header and footer still preserve the
exact q-index partition. Active targets remain in schedule order and, within
each q, increasing t-batch order.

## Two immutable input streams

Rows and target sidecars are separate artifacts so the producer never needs
a second phase-sized host copy.

The row artifact can now be deterministically materialized from the unique
t-major cache instead of asking a phase producer to repeat the logical
q-major lattice. Cache storage-shard cuts and execution-phase cuts are
independent, so the adapter drains and authenticates unselected boundary rows
and the final shard footer before publishing this stream.

The row stream consists of:

| Record | Magic | Bytes |
|---|---:|---:|
| Phase header | `TGDQSRH1` | 360 |
| Row header | `TGDLTMR1` | 64 |
| Row payload | — | 1,048,576 |
| Phase footer | `TGDQSRF1` | 136 |

Its exact size for \(R\) rows is

```text
360 + R * (64 + 1,048,576) + 136
```

The sidecar stream consists of:

| Record | Magic | Bytes |
|---|---:|---:|
| Phase header | `TGDQSSH1` | 432 |
| Lane header | `TGDQSLH1` | 152 |
| Target header | `TGDQSTG1` | 152 |
| Factors | — | 32 per target row |
| Taylor tails | — | 8 per target row |
| Lane footer | `TGDQSLF1` | 200 |
| Phase footer | `TGDQSSF1` | 200 |

Each target identity contains execution-q index, actual q, phase, lane,
first/stop t index, and batch count. Per-row and per-sidecar hashes bind raw
payloads. Separate row, target, lane-target, lane, lane-stream, body-stream,
and whole-file commitments bind exact order and accounting. The CLI also
requires external SHA-256 pins for the schedule plan, row artifact, sidecar
artifact, and recovery seeds.

## Execution and TOCTOU closure

The worker first authenticates both complete artifacts before selecting
CUDA or writing stdout. It then performs independent execution reads:

1. allocate one resident device lattice buffer;
2. reread, validate, and hash each row through one 1-MiB staging buffer;
3. upload each row directly to its final offset;
4. require the row footer and whole external row SHA again;
5. reread each lane, target, factor block, tail block, and commitment;
6. reconstruct and upload descriptors only on an actual-q transition;
7. launch against the resident row offset and write one target output;
8. require every lane/footer chain and the whole external sidecar SHA again;
9. publish a canonical terminal summary only after all checks succeed.

A post-preflight substitution is therefore detected by the consumed-byte
execution replay. A late sidecar or device failure can leave an
unauthenticated stdout prefix, but never a terminal summary. Supervisors must
accept output only together with the independently replayed summary.

Two CUDA events are created once with the plan and reused for every target.
The descriptor device allocation is reused across q transitions; a
descriptor table is copied exactly once for each active q.

## TGDAFFI1 transport and backpressure

Each target is emitted immediately as one ordinary `TGDAFFI1` frame:

```text
72-byte TGDAFFI1 header
batch_count * phi(q) complex intervals, 32 bytes each
```

The header binds actual q, component count, batch count, group order, first t
numerator, t denominator, t step, and exact value count. A frame is bounded
by `25,600,000` intervals, or `819,200,000` payload bytes plus its 72-byte
header. The executor retains only one target result and uses blocking stdout,
so a pipe/socket consumer supplies operating-system backpressure.

For a phase with target count \(T\) and value count \(N\), projected transport
volume is:

```text
72 * T + 32 * N
```

The maximum pinned phase has `T = 5,380,665` and
`N = 34,172,695,117,846`, giving the exact
`1,093,526,631,178,952`-byte projection above. Writing that stream to a
regular file is not a source-feasibility strategy. Until a bounded
semantic/sign reducer consumes the stream directly and publishes compact
terminal state, the source execution and zero-closure flags must remain
false.

## Separate buffer formulas

For:

- \(S\): authenticated seed-record count;
- \(R\): resident row count;
- \(G\): maximum active group order;
- \(B\): maximum target batch count; and
- \(V\): maximum target value count,

the exact peak of explicit live CUDA allocations is:

```text
48*S                  recovery seeds
+ 1,048,576*R         resident lattice
+ 8*G                 descriptor table
+ 32*B                factors
+ 8*B                 tails
+ 32*V                one target result
```

`cudaMemGetInfo` must show that total plus a separate 512-MiB reserve before
allocation. CUDA context memory, event implementation storage, allocator
fragmentation, and future downstream state are not in the exact explicit
allocation formula; only the reserve covers them.

Executor payload staging on the host is separately bounded by:

```text
max(1,048,576, 8*G + 40*B + 32*V)
```

This is a payload-buffer bound, not a claim about allocator metadata or the
authenticated seed/schedule containers. Disk inputs are separately reported
as the exact row artifact, sidecar artifact, and their sum. Projected
`TGDAFFI1` bytes are reported as stream transport, never as required host,
device, or disk buffering.

For the bounded KAT:

```text
explicit device allocations       7,237,408 bytes
device safety reserve           536,870,912 bytes
host payload staging bound        1,048,576 bytes
row artifact                      2,097,776 bytes
sidecar artifact                      2,264 bytes
total disk input                  2,100,040 bytes
projected/output stream           1,204,512 bytes
```

For exact source phase 7, structural reconstruction (not execution) gives:

```text
resident rows                         39,488
resident lattice bytes        41,406,169,088
sidecar artifact bytes         53,852,286,440
host payload staging bound        272,302,192
explicit device allocations    41,774,471,232
```

The device number includes all `1,999,999` source seed records and the
largest descriptor, sidecar, and target-output allocations in that phase.
It still is not an H100-fit result because context/event storage,
fragmentation, the semantic reducer, and downstream transform state are not
included or measured.

## Known-answer and attack evidence

The CUDA KAT uses two shared rows, two q lanes, four targets, and nonmonotone
execution q order `10080, 18480, 11088, 10001`. It records:

```text
phase plan SHA-256
cdf628fd558019d0649cd01a176dd0466e2dd98a2e31b95baa956a807fa39b7d

row artifact SHA-256
10ed422992a21b4f74a862cd52f809003869cecd30e6e1c75cbdd0604c10d0ac

sidecar artifact SHA-256
1b1dc1c3ffb0ddc67568b4d2d35b88e79e5bb5ffe2fa8533669dd9862a4d79e7

output SHA-256
deb868eb9f3ced5e5275df24ca40bd0158e3b7b860c6165d5b4f3935ad6a041e
```

The output is byte-identical to the current resident phase, the row-repeated
formulaic service, and four concatenated legacy `TGDLQB2` executions. The
stream inputs total `2,100,040` bytes versus `2,098,776` for the current
resident artifact and `8,390,744` for the formulaic artifact. The new
separation costs 1,264 wire bytes versus the current resident seam and saves
6,290,704 bytes versus formulaic row repetition.

Tests reject row truncation, row substitution, row reorder, sidecar
truncation, factor substitution, q substitution, target reorder, lane
reorder, plan substitution, and a sidecar swap performed after complete
preflight but before execution. Separate post-preflight row substitution is
also rejected before output. Compiled KATs execute empty q lanes and a
65-row/two-target q, requiring one descriptor reconstruction/upload and two
event reuses.

Rebuild and rerun with:

```bash
cmake -S . -B build/tg-production-kat
cmake --build build/tg-production-kat \
  --target sparkinterval-tg-dirichlet-resident-qmajor-stream \
           sparkinterval-tg-dirichlet-largeq-seeded -j2
python3 -m unittest -v \
  tests.test_tg_dirichlet_resident_qmajor_stream \
  tests.test_tg_dirichlet_cache_resident_feed
ctest --test-dir build/tg-production-kat \
  -R tg_dirichlet_resident_qmajor_stream_known_answers \
  --output-on-failure
```

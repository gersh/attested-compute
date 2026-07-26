# Dirichlet t-block execution supervisor

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

[`dirichlet_tblock_supervisor.py`](../../tg_verifier/dirichlet_tblock_supervisor.py)
and its explicit worker protocol connect an authenticated `TGDLQSP1` lane to
a long-lived, back-pressured subprocess without writing the
76,770,217-record q-major manifest.

This is currently a structural execution seam, not a production
implementation of Platt's Theorem 7.1. Production admission is deliberately
disabled. A bounded protocol-v2 path now closes the typed-bundle-byte replay
boundary and explicitly reconciles block-major worker output with deterministic
adapter admission. A separately pinned bounded worker also executes actual
multi-q composer/native-transform/FLINT-consumer arithmetic. Neither mode is
source evidence.

## Constant-size roster formula

The supervisor keeps the spool file descriptor open, authenticates the
archive once, and advances through the lane in aligned blocks of at most 64
rows. The eight source lanes contain:

| lane | block count |
|---:|---:|
| 0 | 14 |
| 1 | 12 |
| 2 | 14 |
| 3 | 12 |
| 4 | 16 |
| 5 | 24 |
| 6 | 68 |
| 7 | 1,840 |
| total | 2,000 |

For block start \(u\), the active target predicate is the simple equation

\[
  10001 \le q \le 400000
  \quad\text{and}\quad
  u \le \operatorname{maximum\_t\_index}(q),
\]

where

\[
 \operatorname{maximum\_t\_index}(q)=
 \left\lfloor
 \frac{64\max(100000000,\,200q+c(q))}{5q}
 \right\rfloor,
 \qquad
 c(q)=
 \begin{cases}
 75000000,&q\text{ even},\\
 37500000,&q\text{ odd}.
 \end{cases}
\]

The target's stop is

\[
  \min(u+64,\ \text{lane stop},\
       \operatorname{maximum\_t\_index}(q)+1).
\]

The request binds this formula, its source-contract digest, the ordered
64-or-fewer `(t_index, SHA256(payload))` identities, and exact active-target
and row-reference counts. A histogram/suffix index over the 390,000 moduli
computes all source counts without iterating over all target references or
emitting a q list. The independently pinned totals are recovered:

```text
76,770,217 fixed-q targets
4,901,051,274 (q,t) row references
0 q-major manifest lines
```

The worker is responsible for iterating those q values in increasing order
and deriving each fixed-q descriptor. The bounded structural worker
independently performs that enumeration. A future production worker must
also switch or retain the corresponding FFT plans and completed-\(L\) state.

## Framed service protocol

The worker emits one canonical-JSON handshake. For each block the supervisor
then writes:

1. one canonical-JSON request line;
2. exactly `row_count * 1,048,576` raw payload bytes; and
3. no next request until one canonical-JSON response is validated.

This gives literal one-request-at-a-time backpressure. The worker rehashes
every streamed payload against the bounded row roster. The supervisor
independently hashes the complete payload stream and requires the response to
bind that digest, the exact roster formula/counts, and the preceding result
chain.

On malformed output, short input/output, a substituted response, nonzero
exit, or an exception, the supervisor terminates the worker process group and
does not write a checkpoint for the failed block.

The structural worker is:

```bash
python3 tools/tg_dirichlet_tblock_worker.py
```

It executes only payload authentication and exact target enumeration. Its
handshake says `false` for actual composition, all-character transformation,
completed-\(L\) consumption, typed-bundle output, adapter admission, CUDA,
Turing completeness, attestation, and atom discharge.

## Bounded protocol v2: actual bundle bytes

[`dirichlet_tblock_bundle_supervisor.py`](../../tg_verifier/dirichlet_tblock_bundle_supervisor.py)
and
[`dirichlet_tblock_bundle_worker.py`](../../tg_verifier/dirichlet_tblock_bundle_worker.py)
implement the next bounded seam. For each request the worker emits:

1. a canonical stream header with the exact active-target count;
2. for every target, a canonical frame header, an unsigned 64-bit byte
   length, and the actual canonical typed-bundle bytes; and
3. a canonical response that is forbidden from claiming supervisor replay or
   adapter work.

The supervisor independently hashes the received bytes, stages each artifact
under a deterministic immutable name, extracts and checks its semantic
self-hash, and freshly calls the existing
`TMajorTypedBundleLaneAdapter.accept_bundle`. That call itself invokes the
existing `replay_bundle`, which reconstructs the typed bundle from the source
contract, retained pipeline receipt, and all nested artifacts. The
supervisor—not the worker—then constructs the artifact/admission hash chain
and result-chain transition. A checkpoint is written only after every frame
in that request has passed those calls.

Resume does not trust a compact “admitted” boolean. It reopens every staged
artifact without following a final symlink, recomputes its exact size and
SHA-256, freshly replays and readmits it to reconstruct adapter state, and
requires the resulting admission record and hash chains to equal the
checkpoint. For the native compact-event profile it also reconstructs the
per-character leaf state from the nested summary, validates the exact
q/primitive roster/5/64 grid, merges it with the previous state for that q
only when the ordinate ranges are exactly adjacent, and rereads a canonical
`TGDCSB02` binary state artifact. The checkpoint binds the state before,
leaf, state after, binary hash and size, and any sign change inserted across
the block boundary. `TGDCSB02` also retains every maximal half-open ambiguity
range and every ordered exact sign-change bracket. Its per-character index
gives canonical absolute offsets and lengths for both sparse sections.

V2 has two fail-closed worker profiles:

- The transport worker only transports prebuilt artifacts. Its handshake
  truthfully says that it did not run the residue composer, all-character
  transform, completed-\(L\) consumer, typed-bundle replay, or adapter.
- The bounded native plan-switch worker validates a self-hashed recipe, all
  input artifact hashes, the worker module and launcher hashes, every runtime
  binary/script hash, and a pinned Python-FLINT `0.9.0` / FLINT `3.6.0`
  version probe. The supervisor additionally requires external pins for the
  complete handshake, implementation aggregate, recipe, and runtime-artifact
  aggregate. Only then may its handshake advertise actual composer,
  q-specific native all-character, FLINT consumer, and multi-q plan-switch
  capability.

The native worker invokes the existing fixed-q pipeline once for every active
q in increasing order. A q change therefore creates and executes a new native
plan rather than silently reusing the previous modulus. It builds and emits
the resulting typed bundles; the supervisor still independently replays and
admits them.

Production contracts are unconditionally rejected before either worker is
launched. Even externally pinned KAT workers cannot turn these receipts into
certified analytic inputs, source evidence, CUDA or trusted-compute
attestation, zero or Turing completeness, or atom discharge.

To keep the checkpoint and control records within their fixed bounds, v2
also rejects a block with more than 64 active bundle targets before launching
the worker. This is a KAT limit, not a proposed source-scale batch size.

## Immutable resume checkpoints

Every successful block produces one canonical file:

```text
block-00000000.checkpoint.json
block-00000001.checkpoint.json
...
```

Each v1 checkpoint contains the exact request and response, its predecessor
checkpoint digest, result-chain transition, and a self-hash. Writers refuse
to replace existing files. Resume reconstructs every formulaic request from
the still-authenticated spool metadata and rejects a substitution, skip,
reorder, malformed filename, or broken chain. Already completed payloads are
not reread. In contrast, bounded v2 rereads, rehashes, replays, and readmits
every staged typed bundle during resume. A production v1 resume additionally
requires the caller to pin the expected checkpoint-chain head; v2 does not
admit production at all.

These hashes are tamper-evident only relative to an externally retained head.
They are not signatures and cannot prevent a privileged attacker from
rewriting an entire unpinned chain. Future confidential-compute evidence must
bind the externally pinned implementation and handshake hashes, the initial
request chain, the terminal result/checkpoint chains, and the output artifact
hashes.

## Explicit target-order reconciliation

The original adapter order is `q_major_then_t_block`. A t-block worker must
respond before receiving the next block, so requiring that order for multiple
q values and multiple blocks would deadlock or require an unbounded hidden
buffer. Protocol v2 instead hash-binds the order
`t_block_major_then_q` in every request and in the adapter admission chain:

```text
block 0: q_start, q_start+1, ...
block 1: q_start, q_start+1, ...
...
```

`TMajorTypedBundleLaneAdapter` retains q-major as its default for existing
manifest users and adds this explicit block-major mode for v2. In either mode
it derives every expected target from the authenticated contract, freshly
replays each bundle, compares its lattice payloads to authenticated t-major
cache rows, and refuses a skip, duplicate, substitution, or reorder before
advancing. Thus the two orders enumerate the same finite target relation, but
their different admission chains remain visible rather than being conflated.

## Exact production boundary

The existing all-character executable exposes a genuinely fixed-`q`
`--framed-service Q ...` process and rejects a modulus change. The existing
pipeline likewise validates one contiguous fixed-q shard. It cannot be
silently repurposed as a t-major multi-q service.

The separate
[`TGDLTMB1` row-resident CUDA component](DIRICHLET_TMAJOR_CUDA_BLOCK.md)
now executes composition for every active q in one t block and emits
self-delimiting `TGDAFFI1` frames. It is not yet a worker for this protocol:
it does not run the all-character/completed-\(L\) stages or emit typed bundles.

The v1 supervisor therefore rejects a production contract unless the worker
has externally pinned implementation and handshake digests and advertises
the complete multi-q service. More importantly, production is still rejected
even when an untrusted worker advertises every capability and returns
plausible counts and hashes. Self-asserted booleans and opaque digests are not
execution evidence.

The bounded v2 supervisor is stricter: it rejects a production contract before
launching the worker, regardless of pins or advertised capabilities.

The bounded v2 path now demonstrates framed-byte receipt, fresh replay,
block-major adapter admission, and actual per-q arithmetic/plan switching.
Production admission remains disabled until the source-scale system:

1. materializes certified (not synthetic KAT) lattice/recovery inputs directly
   from the authenticated source campaign and establishes the source-scale
   resource bounds;
2. persists authenticated per-q completed-\(L\) and zero-isolation state
   across t blocks instead of treating each typed target independently;
3. independently replays or otherwise certifies the discarded composition
   and FFT arithmetic rather than only replaying retained typed receipts;
4. resolves exceptional/indeterminate cases and supplies an accepted Turing
   completeness argument with multiplicities preserved;
5. binds the measured implementation and request/result/artifact chains into
   hardware attestation; and
6. connects the resulting evidence to the Lean trust boundary. No external
   atom is discharged by this worker or supervisor.

The bounded real-service test makes the current boundary visible. The
original narrow synthetic fixture is rejected by the actual FLINT
completed-\(L\) consumer. Replacing each fixture rectangle \([a,b]\) only by
the mathematically justified hull
\([\min(a,0),\max(b,0)]\) makes the real composer, all-character executable,
FLINT consumer, typed-bundle replay, and t-major adapter pass. This tests the
interfaces; the deliberately widened synthetic rectangles are not analytic
evidence.

That real-service KAT is intentionally adjacent to, rather than advertised by,
the structural multi-q worker. The native all-character executable used by
the KAT is fixed-q. Wrapping a single q=10001 invocation in a worker handshake
that claimed multi-q plan switching would obscure the exact incompatibility
the supervisor is meant to expose. The structural worker therefore tests the
t-block scheduling protocol honestly, while the adjacent KAT tests the real
fixed-q component and typed-bundle interfaces honestly.

## Tests and measured host overhead

Run the protocol, adversarial checkpoint, downstream-failure, and production
fail-closed tests with:

```bash
python3 -m unittest -v tests.test_tg_dirichlet_tblock_supervisor
```

When the pinned FLINT and native KAT executables are present, run the actual
component-boundary and protocol-v2 tests with:

```bash
/tmp/tg-flint-venv/bin/python -m unittest -v \
  tests.test_tg_dirichlet_largeq_pipeline.DirichletLargeQPipelineProcessKat
```

The v2 test builds a real fixed-q typed bundle through the existing
FLINT/native pipeline and authenticated t-major row fixture, then proves a
successful transport/replay/admission/resume cycle. It separately injects
bundle-byte substitution, truncation, frame reordering, and a worker lie about
supervisor-only replay/admission. Every attack is rejected before a
checkpoint or final receipt is written.

The native multi-q small KAT covers q=10001 through q=10003 in one block and
injects reversed-q output, substituted bundles, truncation, and a self-hashed
plan-switch lie. The medium KAT covers q=10001 and q=10002 across 65 rows and
two blocks, checks the admitted order `(0,q1),(0,q2),(64,q1),(64,q2)`, checks
the binary q-state before/after chain, and rejects truncated, substituted, or
reordered binary state plus swapped block checkpoints on resume. The storage
KAT additionally rejects sparse-section gaps, overlaps, reordered range
records, nonzero reserved bytes, counter/offset overflow, and noncanonical
byte encodings:

```bash
/tmp/tg-flint-venv/bin/python -m unittest -v \
  tests.test_tg_dirichlet_largeq_pipeline.DirichletLargeQPipelineProcessKat.test_native_multi_q_plan_switch_worker_small_kat_and_attacks \
  tests.test_tg_dirichlet_largeq_pipeline.DirichletLargeQPipelineProcessKat.test_native_multi_q_plan_switch_worker_medium_two_block_order
```

On the local ARM host on 2026-07-23, the original raw-event medium KAT took
about 63.75 seconds. The compact-event version before state persistence took
44.95 seconds. With the earlier aggregate-only binary q-state it took 46.29
seconds and peaked at 121,464 KiB RSS. After exact ambiguity/bracket retention
and the expanded resume attack matrix, it passed in 56.255 seconds (56.33
seconds whole-process wall), peaked at 121,628 KiB RSS, and reported 1,264,448
platform filesystem-output blocks. That counter is cumulative write traffic,
not retained bytes or a portable KiB measure. All of these are bounded KAT
measurements rather than source or H100 projections.

## Storage accounting and source-scale hard gate

Before compact-event output, the retained medium campaign contained 475
regular files totaling exactly
966,228,370 bytes (921.47 MiB); allocated blocks total 967,344,128 bytes.
The measured 2,439,249,920 bytes (2.27 GiB) of filesystem output are 2.52
times the retained bytes because fixture files are created, widened, and then
consumed into new artifacts.

The exact retained breakdown is:

| component | files | logical bytes |
|---|---:|---:|
| cache | 2 | 68,163,856 |
| spool plus receipt | 2 | 68,164,573 |
| per-target lattice inputs | 130 | 156,796,640 |
| per-target lattice outputs | 130 | 40,953,120 |
| per-target finite recovery | 130 | 40,953,640 |
| q-shared root artifacts | 8 | 1,151,411 |
| raw worker event streams | 4 | 589,831,195 |
| other worker pipeline files | 40 | 38,427 |
| worker typed bundles | 4 | 22,140 |
| staged typed-bundle copies | 4 | 22,140 |
| checkpoint JSON | 2 | 24,840 |
| target controls/receipts and campaign metadata | 19 | 106,388 |

Raw event JSON was 61.0% of that pre-compaction retained campaign. This is a deliberately
pathological consequence of zero-hulling the synthetic q=10001 rectangles:
the 65 q=10001 rows produce 589,830,883 event bytes, or
9,074,321.28 bytes per `(q,t)` reference. q=10002 produces only its two
156-byte event headers. This is not a measured production event rate.

Byte comparison also finds the more general duplication problem. Each of the
65 distinct 1,048,576-byte t-row payloads occurs in the cache, the spool, the
q=10001 lattice input, and the q=10002 lattice input. Those four copies occupy
272,629,760 bytes; a row-level content-addressed store would use 68,157,440
bytes and save 204,472,320 bytes in this KAT. Whole-file deduplication saves
only 32,066 bytes because q-specific headers make the larger files differ.

The inventory and deliberately naive projection are reproducible with:

```bash
python3 tools/tg_dirichlet_tblock_storage.py inventory CAMPAIGN_ROOT
python3 tools/tg_dirichlet_tblock_storage.py project CAMPAIGN_ROOT
```

Linearizing this synthetic layout over 4,901,051,274 source row references is
a storage-hazard calculation, not a physical production estimate:

| naively retained artifact | projected bytes |
|---|---:|
| lattice input/output/recovery copies | 8,999,212,328,293,320 (9.00 PB) |
| raw events at the measured two-q mean | 22,236,868,689,997,635 (22.24 PB) |
| raw events at the pathological q=10001 rate | 44,473,713,854,949,153 (44.47 PB) |
| one content-addressed copy of every unique row | 134,205,145,088 (134.21 GB) |

That target-row linearization is not the strongest warning. The exact
large-q base scan has 191,701,043,433,012 primitive-character samples. A
two-bit sign code for each sample would therefore require
47,925,260,858,253 bytes (47.925 TB) before framing. Applying the deliberately
pathological q=10001 raw-JSON bytes per primitive sample gives about 181.5 PB.
Neither number is a production event-rate estimate; both show why per-sample
persistence must not be the production design.

The existing protocol already sends each unique row block once, so its source
row-payload network floor is 134.21 GB rather than a per-q 5.14 PB copy. At
the full-64-row measured bundle size, framed typed-bundle JSON projects to
about 0.664 TB. Raw events are referenced local artifacts rather than framed
stdout payloads, but uploading them to shared Azure storage would inherit the
22--44 PB pathological hazard unless they are reduced at the worker.

The current bounded implementation now has five independent brakes:

1. The native recipe hash-binds a default 640 MiB event limit per target and a
   1 GiB total retained worker-output limit. The event writer checks its byte
   budget before each record is written.
2. The supervisor recovers the event-artifact size from each freshly replayed
   nested receipt, hash-binds that accounting into the artifact/checkpoint
   chain, and independently enforces a 1 GiB cumulative bounded-KAT limit.
3. [`dirichlet_tblock_storage.py`](../../tg_verifier/dirichlet_tblock_storage.py)
   implements immutable SHA-256 chunk reuse and a bounded-memory semantic
   event admission pass. Its production preflight is unconditionally closed.
4. The native worker emits a compact event summary rather than raw NDJSON.
   The summary binds event order, counters, exact fixed-q coverage, and the
   per-character associative boundary state. Raw event records are not needed
   for bounded typed-bundle resume.
5. The supervisor merges adjacent states and stores the result in canonical
   `TGDCSB02`: a 176-byte header, 104-byte character indexes, 16-byte maximal
   ambiguity ranges, and 32-byte ordered brackets. The exact size is
   `176 + 104*C + 16*A + 32*B`. The all-ambiguous q=10001 KAT has `C=A=9,585`
   and `B=0`, so its state is exactly 1,150,376 bytes; q=10002's empty roster
   is exactly 176 bytes.
6. [`dirichlet_compact_state_finalizer.py`](../../tg_verifier/dirichlet_compact_state_finalizer.py)
   freshly replays externally pinned completed lane heads in lane order,
   requires contiguous assignments and monotonically retiring q rosters,
   applies the same associative boundary rule across lanes, and freshly
   replays the final per-q binaries. A three-lane q=10001 synthetic run
   (64 samples per lane) merged three 1,150,376-byte inputs to one
   1,150,376-byte output in 1.427 seconds; whole-process setup plus finalizer
   took 2.20 seconds and 104,620 KiB maximum RSS.

The exact online statistic needed for an ordinary resolved scan is small:
canonical character identity, exact covered sample domain, first and last
determinate ordinate/sign, leading and trailing ambiguity, cumulative sample
and sign counts, and the internal bracket lower count. Those fields compose
associatively; the merge inserts one boundary bracket precisely when the two
outer determinate signs differ. A commitment protects ordering, but is not a
proof that interval arithmetic ran.

Source closure needs more than exact restart state. A refinement worker must
consume the retained ambiguity ranges, retain every
upsampling/Euler--Maclaurin resolution, and produce the paired
Booker/Rumely/Trudgian Turing total-zero count. Direct producer-to-binary
streaming is also still absent: the current supervisor first parses a bounded
JSON character roster and only then writes `TGDCSB02`. More importantly, the
390,000 large-q headers plus 29,547,446,729 fixed character indexes already
require exactly 3,073,003,099,816 bytes (3.073 TB) before one ambiguity range
or bracket. At an illustrative—not exact source count—`3.8e13` brackets,
32-byte bracket records alone would be 1,216,000,000,000,000 bytes. This
source layout is therefore explicitly rejected, not advertised as the final
storage design. Unique t rows must also be integrated into the fixed-q
pipeline as one content-addressed payload plus bounded q sidecars; the CAS
remains only a primitive. Therefore
`source_scale_storage_admitted` remains `false`, and no source-scale
feasibility, zero-completeness, Turing-completeness, Lean, attestation, or
external-atom claim is made.

The separate
[`TGDCSB03` source-streaming path](DIRICHLET_SOURCE_STREAMING_V3.md) now
removes the 104-byte fixed index and does not retain exact bracket coordinates
in production state. It packs four flags plus a canonically sized transition
count per character and retains only maximal ambiguity ranges. The exact
large-q final dense floor is 62.260 GB; all eight lane-head floors total
313.234 GB before per-q/page padding and exceptions. A q finalizer can retain
an aggregate count and sparse exception MMR, then discard dense pages. This
does not change this document's admission result: the arithmetic producer is
not yet fused into v3, source ambiguity density is unmeasured, and the
pointwise lower-bound, exact same-roster Turing, refinement, attestation, and
Lean realization premises remain false.

For two-row blocks, fresh 2-, 3-, and 4-q supervisor runs took 3.60, 5.41,
and 6.39 seconds. Per-target diagnostic timings were:

| q | composer wall (s) | native plan prep (s) | native transform (s) | FLINT consumer wall (s) | pipeline wall (s) |
|---:|---:|---:|---:|---:|---:|
| 10001 | 0.35–0.38 | 0.031 | 0.0010 | 1.09–1.11 | 1.35 |
| 10002 | 0.39–0.40 | 0.152 | 0.0004 | 0.44–0.45 | 0.60–0.61 |
| 10003 | 0.40–0.41 | 0.146 | 0.0008 | 0.96–0.98 | 1.19 |
| 10004 | 0.26 | 0.014 | 0.0006 | 0.45 | 0.62 |

These are explicitly diagnostic KAT timings, not proof evidence or a
source-scale estimate. The component processes are pipelined, so their wall
times overlap and must not be summed to reconstruct pipeline wall time.

Reproduce the control-plane benchmark with:

```bash
python3 tools/benchmark_tg_dirichlet_tblock_supervisor.py \
  --repetitions 5 --io-rows 64
```

On the local ARM host on 2026-07-23, repeated runs put the minimum full-q
histogram construction at `0.216--0.219 s`, all-eight-lane accounting at
about `0.0050 s`, and one 64-MiB structural block at `0.320--0.355 s` through
spool authentication, the subprocess pipe, the row/stream SHA-256 bindings,
response validation, checkpoint fsync, and final receipt
(`180.5--200.1 MiB/s` per unique payload byte). This is a
control-plane/I/O benchmark only. It does not measure CUDA, residue
composition, 76.8 million transforms, completed-\(L\) state, or Turing work,
so it must not be used as the analytic campaign ETA.

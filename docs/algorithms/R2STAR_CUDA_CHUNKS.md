# Bounded exact CUDA chunks for the Ramaré R2Star campaign

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

## Scope

`sparkinterval-tg-r2star-chunk` produces a bounded chunk for the exact Python
contract in `tg_verifier/r2star.py`. The contract suite independently
recomputes every chunk it invokes: factor rows, rational logarithm bounds,
Euler-gamma bounds, coefficient intervals, prefix interval, minimum squared
slack, and canonical record hash. A standalone successful runner receipt only
sets `python_contract_replay_required: true`; it does not claim that replay
already occurred.

This is not a completed run through 21 billion or a discharge of
`ramare_zuniga_2024_lemma_6_2_source`.

The Azure measured workload now packages
`reference/tg_r2star_arithmetic_replay.cpp` as a separate CPU-only checker.
After the GPU campaign finishes, and again during retained-export trace
verification, it reconstructs all 21 billion rows from the integers:

- complete distinct-prime-factor support and its canonical digest;
- the directed Q32 logarithm and coefficient row and its little-endian digest;
- the incoming-to-outgoing prefix interval; and
- the exact squared-envelope minimum and witness.

The checker consumes a strict plan made only from receipt commitments, checks
gap-free range/state geometry before starting, parallelizes independent
million-row chunks across at most 32 CPU workers, and rejects any mismatch.
The supervisor reads the reviewed replayer bytes once, checks their expected
source-closure digest, writes a private read/execute-only captured copy, and
executes that copy. The replay result and retained evidence record the digest
of those exact captured bytes; a later path substitution therefore cannot be
reported as the reviewed executable.
The registered `true` result is unavailable unless this pass succeeds. The
retained archive includes a canonical
`independent-arithmetic-replay.json` record fixing the checker hash, row/chunk
counts, final chain hash, and global minimum; external trace verification
reruns all arithmetic before accepting that record. This closes the earlier
“structural replay only” weakness; it does not replace the still-explicit Lean
realization obligation described below.

## Lean theorem boundary

[`R2StarSourceSemantics.lean`](../../SparkInterval/TernaryGoldbach/R2StarSourceSemantics.lean)
now contains the exact source coefficient, summatory function, and
real-variable Lemma 6.2 proposition. Its kernel-reducible checker validates
gap-free chunk geometry and incoming/outgoing Q32 states. Given explicit
`SourceScaleEvidence`, Lean proves interval-prefix composition, converts the
squared integer guard to the real endpoint inequality, and lifts integer
endpoints to every real `X` by the natural-floor slab argument.

The important remaining refinement is visible as
`ExternalChunkRealization.coefficientRealizes`: every streamed delta must
enclose Mathlib's literal

```text
(vonMangoldt * vonMangoldt)(n) - vonMangoldt(n) * log(n) + 2 * gamma.
```

The CUDA factor-support recurrence and rational log/Euler-gamma routines are
intended to construct that evidence, but their C++-to-Lean refinement is not
yet proved. A hash or minimum-slack summary cannot manufacture it.

[`RegisteredR2StarCertificate.lean`](../../SparkInterval/Execution/RegisteredR2StarCertificate.lean)
adds the closed H100 invocation and signed-success reduction. Only the
existing `accepted_run_certificate_sound` axiom appears at that outer physical
boundary. The invocation admits an honest `"false"` result, so the registered
relation is satisfiable independently of the source claim. No successful
receipt exists yet. The Azure inventory stages the terminal result, exact
`ramareZunigaLemma62ProductionV1` invocation, and source-claim theorem, but
keeps the row disabled: a pre-populated structural hash chain is not authority
for the row computations or their recurrence-to-Mathlib refinement.

The fixed CUDA configuration is:

| Parameter | Value |
| --- | ---: |
| scale bits | 32 |
| atanh-series terms | 20 |
| harmonic terms | 100,000 |
| directed Euler-gamma lower integer | 2,479,051,107 |
| directed Euler-gamma upper integer | 2,479,194,040 |

The two gamma integers are exactly what the arbitrary-precision Python
contract computes for this configuration.

## Exact logarithms with a sparse fallback

For `1 <= x <= 2`, the Python reference uses

```text
z = (x-1)/(x+1)
log(x) = 2 * sum z^(2j+1)/(2j+1)
```

with a positive geometric-tail bound.  The CUDA kernel encloses that same
rational expression in Q64 integer intervals:

- four radix-`2^16` division digits compute exact floor and ceiling bounds for
  `z*2^64` without floating point or an implicit 128-bit division;
- `__umul64hi` and the low product word give exact directed Q64 products;
- every division by an odd series denominator is rounded explicitly;
- the geometric tail uses a rigorous lower bound for `1-z^2`; and
- the exponent and mantissa intervals are accumulated in two-word unsigned
  integers.

The kernel converts Q64 to scale `2^32` only if both ends determine the same
floor for the lower rational bound and the same ceiling for the upper rational
bound. Otherwise it marks the row `log_resolution_ambiguous`. The runner then
recomputes that row using arbitrary-precision integer numerators and
denominators, with exactly the Python series, tail, floor, ceil, factor, and
coefficient formulas. It copies the corrected row back before either CUDA
transition runs. No binary floating-point widening enters this fallback.
For example, `n = 1,364,330` exercises the path and the contract test compares
the resulting chunk with an independent Python replay.

## Transition and overflow boundary

Valid rows reproduce the Python coefficient formulas:

```text
omega(n) = 1:  [-ceil(log(p)_up^2/S), -floor(log(p)_lo^2/S)]
omega(n) = 2:  [ floor(2 log(p)_lo log(q)_lo/S),
                 ceil(2 log(p)_up log(q)_up/S)]
otherwise:     [0, 0]
```

where `S = 2^32`.  Twice the directed Euler-gamma interval is then added.
A deterministic blocked CUDA transition scans 1,024-row local prefixes,
composes their signed incoming offsets with checked additions, evaluates the
envelope rows in parallel, and reduces block minima in index order.  It checks

```text
(100 * max(abs(R_lower), abs(R_upper)))^2
  <= 193^2 * n * log(n)_lower^2.
```

Every signed prefix addition is guarded before evaluation.  The left side is
accepted only when `100*magnitude` fits `u64`; its square then fits `u128`.
For the source range, `log(n)_lower < 2^37`, so the right-side coarse maximum

```text
193^2 * 21,000,000,000 * (2^37)^2 < 2^128
```

fits the checked two-word multiplication.  Every intermediate multiplication
still has an explicit overflow test.  A successful chunk therefore has no
unreported machine-integer wraparound.  This does not assume the theorem to
bound the prefix: an out-of-range incoming or intermediate state simply
rejects.

The original one-thread transition remains available behind
`--cross-check-serial`.  The contract suite compares every summary field
across internal block boundaries, including a negative incoming state.  A
synthetic known-answer test makes every endpoint's squared slack equal to zero
across three blocks and checks that strict ordered reduction retains the
earliest witness, `n = 3`.  Block-total and per-row signed additions are
checked before use; an overflow rejects rather than wrapping.

Scale 40 was not selected.  At the source endpoint the claimed bound itself
can occupy about 79% of signed 64-bit range, versus about 0.31% at scale 32.
It also leaves only 24 Q64 guard bits, causing far more unresolved rounding
rows.  Scale 32 gives substantially clearer overflow and resolution margins.

## Hash compatibility and composability

The GPU factor record retains the first two factors and caps `omega` at three,
which is enough for the coefficient. The receipt's factor-support digest is
stronger: a separate host segmented sieve divides every row by every base
prime, retains every distinct factor (up to the proved source-range maximum of
ten), and emits them using Python's exact encoding

```text
"r2star-distinct-prime-support-u64be-v1" NUL
u64be(n) | u64be(factor_count) | factor_count * u64be(factor)
```

and checks that each capped GPU record agrees.  The chunk body is serialized
with exactly Python's sorted compact JSON spelling before SHA-256.  Tests feed
the resulting fields directly to `R2StarChunk` and verify them with the
arbitrary-precision Python implementation.

`previous_hash`, the incoming interval, and the half-open range make chunks
composable.  SHA-256 provides deterministic integrity and linkage, not
authentication or evidence of a particular physical GPU execution.

## Commands and measured boundary

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --target sparkinterval-tg-r2star-chunk

./build/dgx-spark/sparkinterval-tg-r2star-chunk \
  --lower 1 --count 64

python3 tests/tg_r2star_cuda_chunk_contract.py \
  --runner build/dgx-spark/sparkinterval-tg-r2star-chunk
```

The direct binary permits at most 64 rows outside the measured-worker scope.
The C++ boundary checks the same four runner-reserved environment fields as
the Python dispatch layer. This is accidental-execution hygiene, not security:
the independently appraised measured transcript and signed receipt remain the
security evidence.

The full-source supervisor runs inside the measured Azure job. It captures and
hashes the runner, verifies every receipt before atomically retaining it, and
resumes only from the complete gap-free hash/state prefix. The following are
production-worker commands, not local-build instructions:

```bash
python3 tools/tg_r2star_campaign.py run \
  --runner build/dgx-spark/sparkinterval-tg-r2star-chunk \
  --output-dir /durable/r2star-21b \
  --segment-count 1000000

python3 tools/tg_r2star_campaign.py verify /durable/r2star-21b

python3 tools/tg_r2star_campaign.py verify-arithmetic \
  /durable/r2star-21b \
  --arithmetic-replayer \
  build/dgx-spark/sparkinterval-tg-r2star-arithmetic-replay \
  --replay-threads 32 \
  --registered-result-output /durable/r2star-21b/registered-result.txt
```

For a local bounded component check, use at most 64 rows. Larger benchmarks
also require measured-worker scope:

```bash
python3 tools/tg_r2star_benchmark.py \
  --runner build/dgx-spark/sparkinterval-tg-r2star-chunk \
  --arithmetic-replayer \
  build/dgx-spark/sparkinterval-tg-r2star-arithmetic-replay \
  --lower 1 \
  --count 64 \
  --repetitions 1
```

The native benchmark plan has its own wire header and returns
`status: BENCHMARK_ONLY`; the registered-result checker accepts neither that
header nor that status. The benchmark report also fixes
`admissible_as_external_atom_evidence: false` and
`target_sku_measurement: false`.

Within the measured worker, use `--max-chunks N` for a clean bounded stop.
Running the same command later with the identical runner and configuration
resumes at the first missing chunk. The retained chain's hashes provide
integrity, not authentication; the signed measured-run receipt supplies the
authenticated execution boundary and does not by itself discharge Lean.
`verify-arithmetic` exposes `--registered-result-output`; `run` accepts it only
as an inseparable pair with `--arithmetic-replayer`, and structural `verify`
does not accept it. The registered result is created exclusively, contains the
canonical four bytes `true`, and is refused until the literal 21-billion
endpoint, final hash, minimum endpoint guard, and complete independent CPU row
replay are present. Its Lean meaning still passes through the single
registered trusted-compute axiom; the writer does not claim an independent
row-by-row C++-to-Lean refinement.

After the segmented host pass was added, fresh one-million-row GB10 runs on
2026-07-20 took 1.02 seconds at `[1,1000001)` and 1.06 seconds at the final
million-row source block. The high block used one exact rational fallback;
its segmented factor comparison and hashing took 582 ms, while the three CUDA
kernel phases totaled about 6.54 ms. Linear extrapolation is roughly 6.2 hours
for 21,000 chunks before durable-storage and supervisor overhead. That is a
planning estimate, not a completed campaign or an H100 measurement.

On 2026-07-23, the fail-closed benchmark command ran three repetitions at both
ends of the source interval on GB10. Producer medians were 1.003546042 s for
`[1,1000001)` and 1.036697658 s for
`[20999000001,21000000001)`. Independent one-thread CPU replay medians were
0.921640459 s and 0.897319285 s, respectively. The corresponding linear
sensitivities are 5.85--6.05 hours for the serial producer and 5.23--5.38
single-thread hours for replay. The source-scale replayer can assign distinct
million-row chunks to up to 32 workers, but no ideal scaling claim is made.
These are bounded local component measurements, not an H100 measurement or
external-atom evidence.

### Bounded ordered-segment CPU replay candidate

The independent CPU replayer now has an opt-in
`--segment-rows N` candidate.  Omitting that option preserves the reviewed
serial-per-chunk implementation.  In candidate mode each segment independently
reconstructs complete factor support and the same directed Q32 rows.  A
read-only cache reuses directed log intervals for base primes and for a prime
row's already-computed `log n`; it also retains the exact-fallback bit, so
reuse cannot erase an ambiguous Q64-to-Q32 conversion.

Completed segments are stored by ordinal.  Before merging them,
`is_exact_r2star_replay_partition` requires the exact ordinal and endpoint
partition of the retained chunk.  The factor-support bytes, directed-row
bytes, and prefix/envelope transition are then three independent folds, each
consumed strictly in source order.  The folds may run concurrently, but no
segment chooses an incoming prefix.  They must reproduce the unchanged
whole-chunk factor SHA-256, row SHA-256, outgoing interval, minimum squared
slack and index, and exact-fallback count.  The output report is byte-for-byte
the same as the nonsegmented replayer.

The bounded KAT
`tg_r2star_replay_segment_partition_known_answers` rejects reordering,
omission, a mutated/gapped endpoint, overlap, and duplicate ordinals.
`tests.test_tg_r2star_arithmetic_replay` additionally compares serial and
segmented stdout bytes and checks fail-closed mutations of both digests, the
outgoing state, the minimum witness, and the fallback count.  These checks
exercise the optimization boundary; they are not a C++-to-Lean realization
theorem.

The ordinary Lean module
`SparkInterval.TernaryGoldbach.R2StarReplaySegmentation` proves the matching
architecture-independent identity:
`foldSegments state segments = foldRows state segments.flatten`.  It also
derives equality of terminal states for any two ordered partitions with the
same flattening.  Fresh `#print axioms` checks for all three supporting
theorems report no axioms.  This proves the grouping
identity, not that a physical C++ segment contains the claimed Lean rows or
that an Azure execution occurred.

On 2026-07-25, seven repetitions on the local 20-core DGX Spark CPU used
`--threads 16 --segment-rows 2048`.  The million-row low and terminal plans
were the exact retained CUDA commitments.  Locally supplied measured-worker
guard variables only allowed the bounded timing run; they are not
authentication or Azure evidence.

| million-row plan | serial median | segmented median | speedup | linear 21-billion-row sensitivity |
|---|---:|---:|---:|---:|
| `[1,1000001)` | `0.926998326 s` | `0.249986601 s` | `3.7082x` | `5.407 h` serial / `1.458 h` segmented |
| `[20999000001,21000000001)` | `0.898988396 s` | `0.279385579 s` | `3.2177x` | `5.244 h` serial / `1.630 h` segmented |

Because a complete plan has many chunks, its 32-thread scheduler normally
assigns one inner thread to each of 32 chunks.  A separate seven-repeat
one-thread check of the final candidate therefore compared the relevant path:
low-range `0.926998326 s` serial versus `0.702859939 s` segmented
(`1.3189x`), and terminal `0.898988396 s` versus `0.733981331 s`
(`1.2248x`).  Thus `2048` does not regress either bounded endpoint in the
production scheduler's one-thread-per-chunk regime, but a full multi-chunk
target-SKU check remains necessary.

The production path is wired to this candidate rather than leaving it as an
unreachable benchmark flag.  `verify_campaign_arithmetic` and
`write_registered_result` default to `2048`; `tg_r2star_campaign.py` exposes
`--replay-segment-rows` and maps the explicit value `0` back to the serial
reference.  The closed measured workload pins `2048`.  Both its arithmetic
replay evidence and the registered-result metadata record the thread count
and segment-row choice, so a later appraisal can distinguish the optimized
and serial executions.

The optimized binary SHA-256 was
`5e4dfc622e6f4b288a5a5c005fe83fd7bfd8925e9e9130724380bc7c192392cb`.
The low and terminal plan SHA-256 values were respectively
`9d2e632157106451a9ff03b6355250886416f5f9f2cb91c3afe4195987119579`
and
`e7be93709ab4f3aea5c599952317241ab1d50247ed1cf192159e068c1a19242c`.
The terminal optimized run used `131016 KiB` maximum RSS in one
`/usr/bin/time` sample.

This is a linear, bounded component sensitivity.  It is not a full-source
run, a target Azure CPU or H100 measurement, a retained confidential-compute
receipt, a Lean realization, or discharge of the R2Star atom.  In particular,
the source plan has many chunks and can instead spend its thread budget across
chunks; end-to-end scheduling, memory, storage, and attestation overhead still
need a target-SKU pilot.

The production factory creates one terminal job on one NCC H100 node, not
eight independent source shards: each chunk's incoming interval depends on
the previous chunk. The present Azure planning band is therefore 1--8
uncalibrated node-hours with a parallelism cap of one. At the pinned planning
prices this is `$6.98`--`$55.84` PAYG or `$1.42`--`$11.35` Spot for compute
only; storage, retries, evidence collection, and capacity are excluded. A
target-SKU pilot must replace that sensitivity before the route can be
promoted.

The remaining production work is concrete:

1. run and retain the complete gap-free chain and its now-mandatory full CPU
   arithmetic replay; and
2. construct the registered Lean `Certificate` and `SourceScaleEvidence` from
   the measured output, including the explicit proof/refinement that the
   factor-support recurrence and directed transcendental enclosures satisfy
   `coefficientRealizes` and `logLowerRealizes`.

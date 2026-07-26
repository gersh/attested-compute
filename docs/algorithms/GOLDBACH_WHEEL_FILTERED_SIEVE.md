# Goldbach cofactor-filtered sieve tail

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is an exact, composable source post-transform for the diagnostic
word-owner + warp-tail + shifted-coverage GoldbachGPU path. It does not change
the reviewed production source, production hashes, or receipt identity. It
has passed bounded differential checks on the local NVIDIA GB10, but it is not
a source-scale verification or an H100 measurement.

The current content-addressed source/binary qualification, fixed-answer KATs,
SM90 PTX/SASS lexical audits, and H100 calibration package are documented in
[`GOLDBACH_OPTIMIZED_CANDIDATE_QUALIFICATION.md`](GOLDBACH_OPTIMIZED_CANDIDATE_QUALIFICATION.md).

The retained measured choice is:

```text
word-owner cutoff       2039
warp-parallel cutoff   32749
cofactor filter limit     47
```

## Why an atomic can be omitted

The word-owner initializer has already cleared every odd candidate divisible
by each prime through `2039`. A later tail-prime progression term has the
form

```text
candidate = p * k,       p > 2039, k > 0.
```

If `k` is divisible by one of

```text
3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
```

then that small prime also divides `candidate`. It is at most both `p` and
`k`, so its square is at most `p*k`; the word-owner square guard has therefore
already cleared the bit. Skipping the later global `atomicAnd` changes no
bit.

The CUDA predicate uses one `k mod 15015` reduction for
`3*5*7*11*13` and direct constant-modulus tests for the remaining primes.
The kernel does not divide `candidate` to recover `k`: the original first
multiple calculation already supplies the quotient, the tail progression
updates it by `2`, and warp rounds update each lane's quotient by `64`.

[`GoldbachWheelFilter.lean`](../../SparkInterval/TernaryGoldbach/GoldbachWheelFilter.lean)
proves:

- the remainder predicate is equivalent to divisibility by the selected
  filter primes;
- the `+2` tail and `+64` warp cofactor equations; and
- every rejected tail event satisfies the existing `ClearedBy` predicate,
  including its square guard.

The Lean declarations use only standard Mathlib/Lean axioms reported by their
fresh `#print axioms`; there is no `sorryAx`.

[`GoldbachAtomicClears.lean`](../../SparkInterval/TernaryGoldbach/GoldbachAtomicClears.lean)
then models each packed-word `atomicAnd` as one linearizable bit clear.  It
proves that every serialization order has the same final word and that
removing the wheel-rejected events is exact once the word-owner initializer
realizes its proved `ClearedBy` set.  This closes the concurrent clear-set
algorithm; compiler refinement and the hardware linearizability contract
remain explicit physical obligations.

## Source and qualification paths

The post-transform and its fail-closed full-word crosscheck are in:

- `tg_verifier/goldbach_wheel_filtered_tail_optimizer.py`;
- `tools/benchmark_goldbach_wheel_filter.py`;
- `gpu/platform/h100/h100_tg_goldbach_wheel_filter_kat.cu`; and
- `tools/run_goldbach_wheel_filter_kat.py`.

`rewrite_wheel_filtered_sieve` accepts the output of the independent
word-owner, warp-tail, and shifted-coverage transforms. It checks unique
source markers and leaves every production identity untouched.

`rewrite_wheel_filtered_sieve_crosscheck` allocates an independent reference
prime window, runs the original unfiltered warp/tail kernels and the filtered
kernels, and compares every live packed word before phase 1. On the exact
terminal 600-million-even benchmark

```text
[31249998800000002, 31250000000000000]
```

all three 200-million-even segments matched word for word. The crosscheck
source SHA-256 was

```text
f87c3c8753f326c583ea613e2d9bf70969a1ad30b75b6c0c98a39b5cf242b660
```

and it completed with zero phase-2 fallbacks.

The independent CUDA KAT compares:

1. a CPU arithmetic-progression replay;
2. the unfiltered CUDA global-atomic sieve; and
3. the filtered CUDA warp/tail partition.

It checks four 262,144-odd windows, including a `p^2` activation range, the
source-height magnitude, and a final window ending exactly at `UINT64_MAX`.
The filter-47 run passed on compute capability 12.1 with these FNV-1a word
digests:

```text
c5a02e2b2bb2b0d0
869bd81a9a1827a4
bb99908cdab9d2e6
ac6c9b891d576bbb
```

The KAT source SHA-256 was
`cd9d07cf8d62fe43cac0e14050cd0a50a44f4a704301428a04df049b0330bf22`.

Compute Sanitizer memcheck also ran the retained filter-47 executable over
the complete 600-million-even range and reported:

```text
Phase 2 fallbacks      : 0
ERROR SUMMARY: 0 errors
```

These are regression and differential evidence, not a proof that a compiled
CUDA binary refines the Lean model.

## GB10 measurements

All confirmation rows used two warmups and seven timed executions of the
exact terminal range. The source tool validates the exact range, count,
success sentence, primality mode, and zero fallback count on every run.

| Variant | Median seconds | Rate versus same-session control |
| --- | ---: | ---: |
| unfiltered cutoff 32749 | 0.363824 | 1.00000x |
| filter through 13 | 0.287481 | 1.26556x |
| filter through 19 | 0.286507 | 1.26986x |
| filter through 47 | **0.273041** | **1.33249x** |

The filter-47 median is about 2.197 billion evens/s on this bounded GB10
sample. One run was a 0.409196-second scheduling outlier; the other six were
between 0.269773 and 0.276690 seconds, so the median is not determined by the
outlier.

A runtime reciprocal replacement for per-prime 64-bit division was also
tested and rejected: its seven-run median was 0.347522 seconds against a
0.343505-second same-session control. That unsuccessful transform was not
retained.

## Integrated packed-coverage result

The filter now composes with the warp-through-32749, shifted-word phase-1,
and packed missing-bit-count transforms.  The two possible orders of the
wheel filter and packed-count transforms generate byte-identical source.  A
seven-run same-process comparison over the exact 600-million-even terminal
range measured:

| Variant | Median seconds | Rate versus baseline |
| --- | ---: | ---: |
| prepared hardened baseline | 0.636503 | 1.00000x |
| warp + shifted phase 1 + packed count | 0.362684 | 1.75498x |
| wheel-47 + warp + shifted phase 1 + packed count | **0.267971** | **2.37527x** |

The integrated generated source SHA-256 is
`2e4eedcf9d301c454c3e0174cccbe0f7a7a11350475ec8d681515d2a7ded333c`;
the retained bounded executable SHA-256 is
`5da352def17a1cec599cbeef1113f0aadbb15bbca41a833feba83674f1a64bd8`.
That executable was the earlier ad hoc benchmark build. The reproducible
qualification build has a separately documented exact pin. Neither is a
registered production identity.

A single unified diagnostic independently executes the unfiltered and
filtered sieve, the original and shifted phase-1 kernels, and the byte and
packed missing-bit counters.  It compares every sieve word, every live
phase-1 bit, and both exact counts before acceptance.  Its generated source
SHA-256 is
`7baa018b8e9d2a724c7808c2c5aaca4c98024d673baa3bb0104094c66ac33c67`.
It accepted all 20,000,000,000 evens in the 100-segment terminal test with no
mismatch and zero fallback.  Compute Sanitizer separately ran the productive
integrated executable over all 600,000,000 terminal evens and reported zero
errors.  The low-boundary 600-million-even range and a 600,000,123-even
non-word-aligned terminal range also passed.

Three 100-segment productive runs took `2.38136`, `2.27927`, and
`2.41579` seconds of computation.  A second unprofiled repeat set took
`2.36017`, `2.32496`, and `2.35908` seconds; its median is
`8.4779` billion evens/s.  Using that repeat median and the largest
initialization seen in the first set (`0.427747` seconds) for every leaf,
eight equal-throughput GB10 GPUs, and no H100 speedup gives an arithmetic
envelope of:

- `64.9675` wall hours (`2.7070` days);
- `$3,627.79` at the checked on-demand cluster price; and
- `$737.53` at the checked spot cluster price.

An independent later spot check measured `0.269137` seconds for the
600-million-even terminal range and `2.32627` seconds for 20 billion terminal
evens, or `8.597` billion evens/s, with `0.436` seconds of initialization.
These remain bounded GB10 observations. The H100 calibration workload records
whole-process wall time so its projection can additionally charge residual
process overhead, as well as initialization, once per checkpoint leaf.

The projection excludes scheduling, confidential attestation, retries,
storage, and final replay.  Its machine-readable result continues to set
`production_gate_passed=false`, `target_h100_measured=false`, and
`source_identity_promoted=false`.

`tools/prepare_goldbach_gpu_optimized.py` now materializes this exact
candidate from a freshly verified output of `tools/prepare_goldbach_gpu.py`.
It fixes the warp and wheel cutoffs, applies all four transforms, requires the
generated `goldbach.cu` SHA-256 above and exact `71,853`-byte size, binds the
transformer-module identities and complete output closure, and either creates
an absent destination or revalidates an identical one.  Its report
deliberately retains:

```text
classification = qualified-source-candidate-not-production-registration
production_identity_promoted = false
target_h100_measured = false
execution_attested = false
lean_claim_discharged = false
```

This removes `/tmp` benchmark trees from the reproducibility boundary without
prematurely registering the source for production.

```bash
python3 tools/prepare_goldbach_gpu.py \
  /pinned/goldbach-gpu /work/goldbach-hardened
python3 tools/prepare_goldbach_gpu_optimized.py --pretty \
  /work/goldbach-hardened /work/goldbach-wheel47-candidate
```

The 20-billion-even Nsight profile attributed `2.066887392 s` of summed GPU
kernel time as follows: `1.076293 s` (`52.1%`) to the remaining atomic tail,
`0.451043 s` (`21.8%`) to word-owner initialization, `0.338024 s` (`16.4%`)
to the warp sieve, `0.192289 s` (`9.3%`) to shifted coverage, and
`0.009239 s` (`0.4%`) to packed counting.  A grouped-residue tail experiment
improved its seven-run median by only `0.069%`, within noise, and was removed.

A structural race-free alternative was also rejected after an exact terminal
segment feasibility run.  That segment contained `120,704,837` raw tail
visits, `33,478,814` wheel-filtered events, and `24,546,194` unique cleared
bits; `8,932,620` events (`26.681%`) were duplicates.  A two-pass
count/scan/fill plus CUB radix sort and exclusive word-leader reduction needed
`561.7 MiB` and a seven-run median of `11.228 ms`, versus `10.763 ms` for the
existing atomic tail.  It was already `2.25%` slower before integration
overhead, while the acceptance gate required a tail at or below `10.143 ms`
for a three-percent whole-run improvement.  The prototype exactly matched
the independent `33,478,814` event count and reported no bounds error, but was
deleted after failing this performance gate.  The retained atomic route is
therefore the faster measured design; its order independence and redundant
clear elimination are modeled in
`SparkInterval.TernaryGoldbach.GoldbachAtomicClears`.

A later exact CTA-local hash-combiner experiment is documented in
[`GOLDBACH_TAIL_COMBINER_QUALIFICATION.md`](GOLDBACH_TAIL_COMBINER_QUALIFICATION.md).
On the same complete terminal-segment geometry it combined away only
`55,584` of `33,478,814` wheel-surviving events (`0.166027%`) and was
`1.14376x` as slow by the median of three nine-run interleaved GB10 sessions.
It therefore remains macro-off and unpromoted.

A later wheel-gap enumerator experiment is documented in
[`GOLDBACH_WHEEL_GAP_TAIL_QUALIFICATION.md`](GOLDBACH_WHEEL_GAP_TAIL_QUALIFICATION.md).
Its modulus-30030 lookup and optional running 17-through-47 remainders exactly
matched the CPU, raw CUDA, and current wheel-through-47 output on the complete
terminal-segment and three-window terminal-600-million geometries.  Repeated
whole-tail timings crossed between faster and slower than the current kernel,
however, with all differences under one percent on the larger geometry.  It
therefore also remains macro-off and unpromoted.

## Remaining verification boundary

Before promotion, the project still needs:

1. source-height and target-shard H100 confidential-mode measurements;
2. semantic review of emitted PTX and SASS beyond the completed lexical
   atomic-width, kernel-set, popcount, and resource audit, including division
   lowering and all overflow branches;
3. a compiler/architecture refinement connecting that binary to the Lean
   cofactor and packed-bit equations;
4. source-scale checkpoint and receipt qualification; and
5. a new registered algorithm identity only after those checks.

The current result narrows the mathematical optimization to a simple
human-auditable statement: an omitted `p*k` clear is already supplied by a
small divisor of `k`.

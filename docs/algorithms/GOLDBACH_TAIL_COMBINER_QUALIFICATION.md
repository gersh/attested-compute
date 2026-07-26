# Goldbach CTA-local tail-combiner qualification

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Outcome

The exact CTA-local combiner is correct on the bounded and historical-segment
qualification corpus, but it is **not a performance candidate on the local
NVIDIA GB10**.  On one complete historical terminal segment it eliminated
only `55,584` of `33,478,814` wheel-surviving global clear events
(`0.166027%`).  Across three independent sessions of nine interleaved runs,
the median of session medians was `11.064320 ms`, versus `9.673632 ms` for
the ordinary atomic tail: the candidate was `1.14376x` as slow.  It remains
macro-off, qualification-only, and unpromoted.  This is not an H100
measurement.

The result explains why a global event sort could observe substantial
duplicate work while a CTA-local combiner does not: consecutive prime-owner
threads almost never target the same 64-bit word in the same two-event epoch.
The local table emits `33,423,230` global atomics, or `99.833973%` of the
ordinary event count, before paying its shared hashing and barrier cost.

## Isolation from production

The experiment consists only of:

- `gpu/platform/h100/h100_tg_goldbach_tail_combiner_qualification.cu`;
- `tools/qualify_goldbach_tail_combiner.py`; and
- `tests/test_goldbach_tail_combiner_qualification.py`.

The CUDA source fails compilation unless
`SPARKINTERVAL_ENABLE_GOLDBACH_TAIL_COMBINER_QUALIFICATION` is explicitly
defined.  The runner defines that macro.  CMake does not mention it, no
default target builds it, and none of the prepared or optimized GoldbachGPU
source transformers imports it.  Consequently no production body, source
hash, artifact pin, registration, campaign default, or receipt identity
changes.

Every result retains:

```text
lean_bridge_complete          = false
performance_evidence_eligible = false
production_identity_promoted  = false
production_ready              = false
runtime_instrumentation_status = not-inspected-by-runner
```

The last field is intentionally honest: an ordinary direct run does not
become sanitizer evidence merely because it used an optimized build.

## Exact routing rule

The ordinary tail associates each wheel-surviving progression event with

```text
(wordIndex, clearMask)
```

where `clearMask = ~(1 << bitWithinWord)`.  A 256-thread CTA advances at most
two events per prime-owner thread in one uniform epoch.  Its 512 exact-key
shared slots begin as `(EMPTY, ~0)`.

For each eligible event:

1. open addressing uses `atomicCAS` to find either `EMPTY` or the identical
   `wordIndex`;
2. a successful event contributes exactly once with shared
   `atomicAnd(slotMask, clearMask)`;
3. an event that exhausts all active slots performs exactly one unchanged
   global `atomicAnd(words + wordIndex, clearMask)` fallback;
4. after a CTA barrier, one thread per occupied slot performs exactly one
   global `atomicAnd(words + key, slotMask)`; and
5. a second barrier precedes resetting the table.

Keys never change between publication and flush.  Masks are initialized to
all ones before keys can be published.  There is no event buffer, drop
branch, overwrite branch, or capacity-dependent acceptance.  The executable
checks the exact accounting equation

```text
eligible_event_count =
  combined_event_count + fallback_event_count
```

and independently requires CPU, ordinary CUDA, and combined CUDA equality
for every output word.

This is the concrete schedule corresponding to the Lean-facing algebraic
boundary: a permutation of individual clear events into exact keyed batches
plus unchanged fallback events, followed by the fact that ANDing one
combined mask equals applying its individual clear masks.  The remaining
boundary is the physical CUDA/compiler realization and an authenticated
artifact/run binding; the qualification does not claim either.

## Lean algorithm boundary

[`GoldbachAtomicBatching.lean`](../../SparkInterval/TernaryGoldbach/GoldbachAtomicBatching.lean)
proves the abstract bounded algorithm with only Lean's foundational trio.
In particular:

- `applyClearMask_eq_runClears` proves that one keyed AND mask has the same
  bit semantics as its represented individual clears;
- `partitioned_batch_schedule_eq` accepts an explicit `List.Perm` coverage
  premise for arbitrary combined entries plus fallback; and
- `bounded_batch_schedule_eq` proves that the pure `batchStream` bounded-table
  algorithm itself supplies exact once-only coverage, including the
  full-table fallback.

The CUDA counters and whole-word equality are runtime qualification evidence;
they are **not** a formal proof that physical keys, masks, or events realize
the Lean lists, and they do not manufacture the `List.Perm` premise.  A
physical refinement would still have to prove:

1. the copied prime roster and each guarded arithmetic progression enumerate
   exactly the intended `AddressedClear` events, including the wheel filter,
   `p²` replacement, word/bit division, and all `uint64_t` bounds;
2. every successful physical probe publishes the exact immutable word key
   and ANDs the exact bit mask, while exhaustive probing takes the fallback
   exactly once;
3. shared-memory atomic ordering and both CTA barriers make every mask update
   visible before exactly one occupied-slot flush and before table reset;
4. physical 64-bit global `atomicAnd` operations are linearizable at the
   modeled word address and preserve every pre-existing clear;
5. CUDA compilation through PTX and SASS, the driver, and the target
   architecture realize those source operations; and
6. an authenticated run binds the reviewed source/compiler/device artifact,
   exact input roster and geometry, and complete output.

Those gaps are why `lean_bridge_complete=false` remains mandatory even though
the abstract algorithm and the runtime differential checks are both green.

## Differential and mutation coverage

Five fixed-answer cases use an independently generated exact prime roster and
an independent CPU arithmetic-progression replay:

| Case | Purpose | Eligible events | Fallback requirement |
| --- | --- | ---: | --- |
| prime-square activation | checks the `p²` replacement boundary | 2 | zero |
| source-height normal | ordinary exact-key locality | 13,217 | zero |
| forced collision | all keys begin probing at slot zero | 13,217 | zero |
| forced full table | only eight slots, so both routes must occur | 13,217 | positive |
| `UINT64_MAX` edge | subtraction-form termination and overflow guards | 13,408 | zero |

The forced-collision and forced-full-table cases start from a patterned,
partially cleared word array.  They have the same expected SHA-256,
`064ae7ae298ff1d13feede4ae154b41e9a66387508ce3d9310277835d13d6774`,
which checks both exact fallback behavior and preservation of pre-cleared
bits.  The edge case ends exactly at `18446744073709551615`.

The Python validator pins all five canonical geometries, set-bit counts, and
whole-output SHA-256 values.  It rejects unknown fields, changed source
boundaries, malformed resource claims, lost/duplicated event accounting,
unexercised collision/fallback paths, altered timings, and any promotion or
Lean-closure flag.  Focused unit tests mutate each of those classes.

## Historical terminal-segment measurement

Run the bounded suite and the full terminal-segment tail measurement with:

```bash
python3 tools/qualify_goldbach_tail_combiner.py \
  --source-segment --pretty --out /tmp/goldbach-tail-combiner.json
```

The source-shaped measurement fixes:

- `q_low = 31249999599000003`;
- `q_high = 31250000000000001`;
- `200,500,000` odd values (`3,132,813` 64-bit words);
- every tail prime in `(32749, floor(sqrt(q_high))]`;
- `9,856,924` exact tail primes; and
- `33,478,814` wheel-surviving events.

The last count independently reproduces the previously reported event count
for this terminal segment.  Every one of the `3,132,813` output words matched
the CPU replay and ordinary CUDA output, with canonical little-endian
SHA-256
`38d96197eced197c443261c23f35fd2c37ede59e2add9d5c82e15d0d2e4e0428`.
The nine timings alternate launch order between ordinary and candidate
kernels.  Memory copies, prime generation, independent CPU replay, and the
instrumented locality pass are outside the reported kernel times.

Three independent local sessions reported:

| Session | Ordinary median | Candidate median | Candidate / ordinary |
| --- | ---: | ---: | ---: |
| 1 | `9.826336 ms` | `11.033952 ms` | `1.122896x` |
| 2 | `9.673632 ms` | `11.213056 ms` | `1.159136x` |
| 3 | `9.499072 ms` | `11.064320 ms` | `1.164779x` |

The median-of-session-medians ratio is `1.143761x`.  No timing value is used
to establish semantic acceptance.

The measured report is local evidence, not a checked-in dependency.  Timing
is not an admission condition.  In particular, no speedup is inferred from
the much smaller bounded workload or from sanitizer-instrumented execution.

## Resource and sanitizer checks

The local SM 12.1 Release build reports:

| Kernel | Registers/thread | Static shared | Local/thread | Max threads |
| --- | ---: | ---: | ---: | ---: |
| ordinary tail | 38 | 0 | 0 | 1024 |
| uninstrumented combiner | 40 | 8192 bytes | 0 | 1024 |

The separately compiled strict SM90 artifact contains only `sm_90` cubins.
`ptxas` reports 30 registers, one barrier, 8192 bytes shared memory, zero
stack, and zero spills for the uninstrumented SM90 combiner; the instrumented
variant uses 32 registers.  This is compilation/resource evidence, not an
H100 runtime result.

Bounded Compute Sanitizer runs completed with:

```text
memcheck:  ERROR SUMMARY: 0 errors
initcheck: ERROR SUMMARY: 0 errors
racecheck: 0 hazards displayed (0 errors, 0 warnings)
```

Sanitizer timings are deliberately ignored.

## Decision and next optimization target

Do not integrate or promote this combiner.  The exact locality histogram
shows that same-word CTA batching attacks too little of the `52.1%` tail
kernel cost.  A useful next tail experiment must change event locality or
remove work before global emission—without reintroducing the repeated-prime
cost that made the earlier tiled design unattractive.  Any such experiment
needs its own source identity, exact CPU/ordinary-CUDA differential corpus,
overflow and capacity mutations, compiler-resource gate, and interleaved
whole-tail measurement before consideration.

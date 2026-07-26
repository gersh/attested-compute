# Race-free tile-compacted odd-prime sieve

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is an exact, bounded prototype for the binary-Goldbach prime-window
producer. It is not a verification through `4*10^18`, is not registered, and
emits `source_scale_completed=false` and `receipt_eligible=false`. Its purpose
is to replace the persistent sieve's unsynchronized same-value byte stores
with an execution path whose write ownership can be checked directly.

The prototype passes an independent CPU known-answer comparison and a
source-height replay, but the measured end-to-end rate remains far below a
practical Azure campaign. It does not alter the registered Goldbach v1
algorithm or any source semantic binding.

## Exact finite equation

For a window beginning at odd `oddLow`, bit `j` represents

```text
q(j) = oddLow + 2*j,       0 <= j < W.
```

For each odd prime `p <= floor(sqrt(lastCandidate))`, the first position is

```text
j0 = (max(p*p, least odd multiple of p >= oddLow) - oddLow) / 2,
```

and the composite positions are exactly `j0 + k*p`. The executable rejects a
base-prime bound below the required square root. The `p*p` guard preserves the
bit for `p` when a campaign begins near one.

The implementation retains the persistent dense/sparse prime schedule from
the bucketed prototype, then performs four GPU stages for each segment:

1. count the compacted `(tile, localOffset, stride)` events;
2. construct checked CSR tile ranges by an exact prefix sum;
3. fill those disjoint ranges; and
4. launch one CUDA block per tile, replaying its events into packed shared
   words.

The base wheel primes `3, 5, 7, 11, 13` are cleared by the unique lane owning
each packed word. All compacted events use 64-bit shared-memory `atomicAnd`,
then a barrier. After that barrier, exactly one lane writes each global
`uint64_t` output word. Initialization is also word-owned. Thus the reviewed
path has no unsynchronized colliding shared-word clear. CUDA 13 PTX for the
GB10 build contains `atom.shared.and.b64` for event clears and one
`st.global.u64` owner store per output word.

For a dense prime, the number of tile records is bounded by

```text
min(tileCount, ceil(W / p)).
```

Each sparse prime contributes at most one record in a segment. The host sums
these integer bounds before allocating the event array, rejects a bound above
`uint32_t`, and makes an overflow flag fail closed in both producer kernels.

## Files and checks

The reviewed pieces are:

* `gpu/platform/h100/h100_tg_goldbach_tile_sieve.cu`: scheduler integration,
  two-pass compaction, word-owned shared sieve, canonical digest, and CPU
  replay;
* `tg_verifier/goldbach_tile_sieve_projection.py`: transparent fleet
  sensitivity calculations;
* `tools/tg_goldbach_tile_sieve_projection.py`: the measured GB10 projection;
* `tests/tg_goldbach_tile_sieve_known_answers.py`: independent Python
  persistent-sieve known answer; and
* `tests/test_tg_goldbach_tile_sieve.py`: projection bounds and failure tests.

Build and run the optional target with:

```bash
cmake -S . -B build/goldbach-tile-sieve \
  -DSPARKINTERVAL_BUILD_TG_GOLDBACH_TILE_SIEVE=ON \
  -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/goldbach-tile-sieve \
  --target sparkinterval-tg-goldbach-tile-sieve -j
ctest --test-dir build/goldbach-tile-sieve \
  -R tg_goldbach_tile_sieve_known_answers --output-on-failure
```

The KAT checks all 65,536 bits in 16 segments near `10^12`, including 4,771
prime bits and 12,661 sparse events. The Python model and CUDA full replay
obtain this canonical little-endian packed-word digest:

```text
80a8f7b33e6f9f95c9bb953d30b79cbc6e5de3817fd0dc4dce0a8a69dfb63e4d
```

A separate low-range run checks delayed `p*p` activation. These finite checks
do not prove the CUDA memory-model refinement or source-scale completeness.

## Source-height GB10 measurement

The measured command covered 2,147,483,648 consecutive odd candidates just
below `4*10^18`, used every odd base prime through `2*10^9`, and replayed the
first 67,108,864-bit segment on the CPU. The device was an NVIDIA GB10 with
CUDA 13.0 and `sm_121`; `tileOdds=32768`.

| Quantity | Measurement |
| --- | ---: |
| Base primes | 98,222,286 |
| Scheduled non-wheel primes | 98,222,281 |
| Compacted events | 1,547,574,553 |
| Conservative device-state bound | 1,180,691,604 bytes |
| One-time base setup | 1.615 s |
| Host schedule | 3.739 s |
| GPU stage | 0.632 s |
| End-to-end pipeline | 4.405 s |
| Pipeline rate | 487.55 million odd candidates/s |
| CPU replay | 0.911 s |
| Replayed prime bits | 3,131,731 |

The replay digest was:

```text
d00c2eb88dde767f9758ea0b93ffdd14e70328d75ee165c330b2588aca239495
```

This is a full-root, source-height shard benchmark, not a run across all two
quintillion odd candidates. Base setup is reported separately because it can
be amortized over a persistent worker. Pipeline time includes host scheduling,
copies, compaction, marking, output, and synchronization.

## Bounded Azure sensitivity

There is no H100 measurement. The following table only applies stated
speedups to the measured GB10 component times for two quintillion odd
candidates and eight devices.

| Assumption | Eight-device wall time |
| --- | ---: |
| Eight devices at the measured pipeline rate | 142,435 h (16.25 y) |
| GPU stage alone is 12.3x faster; GB10 host retained | 123,652 h (14.11 y) |
| Entire pipeline is 12.3x faster | 11,580 h (1.32 y) |
| Host cost is zero; measured GPU stage is 12.3x faster | 1,662 h (69.3 d) |

An eight-device seven-day campaign needs about 413.36 billion candidates/s
per device, or 847.8 times the measured end-to-end GB10 rate. Even the
deliberately optimistic zero-host sensitivity needs about 80 equal devices to
finish in a week. These figures are engineering lower bounds, not H100 ETAs or
cost forecasts.

## Remaining work

The write-race issue is addressed in this prototype, but event production and
replay still perform too much work. A production attempt would need at least:

1. GPU-resident persistent buckets or a fused tile-event producer that removes
   the single-threaded host schedule;
2. substantially fewer dense-prime tile events, probably through a different
   residue or wheel decomposition rather than tuning this layout;
3. a gap-free, checkpointed handoff from exact packed prime windows to the
   shifted-OR coverage stage;
4. a source-height H100 confidential-mode benchmark of the fused stages;
5. a PTX/SASS-to-specification refinement for the final binary; and
6. registration under a new algorithm identity only after those reviews.

The historical finite computation and a cache-efficient segmented-sieve
baseline are documented by Oliveira e Silva, Herzog, and Pardi,
[*Empirical verification of the even Goldbach conjecture and computation of
prime gaps up to `4*10^18`*](https://doi.org/10.1090/S0025-5718-2013-02787-1).


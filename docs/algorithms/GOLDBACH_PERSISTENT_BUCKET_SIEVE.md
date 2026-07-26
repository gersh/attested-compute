# Persistent bucketed odd-prime sieve

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is a concrete, bounded production-shape component for the word-oriented
binary-Goldbach route. It is **not** a completed verification through
`4*10^18`, is not receipt-eligible, and is not registered as a replacement for
the existing Goldbach v1 algorithm. The measured implementation is still far
too slow for a one-week Azure campaign.

The component closes one earlier engineering gap: consecutive prime windows
no longer rediscover a first multiple for every odd prime below `2*10^9` in
every segment. Its output is the same packed `uint64_t` prime-bitset consumed
by [`h100_tg_goldbach_shift_or.cu`](../../gpu/platform/h100/h100_tg_goldbach_shift_or.cu).
The follow-up
[`GOLDBACH_TILE_COMPACTED_SIEVE.md`](GOLDBACH_TILE_COMPACTED_SIEVE.md) replaces
the candidate's colliding byte stores with word-owned, shared-memory atomic
clears, while documenting the remaining source-scale performance gap.

## Exact finite equation

For an odd segment beginning at `oddLow`, bit `j` represents

```text
q(j) = oddLow + 2*j,       0 <= j < W.
```

Every composite `q(j)` has an odd prime divisor at most
`floor(sqrt(q(j)))`. The runner therefore rejects a base-prime bound smaller
than the square root of the campaign's last candidate. A prime `p` begins at

```text
max(p*p, least odd multiple of p not below oddLow)
```

and successive odd multiples are `p` positions apart in the packed index.
Starting at `p*p` is essential: it does not clear the bit representing `p`
itself.

The implementation splits the persistent state as follows.

* `p <= W`: the GPU retains the next relative offset between launches. These
  are the dense primes that can hit each segment.
* `p > W`: at most one raw odd multiple occurs in a segment. A circular host
  bucket stores the prime only under the segment containing its next relevant
  multiple. It is not visited in intervening segments.
* A prime is activated only when `p*p` first enters the campaign. This keeps a
  campaign starting near 1 exact as well as a source-height shard.

The byte path initializes a `3*5*7*11*13 = 15015` wheel. Sparse buckets retain
only multiples whose cofactor survives that wheel. There are 5,760 surviving
residues and the largest transition is 11 odd-multiplier steps, which fixes the
reviewed bucket-ring horizon. Dense GPU threads deliberately mark every later
odd multiple after their first wheel survivor; those redundant zero writes do
not omit any candidate.

All intended colliding byte stores write the identical value zero, and the
reviewed CUDA 13 build lowers them to `st.global.u8`. This observation and a
bounded replay are not a proof of the concurrent CUDA/C++ execution. The final
packing kernel assigns one warp to one 64-bit word and uses two ballots, so
each packed word has a single writer. The executable also offers
`--atomic-words`, which uses race-free packed `atomicAnd` as the conservative
exact path and obtains the same full KAT digest. A PTX/SASS refinement of the
faster same-value store remains outstanding, so both paths emit
`receipt_eligible=false`.

## Files and checks

The reviewed pieces are:

* `gpu/include/sparkinterval/tg_goldbach_bucket_sieve.hpp`: bounded-memory base
  prime generation, one-time activation, dense/sparse partition, wheel-aware
  circular buckets, and a stateless packed-word CPU replay;
* `gpu/platform/h100/h100_tg_goldbach_bucket_sieve.cu`: persistent CUDA dense
  state, sparse-event upload, wheel initialization, exact word packing, and
  fail-closed full-word comparisons;
* `tg_verifier/goldbach_bucket_sieve.py`: an independently written Python
  persistent model, stateless replay, trial-division oracle, and transparent
  source work model;
* `tests/test_tg_goldbach_bucket_sieve.py`: bounded activation, bucket, digest,
  and failure tests; and
* `tests/tg_goldbach_bucket_sieve_known_answers.py`: cross-language CUDA/Python
  known answer.

Build and run the optional target with:

```bash
cmake -S . -B build/goldbach-bucket-sieve \
  -DSPARKINTERVAL_BUILD_TG_GOLDBACH_BUCKET_SIEVE=ON \
  -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/goldbach-bucket-sieve \
  --target sparkinterval-tg-goldbach-bucket-sieve -j
ctest --test-dir build/goldbach-bucket-sieve \
  -R tg_goldbach_bucket_sieve_known_answers --output-on-failure
```

The isolated CUDA build used for the measurements was:

```bash
nvcc -std=c++20 -O3 -lineinfo -arch=sm_121 -Igpu/include \
  gpu/platform/h100/h100_tg_goldbach_bucket_sieve.cu \
  -o /tmp/h100_tg_goldbach_bucket_sieve
```

The cross-language KAT checks all 65,536 candidate bits in 16 consecutive
segments near `10^12`. It activates 78,492 scheduled primes, processes 12,661
wheel-surviving sparse events, and obtains the canonical little-endian packed
word digest

```text
80a8f7b33e6f9f95c9bb953d30b79cbc6e5de3817fd0dc4dce0a8a69dfb63e4d
```

The independent Python model obtains the same digest without using the C++
scheduler or CUDA kernel. A separate low-range test compares every word with
trial division and exercises delayed `p*p` activation.

## GB10 measurements

The local device was an NVIDIA GB10 with CUDA 13.0 and `sm_121`. Pipeline time
includes host bucket scheduling, host-to-device sparse-event copies, wheel
initialization, marking, packing, and synchronization. Base-prime generation
is reported separately because it occurs once per long-lived shard. CPU replay
is outside the timed pipeline.

| Range/model | Work | Full replay | Base setup | Host schedule | GPU stage | Pipeline | Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| near `10^16`, root `10^8` | 16 x `2^24` odds | 2 segments | 0.082 s | 0.226 s | 0.375 s | 0.608 s | 441.4 M odds/s |
| near `10^16`, packed atomic | 16 x `2^24` odds | 2 segments | 0.082 s | 0.209 s | 1.826 s | 2.044 s | 131.4 M odds/s |
| near `4*10^18`, root `2*10^9` | 32 x `2^26` odds | none | 1.630 s | 3.645 s | 3.379 s | 7.044 s | 304.9 M odds/s |
| near `4*10^18`, root `2*10^9` | 4 x `2^26` odds | 1 segment | 1.642 s | 2.300 s | 0.420 s | 2.739 s | 98.0 M odds/s |

The final row is deliberately short and initialization-dominated, but it
provides a real source-height full-word comparison. Its 67,108,864 replayed
bits contained 3,133,424 primes and produced digest
`06ec36f2e687dd58d527f85d6db7de57b45f285291fa7263a7d3020d6fe361dd`.
The longer source-height run retained all 98,222,281 scheduled primes, used a
330-slot ring, processed 142,159,001 sparse events, and reported a conservative
1,571,556,496-byte persistent-state bound.

Except for the row explicitly labelled `packed atomic`, performance rows use
the faster same-value byte-store candidate. The atomic row is race-free and
obtains the identical replay digest, but it is 3.36x slower on the bounded
`10^16` workload. Consequently the source ETA below is already an optimistic
engineering sensitivity, not an ETA for the conservative exact path.

## Source work and ETA

For `W=2^26`, `source_scale_work_model()` records these auditable quantities:

```bash
python3 tools/tg_goldbach_bucket_sieve_model.py --pretty
```

```text
odd candidates through 4e18                    2,000,000,000,000,000,000
segments                                       29,802,322,388
odd primes through 2e9                         98,222,286
dense scheduled primes through 2^26            3,957,803
sparse scheduled primes                        94,264,478
estimated dense stores per segment             121,403,840
estimated wheel-surviving sparse events/segment  4,442,755
estimated composite stores over full range     3.751e18
candidate-byte initializations over full range 2.000e18
```

The event estimates use the displayed Mertens reciprocal-prime approximation;
they are a sizing model, not a certificate. Prime counts and data-structure
sizes are explicit integers.

At the measured 304.9 million odd candidates/s, eight equal GB10s would take
about 227,790 wall-clock hours (26.0 years). Giving only the GPU portion an
uncalibrated 6x or 12.3x H100 speedup still projects roughly 136,743 or 127,417
hours on eight nodes, because the current single-threaded host scheduler then
dominates. Even an infinitely fast marking kernel leaves a 118,534-hour host
floor. A seven-day eight-GPU run requires about 413.4 **billion** candidates/s
per GPU, 1,356x the measured end-to-end GB10 rate.

Using the repository's July 2026 price snapshot (`$9,381` on-demand or `$1,907`
spot per seven days for eight NCC H100 nodes), the 12.3x GPU-only sensitivity
would be roughly `$7.1M` on demand or `$1.45M` spot. This is not a purchasing
forecast: no H100 measurement exists, the Azure host differs from GB10, and a
multi-year spot campaign is operationally implausible. It demonstrates that
this version does not meet the project's one-week / `$10k` objective.

## Remaining production obstacles

The next performance version must avoid a scattered store for nearly every
prime divisor event. Plausible directions are a residue-tiled sieve in which a
CTA owns output words, GPU-resident compacted bucket queues, and parallel host
bucket construction with pinned double buffers. Each needs a fresh exact
packed-word replay and a machine-code audit. The campaign also still needs:

1. durable checkpoint serialization and restart validation for the persistent
   ring and dense offsets;
2. an exact no-gap handoff from each prime window to the shifted-OR coverage
   words, including overlap and tail masks;
3. an H100 confidential-mode benchmark of sieve plus coverage together;
4. PTX/SASS refinement for the chosen marking memory semantics; and
5. registration under a new algorithm identity only after those reviews.

No existing Goldbach v1 semantics or semantic binding was modified or enabled
by this work.

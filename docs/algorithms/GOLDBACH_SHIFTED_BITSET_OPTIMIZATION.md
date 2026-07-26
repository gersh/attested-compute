# Word-oriented binary-Goldbach coverage

Copyright (c) 2026 Gershon Bialer. All rights reserved. SPDX-License-Identifier: MIT.

## Status

This is an implemented and locally benchmarked replacement for the coverage
kernel in the current GoldbachGPU route.  The checked diagnostic transformer
now operates on the route's actual packed segmented-sieve words, retains the
original low-boundary path, and can run both implementations and compare every
live result bit.  Combined with the warp-per-prime sieve tier, the
cofactor-filtered tail, and packed missing-bit counting, it reduces the exact
terminal 600-million-even benchmark by `2.375x` on the local GB10.

This supersedes the synthetic coverage-only performance concern below, but it
does not promote a production executable.  Durable leaf receipts, an exact
confidential-H100 calibration, source identity review, and a physical
CUDA/compiler refinement boundary remain open.  The separate persistent-bucket
and tile-compacted sieve experiments remain useful negative results; they are
not the current integrated candidate.

The existing production candidate assigns one GPU thread to each even number
and performs successive scattered prime-bit probes. That route has a measured
multi-year source-scale projection. The new kernel assigns one thread to a
64-even-number word and ORs coalesced shifted words from the odd-prime bitset.

## Human-readable reduction

Let bit `j` in a prime window mean that

```text
q = qLow + 2*j
```

is prime. For a fixed small odd prime `p` and the first even number `evenLow`
in an output word, compute `shift` and check the exact equation

```text
evenLow = qLow + p + 2*shift.
```

Then source bit `shift+i` certifies

```text
evenLow + 2*i
  = p + (qLow + 2*(shift+i)).
```

Thus one shifted 64-bit load simultaneously tests the same prime `p` for 64
consecutive even integers. OR is monotone, so a word may stop as soon as all
live bits are one. The last word uses an explicit tail mask.

`SparkInterval/TernaryGoldbach/GoldbachShiftedBitset.lean` proves this
reduction, including that the packed natural-word OR has exactly the same bits
as the logical existential search. A final gap-free indexed campaign theorem
derives the exact `BinaryGoldbachClaim` consumed by
`GoldbachSourceSemantics`. Its public theorems depend only on Lean's standard
base trio (`propext`, `Classical.choice`, and `Quot.sound`); there is no
execution axiom, `native_decide`, or sampled premise. The physical GPU run
remains a separate measured-execution boundary.

The formal model also proves the concrete two-load extractor used by CUDA:
for `0 ≤ shift < 64`, every live bit of
`(low >> shift) | (high << (64 - shift))` is the corresponding source bit.
The proof treats `shift = 0` separately, uses an explicit 64-bit bound to
exclude stale high bits from `low`, reconstructs the cross-word index, and
then instantiates the packed-OR soundness theorem without an extractor
premise.  It also proves that the literal machine test
`(covered & (2^liveCount - 1)) = (2^liveCount - 1)` forces every live lane to
contain a Goldbach witness.  The packed-count theorem further shows that a
zero sum of per-word population counts is equivalent to that mask equation
for every word, assuming only the standard machine fact that population count
is zero exactly on the zero word.  The host guard `SEG_SIZE ≤ UInt32.max`
keeps the physical atomic accumulator from wrapping to zero.  The remaining
physical boundary is therefore CUDA/compiler refinement of `__popcll`, the
atomic addition, and the word operations—not the word-shift, mask, or
zero-count arithmetic itself.

## Implemented probe

`gpu/platform/h100/h100_tg_goldbach_shift_or.cu` contains the actual shifted
two-word extraction, word OR, exact tail-mask check, early exit, failure count,
and an exact CPU replay of the first 4,096 result words. Its benchmark bitset
is deterministic synthetic data with prime-like density `1/43`; it is clearly
labelled `synthetic_only=true` and cannot produce a Goldbach receipt.
`tg_verifier/goldbach_shifted_bitset.py` is a second, exact integer replay of
the alignment, carry-word extraction, OR, and tail-mask equations; its bounded
known-answer tests do not require CUDA.

Build the optional target with:

```bash
cmake -S . -B build/goldbach-shift-or \
  -DSPARKINTERVAL_BUILD_TG_GOLDBACH_SHIFT_OR=ON \
  -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/goldbach-shift-or \
  --target sparkinterval-tg-goldbach-shift-or -j
```

or compile the isolated probe directly:

```bash
nvcc -std=c++20 -O3 -lineinfo -arch=sm_121 \
  gpu/platform/h100/h100_tg_goldbach_shift_or.cu \
  -o build/h100_tg_goldbach_shift_or
```

## DGX Spark measurement

The local NVIDIA GB10 used CUDA 13.0 and `sm_121`. Every row used 2,048
distinct unaligned shifts, density denominator 43, no failed word, and an
exact 4,096-word CPU replay.

| Live evens | Mean kernel time | Evens/s | Mean shifts/word | Max shifts |
| ---: | ---: | ---: | ---: | ---: |
| 67,108,864 | 1.029 ms | 65.25 billion | 202.58 | 699 |
| 268,435,456 | 3.930 ms | 68.30 billion | 202.22 | 845 |
| 1,073,741,824 | 15.577 ms | 68.93 billion | 202.27 | 845 |

The stable rate across a 128 MiB output working set makes a small-cache-only
explanation unlikely. At 68.93 billion evens/s, the coverage stage alone
projects to 1,007.4 hours on eight equal-throughput GB10 GPUs. An eight-H100
run needs a per-device speedup of 6.0x to bring this stage below seven days.
The H100-vs-GB10 bandwidth ratio is larger than that, but it is only a
sensitivity bound until the exact kernel runs on H100.

At the repository's July 2026 Azure price snapshot, the seven-day threshold
would cost about `$9,381` on demand or `$1,907` at the displayed spot rate for
eight `Standard_NCC40ads_H100_v5` nodes. A 12.3x sensitivity gives about 81.9
hours and `$4,573` on demand or `$930` spot for this stage. These figures do
not include the prime sieve, checkpoint I/O, retries, or attestation.

The synthetic table isolates the algebraic coverage kernel and must not be
used as the current end-to-end estimate.  The later integrated real-sieve
route measured `0.267971 s` median for 600,000,000 terminal evens over seven
runs, with zero fallback, compared with `0.636503 s` for the prepared
baseline.  A unified diagnostic independently compared every unfiltered and
cofactor-filtered sieve word, both phase-1 implementations, and the byte and
packed missing-bit counts over 20 billion evens without a mismatch.
Low-boundary and non-word-aligned terminal runs also passed, as did the
independent CPU/CUDA KATs and CUDA memory sanitizer.  See
[`GOLDBACH_10POW27_CAMPAIGN.md`](GOLDBACH_10POW27_CAMPAIGN.md) for the exact
scope and the unpromoted prototype projection.

## Remaining production work

The speedup removes the scattered per-even coverage bottleneck, but the full
one-week claim is still unproved. A source-scale run also needs:

1. review and pin the generated word-owner/warp-tail/shifted-coverage source,
   then measure that exact executable on the intended H100 SKU;
2. a theorem/refinement check connecting the packed machine words and tail
   masks to the abstract `PrimeWindow` and `Shift` structures;
3. deterministic checkpoint and reduction records that retain full gap-free
   coverage while avoiding one receipt per tiny segment;
4. H100 confidential-mode measurements of sieve plus coverage, not coverage
   alone; and
5. registration as a new algorithm version only after those measurements and
   source identities are reviewed.

The cache-efficient segmented-sieve baseline and the historical `4*10^18`
computation are described by Oliveira e Silva, Herzog, and Pardi,
[*Empirical verification of the even Goldbach conjecture and computation of
prime gaps up to `4*10^18`*](https://doi.org/10.1090/S0025-5718-2013-02787-1).
The exact finite result used by ternary Goldbach is stated by Helfgott and
Platt, [*Numerical Verification of the Ternary Goldbach Conjecture up to
`8.875*10^30`*](https://arxiv.org/abs/1305.3062).

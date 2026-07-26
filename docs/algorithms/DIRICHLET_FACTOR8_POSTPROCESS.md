# Directed factor-eight completed-value postprocessing

Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT.

This component accelerates the routine eight-times-finer interpolation step
after real completed-\(L\) intervals have been constructed on Platt's
\(5/64\) lattice. It performs a bounded forty-tap directed interval
convolution, adds an explicit interpolation-error allowance, classifies each
target as strictly negative, ambiguous, or strictly positive, and packs four
decisions per byte. It also counts adjacent opposite strict signs.

It is a finite arithmetic component, not a proof of Platt's Theorem 7.1. In
particular, it does not prove the upstream completed-\(L\) intervals, the
accepted manuscript's uniform interpolation-error claim, zero multiplicity or
completeness, the corrected Turing argument, or physical CUDA instruction
semantics.

## Exact work audit

The former production-sizing row called
`1,571,337,544,104,271` objects "completed intervals." That count is more
specific: it is the number of primitive-character times target-grid
coordinates on the routine factor-eight grid. The exact schedule is:

| Work object | Exact count |
|---|---:|
| Base \(5/64\)-grid completed-value intervals | 196,430,125,886,102 |
| All factor-eight target coordinates | 1,571,337,544,104,271 |
| Aligned targets that reuse a base interval | 196,430,125,886,102 |
| Nonaligned targets requiring interpolation | 1,374,907,418,218,169 |
| Forty-tap interval products | 54,996,296,728,726,760 |

The old 100,985/s benchmark measured one synthetic input interval accumulated
into a direct Whittaker--Shannon sum. Dividing the target-coordinate count by
that per-term rate was dimensionally invalid. It was neither a completed-value
rate nor a factor-eight target rate.

`tg_verifier/dirichlet_factor8_postprocess.py::work_audit` recomputes the last
three rows from the independently pinned production inventory.

## Source-shaped formula

The accepted-manuscript production parameters are retained literally:

- \(B=32/5\), so the source spacing is \(1/(2B)=5/64\);
- Gaussian parameter \(h=7/32\);
- truncation \(N=20\);
- target phases \(r=1,\ldots,7\) between adjacent source samples; and
- source offsets \(k=-19,\ldots,20\).

For target phase \(r\) and source offset \(k\), the coefficient artifact
contains an outward binary64 enclosure of

\[
 \exp\left(-\frac{\delta^2}{2h^2}\right)
 \frac{\sin(\pi(r/8-k))}{\pi(r/8-k)},\qquad
 \delta=\frac{r/8-k}{2B}.
\]

There are only \(7\cdot40=280\) coefficients. Pinned Arb generates them at 256
bits; an independent 320-bit pass checks that every retained binary64 interval
contains the source expression. None crosses zero.

Aligned phase-zero targets reuse the input interval exactly. Nonaligned
targets receive the forty-term interval sum plus the caller's explicit
error upper bound. Python compares that binary64 value as an exact rational
and rejects anything below \(86/10^9\); the CUDA runner independently enforces
the outward binary64 threshold. Thus a zero or understated request cannot
erase the paper-level allowance. A strict sign is emitted only when the final
interval lies wholly on one side of zero.

## Arithmetic optimization

The four-corner reference interval product evaluates all endpoint products.
Because every checked coefficient interval has a fixed strict sign,
monotonicity selects exactly one endpoint product for each lower and upper
bound. The optimized kernel combines each selected product with the running
sum through explicit `__fma_rd` and `__fma_ru`. This reduces eight directed
multiplications plus two additions per tap to two directed fused
multiply-adds. A 72-interval shared-memory tile covers all source values needed
by one 256-target block.

The reference and optimized modes remain in the same executable. The
benchmark alternates them and requires their complete output artifacts to be
byte-identical. Exact-rational tests separately enumerate negative,
zero-crossing, and positive input intervals against positive and negative
coefficient intervals and prove the selected two-corner hull equals the
general four-corner hull for those cases.

A separate counter-only A/B used a deliberately easy constant all-positive
input and measured about 416.4 million targets/s. That number is not the
source-shaped throughput: the uniform signs reduce counter contention and
control-flow pressure. It was used only to decide whether to retain
warp-aggregated counters (they were consistently about 0.21% slower, so they
were removed). Sizing below uses the complete three-kernel runner on the
periodic mixed-sign input: interval convolution/classification, packed-code
emission, and adjacent-transition counting are all inside the timed region.

## Fail-closed wire and checker

The three bounded little-endian formats are:

| Magic | Role |
|---|---|
| `TGDF8CF1` | source parameters, 280 coefficient intervals, payload SHA-256 |
| `TGDF8IN1` | one character shard, coordinates, completed-value intervals, explicit error upper bound, coefficient/upstream/payload hashes |
| `TGDF8SG1` | two-bit decisions, exact counts, transition count, coefficient/input/payload hashes, device status |

All parsers require exact lengths, canonical reserved fields, finite ordered
intervals, complete interpolation padding, exact digest bindings, and no
trailing bytes. CUDA failures use the reserved code and a nonzero reduced
status; either makes publication fail.

The independent checker does not reproduce CUDA rounding. It interprets every
binary64 endpoint as an exact rational, constructs every four-corner interval
product with unbounded Python integers, adds the exact retained binary64 error
upper bound, and verifies each published strict sign. Ambiguity is accepted
conservatively. Counters and adjacent transitions are regenerated from the
packed payload. A forged strict sign is a regression test.

This establishes the bounded arithmetic implication

```text
retained completed-value intervals
+ Arb-checked coefficient intervals
+ explicit interpolation-error upper bound
-------------------------------------------------
published strict signs are valid for the finite retained convolution
```

It does not establish that the inputs enclose the analytic completed
\(L\)-function or that the interpolation-error upper bound applies uniformly.

## GB10 benchmark

The reproducible command is:

```bash
/tmp/tg-flint-venv/bin/python \
  tools/benchmark_tg_dirichlet_factor8_postprocess.py \
  build/tg-production-kat/sparkinterval-tg-dirichlet-factor8-postprocess \
  --base-count 1048576 --repeats 50 --trials 3 --pretty
```

On the local NVIDIA GB10, each trial classified 8,388,288 target coordinates.
The retained 2026-07-25 result was:

| Mode | Target samples/s |
|---|---:|
| Four-corner reference, median | 212,443,210 |
| Signed-coefficient directed-FMA, range | 350,556,995--350,580,961 |
| Signed-coefficient directed-FMA, median | 350,576,168 |
| Median paired speedup | 1.65021x |

All three optimized artifacts were byte-identical to their paired reference
artifacts. A separate 704-target shard had every strict result replayed with
exact rational endpoint arithmetic. This is a synthetic kernel measurement on
GB10, not an H100 or source-campaign measurement, and it proves no physical
CUDA refinement.

Scaling all factor-eight target coordinates by the measured median gives
1,245.04 single-GB10 GPU-hours, or 155.63 ideal hours on eight equal GB10s.
That arithmetic projection excludes upstream completed-value construction,
input generation and transfer, boundary padding, exceptional factors 32/128/
512, the uniform interpolation-error proof, attestation, zero/Turing closure,
and source-scale independent replay. No H100 multiplier is claimed before a
strict `sm_90` pilot.

## Commands

```bash
/tmp/tg-flint-venv/bin/python \
  tools/tg_dirichlet_factor8_postprocess.py --pretty work

/tmp/tg-flint-venv/bin/python \
  tools/tg_dirichlet_factor8_postprocess.py --pretty \
  coefficients /tmp/factor8-coefficients.bin

/tmp/tg-flint-venv/bin/python \
  tools/tg_dirichlet_factor8_postprocess.py --pretty \
  verify-coefficients /tmp/factor8-coefficients.bin

cmake --build build/tg-production-kat \
  --target sparkinterval-tg-dirichlet-factor8-postprocess -j2

TG_DIRICHLET_FACTOR8_RUNNER="$PWD/build/tg-production-kat/sparkinterval-tg-dirichlet-factor8-postprocess" \
  /tmp/tg-flint-venv/bin/python -m unittest -v \
  tests.test_tg_dirichlet_factor8_postprocess
```

The strict H100 target
`sparkinterval-h100-tg-dirichlet-factor8-postprocess` is compiled for `sm_90`
and rejects the local GB10. That build/runtime guard is a deployment check,
not a proof of the generated machine code.

## Remaining integration gaps

1. Feed retained completed-real intervals from the persistent all-character
   graph without materializing the source-wide stream.
2. Prove or replace the accepted manuscript's uniform \(8.6\cdot10^{-8}\)
   interpolation-error statement over the entire live parameter range.
3. Add boundary padding, indeterminate refinement, and the factors 32, 128,
   and 512 exception ladder.
4. Replace the full two-bit shard payload by an authenticated event/ambiguity
   range stream once its cross-shard boundary state has an independent replay.
5. Run a strict H100 pilot, including input transport and compact-event
   reduction, before using an H100 performance projection.
6. Connect sign brackets, multiplicity-preserving isolation, and the reviewed
   Turing upper count to the Lean external proposition.

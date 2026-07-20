# GRH POC benchmarks and full-run extrapolation

Limited-test measurements of the GRH proof-of-concept
(see [GRH_POC.md](GRH_POC.md)) on the local DGX Spark (NVIDIA GB10,
`sm_121`, CUDA 13.0, aarch64, 20-core Grace, 119 GiB unified memory), and
a cost model for Platt's full range (arXiv:1305.3087: all primitive
characters, `q <= 400000`, `q t0 ~ 1e8`).

All GPU times are CUDA-event times for the interval kernels themselves;
wall times additionally include the Python driver (character group,
Gauss sums, mpmath cross-checks, certificate emission), which is untuned
and dominated by mpmath.

## Limited-test runs (DGX Spark)

| Run | characters | window | zeros bracketed | GPU ms | term-evals | wall s |
| --- | --- | --- | --- | --- | --- | --- |
| `q=3, T=200` | 1 | `[-1, 200]` | 114 | 1.8 | 8.3e5 | 2.1 |
| `q=4, T=200` | 1 | `[-1, 200]` | 122 | 1.8 | 8.3e5 | 2.1 |
| `q=5, T=30` | 3 | `[-1, 30]` | 32 | 1.1 | 1.0e5 | 1.0 |
| `q=5, T=2000` | 3 | `[-1, 2000]` | 6085 | 186 | 1.46e8 | 23 |
| `q=101, T=100` | 99 | `[-1, 100]` | 10085 | 50 | 1.19e7 | 270 |
| `q=1009, T=50` (16 of 1002 primitive) | 16 | `[-1, 50]` | 1024 | 70 | 4.24e7 | 208 |
| `q=100003, T=30` (4 of 100002) | 4 | `[-1, 30]` | 236 | 4082 | 2.57e9 | 36 |

Observations:

- Every zero count matched the Turing-method main term within the `S(t)`
  slack (e.g. `q=5, T=2000`: 2028/2028/2029 found vs main terms
  2028.47/2027.99/2028.47; `q=100003, T=30`: 58/59/60/59 vs
  59.29/58.80/59.29/58.80).  Bracket midpoints for the real character
  mod 5 reproduce the LMFDB zero ordinates.
- Every sampled enclosure (including bracket endpoints) contained the
  independent 60-digit mpmath recomputation.
- Enclosure widths: ~1e-11 at `t ~ 30`, ~1e-8 at `t ~ 2000`, consistent
  with the `M * ulp(t log m)` accumulation model.

## Kernel throughput (single launch)

A single `hurwitz_kernel` launch with `t_count = 25000`, `phi = 4`,
`M = 2000` (2.0e8 term evaluations, `t ~ 1000`):

```text
hurwitz_ms = 204.9   lambda_ms = 2.1
terms/s    = 9.76e8
```

One term evaluation is one directed-rounded interval evaluation of
`(nq+a)^{-1/2-it}` accumulated into a complex interval: an interval log,
sqrt, division, sin/cos pair, and ~10 interval mul/adds — roughly 180
double-precision flops with the software transcendentals counted.  The
sustained rate is therefore ~1.8e11 dp-flops/s of rigorous interval
arithmetic on the GB10, which has comparatively weak FP64 (the same code
on an FP64-strong part such as an H100 is expected to run 30-60x faster).

## Full-run cost model

Sieving the exact primitive-character counts over Platt's range
reproduces his numbers: 2.957e10 primitive L-functions, 1.96e14
Lambda-sample evaluations at 5/64 spacing (5.2 samples per zero, matching
the paper's "about 5 times the expected zero density").

**Direct method (this POC) does not scale to the full range**: the
per-sample Euler-Maclaurin cost is `phi(q) * M(t)` with `M ~ 0.7 t`,
giving 2.8e17 term-evals for the full range — ~11.6 GB10-years — and,
decisively, binary64 interval arithmetic loses all precision near
`t ~ 1e7` (argument widths `~M * ulp(t log m)` reach O(1)).  This is
exactly why Platt uses the lattice/Taylor + unit-group-FFT algorithm with
high-precision seeds.

**Lattice-algorithm model.**  Platt's large-q pipeline costs, per t-row
per modulus: a lattice Taylor step (4096 x 50 cells), one 15-term Taylor
interpolation per residue, a Bluestein FFT over the unit group, and per-
character completion.  Counting interval complex multiplies at 60 dp
flops each and summing exactly over Platt's `q` and heights:

```text
total work ~ 1.75e18 interval-arithmetic flops
```

| Hardware | assumed sustained rate | full-run time |
| --- | --- | --- |
| 1x GB10 (this DGX Spark), binary64 intervals | 1.5e11 (measured class) | ~135 days |
| 1x GB10, double-double intervals (4x penalty) | 3.8e10 | ~1.5 years |
| 1x H100 SXM, binary64 intervals | 1e13 (30% of FP64 peak) | ~2 days |
| 1x H100 SXM, double-double intervals | 2.5e12 | ~8 days |
| 8x H100 node, double-double | 2e13 | ~1 day |

Platt's 2013 computation took ~400,000 core-hours (~45 core-years) on
SSE2-era CPU clusters.  The model therefore suggests roughly a
**thousand-fold** hardware-efficiency gain: a full rigorous re-run is a
*days-scale single-node job* on modern FP64-strong GPUs, and a
months-scale job even on this desk-side GB10 — provided the lattice
algorithm (not the direct POC evaluator) is ported, in double-double or
higher interval precision, with the unit-group FFT batched across `t`.

Caveats, in fairness to the model:

- The 30% FP64 efficiency assumption for interval FFT butterflies is
  optimistic; min/max chains and directed-rounding intrinsics reduce
  achievable ILP.  A factor 2-3 penalty would move the H100 estimate to
  the 1-3 week range.
- The Turing-method completeness pass, exceptional-case handling
  (Platt: ~0.0003% of L-functions needed >512x upsampling and MPFI), and
  certificate emission are excluded; Platt reports these were not the
  dominant cost.
- Lean checking of the emitted bracket certificates is linear in the
  zero count.  The kernel-mode checker verified 122 brackets in 5.6 s
  (~22 brackets/s single-threaded, including ~5 s fixed elaboration
  overhead); at that rate the full 3.8e13-zero certificate would be a
  CPU-cluster-scale verification (~5e4 core-years) — the streaming
  checker and per-chunk parallelism documented in
  [ZETA_ZERO_VERIFIER.md](ZETA_ZERO_VERIFIER.md) plus compiled
  (`native_decide`-class or extracted-checker) verification would be
  required for the formal side to keep pace with the GPU side; a
  measured-checker design (the repository's registered-invocation route)
  is the intended long-term answer.

## Reproduction

The runs above:

```bash
python3 tools/run_grh_poc.py run --q 5 --t-hi 2000 \
  --cross-check-stride 2048 --work-dir build/grh-poc/q5-t2000
python3 tools/run_grh_poc.py run --q 101 --t-hi 100 \
  --cross-check-stride 4096 --max-cross-checks 10 \
  --work-dir build/grh-poc/q101-t100
python3 tools/run_grh_poc.py run --q 1009 --t-hi 50 --max-characters 16 \
  --cross-check-stride 8192 --max-cross-checks 6 \
  --work-dir build/grh-poc/q1009-t50
python3 tools/run_grh_poc.py run --q 100003 --t-hi 30 --max-characters 4 \
  --cross-check-stride 100000 --max-cross-checks 4 \
  --work-dir build/grh-poc/q100003-t30
```

`--max-characters` restricts to the first K primitive characters and is a
benchmark-only option; a verification run must cover every primitive
character of the modulus.

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

## Source-scale work and the implemented conditional Taylor stage

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

Section 4.1 of the paper uses `D = 2048` lattice rows and columns
`c = 0,...,N` with `N = 15`: 32,768 complex lattice cells per ordinate, not
the previously documented `4096 x 50`. The repository now implements the
conditional Taylor-reconstruction identity from Lemma 4.2 in
`h100_tg_dirichlet_lattice_kernel.cu`. Given certified lattice rectangles and
a certified omitted-tail radius, it evaluates all sixteen terms with directed
binary64 arithmetic. An independent CPU checker decodes every endpoint as an
exact dyadic rational and checks containment of the natural interval
expression.

The fixed source-stage plan uses the paper's positive grid `t = 5k/64`, the
project cutover `q = 10001`, and all unit residues needed by the subsequent
DFT. It contains exactly:

```text
127,988 positive ordinate rows
4,901,051,274 (q,t) rows
327,089,206,283,008 residue reconstructions
5,233,427,300,528,128 complex Taylor terms
```

A conservative retained source-shaped rate is 69.60 million reconstructions/s
or 1.114 billion complex Taylor terms/s on GB10. This single conditional stage
would therefore take about 54.4 single-GB10 days, or 163 ideal hours on eight
equal GPUs. H100 is not measured locally. The current report uses an explicit
1x--14.3x per-GPU sensitivity, where the upper endpoint is only the H100-NVL /
DGX-Spark memory-bandwidth ratio: **11.4--163 hours on eight H100s**. A 5x--10x
engineering band is 16.3--32.6 hours. This is a stage-only kernel-arithmetic
projection, not a runtime estimate for Theorem 7.1. The
standalone review format would represent 7.85 PB of requests and 15.70 PB of
outputs at full scale; a real engine must generate requests compactly and fuse
or stream Taylor values into the DFT instead of materializing those files.

The exact CPU replay checked 10,000 GPU rows in 1.65 seconds on one local core.
That checker is useful for known answers and bounded conformance, but plainly
cannot replay all 327 trillion rows. A production use of this kernel must bind
the reviewed executable to confidential-compute attestation, while retaining
the exact checker for conformance samples; it must not claim that sampling is
an independent proof of every GPU operation.

Platt reports approximately 400,000 historical SSE2 core-hours for the
**complete** computation. That number includes lattice generation, both
large- and small-modulus algorithms, DFTs, zero isolation, upsampling,
exceptional cases, and Turing completeness. It is not comparable to the
11.4--163-hour sensitivity for this one arithmetic stage.

There is no defensible full-run H100 ETA yet. Certified lattice inputs and
finite recovery, persistent residue composition, the framed CRT/Bluestein
interval DFT, a persistent completed-L consumer, scalable certified
root-number artifacts, Booker's directed-disk small-q engine, and conditional
zero-closure arithmetic now exist as components with bounded KATs. The
small-q path also has a completely parity-bound time-tail/sign reducer and a
post-DFT device classifier that removes the 226.996-TB raw-disk transfer in
device mode. It has only a local synthetic q-level GB10 differential run, not
a source-scale or H100 measurement. Still missing are source-campaign wiring
and runtime closure, a
source-wide interval-width proof, efficient persistent lattice/recovery
production, a uniform interpolation proof, theorem-level review/Lean
realization of the corrected reflected Turing upper bound, source-wide
exception refinement, and the remaining Lean realization theorem. The
rigorous FLINT contour backend remains the fail-closed completeness route,
although it is unscaled.

Further formal-side caveat:

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

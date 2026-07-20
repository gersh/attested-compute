# GRH finite-verification POC (Platt, arXiv:1305.3087)

This document describes the proof-of-concept implementation of the
computation in D. J. Platt, *Numerical computations concerning the GRH*
(arXiv:1305.3087): rigorous isolation of critical-line zeros of Dirichlet
L-functions of primitive character, together with a Lean finite-strip GRH
verification layer that consumes the GPU-produced bracket data.

Platt's Theorem 7.1 verified GRH for all primitive characters of modulus
`q <= 400000` to height `max(1e8/q, 7.5e7/q + 200)` (even `q`) or
`max(1e8/q, 3.75e7/q + 200)` (odd `q`), using interval arithmetic
throughout, a Hurwitz-zeta lattice plus unit-group DFT for large `q`,
Booker's FFT method for small `q`, and Turing's method for completeness.

## What this POC computes

For one modulus `q` and every primitive character `chi` mod `q`, the CUDA
program `gpu/src/grh_lambda_poc.cu` (target `sparkinterval-grh-lambda`)
computes directed-rounded binary64 interval enclosures of Platt's real
completed function

```text
Lambda_chi(t) = eps_chi (q/pi)^{it/2} Gamma((1/2 + a_chi + it)/2)
                exp(pi t/4) L_chi(1/2 + it)
```

on the sample grid of spacing `5/64` used by Platt, via

1. per-residue Dirichlet partial sums `sum_{n<M} (nq+a)^{-1/2-it}` plus the
   Euler-Maclaurin Hurwitz tail through `J = 10` Bernoulli terms with the
   periodized-Bernoulli remainder bound
   `|R_J| <= 4 |(s)_{2J+1}| (2pi)^{-(2J+1)} x^{-(1/2+2J)} / (1/2 + 2J)`;
2. a character combination `L = sum_a chi(a) D_a` (direct summation in this
   POC; Platt uses the CRT/Bluestein unit-group FFT); and
3. the Gamma/exponential factor from a Stirling `log Gamma` enclosure with
   a fixed argument shift of 12 and remainder bound
   `|R| <= |B_{2JG+2}|/((2JG+2)(2JG+1)) sec(arg/2)^{2JG+2} |w|^{-(2JG+1)}`.

The host driver `tools/run_grh_poc.py`:

- constructs the character group by CRT cyclic decomposition with
  baby-step-giant-step discrete logarithms, computes conductors, parities,
  and the root-number factors `eps_chi` from Gauss sums (mpmath, 60
  digits), and verifies `Lambda` reality numerically before any GPU work;
- scans for strict sign changes, resolves ambiguous samples by bisection
  (additional GPU batches), and separates adjacent brackets so the family
  is strictly ordered;
- cross-checks a sample of GPU enclosures (including bracket endpoints)
  against independent mpmath recomputation;
- applies a numeric Turing-style expected-count comparison using the
  main term `(1/pi)(Im log Gamma((1/2+a+it)/2) + (t/2) log(q/pi))` and
  Trudgian's `S(t)` constants `2.17618 + 0.0679955 log(qt/2pi)` from
  Platt's production code (a sanity check, not a formal bound); and
- emits a certificate JSON with each bracket's exact binary64 endpoints
  and value enclosures, which `verify` rechecks on the CPU in exact
  rational arithmetic.

`tools/generate_grh_lean.py` converts a certificate for modulus 3 or 4
into a Lean file that kernel-checks the bracket family and states the
conditional finite-strip GRH theorem (see below).

## Lean layer

New modules under `SparkInterval/Dirichlet/` mirror the Riemann zeta
verifier architecture and reuse its generic bracket/endpoint machinery
(`SparkInterval.Zeta.ZeroCertificate`, `EndpointCertificate`) unchanged:

| Module | Content |
| --- | --- |
| `LZeros` | Zeros of `DirichletCharacter.LFunction` for `chi != 1` form a closed discrete set; compact regions contain finitely many (the Dirichlet analogue of Mathlib's `ZetaZeros`, proved from entirety plus nonvanishing at `s = 2`). |
| `CriticalLine` | The closed rectangle `criticalStrip lo hi = [0,1] x [lo,hi]`, compactness, and the axiom-free deduction: equal distinct-zero counts force every zero in the rectangle onto `re s = 1/2`. |
| `Verifier` | `LCriticalLineZeroBridge`, `LZeroCountUpperBound`, and `GRHVerifierEvidence` with the finite-strip conclusion `all_zeros_on_criticalLine`. |
| `HardyContract` | `DirichletHardyModel`: a continuous real evaluator equal to a nonvanishing phase times `LFunction chi (1/2 + it)`; `verifyEndpointFamily` composes a checked `RationalBracketFamily` with the analytic premises into the finite-strip GRH conclusion. |
| `GRHVerification` | Primitive characters of modulus `>= 2` are nontrivial; the per-modulus statement `GRHVerifiedForModulus`. |
| `SmallModuli` | Concrete `chiThree`/`chiFour` (from Mathlib's `quadraticChar`/`ZMod.χ₄`), the classification `chi != 1 -> chi = chiFour` (the unit groups are `{1,-1}`), and the reduction of `GRHVerifiedForModulus 3/4` to the single nontrivial character. |

The generated certificate files prove, by kernel reduction without
`native_decide`:

- `family.check = true` (strict signs, valid intervals, strict adjacent
  ordering) for the embedded exact-rational bracket family; and
- the rational domain bounds `lo <= lower_i`, `upper_i <= hi`.

The final generated theorem has the shape

```lean
theorem grh_modulus_4_finite_verification
    (f : ℝ → ℝ)
    (model : DirichletHardyModel chiFour f lo hi)
    (hencloses : ∀ i, (grhFamily.entries i).EnclosesEndpoints f)
    (totalUpper : LZeroCountUpperBound chiFour lo hi count) :
    GRHVerifiedForModulus 4 lo hi
```

and `#print axioms` reports only `propext`, `Classical.choice`,
`Quot.sound`.

## Explicit nonclaims

Exactly as for the repository's Riemann zeta verifier, the analytic
premises are stated, not proved:

- `DirichletHardyModel` (that some continuous real evaluator equals a
  nonvanishing phase times `L(1/2+it, chi)`) is a hypothesis.  Proving it
  for the concrete `Lambda_chi` needs formal Gamma-factor and root-number
  theory not yet in Mathlib or this repository.
- `EnclosesEndpoints f` (that the GPU-produced rational intervals enclose
  that evaluator's values at the recorded endpoints) is a hypothesis.  The
  numeric layer supports it by directed rounding, documented CUDA Math API
  maximum-ulp error bounds widened by two extra ulps, and independent
  mpmath cross-checks, but no Lean theorem covers the transcendental
  device functions.
- `LZeroCountUpperBound` (that the rectangle contains at most `count`
  zeros) is a hypothesis.  Platt discharges it with Turing's method; the
  POC only performs the numeric main-term comparison.  A formal Turing
  bound for Dirichlet L-functions is the same missing layer the zeta
  verifier documents.
- No claim is made about heights or moduli beyond the concrete generated
  windows, and nothing here modifies Platt's published result.

Consequently the checked artifacts establish: *if* the three analytic
premises hold for the recorded evaluator, *then* every zero of every
primitive Dirichlet L-function of the stated modulus in the stated
rectangle lies on the critical line.  The premise structure is identical
to the zeta verifier's, so completing the missing analytic layers benefits
both verifiers at once.

- The POC also computes only one-sided windows `[-1, T]` per character.
  Negative ordinates of `chi` correspond to positive ordinates of the
  conjugate character; a conjugation-symmetry lemma for
  `DirichletCharacter.LFunction` would upgrade a conjugation-closed family
  of one-sided verifications to symmetric rectangles, and is future work.

## Certified evaluation layer (`SparkInterval/Certified/`)

The heavy numerical work of endpoint verification is now available as
executable, machine-checked Lean with soundness proofs free of `sorry`,
`native_decide`, and new axioms (all audited declarations depend only on
`propext`, `Classical.choice`, `Quot.sound`):

| Module | Content |
| --- | --- |
| `Rounding` | Outward dyadic rounding (`roundDown/roundUp/roundOut/widen`) preserving containment, so pipelines stay bounded-cost. |
| `Sqrt` | `sqrtInterval` via `Nat.sqrt` bracketing; unconditional containment of `Real.sqrt`. |
| `Exp` | `expSmall/expQ/expInterval` (Taylor + `Real.exp_bound`, scaling-squaring) and `logInterval` (witness search certified a posteriori through exp monotonicity). |
| `SinCos` | `sinCosQ/sinCosInterval`: 2-term Taylor base (`Real.sin_bound`/`cos_bound`), proved double-angle climbing, argument reduction mod `2π` with Mathlib's 20-digit `pi_gt_d20/pi_lt_d20`, Lipschitz interval widening.  Measured widths ~1e-12 at arguments up to 1e6. |
| `Complex` | `ComplexRect` rectangles with proved add/sub/mul/scale/rounding and the norm-widening rule that consumes remainder bounds. |
| `PowGlue` | `r^{-(c+it)} = exp(-c log r)(cos(t log r) - i sin(t log r))` for rational `r > 0`, packaged as a containment rule. |
| `LambdaPremises` | Exact main-term/remainder formulas and the two named analytic premises: `EulerMaclaurinHurwitzBound` (Hurwitz tail) and `StirlingGammaBound` (Gamma factor), stated against Mathlib's `HurwitzZeta.hurwitzZeta` and `Complex.Gamma`.  `ZMod.LFunction` is definitionally the `hurwitzZeta` combination, so no further glue identity is needed. |
| `Atan` | `atanQ/atanInterval` via the arctangent Maclaurin series with sqrt-free argument reduction (`arctan_add`, `arctan_inv_of_pos`); unconditional soundness. |
| `LambdaEval` | `rpowNegEval` (certified power term) and `mainSumEval` (certified truncated Hurwitz sum `∑_{n<M}(n+α)^{-1/2-it}`), both with **unconditional** soundness theorems. |
| `TailEval` | `tailEval`: the full Euler-Maclaurin correction (both `x`-powers, the exact rational-complex `(s-1)⁻¹`, and the Bernoulli terms with exact `emCoeff (j+1)·(s)_{2j+1}` coefficients), with **unconditional** soundness against `hurwitzTail`. |

Demonstrated on real certificate data (q = 4, t = 381/64, M = 161): the
certified main sums evaluate in about one second per residue in the Lean
interpreter and agree with 40-digit mpmath to all displayed digits, with
enclosure widths near 8e-10 — far below the endpoint magnitudes that sign
verification requires.  The interpreter is fast enough for POC-scale
certificates; compiled evaluation covers larger ones.

Because the truncated sums are the dominant cost (the Euler-Maclaurin
tail and Stirling factor are O(1) small expressions per endpoint), this
layer makes the *heavy* computation certified end-to-end, and with
`tailEval` the entire Hurwitz-zeta side (main sum plus correction terms)
is enclosed unconditionally.  The remaining assembly — the Stirling
Gamma-factor evaluator on the same primitives (complex log via certified
`log` and `arctan`), a rational upper bound for `hurwitzTailError`, and
consumption of the two named premises through
`ComplexRect.widen_contains_of_norm_le` — replaces the per-row
`EnclosesEndpoints` hypothesis of the generated theorems by exactly
`EulerMaclaurinHurwitzBound ∧ StirlingGammaBound`: two clean, deferred
analysis facts in place of thousands of numeric claims.  Every needed
primitive exists and is proved; that assembly is composition work on
this layer, with no new certified-numerics obligations.

## Numerical validity envelope

Directed-rounded binary64 interval arithmetic bounds the sin/cos argument
`t log m` to width of a few ulps of `t log m`; summed over the
`M ~ 0.7 (t + 30)` Euler-Maclaurin terms, enclosure widths grow roughly
like `M * ulp(t log M)`.  In practice the POC produces widths near 1e-11
at `t ~ 30` and 1e-8 at `t ~ 2000`, comfortably below typical `|Lambda|`
scales; the direct method degrades beyond `t ~ 1e5` and is unusable at
Platt's full heights, exactly why his lattice/Taylor and FFT algorithms
evaluate in higher precision and only round the results to double
intervals.  A production run must either port the lattice algorithm with
high-precision seeds (Platt used 300-bit MPFI) or use double-double
interval arithmetic on the GPU.

## Reproducing

```bash
cmake -S . -B build/grh-dev -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/grh-dev --target sparkinterval-grh-lambda
python3 tools/run_grh_poc.py run --q 4 --t-hi 200 \
  --work-dir build/grh-poc/q4-t200
python3 tools/run_grh_poc.py verify build/grh-poc/q4-t200/grh-certificate.json
python3 tools/generate_grh_lean.py \
  --certificate build/grh-poc/q4-t200/grh-certificate.json \
  --output build/grh-poc/lean/GeneratedChiFourCert.lean
./tools/safe_lean.sh build/grh-poc/lean/GeneratedChiFourCert.lean
```

Benchmark results and full-run extrapolation live in
`docs/algorithms/GRH_POC_BENCHMARKS.md`.

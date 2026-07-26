/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Analysis.SpecialFunctions.Gamma.Basic
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Sinc

/-!
# Source-shaped boundary for Platt's interpolation Lemma C.3

Appendix C of D. J. Platt, *Isolating some non-trivial zeros of zeta*
(Math. Comp. 86 (2017), 2449--2467) separates two errors in the
Whittaker--Shannon interpolation:

* Lemma C.1 bounds the error caused by the function not being exactly
  band-limited (via Weiss's theorem); and
* Lemma C.3 bounds the omitted tails of the infinite sampling sum.

The author manuscript has two evident typographical errors in the displayed
statement: its summation condition says `|n - t0/A| > Ns`, although the sinc
kernel, the first omitted term in the proof, and the implementation all force
`|n - A*t0| > Ns`; and `X` contains a lowercase `h` where the surrounding
Appendix C consistently uses the interpolation width `H`.  Both the printed
and corrected summation conditions are represented below, and all soundness
theorems deliberately use the corrected form justified by the proof.

The file also records the exact parameters used by the public `zeta_arb`
source and the theorem that composes the C.1 and C.3 errors.  The analytic
assertion of corrected Lemma C.3 is a proposition supplied to the composition
theorem, not a new Lean axiom.  This keeps the remaining analytic work visible
instead of silently replacing it by the decimal `2.45e-40` from
`parameters.h`.

The reusable parts that Mathlib already supports are proved here:

* Platt's normalized sinc is exactly `Real.sinc (pi * x)`;
* its off-lattice absolute value is at most `1 / (pi * |x|)`;
* an absolutely summable pointwise majorant proves the tail estimate;
* the full interpolation error is the sum of the Weiss and tail errors; and
* the C source's spacing, bandwidth, Gaussian width, number of terms, and
  rational error budget are recorded without binary floating-point rounding.

There is no axiom, `sorry`, `native_decide`, execution-trust bridge, or claim
that a numerical experiment proves the remaining analytic inequality.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PlattLemmaC3

open scoped BigOperators
open MeasureTheory

/-! ## Literal analytic notation from the paper -/

/-- Platt's normalized sinc, `sin (pi*x) / (pi*x)` away from zero and `1` at
zero.  Mathlib's `Real.sinc` is unnormalized, hence the explicit factor of
`pi`. -/
noncomputable def normalizedSinc (x : ℝ) : ℝ :=
  Real.sinc (Real.pi * x)

@[simp] theorem normalizedSinc_zero : normalizedSinc 0 = 1 := by
  simp [normalizedSinc]

/-- Literal quotient form used in Theorem 4.3 and Lemma C.3 of the paper. -/
theorem normalizedSinc_eq_sin_div {x : ℝ} (hx : x ≠ 0) :
    normalizedSinc x = Real.sin (Real.pi * x) / (Real.pi * x) := by
  rw [normalizedSinc, Real.sinc_of_ne_zero]
  exact mul_ne_zero Real.pi_ne_zero hx

/-- The sinc estimate used in the first step of the proof of Lemma C.3. -/
theorem abs_normalizedSinc_le_inv {x : ℝ} (hx : x ≠ 0) :
    |normalizedSinc x| ≤ 1 / (Real.pi * |x|) := by
  have hargument : Real.pi * x ≠ 0 := mul_ne_zero Real.pi_ne_zero hx
  have hdenominator : 0 < |Real.pi * x| := abs_pos.mpr hargument
  calc
    |normalizedSinc x| =
        |Real.sin (Real.pi * x)| / |Real.pi * x| := by
          rw [normalizedSinc_eq_sin_div hx, abs_div]
    _ ≤ 1 / |Real.pi * x| := by
      exact (div_le_div_iff_of_pos_right hdenominator).2
        (Real.abs_sin_le_one (Real.pi * x))
    _ = 1 / (Real.pi * |x|) := by
      rw [abs_mul, abs_of_pos Real.pi_pos]

/-- The paper's proof keeps the looser factor `A/(pi*Ns)`.  For `A ≥ 1`
this follows from the sharper normalized-sinc bound whenever the corrected
lattice-index distance is at least `Ns`. -/
theorem abs_normalizedSinc_le_paper_factor
    {x Ns A : ℝ} (hNs : 0 < Ns) (hdistance : Ns ≤ |x|) (hA : 1 ≤ A) :
    |normalizedSinc x| ≤ A / (Real.pi * Ns) := by
  have hx : x ≠ 0 := by
    intro hzero
    rw [hzero, abs_zero] at hdistance
    exact (not_lt_of_ge hdistance) hNs
  have hdenominator : 0 < Real.pi * Ns := mul_pos Real.pi_pos hNs
  calc
    |normalizedSinc x| ≤ 1 / (Real.pi * |x|) :=
      abs_normalizedSinc_le_inv hx
    _ ≤ 1 / (Real.pi * Ns) := by
      apply one_div_le_one_div_of_le hdenominator
      exact mul_le_mul_of_nonneg_left hdistance Real.pi_pos.le
    _ ≤ A / (Real.pi * Ns) := by
      exact (div_le_div_iff_of_pos_right hdenominator).2 hA

/-- The upper incomplete Gamma function in the convention used by Platt:
`Gamma(s,x) = integral from x to infinity of u^(s-1) exp(-u) du`.

Mathlib currently provides the complete Gamma function, but does not expose a
named upper incomplete Gamma function.  Defining the paper's integral avoids
giving an opaque special-function symbol any additional trust.
-/
noncomputable def upperIncompleteGamma (s x : ℝ) : ℝ :=
  ∫ u in Set.Ioi x, Real.rpow u (s - 1) * Real.exp (-u)

/-- Exponent `beta = 1/6 + log(log t0)/log t0` in Lemmas C.2 and C.3. -/
noncomputable def beta (t0 : ℝ) : ℝ :=
  1 / 6 + Real.log (Real.log t0) / Real.log t0

/-- The quantity `X` in Lemma C.3, correcting the statement's lowercase `h`
to the interpolation width `H` used in Lemma C.2 and in the proof. -/
noncomputable def X (t0 A H Ns : ℝ) : ℝ :=
  Real.rpow (t0 + Ns / A) (beta t0) *
    Real.exp (-(Ns ^ 2 / (2 * A ^ 2 * H ^ 2)))

/-- The quantity `Y` in the published statement of Lemma C.3. -/
noncomputable def Y (t0 A H Ns : ℝ) : ℝ :=
  Real.rpow 2 ((2 * beta t0 - 1) / 2) *
    Real.rpow t0 (beta t0) * A * H *
      upperIncompleteGamma (1 / 2) (Ns ^ 2 / (2 * A ^ 2 * H ^ 2))

/-- The quantity `Z` in the published statement of Lemma C.3. -/
noncomputable def Z (t0 A H : ℝ) : ℝ :=
  Real.rpow 2 ((3 * beta t0 - 1) / 2) * A *
    Real.rpow H (beta t0 + 1) *
      upperIncompleteGamma ((beta t0 + 1) / 2) (t0 ^ 2 / (2 * H ^ 2))

/-- Right-hand side of the published Lemma C.3. -/
noncomputable def publishedTailBound (t0 A H Ns : ℝ) : ℝ :=
  6 * A / (Real.pi * Ns) * (X t0 A H Ns + Y t0 A H Ns + Z t0 A H)

/-- The Gaussian window `W(t)` after factoring out the source's completed,
exponentially scaled zeta value. -/
noncomputable def gaussianWindow
    (scaledCompletedZeta : ℝ → ℝ) (t0 H t : ℝ) : ℝ :=
  scaledCompletedZeta t * Real.exp (-((t - t0) ^ 2 / (2 * H ^ 2)))

/-- One term selected by the summation condition *as printed* in the public
author manuscript, namely `|n - t0/A| > Ns`.  This condition is incompatible
with both the displayed sinc kernel and the proof's first omitted sample, so
it is retained only to make the correction human-auditable. -/
noncomputable def printedTailTerm
    (W : ℝ → ℝ) (t0 A Ns : ℝ) (n : ℤ) : ℝ :=
  if Ns < |(n : ℝ) - t0 / A| then
    W ((n : ℝ) / A) * normalizedSinc (A * ((n : ℝ) / A - t0))
  else
    0

/-- One omitted term using the corrected condition `|n - A*t0| > Ns`.
Indeed, the sample `W(n/A)` is `Ns/A` from the target exactly when
`|n-A*t0| = Ns`; this is also the indexing implemented by `inter.c`. -/
noncomputable def tailTerm
    (W : ℝ → ℝ) (t0 A Ns : ℝ) (n : ℤ) : ℝ :=
  if Ns < |(n : ℝ) - t0 * A| then
    W ((n : ℝ) / A) * normalizedSinc (A * ((n : ℝ) / A - t0))
  else
    0

/-- Exact conclusion supplied by the source's Lemma C.3 at one target.  The
separate `Summable` field prevents Lean's default value for a non-summable
`tsum` from making the proposition vacuous. -/
def HoldsAt (W : ℝ → ℝ) (t0 A H Ns : ℝ) : Prop :=
  Summable (tailTerm W t0 A Ns) ∧
    |∑' n : ℤ, tailTerm W t0 A Ns n| ≤ publishedTailBound t0 A H Ns

/-- The claim with the manuscript's printed (dimensionally inconsistent)
summation condition.  It is documentary and is never used by a soundness
theorem in this file. -/
def PrintedHoldsAt (W : ℝ → ℝ) (t0 A H Ns : ℝ) : Prop :=
  Summable (printedTailTerm W t0 A Ns) ∧
    |∑' n : ℤ, printedTailTerm W t0 A Ns n| ≤
      publishedTailBound t0 A H Ns

/-- Side conditions printed in Lemma C.3, together with the positive `A,H`
context inherited from Section 4.2.  The paper writes `t0 > exp(e)`, where
`e = exp(1)`, and takes `Ns` to be a positive integer. -/
def PublishedConditions (t0 A H : ℝ) (Ns : ℕ) : Prop :=
  Real.exp (Real.exp 1) < t0 ∧
    0 < A ∧ 0 < H ∧ 0 < Ns ∧ (Ns : ℝ) ≤ t0 * A

/-- Corrected theorem shape of published Lemma C.3 for a previously defined
window `W`.  The correction is forced by the proof, not a weakening of the
bound.  This definition is intentionally a proposition rather than an axiom
declaration; downstream code must provide a proof or retain the source
citation explicitly. -/
def PublishedClaim (W : ℝ → ℝ) (t0 A H : ℝ) (Ns : ℕ) : Prop :=
  PublishedConditions t0 A H Ns → HoldsAt W t0 A H Ns

/-- Exact proposition obtained if the manuscript's displayed lower summation
index is transcribed without correction.  This is exposed only for source
comparison; consumers must use `PublishedClaim`. -/
def PrintedClaim (W : ℝ → ℝ) (t0 A H : ℝ) (Ns : ℕ) : Prop :=
  PublishedConditions t0 A H Ns → PrintedHoldsAt W t0 A H Ns

/-- Abstract majorant proof for the infinite tail.  This is the exact
functional-analysis step used after the paper derives a summable positive
majorant; no convergence fact is hidden in `tsum`. -/
theorem holdsAt_of_summable_majorant
    {W : ℝ → ℝ} {t0 A H Ns : ℝ} {majorant : ℤ → ℝ}
    (hmajorant : Summable majorant)
    (hterm : ∀ n, |tailTerm W t0 A Ns n| ≤ majorant n)
    (hmajorantSum : (∑' n, majorant n) ≤ publishedTailBound t0 A H Ns) :
    HoldsAt W t0 A H Ns := by
  have htail : Summable (tailTerm W t0 A Ns) :=
    hmajorant.of_norm_bounded fun n ↦ by
      simpa only [Real.norm_eq_abs] using hterm n
  constructor
  · exact htail
  · rw [← Real.norm_eq_abs]
    calc
      ‖∑' n : ℤ, tailTerm W t0 A Ns n‖ ≤
          ∑' n : ℤ, ‖tailTerm W t0 A Ns n‖ :=
        norm_tsum_le_tsum_norm htail.norm
      _ ≤ ∑' n : ℤ, majorant n :=
        htail.norm.tsum_le_tsum
          (fun n ↦ by simpa only [Real.norm_eq_abs] using hterm n)
          hmajorant
      _ ≤ publishedTailBound t0 A H Ns := hmajorantSum

/-! ## Composition with the separate Weiss error -/

/-- Pure error composition used by the interpolation certificate.  `full` is
the infinite sampling sum, `finite` is the source's 140-term sum, and `tail`
is their difference.  The first hypothesis is the non-bandlimited/Weiss error
(Appendix C.1); the second is the C.3 decomposition.

Keeping these hypotheses separate prevents the C.3 tail estimate from being
mistaken for a proof of the Whittaker--Shannon reconstruction itself.
-/
theorem interpolation_error_le
    {value full finite tail weissBound tailBound : ℝ}
    (hweiss : |value - full| ≤ weissBound)
    (hdecomposition : full = finite + tail)
    (htail : |tail| ≤ tailBound) :
    |value - finite| ≤ weissBound + tailBound := by
  have hidentity : value - finite = (value - full) + tail := by
    rw [hdecomposition]
    ring
  rw [hidentity]
  exact (abs_add_le _ _).trans (add_le_add hweiss htail)

/-- Source-shaped specialization: a valid Lemma C.3 conclusion plus a Weiss
bound controls the finite interpolation error. -/
theorem interpolation_error_le_publishedTail
    {W : ℝ → ℝ} {t0 A H Ns value full finite weissBound : ℝ}
    (hc3 : HoldsAt W t0 A H Ns)
    (hweiss : |value - full| ≤ weissBound)
    (hdecomposition :
      full = finite + (∑' n : ℤ, tailTerm W t0 A Ns n)) :
    |value - finite| ≤ weissBound + publishedTailBound t0 A H Ns :=
  interpolation_error_le hweiss hdecomposition hc3.2

/-! ## Exact mapping to the pinned `zeta_arb` source -/

/-- `parameters.h::one_over_A = 21/512`. -/
noncomputable def sourceSpacing : ℝ := 21 / 512

/-- Paper parameter `A`, the reciprocal sample spacing. -/
noncomputable def sourceA : ℝ := 512 / 21

/-- `parameters.h::H = 13/64 = 0.203125`. -/
noncomputable def sourceH : ℝ := 13 / 64

/-- `parameters.h::Ns = 70`; `inter.c` takes this many points on each side. -/
def sourceNs : ℕ := 70

/-- Exact rational represented by the source decimal `2.45e-40`. -/
def sourceInterpolationBudget : ℚ := 245 / 10 ^ 42

/-- Exact rational value of the binary64 obtained by compiling the source
decimal literal `2.45e-40` (`0x1.557aebd2564ecp-132`). -/
def sourceDecimalBinary64 : ℚ := 1501845630048571 / 2 ^ 182

/-- Exact rational value of the next binary64 number upward
(`0x1.557aebd2564edp-132`), used by the corrected local build. -/
def correctedInterpolationBinary64 : ℚ := 6007382520194285 / 2 ^ 184

theorem sourceSpacing_pos : 0 < sourceSpacing := by
  norm_num [sourceSpacing]

theorem sourceA_pos : 0 < sourceA := by
  norm_num [sourceA]

theorem sourceA_ge_one : 1 ≤ sourceA := by
  norm_num [sourceA]

theorem sourceH_pos : 0 < sourceH := by
  norm_num [sourceH]

theorem sourceA_mul_spacing : sourceA * sourceSpacing = 1 := by
  norm_num [sourceA, sourceSpacing]

theorem source_sample_count : 2 * sourceNs = 140 := by
  norm_num [sourceNs]

theorem sourceInterpolationBudget_pos : 0 < sourceInterpolationBudget := by
  norm_num [sourceInterpolationBudget]

/-- The original C decimal rounds in the unsafe direction for an exact-radius
identification. -/
theorem sourceDecimalBinary64_lt_budget :
    sourceDecimalBinary64 < sourceInterpolationBudget := by
  norm_num [sourceDecimalBinary64, sourceInterpolationBudget]

/-- The hash-pinned corrected C hex literal really encloses the exact rational
radius used by the Lean certificate. -/
theorem sourceInterpolationBudget_le_correctedBinary64 :
    sourceInterpolationBudget ≤ correctedInterpolationBinary64 := by
  norm_num [sourceInterpolationBudget, correctedInterpolationBinary64]

/-- `inter.c` first computes the physical displacement `(i-x)/A` and then
multiplies it by `pi/INTER_A = pi*A`.  This theorem is the exact symbol map to
the normalized sinc argument in Lemma C.3. -/
theorem source_sinc_argument (n : ℤ) (t0 : ℝ) :
    sourceA * ((n : ℝ) / sourceA - t0) = (n : ℝ) - sourceA * t0 := by
  have hA : sourceA ≠ 0 := ne_of_gt sourceA_pos
  field_simp [hA]

/-- A source run is sound only after both the Weiss and C.3 bounds are below
the advertised decimal budget and that budget is actually added to the
computed ball.  This theorem discharges the mathematical weakening to that
single rational radius; it does not assert the currently pinned C source
performed the widening. -/
theorem interpolation_error_le_sourceBudget
    {W : ℝ → ℝ} {t0 value full finite weissBound : ℝ}
    (hc3 : HoldsAt W t0 sourceA sourceH sourceNs)
    (hweiss : |value - full| ≤ weissBound)
    (hdecomposition :
      full = finite +
        (∑' n : ℤ, tailTerm W t0 sourceA sourceNs n))
    (hbudget :
      weissBound + publishedTailBound t0 sourceA sourceH sourceNs ≤
        (sourceInterpolationBudget : ℝ)) :
    |value - finite| ≤ (sourceInterpolationBudget : ℝ) :=
  (interpolation_error_le_publishedTail hc3 hweiss hdecomposition).trans hbudget

end SparkInterval.Zeta.PlattLemmaC3

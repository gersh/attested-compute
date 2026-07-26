/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.Complex
import SparkInterval.Certified.HighDegreeSinCos
import SparkInterval.Certified.HighPrecisionPi
import SparkInterval.Certified.SinCos
import SparkInterval.Dirichlet.FactoredSmallQDFT

/-!
# Fully checked rational enclosures for DFT roots

This module gives an executable exact-rational alternative to trusting a
transcendental root table.  The angle `2πk/N` is first enclosed using the
proved rational bounds on `π`; the certified sine/cosine evaluator then
returns a rational rectangle containing the positive-sign DFT root.

This proves the mathematical root-generation algorithm.  It does not claim
that MPFR, CUDA, a compiler, or a physical run refines the function below.
Those implementation edges remain separate.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.CertifiedRootTable

open SparkInterval.Certificate
open SparkInterval.Certified

/-- Exact rational interval enclosing the positive DFT angle `2πk/N`. -/
def phaseInterval (order exponent : Nat) : RatInterval :=
  (RatInterval.point ((exponent : ℚ) / (order : ℚ))).mul
    rootTwoPiInterval

theorem phaseInterval_containsReal
    (order exponent : Nat) :
    (phaseInterval order exponent).ContainsReal
      ((2 * Real.pi * (exponent : ℝ)) / (order : ℝ)) := by
  have hratio :=
    RatInterval.point_containsReal ((exponent : ℚ) / (order : ℚ))
  have hproduct :=
    RatInterval.mul_containsReal hratio rootTwoPiInterval_containsReal
  have hcast :
      (((exponent : ℚ) / (order : ℚ) : ℚ) : ℝ) =
        (exponent : ℝ) / (order : ℝ) := by
    simp only [Rat.cast_div, Rat.cast_natCast]
  rw [hcast] at hproduct
  have hphase :
      (exponent : ℝ) / (order : ℝ) * (2 * Real.pi) =
        (2 * Real.pi * (exponent : ℝ)) / (order : ℝ) := by
    ring
  simpa only [phaseInterval, hphase] using hproduct

/-- Reduce the exponent before introducing the finite-width rational
enclosure of `π`.  This is important for Bluestein chirps such as `n²`: the
mathematical root is periodic, while the width of a naively scaled `π`
interval would grow with the unreduced numerator. -/
def phaseIntervalReduced (order exponent : Nat) : RatInterval :=
  phaseInterval order (exponent % order)

theorem phaseIntervalReduced_containsReal
    (order exponent : Nat) :
    (phaseIntervalReduced order exponent).ContainsReal
      ((2 * Real.pi * ((exponent % order : Nat) : ℝ)) / (order : ℝ)) := by
  exact phaseInterval_containsReal order (exponent % order)

/-- Positive DFT roots depend only on the exponent modulo their nonzero
order. -/
theorem unitRoot_mod
    {order : Nat} (horder : 0 < order) (exponent : Nat) :
    FactoredSmallQDFT.unitRoot order exponent =
      FactoredSmallQDFT.unitRoot order (exponent % order) := by
  calc
    FactoredSmallQDFT.unitRoot order exponent =
        FactoredSmallQDFT.unitRoot order
          (exponent % order + order * (exponent / order)) := by
            rw [Nat.mod_add_div]
    _ = FactoredSmallQDFT.unitRoot order (exponent % order) *
        FactoredSmallQDFT.unitRoot order (order * (exponent / order)) :=
      FactoredSmallQDFT.unitRoot_add _ _ _
    _ = FactoredSmallQDFT.unitRoot order (exponent % order) *
        FactoredSmallQDFT.unitRoot order order ^ (exponent / order) := by
      rw [FactoredSmallQDFT.unitRoot_mul_right]
    _ = FactoredSmallQDFT.unitRoot order (exponent % order) := by
      rw [FactoredSmallQDFT.unitRoot_order horder, one_pow, mul_one]

/-- A certified rational rectangle for a positive-sign DFT root.

`depth` and `precision` control the exact-rational sine/cosine evaluator.  A
`none` result is a fail-closed range guard, not an assumed root.
-/
def rootRect?
    (depth workPrecision outputPrecision order exponent : Nat) :
    Option ComplexRect :=
  Option.map
    (fun SC =>
      ComplexRect.roundOutRect outputPrecision
        ({ re := SC.2, im := SC.1 } : ComplexRect))
    (sinCosInterval depth workPrecision (phaseInterval order exponent))

theorem rootRect?_containsComplex
    {depth workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      rootRect? depth workPrecision outputPrecision order exponent = some R) :
    R.ContainsComplex
      (FactoredSmallQDFT.unitRoot order exponent) := by
  rcases hsc :
      sinCosInterval depth workPrecision (phaseInterval order exponent) with
    _ | ⟨S, C⟩
  · simp [rootRect?, hsc] at hcheck
  · simp only [rootRect?, hsc, Option.map_some, Option.some.injEq] at hcheck
    subst R
    have hcontains :=
      sinCosInterval_containsReal hsc
        (phaseInterval_containsReal order exponent)
    let θ : ℝ :=
      (2 * Real.pi * (exponent : ℝ)) / (order : ℝ)
    have hre :
        (FactoredSmallQDFT.unitRoot order exponent).re =
          Real.cos θ := by
      unfold FactoredSmallQDFT.unitRoot
      rw [Complex.exp_mul_I]
      change
        (Complex.cos (θ : ℂ) + Complex.sin (θ : ℂ) * Complex.I).re =
          Real.cos θ
      simp
      exact Complex.cos_ofReal_re θ
    have him :
        (FactoredSmallQDFT.unitRoot order exponent).im =
          Real.sin θ := by
      unfold FactoredSmallQDFT.unitRoot
      rw [Complex.exp_mul_I]
      change
        (Complex.cos (θ : ℂ) + Complex.sin (θ : ℂ) * Complex.I).im =
          Real.sin θ
      simp
      exact Complex.sin_ofReal_re θ
    apply ComplexRect.roundOutRect_containsComplex
    constructor
    · rw [hre]
      simpa [θ] using hcontains.2
    · rw [him]
      simpa [θ] using hcontains.1

/-! ## Recommended high-degree fast path -/

/-- Exact rectangles for the four axis roots.  Recognizing these cases before
the rational `π` enclosure is introduced is important at roots such as `i`:
an independently produced exact binary64 singleton should be able to carry a
certificate, rather than being forced to contain a small proxy interval
around an already-known exact value. -/
def exactQuarterRoot? (order exponent : Nat) : Option ComplexRect :=
  let reduced := exponent % order
  if reduced = 0 then
    some (ComplexRect.point 1 0)
  else if 4 * reduced = order then
    some (ComplexRect.point 0 1)
  else if 2 * reduced = order then
    some (ComplexRect.point (-1) 0)
  else if 4 * reduced = 3 * order then
    some (ComplexRect.point 0 (-1))
  else
    none

/-- Every successful exact-axis branch contains the corresponding positive
DFT root. -/
theorem exactQuarterRoot?_containsComplex
    {order exponent : Nat} (horder : 0 < order)
    {R : ComplexRect}
    (hcheck : exactQuarterRoot? order exponent = some R) :
    R.ContainsComplex (FactoredSmallQDFT.unitRoot order exponent) := by
  let reduced := exponent % order
  have hroot :
      FactoredSmallQDFT.unitRoot order exponent =
        FactoredSmallQDFT.unitRoot order reduced := by
    simpa [reduced] using unitRoot_mod horder exponent
  rw [hroot]
  unfold exactQuarterRoot? at hcheck
  change
    (if reduced = 0 then
      some (ComplexRect.point 1 0)
    else if 4 * reduced = order then
      some (ComplexRect.point 0 1)
    else if 2 * reduced = order then
      some (ComplexRect.point (-1) 0)
    else if 4 * reduced = 3 * order then
      some (ComplexRect.point 0 (-1))
    else none) = some R at hcheck
  split at hcheck
  next hzero =>
    subst reduced
    simp only [Option.some.injEq] at hcheck
    subst R
    rw [hzero, FactoredSmallQDFT.unitRoot_zero]
    norm_num [ComplexRect.ContainsComplex, ComplexRect.point,
      RatInterval.ContainsReal, RatInterval.point]
  next hzero =>
    split at hcheck
    next hquarter =>
      simp only [Option.some.injEq] at hcheck
      subst R
      have hreduced : 0 < reduced := Nat.pos_of_ne_zero hzero
      have hangle :
          (2 * Real.pi * (reduced : ℝ)) / (order : ℝ) =
            Real.pi / 2 := by
        have horderReal : (order : ℝ) ≠ 0 := by positivity
        have hquarterReal :
            (4 : ℝ) * (reduced : ℝ) = (order : ℝ) := by
          exact_mod_cast hquarter
        field_simp [horderReal]
        linarith [hquarterReal]
      have hvalue :
          FactoredSmallQDFT.unitRoot order reduced = Complex.I := by
        unfold FactoredSmallQDFT.unitRoot
        rw [hangle]
        convert Complex.exp_pi_div_two_mul_I using 1
        norm_num
      rw [hvalue]
      norm_num [ComplexRect.ContainsComplex, ComplexRect.point,
        RatInterval.ContainsReal, RatInterval.point]
    next hquarter =>
      split at hcheck
      next hhalf =>
        simp only [Option.some.injEq] at hcheck
        subst R
        have hangle :
            (2 * Real.pi * (reduced : ℝ)) / (order : ℝ) =
              Real.pi := by
          have horderReal : (order : ℝ) ≠ 0 := by positivity
          have hhalfReal :
              (2 : ℝ) * (reduced : ℝ) = (order : ℝ) := by
            exact_mod_cast hhalf
          field_simp [horderReal]
          linarith [hhalfReal]
        have hvalue :
            FactoredSmallQDFT.unitRoot order reduced = -1 := by
          unfold FactoredSmallQDFT.unitRoot
          rw [hangle]
          exact Complex.exp_pi_mul_I
        rw [hvalue]
        norm_num [ComplexRect.ContainsComplex, ComplexRect.point,
          RatInterval.ContainsReal, RatInterval.point]
      next hhalf =>
        split at hcheck
        next hthreeQuarter =>
          simp only [Option.some.injEq] at hcheck
          subst R
          have hangle :
              (2 * Real.pi * (reduced : ℝ)) / (order : ℝ) =
                3 * Real.pi / 2 := by
            have horderReal : (order : ℝ) ≠ 0 := by positivity
            have hthreeQuarterReal :
                (4 : ℝ) * (reduced : ℝ) =
                  3 * (order : ℝ) := by
              exact_mod_cast hthreeQuarter
            field_simp [horderReal]
            linarith [hthreeQuarterReal]
          have hvalue :
              FactoredSmallQDFT.unitRoot order reduced = -Complex.I := by
            unfold FactoredSmallQDFT.unitRoot
            rw [hangle]
            have harg :
                (((3 * Real.pi / 2 : ℝ) : ℂ) * Complex.I) =
                  2 * (Real.pi : ℂ) * Complex.I +
                    (-((Real.pi : ℂ) / 2) * Complex.I) := by
              push_cast
              ring
            have hnegativeQuarter :
                Complex.exp
                    (-((Real.pi : ℂ) / 2) * Complex.I) =
                  -Complex.I := by
              convert Complex.exp_neg_pi_div_two_mul_I using 1
              ring
            rw [harg, Complex.exp_add, Complex.exp_two_pi_mul_I,
              hnegativeQuarter, one_mul]
          rw [hvalue]
          norm_num [ComplexRect.ContainsComplex, ComplexRect.point,
            RatInterval.ContainsReal, RatInterval.point]
        next hthreeQuarter =>
          simp at hcheck

/-- Fully checked rational rectangle for a positive-sign DFT root at an
explicit Taylor/climb configuration.

The exponent is reduced modulo the nonzero order before multiplying by the
Machin-certified 128-bit dyadic `π` interval. Order zero is rejected
explicitly. A caller can therefore qualify faster `(terms, depth)` pairs
without duplicating or weakening the mathematical containment theorem.
-/
def rootRectConfigured?
    (terms depth workPrecision outputPrecision order exponent : Nat) :
    Option ComplexRect :=
  if order = 0 then
    none
  else match exactQuarterRoot? order exponent with
    | some exact => some exact
    | none =>
      Option.map
        (fun SC =>
          ComplexRect.roundOutRect outputPrecision
            ({ re := SC.2, im := SC.1 } : ComplexRect))
      (sinCosTaylorBoundedInterval terms depth workPrecision
        (phaseIntervalReduced order exponent))

theorem rootRectConfigured?_containsComplex
    {terms : Nat} (hterms : 0 < terms)
    {depth workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      rootRectConfigured? terms depth workPrecision outputPrecision
        order exponent = some R) :
    R.ContainsComplex
      (FactoredSmallQDFT.unitRoot order exponent) := by
  unfold rootRectConfigured? at hcheck
  split at hcheck
  next hzero =>
    simp at hcheck
  next hnonzero =>
    have horder : 0 < order := Nat.pos_of_ne_zero hnonzero
    cases hexact : exactQuarterRoot? order exponent with
    | some exact =>
        simp only [hexact, Option.some.injEq] at hcheck
        subst R
        exact exactQuarterRoot?_containsComplex horder hexact
    | none =>
        rcases hsc :
            sinCosTaylorBoundedInterval
              terms depth workPrecision
              (phaseIntervalReduced order exponent) with
          _ | ⟨S, C⟩
        · simp [hexact, hsc] at hcheck
        · simp only [hexact, hsc, Option.map_some,
            Option.some.injEq] at hcheck
          subst R
          have hcontains :=
            sinCosTaylorBoundedInterval_containsReal
              hterms hsc
              (phaseIntervalReduced_containsReal order exponent)
          let reducedExponent := exponent % order
          let θ : ℝ :=
            (2 * Real.pi * (reducedExponent : ℝ)) / (order : ℝ)
          have hre :
              (FactoredSmallQDFT.unitRoot order reducedExponent).re =
                Real.cos θ := by
            unfold FactoredSmallQDFT.unitRoot
            rw [Complex.exp_mul_I]
            change
              (Complex.cos (θ : ℂ) + Complex.sin (θ : ℂ) * Complex.I).re =
                Real.cos θ
            simp
            exact Complex.cos_ofReal_re θ
          have him :
              (FactoredSmallQDFT.unitRoot order reducedExponent).im =
                Real.sin θ := by
            unfold FactoredSmallQDFT.unitRoot
            rw [Complex.exp_mul_I]
            change
              (Complex.cos (θ : ℂ) + Complex.sin (θ : ℂ) * Complex.I).im =
                Real.sin θ
            simp
            exact Complex.sin_ofReal_re θ
          rw [unitRoot_mod horder]
          apply ComplexRect.roundOutRect_containsComplex
          constructor
          · rw [hre]
            simpa [θ, reducedExponent] using hcontains.2
          · rw [him]
            simpa [θ, reducedExponent] using hcontains.1

/-- Number of exponential-series terms in the recommended binary64 root
generator.  Thirteen terms with nine climb steps passed the complete
maximum-order source dump. The older eighteen-term/four-step setting first
rejected chirp row `14560`; the earlier conservative production setting used
twenty-four terms and four steps. -/
def fastTaylorTerms : Nat := 13

/-- Nine double-angle steps balance exact-rational polynomial cost against
climb cost while keeping the proved worst-period Taylor tail at essentially
the same scale as the former twenty-four-term/four-step setting. -/
def fastTaylorDepth : Nat := 9

/-- Recommended qualified wrapper around `rootRectConfigured?`. -/
def rootRectFast?
    (workPrecision outputPrecision order exponent : Nat) :
    Option ComplexRect :=
  rootRectConfigured? fastTaylorTerms fastTaylorDepth
    workPrecision outputPrecision order exponent

theorem rootRectFast?_containsComplex
    {workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      rootRectFast? workPrecision outputPrecision order exponent = some R) :
    R.ContainsComplex
      (FactoredSmallQDFT.unitRoot order exponent) := by
  exact rootRectConfigured?_containsComplex
    (terms := fastTaylorTerms) (by norm_num [fastTaylorTerms]) hcheck

end SparkInterval.Dirichlet.CertifiedRootTable

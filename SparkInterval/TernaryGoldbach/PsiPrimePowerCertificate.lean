/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiSourceSemantics

/-!
# Prime-power realization for the CH25 psi certificate

The source worker adds one directed enclosure of `log p` for every prime power
`p ^ k` in its range.  This file proves, in ordinary Lean, that the resulting
canonical Q64 sums enclose Mathlib's `Chebyshev.psi`.

The registered external boundary is deliberately smaller than
`SourceScaleEvidence`:

* `PrimeLogBounds.Realizes` says that the directed integer endpoints enclose
  the corresponding real logarithm;
* `GapSourceScaleEvidence` records exact finite prime-power gap coverage and
  state constancy; and
* its guards are exactly the upper-after-jump and lower-before-next-jump
  integer checks performed by the worker.

The equality between the worker's retained prime-power fold and
`canonicalState` is therefore part of a finite combinatorial premise.  The
registered execution no longer needs to assert an enclosure of
`Chebyshev.psi`, a redundant guard for every integer, or the final
real-variable lemma directly.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate

open Finset
open scoped BigOperators Nat

open SparkInterval.TernaryGoldbach.PsiSourceSemantics

/-- One source-wide table of directed Q64 logarithm endpoints. -/
structure PrimeLogBounds where
  lowerQ64 : Nat → Nat
  upperQ64 : Nat → Nat

namespace PrimeLogBounds

/-- The semantic obligation for the CRlibm-to-Q64 conversion.  It is needed
only at primes in the literal source range. -/
def Realizes (bounds : PrimeLogBounds) : Prop :=
  ∀ p, p ∈ Nat.primesLE sourceLimit →
    (bounds.lowerQ64 p : Real) / scale ≤ Real.log p ∧
      Real.log p ≤ (bounds.upperQ64 p : Real) / scale

end PrimeLogBounds

/-- The exact lower Q64 fold obtained by adding `lowerQ64 p` once for every
prime power `p ^ k ≤ n`.  Mathlib's `p.log n` is precisely that event count. -/
def canonicalLowerQ64 (bounds : PrimeLogBounds) (n : Nat) : Nat :=
  ∑ p ∈ Nat.primesLE n, p.log n * bounds.lowerQ64 p

/-- The corresponding exact upper Q64 fold. -/
def canonicalUpperQ64 (bounds : PrimeLogBounds) (n : Nat) : Nat :=
  ∑ p ∈ Nat.primesLE n, p.log n * bounds.upperQ64 p

/-- Literal lower event fold: one copy of the prime's lower endpoint for each
exponent in `1 .. p.log n`.  This is the mathematical shape of the merged
prime/prime-power stream, independent of its physical ordering. -/
def primePowerLowerQ64 (bounds : PrimeLogBounds) (n : Nat) : Nat :=
  ∑ p ∈ Nat.primesLE n,
    ∑ _k ∈ Finset.Icc 1 (p.log n), bounds.lowerQ64 p

/-- Literal upper event fold. -/
def primePowerUpperQ64 (bounds : PrimeLogBounds) (n : Nat) : Nat :=
  ∑ p ∈ Nat.primesLE n,
    ∑ _k ∈ Finset.Icc 1 (p.log n), bounds.upperQ64 p

/-- Folding one logarithm interval per prime-power event is exactly the
compact `p.log n` multiplication used by `canonicalState`. -/
theorem primePowerLowerQ64_eq_canonicalLowerQ64
    (bounds : PrimeLogBounds) (n : Nat) :
    primePowerLowerQ64 bounds n = canonicalLowerQ64 bounds n := by
  simp [primePowerLowerQ64, canonicalLowerQ64, Nat.card_Icc]

theorem primePowerUpperQ64_eq_canonicalUpperQ64
    (bounds : PrimeLogBounds) (n : Nat) :
    primePowerUpperQ64 bounds n = canonicalUpperQ64 bounds n := by
  simp [primePowerUpperQ64, canonicalUpperQ64, Nat.card_Icc]

/-- Canonical state represented by the worker's ordered prime-power stream. -/
def canonicalState (bounds : PrimeLogBounds) (n : Nat) : State :=
  ⟨canonicalLowerQ64 bounds n, canonicalUpperQ64 bounds n⟩

/-- Directed log bounds imply that the exact prime-power fold encloses
Mathlib's Chebyshev psi function. -/
theorem canonicalState_prefixRealization
    {bounds : PrimeLogBounds} (hrealizes : bounds.Realizes)
    {n : Nat} (hn : n ≤ sourceLimit) :
    PrefixRealization n (canonicalState bounds n) := by
  rw [PrefixRealization, Chebyshev.psi_eq_sum_mul_log_prime]
  constructor
  · simp only [canonicalState, canonicalLowerQ64, Nat.cast_sum,
      Nat.cast_mul]
    rw [Finset.sum_div]
    apply Finset.sum_le_sum
    intro p hp
    have hpSource : p ∈ Nat.primesLE sourceLimit :=
      Nat.primesLE_mono hn hp
    have hpLower := (hrealizes p hpSource).1
    calc
      ((p.log n : Real) * bounds.lowerQ64 p) / scale =
          (p.log n : Real) * ((bounds.lowerQ64 p : Real) / scale) := by
            ring
      _ ≤ (p.log n : Real) * Real.log p :=
        mul_le_mul_of_nonneg_left hpLower (by positivity)
  · simp only [canonicalState, canonicalUpperQ64, Nat.cast_sum,
      Nat.cast_mul]
    rw [Finset.sum_div]
    apply Finset.sum_le_sum
    intro p hp
    have hpSource : p ∈ Nat.primesLE sourceLimit :=
      Nat.primesLE_mono hn hp
    have hpUpper := (hrealizes p hpSource).2
    calc
      (p.log n : Real) * Real.log p ≤
          (p.log n : Real) * ((bounds.upperQ64 p : Real) / scale) :=
        mul_le_mul_of_nonneg_left hpUpper (by positivity)
      _ = ((p.log n : Real) * bounds.upperQ64 p) / scale := by
        ring

/-- Source-scale physical evidence reduced to directed prime-log semantics and
decidable integer endpoint guards.  Unlike `SourceScaleEvidence`, this
structure does not contain `Chebyshev.psi` or the final normalized bound. -/
structure CanonicalSourceScaleEvidence where
  logBounds : PrimeLogBounds
  logBoundsRealize : logBounds.Realizes
  rowSafe : ∀ n, 1 ≤ n → n ≤ sourceLimit →
    SourceRowSafe n (canonicalState logBounds n)

/-- The canonical prime-power certificate supplies the older row interface. -/
def CanonicalSourceScaleEvidence.toSourceScaleEvidence
    (evidence : CanonicalSourceScaleEvidence) : SourceScaleEvidence where
  stateAt := canonicalState evidence.logBounds
  row n hnLower hnUpper :=
    ⟨canonicalState_prefixRealization evidence.logBoundsRealize hnUpper,
      evidence.rowSafe n hnLower hnUpper⟩

/-- Ordinary Lean derives the paper-shaped source claim from the smaller
prime-power certificate boundary. -/
theorem sourceClaim_of_canonical_evidence
    (evidence : CanonicalSourceScaleEvidence) : SourceClaim :=
  sourceClaim_of_evidence evidence.toSourceScaleEvidence

/-! ## Event-gap certificate matching the physical worker

The C++ worker checks the upper guard just after each prime-power jump and the
lower guard just before the next jump.  It does not redundantly check every
integer in a gap where psi is constant.  The following interface captures
that exact geometry and proves the missing monotonicity reduction in Lean.
-/

/-- One constant-state gap beginning just after a prime-power jump.  Ordinary
gaps are half-open `[left,right)`; the last gap is closed at `sourceLimit`. -/
structure Gap where
  left : Nat
  right : Nat
  terminal : Bool
  deriving Repr, DecidableEq

namespace Gap

def Contains (gap : Gap) (n : Nat) : Prop :=
  gap.left ≤ n ∧
    if gap.terminal then n ≤ gap.right else n < gap.right

instance instDecidableContains (gap : Gap) (n : Nat) :
    Decidable (gap.Contains n) := by
  unfold Contains
  infer_instance

/-- The exact guards emitted at the two ends of a constant-state gap. -/
def Guards (bounds : PrimeLogBounds) (gap : Gap) : Prop :=
  1 ≤ gap.left ∧ gap.left ≤ gap.right ∧
    UpperEndpointSafe gap.left
      (canonicalState bounds gap.left).upperQ64 ∧
    if gap.terminal then
      gap.right = sourceLimit ∧
        LowerEndpointSafe gap.right true
          (canonicalState bounds gap.left).lowerQ64
    else
      gap.right ≤ sourceLimit ∧
        LowerEndpointSafe gap.right false
          (canonicalState bounds gap.left).lowerQ64

instance instDecidableGuards (bounds : PrimeLogBounds) (gap : Gap) :
    Decidable (gap.Guards bounds) := by
  unfold Guards LowerEndpointSafe UpperEndpointSafe
  infer_instance

end Gap

/-- Physical evidence in the shape actually checked by the source worker.
Coverage and state constancy are finite prime-power enumeration properties;
all analytic consequences are derived below. -/
structure GapSourceScaleEvidence where
  logBounds : PrimeLogBounds
  logBoundsRealize : logBounds.Realizes
  gaps : List Gap
  guards : ∀ gap, gap ∈ gaps → gap.Guards logBounds
  coverage : ∀ n, 1 ≤ n → n ≤ sourceLimit →
    ∃ gap, gap ∈ gaps ∧ gap.Contains n
  constantState : ∀ gap, gap ∈ gaps → ∀ n, gap.Contains n →
    canonicalState logBounds n = canonicalState logBounds gap.left

private theorem floor_le_sourceLimit {x : Real}
    (hx0 : 0 ≤ x) (hx : x ≤ sourceLimit) : ⌊x⌋₊ ≤ sourceLimit := by
  exact_mod_cast (Nat.floor_le hx0).trans hx

/-- Event-gap guards plus directed prime-log realization imply the complete
paper-shaped claim.  In particular, no per-integer `SourceRowSafe` premise is
needed: Lean proves that the two event-boundary guards control every point in
the constant gap. -/
theorem sourceClaim_of_gap_evidence
    (evidence : GapSourceScaleEvidence) : SourceClaim := by
  intro x hxLower hxUpper
  have hx : 0 < x := lt_of_lt_of_le (by norm_num) hxLower
  let n := ⌊x⌋₊
  have hnLower : 1 ≤ n := Nat.le_floor
    (show ((1 : Nat) : Real) ≤ x by simpa using hxLower)
  have hnUpper : n ≤ sourceLimit := floor_le_sourceLimit hx.le hxUpper
  have hnCast : (n : Real) ≤ x := Nat.floor_le hx.le
  have hnx : Chebyshev.psi x = Chebyshev.psi n :=
    Chebyshev.psi_eq_psi_coe_floor x
  obtain ⟨gap, hgapMem, hgapContains⟩ :=
    evidence.coverage n hnLower hnUpper
  have hguards := evidence.guards gap hgapMem
  have hconstant := evidence.constantState gap hgapMem n hgapContains
  have hprefixN := canonicalState_prefixRealization
    evidence.logBoundsRealize hnUpper
  have hprefix : PrefixRealization n
      (canonicalState evidence.logBounds gap.left) := by
    simpa only [hconstant] using hprefixN
  have hleftN : gap.left ≤ n := hgapContains.1
  have hleftNReal : (gap.left : Real) ≤ (n : Real) := by
    exact_mod_cast hleftN
  have hleftX : (gap.left : Real) ≤ x := by
    exact hleftNReal.trans hnCast
  have hsqrt : 0 < Real.sqrt x := Real.sqrt_pos.2 hx
  constructor
  · have hlower : x - Chebyshev.psi x < Real.sqrt (2 * x) := by
      cases hterminal : gap.terminal with
      | false =>
          simp only [Gap.Guards, Gap.Contains, hterminal, Bool.false_eq_true,
            ↓reduceIte] at hguards hgapContains
          have hxRight : x < gap.right := by
            have hfloorNext : x < ((n + 1 : Nat) : Real) := by
              simpa [n] using Nat.lt_floor_add_one x
            have hnextRight : n + 1 ≤ gap.right := by omega
            exact hfloorNext.trans_le (by exact_mod_cast hnextRight)
          have hright := lowerEndpointSafe_real hguards.2.2.2.2
          refine lowerBarrier_strict
            (right := (gap.right : Real))
            (lower := Chebyshev.psi x) hxLower hxRight ?_
          calc
            (gap.right : Real) - Chebyshev.psi x =
                (gap.right : Real) - Chebyshev.psi n := by rw [hnx]
            _ ≤ (gap.right : Real) -
                (canonicalState evidence.logBounds gap.left).lowerQ64 /
                  scale := by linarith [hprefix.1]
            _ ≤ Real.sqrt (2 * (gap.right : Real)) := hright
      | true =>
          simp only [Gap.Guards, hterminal, ↓reduceIte] at hguards
          have hrightEq : gap.right = sourceLimit := hguards.2.2.2.1
          have hxRightLe : x ≤ gap.right := by simpa [hrightEq] using hxUpper
          have hrightStrict := lowerEndpointSafe_strict_real
            (show 0 < gap.right by simp [hrightEq, sourceLimit])
            hguards.2.2.2.2
          by_cases hxEq : x = gap.right
          · calc
              x - Chebyshev.psi x ≤ x -
                  (canonicalState evidence.logBounds gap.left).lowerQ64 /
                    scale := by
                      rw [hnx]
                      linarith [hprefix.1]
              _ = (gap.right : Real) -
                  (canonicalState evidence.logBounds gap.left).lowerQ64 /
                    scale := by rw [hxEq]
              _ < Real.sqrt (2 * (gap.right : Real)) := hrightStrict
              _ = Real.sqrt (2 * x) := by rw [hxEq]
          · have hxRight : x < gap.right := lt_of_le_of_ne hxRightLe hxEq
            refine lowerBarrier_strict
              (right := (gap.right : Real))
              (lower := Chebyshev.psi x) hxLower hxRight ?_
            calc
              (gap.right : Real) - Chebyshev.psi x =
                  (gap.right : Real) - Chebyshev.psi n := by rw [hnx]
              _ ≤ (gap.right : Real) -
                  (canonicalState evidence.logBounds gap.left).lowerQ64 /
                    scale := by linarith [hprefix.1]
              _ ≤ Real.sqrt (2 * (gap.right : Real)) := hrightStrict.le
    have hsqrtMul : Real.sqrt (2 * x) = Real.sqrt 2 * Real.sqrt x := by
      exact Real.sqrt_mul (by norm_num : (0 : Real) ≤ 2) x
    rw [hsqrtMul] at hlower
    exact (lt_div_iff₀ hsqrt).2 (by nlinarith)
  · have hupperEndpoint := upperEndpointSafe_real hguards.2.2.1
    have hcoefficient :
        (0 : Real) ≤ (upperNumerator : Real) / upperDenominator := by
      positivity
    have hsqrtMono : Real.sqrt gap.left ≤ Real.sqrt x := by gcongr
    apply (div_le_iff₀ hsqrt).2
    calc
      Chebyshev.psi x - x = Chebyshev.psi n - x := by rw [hnx]
      _ ≤ (canonicalState evidence.logBounds gap.left).upperQ64 /
          scale - x := by linarith [hprefix.2]
      _ ≤ (canonicalState evidence.logBounds gap.left).upperQ64 /
          scale - gap.left := by linarith
      _ ≤ ((upperNumerator : Real) / upperDenominator) *
          Real.sqrt gap.left := hupperEndpoint
      _ ≤ ((upperNumerator : Real) / upperDenominator) * Real.sqrt x :=
        mul_le_mul_of_nonneg_left hsqrtMono hcoefficient

end SparkInterval.TernaryGoldbach.PsiPrimePowerCertificate

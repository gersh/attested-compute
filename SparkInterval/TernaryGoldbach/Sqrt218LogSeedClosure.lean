/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

/-!
# Closed ordinary-Lean proof of the Sqrt218 logarithm seeds

This module checks only the thirty fixed rational seed rows used by the
source logarithm ladder.  It is deliberately separate from the generic
ladder definitions so their default build remains fast.

Naively normalizing `expQ` expands every interval multiplication into four
endpoint products.  For a nonnegative interval, however, the endpoints of a
natural power are simply the endpoint powers.  The small symbolic reduction
below exposes that fact before `norm_num` checks the closed rational rows.
There is no native evaluator, external oracle, or production-archive replay.
-/

set_option autoImplicit false

noncomputable section

namespace SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

open TGComputeContracts.Sqrt218
open SparkInterval.TernaryGoldbach.Sqrt218LogCertificate
open SparkInterval.Certificate
open SparkInterval.Certified

private theorem nonnegativeInterval_mul
    (X Y : RatInterval)
    (hX0 : 0 ≤ X.lo) (hX : X.lo ≤ X.hi)
    (hY0 : 0 ≤ Y.lo) (hY : Y.lo ≤ Y.hi) :
    X.mul Y = ⟨X.lo * Y.lo, X.hi * Y.hi⟩ := by
  have hac_ad : X.lo * Y.lo ≤ X.lo * Y.hi :=
    mul_le_mul_of_nonneg_left hY hX0
  have hac_bc : X.lo * Y.lo ≤ X.hi * Y.lo :=
    mul_le_mul_of_nonneg_right hX hY0
  have had_bd : X.lo * Y.hi ≤ X.hi * Y.hi :=
    mul_le_mul_of_nonneg_right hX (hY0.trans hY)
  have hbc_bd : X.hi * Y.lo ≤ X.hi * Y.hi :=
    mul_le_mul_of_nonneg_left hY (hX0.trans hX)
  cases X
  cases Y
  simp_all [RatInterval.mul]

private theorem nonnegativeInterval_powNat
    (I : RatInterval)
    (hI0 : 0 ≤ I.lo) (hI : I.lo ≤ I.hi) :
    ∀ n, I.powNat n = ⟨I.lo ^ n, I.hi ^ n⟩ := by
  intro n
  induction n with
  | zero =>
      simp [RatInterval.powNat, RatInterval.point]
  | succ n inductionHypothesis =>
      rw [RatInterval.powNat, inductionHypothesis]
      rw [nonnegativeInterval_mul]
      · simp only [pow_succ]
      · exact pow_nonneg hI0 n
      · exact pow_le_pow_left₀ hI0 hI n
      · exact hI0
      · exact hI

private theorem expTaylorSum_one_le
    {x : ℚ} (hx : 0 ≤ x) :
    1 ≤ expTaylorSum 40 x := by
  unfold expTaylorSum
  have hterm :
      ∀ m ∈ Finset.range 40,
        0 ≤ x ^ m / (m.factorial : ℚ) := by
    intro m _hm
    positivity
  have hzero : 0 ∈ Finset.range 40 := by
    simp
  have hsingle :=
    Finset.single_le_sum hterm hzero
  norm_num at hsingle ⊢
  exact hsingle

private theorem expSmall40_nonnegative
    {x : ℚ} (hx : 0 ≤ x) :
    0 ≤ (expSmall 40 x).lo := by
  have hsum := expTaylorSum_one_le hx
  have hslack : expSlack 40 < 1 := by
    norm_num [expSlack]
  simp only [expSmall]
  linarith

private theorem expSmall40_valid (x : ℚ) :
    (expSmall 40 x).IsValid := by
  have hslack : 0 ≤ expSlack 40 := by
    norm_num [expSlack]
  simp only [expSmall, RatInterval.IsValid]
  linarith

private theorem roundDown_nonnegative
    {prec : Nat} {x : ℚ} (hx : 0 ≤ x) :
    0 ≤ roundDown prec x := by
  unfold roundDown
  positivity

private theorem seedExpBase_nonnegative
    {x : ℚ} (hx : 0 ≤ x) :
    0 ≤ (roundOut 128 (expSmall 40 (x / 2 ^ 4))).lo := by
  simp only [roundOut]
  apply roundDown_nonnegative
  apply expSmall40_nonnegative
  positivity

private theorem seedExpBase_valid (x : ℚ) :
    (roundOut 128 (expSmall 40 (x / 2 ^ 4))).IsValid :=
  roundOut_isValid (expSmall40_valid _)

private theorem seedExpQ_eq_simple
    {x : ℚ} (hx : 0 ≤ x) :
    expQ 40 4 128 x =
      roundOut 128
        ⟨(roundOut 128 (expSmall 40 (x / 2 ^ 4))).lo ^ 16,
          (roundOut 128 (expSmall 40 (x / 2 ^ 4))).hi ^ 16⟩ := by
  unfold expQ
  rw [nonnegativeInterval_powNat _
    (seedExpBase_nonnegative hx) (seedExpBase_valid x)]
  norm_num

set_option maxHeartbeats 12000000 in
/-- Every entry of the fixed source seed table passes the rational logarithm
checker.  The only finite split is the explicit range `1 ≤ n ≤ 30`. -/
theorem seedCellCheck_closed
    (n : Nat) (hn1 : 1 ≤ n) (hn30 : n ≤ seedAt) :
    seedCellCheck n = true := by
  norm_num [seedAt] at hn30
  interval_cases n
  · norm_num [seedCellCheck]
  all_goals
    unfold seedCellCheck
    rw [if_neg (by norm_num)]
    unfold primeLogRowCheck logCheck
    rw [decide_eq_true_eq]
    simp only [seed]
    constructor
    · norm_num [scale]
    constructor
    · norm_num [scale]
    constructor
    · rw [seedExpQ_eq_simple (by positivity)]
      norm_num [roundOut, roundDown, roundUp, expSmall,
        expTaylorSum, expSlack, scale, Finset.sum_range_succ,
        RatInterval.mul, RatInterval.point]
    · rw [seedExpQ_eq_simple (by positivity)]
      norm_num [roundOut, roundDown, roundUp, expSmall,
        expTaylorSum, expSlack, scale, Finset.sum_range_succ,
        RatInterval.mul, RatInterval.point]

/-- Closed ordinary-Lean proof of the fixed thirty-row seed-table Boolean. -/
theorem seedTableCheck_closed :
    seedTableCheck = true := by
  unfold seedTableCheck
  rw [List.all_eq_true]
  intro offset hoffset
  simp only [List.mem_range] at hoffset
  apply seedCellCheck_closed
  · omega
  · norm_num [seedAt] at hoffset ⊢
    omega

end SparkInterval.TernaryGoldbach.Sqrt218LogLadderCertificate

end

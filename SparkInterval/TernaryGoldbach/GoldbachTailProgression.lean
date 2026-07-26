/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachWheelFilter
import Mathlib.Data.Nat.Bitwise

/-!
# Exact first-multiple arithmetic for the optimized Goldbach tail sieve

The optimized one-thread and one-warp tail kernels start an odd-prime
progression in three source-level steps:

1. compute `ceil(qLow / prime)` by quotient and remainder;
2. advance the quotient once when its multiple is even; and
3. replace that multiple by `prime²` when it lies below the square guard.

The existing word-owner proof shows that 32 warp lanes cover every index of
an already established progression.  This file proves the previously
separate arithmetic obligation: the source-shaped first-multiple calculation
starts no earlier than the guarded range and omits no odd multiple in the
sieve range. Combining
the two results shows that every odd composite witnessed by a retained tail
prime occurs in one exact warp lane and round.

This remains a natural-number model.  CUDA/PTX/compiler realization, checked
`UInt64` guards, the physical prime-roster buffer, and linearizability of the
packed-word atomics remain external obligations.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachTailProgression

open GoldbachWordOwnerSieve

/-- Overflow-free spelling of `ceil(qLow / prime)` used by the CUDA source. -/
def ceilingCofactor (qLow prime : Nat) : Nat :=
  qLow / prime + if qLow % prime = 0 then 0 else 1

/-- Source parity branch: an odd prime needs an odd cofactor in order to
produce an odd candidate. -/
def oddAdjustedCofactor (qLow prime : Nat) : Nat :=
  let quotient := ceilingCofactor qLow prime
  if Even (quotient * prime) then quotient + 1 else quotient

/-- The literal source test `(first & 1) == 0` is exactly the `Even first`
branch used by the arithmetic model. Compiled-instruction refinement is
separate; the bit arithmetic itself is proved in Lean. -/
theorem bitmaskOne_eq_zero_iff_even (value : Nat) :
    value &&& 1 = 0 ↔ Even value := by
  rw [show 1 = 2 ^ 0 by norm_num, Nat.and_two_pow]
  simp [Nat.even_iff]

/-- Source square branch, including the simultaneous `quotient = prime`
update used by the wheel-filtered kernels. -/
def firstCofactor (qLow prime : Nat) : Nat :=
  let quotient := oddAdjustedCofactor qLow prime
  if quotient * prime < prime * prime then prime else quotient

/-- First odd composite marked by the source-shaped tail progression. -/
def firstComposite (qLow prime : Nat) : Nat :=
  firstCofactor qLow prime * prime

/-- Sequential tail term before the 32-lane work redistribution. -/
def tailComposite (qLow prime index : Nat) : Nat :=
  firstComposite qLow prime + (2 * prime) * index

/-! ## Bounded source-facing start model -/

/-- Number of represented odd integers in the inclusive source window
`[qLow, qHigh]`.  The live host makes both endpoints odd; the bit-live theorem
below only needs the lower endpoint and represented candidate to be odd. -/
def oddWindowCount (qLow qHigh : Nat) : Nat :=
  (qHigh - qLow) / 2 + 1

/-- Literal natural-number model of the early-return control flow shared by
the optimized one-thread and one-warp CUDA tail kernels.

The successful payload is `(first composite, first cofactor)`.  The first two
branches are the source `p < 3 || p > qHigh / p` guard.  The next branch is
the guarded ceiling product.  The conjunction is the nested even-multiple
successor guard, and the final branch is the post-square upper guard.

All arithmetic here is still in `Nat`; the bounded acceptance theorem below
supplies the inequalities that make the corresponding `uint64_t` operations
exact. -/
def cudaTailStart?
    (qLow qHigh prime : Nat) : Option (Nat × Nat) :=
  if prime < 3 then none
  else if qHigh / prime < prime then none
  else
    let quotient := ceilingCofactor qLow prime
    if qHigh / prime < quotient then none
    else
      let first := quotient * prime
      if Even first ∧ qHigh - prime < first then none
      else
        let cofactor := firstCofactor qLow prime
        let composite := cofactor * prime
        if qHigh < composite then none
        else some (composite, cofactor)

/-- Every successful source-shaped start necessarily contains the exact
mathematical start defined above; none of the guards can manufacture an
alternative start or cofactor. -/
theorem cudaTailStart_some_eq
    {qLow qHigh prime first cofactor : Nat}
    (hstart :
      cudaTailStart? qLow qHigh prime = some (first, cofactor)) :
    first = firstComposite qLow prime ∧
      cofactor = firstCofactor qLow prime := by
  simp only [cudaTailStart?] at hstart
  split_ifs at hstart
  all_goals simp_all [firstComposite, Nat.mul_comm]
  simpa [hstart.2] using hstart.1.symm

/-- The quotient/remainder ceiling is the least integer quotient needed by
the completeness argument. -/
theorem ceilingCofactor_le_of_le_mul
    {qLow prime cofactor : Nat} (hprime : 0 < prime)
    (hlow : qLow ≤ prime * cofactor) :
    ceilingCofactor qLow prime ≤ cofactor := by
  have hfloor :
      qLow / prime ≤ (prime * cofactor) / prime :=
    Nat.div_le_div_right (c := prime) hlow
  rw [Nat.mul_div_cancel_left cofactor hprime] at hfloor
  by_cases hmod : qLow % prime = 0
  · simpa [ceilingCofactor, hmod] using hfloor
  · have hstrict : qLow / prime < cofactor := by
      apply lt_of_le_of_ne hfloor
      intro heq
      have hdecomp := Nat.div_add_mod qLow prime
      have hmodPositive : 0 < qLow % prime :=
        Nat.pos_of_ne_zero hmod
      rw [heq] at hdecomp
      omega
    simpa [ceilingCofactor, hmod] using hstrict

/-- The source quotient/remainder ceiling really places its multiple at or
above the window lower endpoint. -/
theorem le_ceilingCofactor_mul
    (qLow prime : Nat) (hprime : 0 < prime) :
    qLow ≤ ceilingCofactor qLow prime * prime := by
  by_cases hmod : qLow % prime = 0
  · have hdecomp := Nat.div_add_mod qLow prime
    simp only [hmod, add_zero] at hdecomp
    simpa [ceilingCofactor, hmod, Nat.mul_comm] using hdecomp.symm.le
  · have hdecomp := Nat.div_add_mod qLow prime
    have hmodBound : qLow % prime < prime :=
      Nat.mod_lt _ hprime
    simp only [ceilingCofactor, hmod, if_false]
    nlinarith

/-- After the source parity branch the cofactor is odd. -/
theorem oddAdjustedCofactor_odd
    (qLow prime : Nat) (hprimeOdd : Odd prime) :
    Odd (oddAdjustedCofactor qLow prime) := by
  simp only [oddAdjustedCofactor]
  by_cases heven : Even (ceilingCofactor qLow prime * prime)
  · rw [if_pos heven]
    have hquotientEven : Even (ceilingCofactor qLow prime) := by
      by_contra hnotEven
      have hquotientOdd : Odd (ceilingCofactor qLow prime) :=
        Nat.not_even_iff_odd.mp hnotEven
      exact
        (Nat.not_even_iff_odd.mpr
          (hquotientOdd.mul hprimeOdd)) heven
    exact hquotientEven.add_one
  · rw [if_neg heven]
    exact
      Nat.Odd.of_mul_left (Nat.not_even_iff_odd.mp heven)

/-- Any odd cofactor above the ceiling lies above the parity-adjusted
cofactor.  This is the minimality fact used to prove no odd multiple is
skipped. -/
theorem oddAdjustedCofactor_le
    {qLow prime cofactor : Nat}
    (hceil : ceilingCofactor qLow prime ≤ cofactor)
    (hcandidateOdd : Odd (cofactor * prime)) :
    oddAdjustedCofactor qLow prime ≤ cofactor := by
  simp only [oddAdjustedCofactor]
  by_cases heven :
      Even (ceilingCofactor qLow prime * prime)
  · rw [if_pos heven]
    exact Nat.succ_le_of_lt (lt_of_le_of_ne hceil (by
      intro heq
      subst cofactor
      exact (Nat.not_even_iff_odd.mpr hcandidateOdd) heven))
  · rw [if_neg heven]
    exact hceil

/-- The square adjustment preserves oddness because its two possible
cofactors are both odd. -/
theorem firstCofactor_odd
    (qLow prime : Nat) (hprimeOdd : Odd prime) :
    Odd (firstCofactor qLow prime) := by
  simp only [firstCofactor]
  split
  · exact hprimeOdd
  · exact oddAdjustedCofactor_odd qLow prime hprimeOdd

/-- The literal three-branch source calculation produces an odd multiple at
or above both the window lower endpoint and the prime-square guard. -/
theorem firstComposite_properties
    (qLow prime : Nat) (hprime : 0 < prime)
    (hprimeOdd : Odd prime) :
    qLow ≤ firstComposite qLow prime ∧
      prime * prime ≤ firstComposite qLow prime ∧
      Odd (firstComposite qLow prime) ∧
      prime ∣ firstComposite qLow prime := by
  have hlower :
      qLow ≤ oddAdjustedCofactor qLow prime * prime := by
    apply le_trans (le_ceilingCofactor_mul qLow prime hprime)
    exact Nat.mul_le_mul_right prime (by
      simp only [oddAdjustedCofactor]
      split <;> omega)
  have hoddAdjusted :
      Odd (oddAdjustedCofactor qLow prime) :=
    oddAdjustedCofactor_odd qLow prime hprimeOdd
  simp only [firstComposite, firstCofactor]
  split_ifs with hsquare
  · refine ⟨?_, le_rfl, hprimeOdd.mul hprimeOdd, dvd_mul_left _ _⟩
    exact hlower.trans (Nat.le_of_lt hsquare)
  · refine ⟨hlower, Nat.le_of_not_gt hsquare,
      hoddAdjusted.mul hprimeOdd, dvd_mul_left _ _⟩

/-- Every relevant odd multiple has a cofactor at or above the exact
source-shaped first cofactor. -/
theorem firstCofactor_le_of_candidate
    {qLow prime cofactor : Nat}
    (hprime : 0 < prime)
    (hcandidateOdd : Odd (cofactor * prime))
    (hlow : qLow ≤ cofactor * prime)
    (hsquare : prime * prime ≤ cofactor * prime) :
    firstCofactor qLow prime ≤ cofactor := by
  have hceil :
      ceilingCofactor qLow prime ≤ cofactor :=
    ceilingCofactor_le_of_le_mul hprime (by
      simpa [Nat.mul_comm] using hlow)
  have hadjusted :
      oddAdjustedCofactor qLow prime ≤ cofactor :=
    oddAdjustedCofactor_le hceil hcandidateOdd
  have hprimeCofactor : prime ≤ cofactor := by
    exact Nat.le_of_mul_le_mul_right (by
      simpa [Nat.mul_comm] using hsquare) hprime
  simp only [firstCofactor]
  split <;> assumption

/-- No relevant odd multiple is omitted by the source first-multiple
calculation: it is exactly one term of the `2 * prime` progression. -/
theorem tailComposite_complete
    {qLow prime candidate : Nat}
    (hprime : 0 < prime)
    (hprimeOdd : Odd prime)
    (hcandidateOdd : Odd candidate)
    (hdivides : prime ∣ candidate)
    (hlow : qLow ≤ candidate)
    (hsquare : prime * prime ≤ candidate) :
    ∃ index : Nat, tailComposite qLow prime index = candidate := by
  obtain ⟨cofactor, rfl⟩ := hdivides
  have hcofactorOdd : Odd cofactor :=
    Nat.Odd.of_mul_right hcandidateOdd
  have hfirstLe :
      firstCofactor qLow prime ≤ cofactor :=
    firstCofactor_le_of_candidate hprime
      (by simpa [Nat.mul_comm] using hcandidateOdd)
      (by simpa [Nat.mul_comm] using hlow)
      (by simpa [Nat.mul_comm] using hsquare)
  have hdifferenceEven :
      Even (cofactor - firstCofactor qLow prime) :=
    Nat.Odd.sub_odd hcofactorOdd
      (firstCofactor_odd qLow prime hprimeOdd)
  obtain ⟨index, hindex⟩ := hdifferenceEven
  refine ⟨index, ?_⟩
  have hcofactorEq :
      cofactor = firstCofactor qLow prime + 2 * index := by
    omega
  simp only [tailComposite, firstComposite]
  rw [hcofactorEq]
  ring

/-- Direct model of the one-thread loop's guarded reachability.  Every
iteration strictly before `index` passes
`if (step > qHigh - composite) break`, so the target iteration is emitted. -/
def TailLoopReaches
    (qLow qHigh prime index : Nat) : Prop :=
  tailComposite qLow prime index ≤ qHigh ∧
    ∀ prior, prior < index →
      2 * prime ≤ qHigh - tailComposite qLow prime prior

/-- A bounded target in the sequential progression is reached before the
source loop's overflow-safe upper guard can stop it. -/
theorem tailLoopReaches_of_target
    {qLow qHigh prime candidate index : Nat}
    (hindex : tailComposite qLow prime index = candidate)
    (hhigh : candidate ≤ qHigh) :
    TailLoopReaches qLow qHigh prime index := by
  constructor
  · simpa [hindex] using hhigh
  · intro prior hprior
    have hpriorSucc : prior + 1 ≤ index := by omega
    have hcoefficient :
        (2 * prime) * (prior + 1) ≤ (2 * prime) * index :=
      Nat.mul_le_mul_left (2 * prime) hpriorSucc
    have hnextHigh :
        tailComposite qLow prime (prior + 1) ≤ qHigh := by
      have htoTarget :
          tailComposite qLow prime (prior + 1) ≤
            tailComposite qLow prime index := by
        simp only [tailComposite]
        exact Nat.add_le_add_left hcoefficient _
      exact htoTarget.trans (by simpa [hindex] using hhigh)
    have hnext :
        tailComposite qLow prime (prior + 1) =
          tailComposite qLow prime prior + 2 * prime := by
      simp only [tailComposite]
      ring
    rw [hnext] at hnextHigh
    omega

/-- Equal odd parity turns the source subtraction-and-division bit formula
back into the represented candidate, and an in-window candidate has a live
bit in the allocated inclusive odd window. -/
theorem oddBitIndex_live_of_bounds
    {qLow qHigh candidate : Nat}
    (hqLowOdd : Odd qLow) (hcandidateOdd : Odd candidate)
    (hlow : qLow ≤ candidate) (hhigh : candidate ≤ qHigh) :
    candidate = qLow + 2 * oddBitIndex qLow candidate ∧
      oddBitIndex qLow candidate < oddWindowCount qLow qHigh := by
  have hdifferenceEven : Even (candidate - qLow) :=
    Nat.Odd.sub_odd hcandidateOdd hqLowOdd
  obtain ⟨bit, hbit⟩ := hdifferenceEven
  have hcandidate :
      candidate = qLow + 2 * bit := by
    omega
  have hindex :
      oddBitIndex qLow candidate = bit := by
    simp only [oddBitIndex]
    omega
  constructor
  · simpa [hindex] using hcandidate
  · simp only [oddWindowCount, hindex]
    omega

/-- Any relevant odd composite inside the inclusive source window forces
every start guard to accept.  The returned pair is exactly the mathematical
`firstComposite`/`firstCofactor` pair and the first composite fits in
`uint64_t`.

The hypotheses are source-facing rather than merely algebraic: `prime ≥ 3`
matches the kernel's explicit lower guard, `candidate ≤ qHigh` discharges all
upper early returns, and `qHigh < 2^64` supplies the machine-width endpoint. -/
theorem cudaTailStart_eq_some_of_bounded_candidate
    {qLow qHigh prime candidate : Nat}
    (hprime : 3 ≤ prime)
    (hprimeOdd : Odd prime)
    (hcandidateOdd : Odd candidate)
    (hdivides : prime ∣ candidate)
    (hlow : qLow ≤ candidate)
    (hhigh : candidate ≤ qHigh)
    (hsquare : prime * prime ≤ candidate)
    (hwidth : qHigh < 2 ^ 64) :
    cudaTailStart? qLow qHigh prime =
        some (firstComposite qLow prime, firstCofactor qLow prime) ∧
      firstComposite qLow prime ≤ candidate ∧
      firstComposite qLow prime < 2 ^ 64 ∧
      64 * prime < 2 ^ 64 ∧
      Odd (firstComposite qLow prime) := by
  obtain ⟨cofactor, rfl⟩ := hdivides
  have hprimePositive : 0 < prime := by omega
  have hcandidateOdd' : Odd (cofactor * prime) := by
    simpa [Nat.mul_comm] using hcandidateOdd
  have hlow' : qLow ≤ cofactor * prime := by
    simpa [Nat.mul_comm] using hlow
  have hhigh' : cofactor * prime ≤ qHigh := by
    simpa [Nat.mul_comm] using hhigh
  have hsquare' : prime * prime ≤ cofactor * prime := by
    simpa [Nat.mul_comm] using hsquare
  have hprimeSquareHigh : prime * prime ≤ qHigh :=
    hsquare.trans hhigh
  have hprimeGuard : prime ≤ qHigh / prime := by
    exact (Nat.le_div_iff_mul_le hprimePositive).2 hprimeSquareHigh
  have hceilingCofactor :
      ceilingCofactor qLow prime ≤ cofactor :=
    ceilingCofactor_le_of_le_mul hprimePositive (by
      simpa [Nat.mul_comm] using hlow)
  have hcofactorHigh : cofactor ≤ qHigh / prime := by
    apply (Nat.le_div_iff_mul_le hprimePositive).2
    simpa [Nat.mul_comm] using hhigh
  have hceilingGuard :
      ceilingCofactor qLow prime ≤ qHigh / prime :=
    hceilingCofactor.trans hcofactorHigh
  have hparityGuard :
      ¬ (Even (ceilingCofactor qLow prime * prime) ∧
        qHigh - prime < ceilingCofactor qLow prime * prime) := by
    rintro ⟨heven, htooHigh⟩
    have hadjusted :
        oddAdjustedCofactor qLow prime ≤ cofactor :=
      oddAdjustedCofactor_le hceilingCofactor hcandidateOdd'
    have hsuccessor :
        ceilingCofactor qLow prime + 1 ≤ cofactor := by
      simpa [oddAdjustedCofactor, heven] using hadjusted
    have hsuccessorHigh :
        (ceilingCofactor qLow prime + 1) * prime ≤ qHigh :=
      (Nat.mul_le_mul_right prime hsuccessor).trans hhigh'
    rw [Nat.add_mul] at hsuccessorHigh
    simp only [one_mul] at hsuccessorHigh
    omega
  have hfirstCofactor :
      firstCofactor qLow prime ≤ cofactor :=
    firstCofactor_le_of_candidate hprimePositive hcandidateOdd'
      hlow' hsquare'
  have hfirstHigh :
      firstComposite qLow prime ≤ prime * cofactor := by
    simp only [firstComposite]
    simpa [Nat.mul_comm] using
      Nat.mul_le_mul_right prime hfirstCofactor
  have hfirstCandidate :
      firstComposite qLow prime ≤ prime * cofactor :=
    hfirstHigh
  have hfirstQHigh :
      firstComposite qLow prime ≤ qHigh :=
    hfirstCandidate.trans hhigh
  have hwarpStepWidth : 64 * prime < 2 ^ 64 := by
    by_cases hsmall : prime < 64
    · have : 64 * prime < 64 * 64 :=
        (Nat.mul_lt_mul_left (by norm_num : 0 < 64)).2 hsmall
      norm_num at this ⊢
      omega
    · have hlarge : 64 ≤ prime := by omega
      have hwarpBelowSquare : 64 * prime ≤ prime * prime :=
        Nat.mul_le_mul_right prime hlarge
      exact
        (hwarpBelowSquare.trans hprimeSquareHigh).trans_lt hwidth
  have haccepted :
      cudaTailStart? qLow qHigh prime =
        some (firstComposite qLow prime, firstCofactor qLow prime) := by
    simp only [cudaTailStart?]
    rw [if_neg (by omega : ¬ prime < 3)]
    rw [if_neg (by omega : ¬ qHigh / prime < prime)]
    rw [if_neg (by omega :
      ¬ qHigh / prime < ceilingCofactor qLow prime)]
    rw [if_neg hparityGuard]
    have hfinalGuard :
        ¬ qHigh < firstCofactor qLow prime * prime := by
      exact Nat.not_lt_of_ge (by
        simpa only [firstComposite] using hfirstQHigh)
    rw [if_neg hfinalGuard]
    rfl
  refine
    ⟨haccepted, hfirstCandidate, hfirstQHigh.trans_lt hwidth,
      hwarpStepWidth, ?_⟩
  exact
    (firstComposite_properties qLow prime hprimePositive hprimeOdd).2.2.1

/-- Bounded one-thread completeness: the source start is accepted, the
sequential source progression reaches the candidate, and its literal packed
odd-window bit is live. -/
theorem boundedTail_complete
    {qLow qHigh prime candidate : Nat}
    (hprime : 3 ≤ prime)
    (hprimeOdd : Odd prime) (hqLowOdd : Odd qLow)
    (hcandidateOdd : Odd candidate)
    (hdivides : prime ∣ candidate)
    (hlow : qLow ≤ candidate) (hhigh : candidate ≤ qHigh)
    (hsquare : prime * prime ≤ candidate)
    (hwidth : qHigh < 2 ^ 64) :
    cudaTailStart? qLow qHigh prime =
        some (firstComposite qLow prime, firstCofactor qLow prime) ∧
      ∃ index : Nat,
        tailComposite qLow prime index = candidate ∧
          TailLoopReaches qLow qHigh prime index ∧
          candidate =
            qLow + 2 * oddBitIndex qLow candidate ∧
          oddBitIndex qLow candidate < oddWindowCount qLow qHigh := by
  have hstart :=
    cudaTailStart_eq_some_of_bounded_candidate hprime hprimeOdd
      hcandidateOdd hdivides hlow hhigh hsquare hwidth
  obtain ⟨index, hindex⟩ :=
    tailComposite_complete (by omega) hprimeOdd hcandidateOdd
      hdivides hlow hsquare
  have hbit :=
    oddBitIndex_live_of_bounds hqLowOdd hcandidateOdd hlow hhigh
  have hreaches :=
    tailLoopReaches_of_target hindex hhigh
  exact ⟨hstart.1, index, hindex, hreaches, hbit⟩

/-- The 32-lane kernel schedule is complete as well: Euclidean division of
the sequential progression index supplies the exact lane and round. -/
theorem warpTail_complete
    {qLow prime candidate : Nat}
    (hprime : 0 < prime)
    (hprimeOdd : Odd prime)
    (hcandidateOdd : Odd candidate)
    (hdivides : prime ∣ candidate)
    (hlow : qLow ≤ candidate)
    (hsquare : prime * prime ≤ candidate) :
    ∃ lane : Fin 32, ∃ round : Nat,
      warpComposite
        (firstComposite qLow prime) (2 * prime) lane round =
        candidate := by
  obtain ⟨index, hindex⟩ :=
    tailComposite_complete hprime hprimeOdd hcandidateOdd
      hdivides hlow hsquare
  refine ⟨laneOfIndex index, index / 32, ?_⟩
  rw [warpComposite_covers]
  exact hindex

/-- Direct model of the one-warp loop's guarded reachability for one lane.
Every earlier lane round passes the `warpStep > qHigh - composite` break
test, so the target round is emitted. -/
def WarpLoopReaches
    (qHigh first step : Nat) (lane : Fin 32) (round : Nat) : Prop :=
  step * (lane : Nat) ≤ qHigh - first ∧
    warpComposite first step lane round ≤ qHigh ∧
    ∀ prior, prior < round →
      step * 32 ≤ qHigh - warpComposite first step lane prior

/-- A bounded target in one lane progression is reached before the source
warp loop's overflow-safe upper guard can stop it. -/
theorem warpLoopReaches_of_target
    {qHigh first step candidate round : Nat} {lane : Fin 32}
    (hwarp : warpComposite first step lane round = candidate)
    (hhigh : candidate ≤ qHigh) :
    WarpLoopReaches qHigh first step lane round := by
  constructor
  · have hzeroLe :
        warpComposite first step lane 0 ≤
          warpComposite first step lane round := by
      simp only [warpComposite, Nat.mul_zero, Nat.add_zero]
      apply Nat.add_le_add_left
      apply Nat.mul_le_mul_left
      omega
    have hzeroHigh :
        warpComposite first step lane 0 ≤ qHigh :=
      hzeroLe.trans (by simpa [hwarp] using hhigh)
    simp only [warpComposite, Nat.mul_zero, Nat.add_zero] at hzeroHigh
    exact Nat.le_sub_of_add_le (by
      simpa [Nat.add_comm] using hzeroHigh)
  constructor
  · simpa [hwarp] using hhigh
  · intro prior hprior
    have hcoordinate :
        (lane : Nat) + 32 * (prior + 1) ≤
          (lane : Nat) + 32 * round := by
      omega
    have hscaled :
        step * ((lane : Nat) + 32 * (prior + 1)) ≤
          step * ((lane : Nat) + 32 * round) :=
      Nat.mul_le_mul_left step hcoordinate
    have hnextHigh :
        warpComposite first step lane (prior + 1) ≤ qHigh := by
      have htoTarget :
          warpComposite first step lane (prior + 1) ≤
            warpComposite first step lane round := by
        simp only [warpComposite]
        exact Nat.add_le_add_left hscaled _
      exact htoTarget.trans (by simpa [hwarp] using hhigh)
    have hnext :
        warpComposite first step lane (prior + 1) =
          warpComposite first step lane prior + step * 32 := by
      simp only [warpComposite]
      ring
    rw [hnext] at hnextHigh
    omega

/-- Bounded one-warp completeness: the accepted source start reaches the
candidate in one exact lane/round pair, and the targeted packed bit is live. -/
theorem boundedWarpTail_complete
    {qLow qHigh prime candidate : Nat}
    (hprime : 3 ≤ prime)
    (hprimeOdd : Odd prime) (hqLowOdd : Odd qLow)
    (hcandidateOdd : Odd candidate)
    (hdivides : prime ∣ candidate)
    (hlow : qLow ≤ candidate) (hhigh : candidate ≤ qHigh)
    (hsquare : prime * prime ≤ candidate)
    (hwidth : qHigh < 2 ^ 64) :
    cudaTailStart? qLow qHigh prime =
        some (firstComposite qLow prime, firstCofactor qLow prime) ∧
      ∃ lane : Fin 32, ∃ round : Nat,
        warpComposite
            (firstComposite qLow prime) (2 * prime) lane round =
          candidate ∧
        WarpLoopReaches qHigh
          (firstComposite qLow prime) (2 * prime) lane round ∧
        candidate =
          qLow + 2 * oddBitIndex qLow candidate ∧
        oddBitIndex qLow candidate < oddWindowCount qLow qHigh := by
  have hstart :=
    cudaTailStart_eq_some_of_bounded_candidate hprime hprimeOdd
      hcandidateOdd hdivides hlow hhigh hsquare hwidth
  obtain ⟨lane, round, hwarp⟩ :=
    warpTail_complete (by omega) hprimeOdd hcandidateOdd
      hdivides hlow hsquare
  have hbit :=
    oddBitIndex_live_of_bounds hqLowOdd hcandidateOdd hlow hhigh
  have hreaches :=
    warpLoopReaches_of_target hwarp hhigh
  exact ⟨hstart.1, lane, round, hwarp, hreaches, hbit⟩

/-- Every emitted sequential tail term is a legitimate mathematical clear
event for its retained prime. -/
theorem tailComposite_clearedBy
    (basePrimes : List Nat) (qLow prime index : Nat)
    (hprime : 0 < prime) (hprimeOdd : Odd prime)
    (hmember : prime ∈ basePrimes) :
    ClearedBy basePrimes (tailComposite qLow prime index) := by
  have hproperties :=
    firstComposite_properties qLow prime hprime hprimeOdd
  refine ⟨prime, hmember, ?_, ?_⟩
  · apply Nat.dvd_add hproperties.2.2.2
      (dvd_mul_of_dvd_left (dvd_mul_left prime 2) index)
  · exact hproperties.2.1.trans
      (Nat.le_add_right _ _)

#print axioms ceilingCofactor_le_of_le_mul
#print axioms le_ceilingCofactor_mul
#print axioms bitmaskOne_eq_zero_iff_even
#print axioms cudaTailStart_some_eq
#print axioms oddAdjustedCofactor_odd
#print axioms oddAdjustedCofactor_le
#print axioms firstCofactor_odd
#print axioms firstComposite_properties
#print axioms firstCofactor_le_of_candidate
#print axioms tailComposite_complete
#print axioms tailLoopReaches_of_target
#print axioms oddBitIndex_live_of_bounds
#print axioms cudaTailStart_eq_some_of_bounded_candidate
#print axioms boundedTail_complete
#print axioms warpTail_complete
#print axioms warpLoopReaches_of_target
#print axioms boundedWarpTail_complete
#print axioms tailComposite_clearedBy

end SparkInterval.TernaryGoldbach.GoldbachTailProgression

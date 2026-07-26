/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CStepRefinement

/-!
# Source-level restoring division for the Sqrt218 C checker

This module models the reachable successful path of `tg_u128_div_u64`.
The source scans all 128 numerator bits from most to least significant,
shifts the two-limb remainder, conditionally restores by subtracting the
one-word denominator, and rejects any quotient bit at index at least 64.

`cDivLoop` is the exact natural-number normal form of those limb operations.
Its pre-shift guard is the source guard on `rem_hi`; the conditional
subtraction and high-quotient-bit rejection occur in source order.  The
result word is represented without wrap because every set bit is distinct.
The terminal word bounds make the C field types explicit.

The main theorem proves, symbolically for arbitrary input limbs, that every
successful call returns natural-number quotient and remainder.  No concrete
certificate or production-sized computation occurs here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CU128DivRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

structure CDivResult where
  quotient : Nat
  remainder : Nat
  deriving Repr, DecidableEq, Inhabited

/-- The numerator bit read by the source at `bit_index`. -/
def cNumeratorBit (numerator bitIndex : Nat) : Nat :=
  numerator / 2 ^ bitIndex % 2

/-- Restoring division after `position` low bits remain to be scanned.

`result` is the mathematical value of the source `uint64_t` bitset.  On a
reachable state it is a multiple of `2^position`, so adding the fresh bit
`2^(position-1)` is exactly the source `|=` operation.
-/
def cDivLoop (numerator denominator : Nat) :
    Nat → Nat → Nat → Option CDivResult
  | 0, remainder, result =>
      if remainder < limbBase ∧ result < limbBase then
        some ⟨result, remainder⟩
      else
        none
  | position + 1, remainder, result =>
      if remainder < 2 * limbBase then
        let bit := cNumeratorBit numerator position
        let shifted := 2 * remainder + bit
        if denominator ≤ shifted then
          if position < 64 then
            cDivLoop numerator denominator position
              (shifted - denominator) (result + 2 ^ position)
          else
            none
        else
          cDivLoop numerator denominator position shifted result
      else
        none

/-- Full source entry, including the zero-denominator rejection. -/
def cU128DivU64
    (numeratorHi numeratorLo denominator : Nat) :
    Option CDivResult :=
  if denominator = 0 then
    none
  else
    cDivLoop
      (numeratorHi * limbBase + numeratorLo)
      denominator 128 0 0

theorem cNumeratorBit_lt_two
    (numerator bitIndex : Nat) :
    cNumeratorBit numerator bitIndex < 2 := by
  exact Nat.mod_lt _ (by omega)

/-- Binary decomposition of the prefix exposed by the next source bit. -/
theorem div_pow_succ
    (numerator position : Nat) :
    numerator / 2 ^ position =
      2 * (numerator / 2 ^ (position + 1)) +
        cNumeratorBit numerator position := by
  have hdecomp :=
    Nat.mod_add_div (numerator / 2 ^ position) 2
  have hdiv :
      numerator / 2 ^ position / 2 =
        numerator / 2 ^ (position + 1) := by
    rw [Nat.div_div_eq_div_mul, pow_succ]
  unfold cNumeratorBit
  rw [← hdiv]
  omega

/-- Arithmetic invariant of a reachable loop state.

`prefixQuotient` is the quotient of the already scanned high prefix.  The
source result bitset is that prefix quotient shifted left by the number of
unscanned positions.
-/
def CDivInvariant
    (numerator denominator position remainder result : Nat) : Prop :=
  ∃ prefixQuotient,
    result = prefixQuotient * 2 ^ position ∧
      numerator / 2 ^ position =
        prefixQuotient * denominator + remainder ∧
      remainder < denominator

private theorem invariant_no_restore
    {numerator denominator position remainder result : Nat}
    (hinvariant :
      CDivInvariant numerator denominator (position + 1)
        remainder result)
    (hshifted :
      2 * remainder + cNumeratorBit numerator position <
        denominator) :
    CDivInvariant numerator denominator position
      (2 * remainder + cNumeratorBit numerator position) result := by
  rcases hinvariant with
    ⟨prefixQuotient, hresult, hprefix, hremainder⟩
  refine ⟨2 * prefixQuotient, ?_, ?_, hshifted⟩
  · rw [hresult, pow_succ]
    ring
  · rw [div_pow_succ, hprefix]
    ring

private theorem invariant_restore
    {numerator denominator position remainder result : Nat}
    (hinvariant :
      CDivInvariant numerator denominator (position + 1)
        remainder result)
    (hrestore :
      denominator ≤
        2 * remainder + cNumeratorBit numerator position) :
    CDivInvariant numerator denominator position
      (2 * remainder + cNumeratorBit numerator position - denominator)
      (result + 2 ^ position) := by
  rcases hinvariant with
    ⟨prefixQuotient, hresult, hprefix, hremainder⟩
  have hbit :=
    cNumeratorBit_lt_two numerator position
  have hshiftedLt :
      2 * remainder + cNumeratorBit numerator position <
        2 * denominator := by
    omega
  refine ⟨2 * prefixQuotient + 1, ?_, ?_, by omega⟩
  · rw [hresult, pow_succ]
    ring
  · rw [div_pow_succ, hprefix]
    have hsplit :
        2 * remainder + cNumeratorBit numerator position =
          denominator +
            (2 * remainder + cNumeratorBit numerator position -
              denominator) := by
      omega
    calc
      2 * (prefixQuotient * denominator + remainder) +
            cNumeratorBit numerator position =
          (2 * prefixQuotient) * denominator +
            (2 * remainder + cNumeratorBit numerator position) := by
        ring
      _ =
          (2 * prefixQuotient) * denominator +
            (denominator +
              (2 * remainder + cNumeratorBit numerator position -
                denominator)) := by
        exact
          congrArg
            (fun value =>
              (2 * prefixQuotient) * denominator + value)
            hsplit
      _ =
          (2 * prefixQuotient + 1) * denominator +
            (2 * remainder + cNumeratorBit numerator position -
              denominator) := by
        ring

/-- A successful loop from an invariant state returns an ordinary Euclidean
decomposition, together with explicit word bounds. -/
theorem cDivLoop_sound
    {numerator denominator position remainder result : Nat}
    {output : CDivResult}
    (_hdenominatorPositive : 0 < denominator)
    (hdenominatorFits : denominator < limbBase)
    (hinvariant :
      CDivInvariant numerator denominator position remainder result)
    (hrun :
      cDivLoop numerator denominator position remainder result =
        some output) :
    output.quotient * denominator + output.remainder = numerator ∧
      output.remainder < denominator ∧
      output.quotient < limbBase := by
  induction position generalizing remainder result with
  | zero =>
      simp only [cDivLoop] at hrun
      by_cases hterminal :
          remainder < limbBase ∧ result < limbBase
      · rw [if_pos hterminal] at hrun
        have houtput : CDivResult.mk result remainder = output :=
          Option.some.inj hrun
        subst output
        rcases hinvariant with
          ⟨prefixQuotient, hresult, hprefix, hremainder⟩
        simp only [pow_zero, Nat.mul_one] at hresult hprefix
        subst result
        simpa only [CDivResult.quotient, CDivResult.remainder,
          Nat.div_one] using
          And.intro hprefix.symm ⟨hremainder, hterminal.2⟩
      · rw [if_neg hterminal] at hrun
        contradiction
  | succ position inductionHypothesis =>
      simp only [cDivLoop] at hrun
      have hremainderLt : remainder < denominator := by
        rcases hinvariant with
          ⟨_prefixQuotient, _hresult, _hprefix, hremainder⟩
        exact hremainder
      have hshiftGuard : remainder < 2 * limbBase := by
        exact hremainderLt.trans
          (hdenominatorFits.trans (by omega))
      rw [if_pos hshiftGuard] at hrun
      let bit := cNumeratorBit numerator position
      let shifted := 2 * remainder + bit
      by_cases hrestore : denominator ≤ shifted
      · rw [if_pos hrestore] at hrun
        by_cases hquotientBit : position < 64
        · rw [if_pos hquotientBit] at hrun
          apply inductionHypothesis
            (invariant_restore hinvariant (by
              simpa only [shifted, bit] using hrestore)) hrun
        · rw [if_neg hquotientBit] at hrun
          contradiction
      · rw [if_neg hrestore] at hrun
        apply inductionHypothesis
          (invariant_no_restore hinvariant (by
            simpa only [shifted, bit] using
              (Nat.lt_of_not_ge hrestore))) hrun

theorem numerator_fits_capacity
    {numeratorHi numeratorLo : Nat}
    (hhi : numeratorHi < limbBase)
    (hlo : numeratorLo < limbBase) :
    numeratorHi * limbBase + numeratorLo < capacity := by
  calc
    numeratorHi * limbBase + numeratorLo <
        numeratorHi * limbBase + limbBase := by omega
    _ = (numeratorHi + 1) * limbBase := by ring
    _ ≤ limbBase * limbBase := by
      exact Nat.mul_le_mul_right limbBase (Nat.succ_le_of_lt hhi)
    _ = capacity := by rfl

/-- Successful `tg_u128_div_u64` returns exact natural division and modulus,
and its quotient is a genuine `uint64_t` word. -/
theorem cU128DivU64_sound
    {numeratorHi numeratorLo denominator : Nat}
    {output : CDivResult}
    (hhi : numeratorHi < limbBase)
    (hlo : numeratorLo < limbBase)
    (hdenominator : denominator < limbBase)
    (hrun :
      cU128DivU64 numeratorHi numeratorLo denominator =
        some output) :
    0 < denominator ∧
      output.quotient =
        (numeratorHi * limbBase + numeratorLo) / denominator ∧
      output.remainder =
        (numeratorHi * limbBase + numeratorLo) % denominator ∧
      output.quotient < limbBase ∧
      output.remainder < denominator := by
  unfold cU128DivU64 at hrun
  by_cases hzero : denominator = 0
  · rw [if_pos hzero] at hrun
    contradiction
  · rw [if_neg hzero] at hrun
    have hdenominatorPositive : 0 < denominator :=
      Nat.zero_lt_of_ne_zero hzero
    let numerator := numeratorHi * limbBase + numeratorLo
    have hnumerator : numerator < capacity := by
      exact numerator_fits_capacity hhi hlo
    have hpow : 2 ^ 128 = capacity := by
      norm_num [capacity, limbBase, pow_succ]
    have hprefix : numerator / 2 ^ 128 = 0 := by
      apply Nat.div_eq_of_lt
      rw [hpow]
      exact hnumerator
    have hinvariant :
        CDivInvariant numerator denominator 128 0 0 := by
      refine ⟨0, by simp, ?_, by omega⟩
      simpa only [zero_mul, zero_add] using hprefix
    have hsound :=
      cDivLoop_sound
        hdenominatorPositive hdenominator hinvariant hrun
    have hquotient :
        numerator / denominator = output.quotient := by
      apply Nat.div_eq_of_lt_le
      · omega
      · calc
          numerator =
              output.quotient * denominator + output.remainder := by
            exact hsound.1.symm
          _ < output.quotient * denominator + denominator := by
            omega
          _ = (output.quotient + 1) * denominator := by ring
    have hremainder :
        numerator % denominator = output.remainder := by
      have hdecomp := Nat.mod_add_div numerator denominator
      rw [hquotient] at hdecomp
      have hmodDecomp :
          output.quotient * denominator +
              numerator % denominator =
            numerator := by
        simpa only [Nat.add_comm, Nat.mul_comm] using hdecomp
      exact Nat.add_left_cancel (hmodDecomp.trans hsound.1.symm)
    exact
      ⟨hdenominatorPositive, hquotient.symm, hremainder.symm,
        hsound.2.2, hsound.2.1⟩

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CU128DivRefinement

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CPrimitives
import SparkInterval.TernaryGoldbach.Sqrt218.Operational.V2.Pratt

/-!
# Source-level modular arithmetic for the Sqrt218 C checker

This module models the three integer-only helpers `tg_add_mod`,
`tg_mul_mod`, and `tg_pow_mod` in
`cpu_checker/sqrt218/sqrt218_cpu_checker.c`.

The source represents a `uint64_t` word by a natural number together with an
explicit `< 2^64` hypothesis.  Division by two models `>> 1`, and remainder
modulo two models `& 1`.  The conditional-subtraction addition is proved not
to overflow and to equal addition modulo the nonzero modulus.

All theorems are symbolic in their inputs.  This file contains no production
certificate and performs no certificate replay.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CModularRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218Operational.V2

/-! ## `tg_add_mod` -/

/-- Literal arithmetic spelling of `tg_add_mod`.

The C caller invariant is `a < modulus` and `b < modulus`.  Under that
invariant `modulus - b` is positive, the selected subtraction cannot
underflow, and the unselected sum cannot overflow. -/
def cAddMod (a b modulus : Nat) : Nat :=
  if modulus - b ≤ a then
    a - (modulus - b)
  else
    a + b

/-- The conditional-subtraction source helper is exact modular addition. -/
theorem cAddMod_eq_mod
    {a b modulus : Nat}
    (_hmodulus : 0 < modulus)
    (ha : a < modulus)
    (hb : b < modulus) :
    cAddMod a b modulus = (a + b) % modulus := by
  unfold cAddMod
  by_cases hwrap : modulus - b ≤ a
  · rw [if_pos hwrap]
    have hsum : modulus ≤ a + b := by omega
    have hreduced : a + b - modulus < modulus := by omega
    rw [Nat.mod_eq_sub_mod hsum, Nat.mod_eq_of_lt hreduced]
    omega
  · rw [if_neg hwrap]
    have hsum : a + b < modulus := by omega
    exact (Nat.mod_eq_of_lt hsum).symm

theorem cAddMod_lt
    {a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (ha : a < modulus)
    (hb : b < modulus) :
    cAddMod a b modulus < modulus := by
  rw [cAddMod_eq_mod hmodulus ha hb]
  exact Nat.mod_lt _ hmodulus

theorem cAddMod_modEq
    {a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (ha : a < modulus)
    (hb : b < modulus) :
    cAddMod a b modulus ≡ a + b [MOD modulus] := by
  rw [cAddMod_eq_mod hmodulus ha hb]
  exact Nat.mod_modEq _ _

/-- In the source word regime the selected branch also fits in `uint64_t`. -/
theorem cAddMod_word_fits
    {a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (hmodulusWord : modulus < limbBase)
    (ha : a < modulus)
    (hb : b < modulus) :
    cAddMod a b modulus < limbBase :=
  (cAddMod_lt hmodulus ha hb).trans hmodulusWord

/-! ## `tg_mul_mod` -/

/-- One recursive presentation of the source's double-and-add loop.

The branch which doubles `a` is intentionally skipped after shifting the
last nonzero bit, exactly as in C.  Well-founded recursion follows the
strict decrease of `b / 2` when `b` is nonzero. -/
def cMulModLoop
    (result a b modulus : Nat) : Nat :=
  if hzero : b = 0 then
    result
  else
    let nextResult :=
      if b % 2 = 1 then cAddMod result a modulus else result
    let shifted := b / 2
    let nextA :=
      if shifted ≠ 0 then cAddMod a a modulus else a
    cMulModLoop nextResult nextA shifted modulus
termination_by b
decreasing_by
  exact Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)

/-- Source entry: reduce the multiplicand and start with a zero accumulator. -/
def cMulMod (a b modulus : Nat) : Nat :=
  cMulModLoop 0 (a % modulus) b modulus

private theorem mod_two_eq_zero_or_one (value : Nat) :
    value % 2 = 0 ∨ value % 2 = 1 := by
  have hlt : value % 2 < 2 := Nat.mod_lt _ (by omega)
  omega

private theorem div_two_decomposition (value : Nat) :
    value = value % 2 + 2 * (value / 2) := by
  have h := Nat.mod_add_div value 2
  omega

/-- The exact loop result stays in the canonical residue range. -/
theorem cMulModLoop_lt
    {result a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (hresult : result < modulus)
    (ha : a < modulus) :
    cMulModLoop result a b modulus < modulus := by
  induction b using Nat.strong_induction_on generalizing result a with
  | h b inductionHypothesis =>
      rw [cMulModLoop]
      by_cases hzero : b = 0
      · simp only [hzero, dite_true]
        exact hresult
      · simp only [hzero, dite_false]
        have hshift :
            b / 2 < b :=
          Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)
        let nextResult :=
          if b % 2 = 1 then cAddMod result a modulus else result
        let shifted := b / 2
        let nextA :=
          if shifted ≠ 0 then cAddMod a a modulus else a
        have hnextResult : nextResult < modulus := by
          dsimp only [nextResult]
          split
          · exact cAddMod_lt hmodulus hresult ha
          · exact hresult
        have hnextA : nextA < modulus := by
          dsimp only [nextA]
          split
          · exact cAddMod_lt hmodulus ha ha
          · exact ha
        exact
          inductionHypothesis shifted (by simpa [shifted] using hshift)
            hnextResult hnextA

/-- Loop invariant: the returned residue is congruent to
`result + a * b` modulo `modulus`. -/
theorem cMulModLoop_modEq
    {result a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (hresult : result < modulus)
    (ha : a < modulus) :
    cMulModLoop result a b modulus ≡
      result + a * b [MOD modulus] := by
  induction b using Nat.strong_induction_on generalizing result a with
  | h b inductionHypothesis =>
      rw [cMulModLoop]
      by_cases hzero : b = 0
      · subst b
        simp only [dite_true, mul_zero, add_zero]
        exact Nat.ModEq.rfl
      · simp only [hzero, dite_false]
        have hshift :
            b / 2 < b :=
          Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)
        let nextResult :=
          if b % 2 = 1 then cAddMod result a modulus else result
        let shifted := b / 2
        let nextA :=
          if shifted ≠ 0 then cAddMod a a modulus else a
        have hnextResult : nextResult < modulus := by
          dsimp only [nextResult]
          split
          · exact cAddMod_lt hmodulus hresult ha
          · exact hresult
        have hnextResultMod :
            nextResult ≡ result + a * (b % 2) [MOD modulus] := by
          rcases mod_two_eq_zero_or_one b with hbit | hbit
          · simp only [nextResult, hbit, zero_ne_one, if_false, mul_zero,
              add_zero]
            exact Nat.ModEq.rfl
          · simp only [nextResult, hbit, if_true, mul_one]
            exact cAddMod_modEq hmodulus hresult ha
        have hnextA : nextA < modulus := by
          by_cases hshiftNonzero : shifted ≠ 0
          · change
              (if shifted ≠ 0 then cAddMod a a modulus else a) <
                modulus
            rw [if_pos hshiftNonzero]
            exact cAddMod_lt hmodulus ha ha
          · change
              (if shifted ≠ 0 then cAddMod a a modulus else a) <
                modulus
            rw [if_neg hshiftNonzero]
            exact ha
        have hnextAMult :
            nextA * shifted ≡ (a + a) * shifted [MOD modulus] := by
          by_cases hshiftNonzero : shifted ≠ 0
          · have hnextAMod :
                nextA ≡ a + a [MOD modulus] := by
              change
                (if shifted ≠ 0 then cAddMod a a modulus else a) ≡
                  a + a [MOD modulus]
              rw [if_pos hshiftNonzero]
              exact cAddMod_modEq hmodulus ha ha
            exact hnextAMod.mul_right shifted
          · have hshiftZero : shifted = 0 := by omega
            simp only [hshiftZero, mul_zero]
            exact Nat.ModEq.rfl
        have ih :=
          inductionHypothesis shifted (by simpa [shifted] using hshift)
            hnextResult hnextA
        have hcombined :
            nextResult + nextA * shifted ≡
              (result + a * (b % 2)) +
                (a + a) * shifted [MOD modulus] :=
          hnextResultMod.add hnextAMult
        have hdecomp := div_two_decomposition b
        have harithmetic :
            (result + a * (b % 2)) + (a + a) * shifted =
              result + a * b := by
          dsimp only [shifted]
          calc
            (result + a * (b % 2)) + (a + a) * (b / 2) =
                result + a * (b % 2 + 2 * (b / 2)) := by ring
            _ = result + a * b := by rw [← hdecomp]
        rw [harithmetic] at hcombined
        exact ih.trans hcombined

/-- The C multiplication helper returns the canonical product residue. -/
theorem cMulMod_eq_mod
    {a b modulus : Nat}
    (hmodulus : 0 < modulus) :
    cMulMod a b modulus = (a * b) % modulus := by
  have ha : a % modulus < modulus := Nat.mod_lt _ hmodulus
  have hloopLt :
      cMulModLoop 0 (a % modulus) b modulus < modulus :=
    cMulModLoop_lt hmodulus hmodulus ha
  have hloopMod :
      cMulModLoop 0 (a % modulus) b modulus ≡
        0 + (a % modulus) * b [MOD modulus] :=
    cMulModLoop_modEq hmodulus hmodulus ha
  have haMod : a % modulus ≡ a [MOD modulus] :=
    Nat.mod_modEq _ _
  have htarget :
      0 + (a % modulus) * b ≡ a * b [MOD modulus] := by
    simpa using haMod.mul_right b
  have heqMod :
      cMulModLoop 0 (a % modulus) b modulus % modulus =
        (a * b) % modulus :=
    hloopMod.trans htarget
  rw [Nat.mod_eq_of_lt hloopLt] at heqMod
  simpa [cMulMod] using heqMod

/-- The source multiplication result remains a `uint64_t` word whenever its
nonzero modulus is a word. -/
theorem cMulMod_word_fits
    {a b modulus : Nat}
    (hmodulus : 0 < modulus)
    (hmodulusWord : modulus < limbBase) :
    cMulMod a b modulus < limbBase := by
  rw [cMulMod_eq_mod hmodulus]
  exact (Nat.mod_lt _ hmodulus).trans hmodulusWord

/-! ## `tg_pow_mod` -/

/-- The source's repeated-squaring exponentiation loop. -/
def cPowModLoop
    (result base exponent modulus : Nat) : Nat :=
  if hzero : exponent = 0 then
    result
  else
    let nextResult :=
      if exponent % 2 = 1 then
        cMulMod result base modulus
      else
        result
    let shifted := exponent / 2
    let nextBase :=
      if shifted ≠ 0 then cMulMod base base modulus else base
    cPowModLoop nextResult nextBase shifted modulus
termination_by exponent
decreasing_by
  exact Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)

/-- Source entry: canonical one and base residues followed by the exact loop. -/
def cPowMod (base exponent modulus : Nat) : Nat :=
  cPowModLoop (1 % modulus) (base % modulus) exponent modulus

private theorem pow_binary_decomposition (base exponent : Nat) :
    base ^ exponent =
      base ^ (exponent % 2) *
        (base * base) ^ (exponent / 2) := by
  have hdecomp := div_two_decomposition exponent
  calc
    base ^ exponent =
        base ^ (exponent % 2 + 2 * (exponent / 2)) := by rw [← hdecomp]
    _ = base ^ (exponent % 2) *
          base ^ (2 * (exponent / 2)) := by
      rw [pow_add]
    _ = base ^ (exponent % 2) *
          (base * base) ^ (exponent / 2) := by
      rw [pow_mul, pow_two]

theorem cPowModLoop_lt
    {result base exponent modulus : Nat}
    (hmodulus : 0 < modulus)
    (hresult : result < modulus)
    (hbase : base < modulus) :
    cPowModLoop result base exponent modulus < modulus := by
  induction exponent using Nat.strong_induction_on
      generalizing result base with
  | h exponent inductionHypothesis =>
      rw [cPowModLoop]
      by_cases hzero : exponent = 0
      · simp only [hzero, dite_true]
        exact hresult
      · simp only [hzero, dite_false]
        have hshift :
            exponent / 2 < exponent :=
          Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)
        let nextResult :=
          if exponent % 2 = 1 then
            cMulMod result base modulus
          else
            result
        let shifted := exponent / 2
        let nextBase :=
          if shifted ≠ 0 then cMulMod base base modulus else base
        have hnextResult : nextResult < modulus := by
          dsimp only [nextResult]
          split
          · rw [cMulMod_eq_mod hmodulus]
            exact Nat.mod_lt _ hmodulus
          · exact hresult
        have hnextBase : nextBase < modulus := by
          change
            (if shifted ≠ 0 then cMulMod base base modulus else base) <
              modulus
          by_cases hshiftNonzero : shifted ≠ 0
          · rw [if_pos hshiftNonzero, cMulMod_eq_mod hmodulus]
            exact Nat.mod_lt _ hmodulus
          · rw [if_neg hshiftNonzero]
            exact hbase
        exact
          inductionHypothesis shifted (by simpa [shifted] using hshift)
            hnextResult hnextBase

theorem cPowModLoop_modEq
    {result base exponent modulus : Nat}
    (hmodulus : 0 < modulus)
    (hresult : result < modulus)
    (hbase : base < modulus) :
    cPowModLoop result base exponent modulus ≡
      result * base ^ exponent [MOD modulus] := by
  induction exponent using Nat.strong_induction_on
      generalizing result base with
  | h exponent inductionHypothesis =>
      rw [cPowModLoop]
      by_cases hzero : exponent = 0
      · subst exponent
        simp only [dite_true, pow_zero, mul_one]
        exact Nat.ModEq.rfl
      · simp only [hzero, dite_false]
        have hshift :
            exponent / 2 < exponent :=
          Nat.div_lt_self (Nat.zero_lt_of_ne_zero hzero) (by omega)
        let nextResult :=
          if exponent % 2 = 1 then
            cMulMod result base modulus
          else
            result
        let shifted := exponent / 2
        let nextBase :=
          if shifted ≠ 0 then cMulMod base base modulus else base
        have hnextResult : nextResult < modulus := by
          dsimp only [nextResult]
          split
          · rw [cMulMod_eq_mod hmodulus]
            exact Nat.mod_lt _ hmodulus
          · exact hresult
        have hnextResultMod :
            nextResult ≡
              result * base ^ (exponent % 2) [MOD modulus] := by
          rcases mod_two_eq_zero_or_one exponent with hbit | hbit
          · simp only [nextResult, hbit, zero_ne_one, if_false, pow_zero,
              mul_one]
            exact Nat.ModEq.rfl
          · simp only [nextResult, hbit, if_true, pow_one]
            rw [cMulMod_eq_mod hmodulus]
            exact Nat.mod_modEq _ _
        have hnextBase : nextBase < modulus := by
          change
            (if shifted ≠ 0 then cMulMod base base modulus else base) <
              modulus
          by_cases hshiftNonzero : shifted ≠ 0
          · rw [if_pos hshiftNonzero, cMulMod_eq_mod hmodulus]
            exact Nat.mod_lt _ hmodulus
          · rw [if_neg hshiftNonzero]
            exact hbase
        have hnextBasePow :
            nextBase ^ shifted ≡
              (base * base) ^ shifted [MOD modulus] := by
          by_cases hshiftNonzero : shifted ≠ 0
          · have hnextBaseMod :
                nextBase ≡ base * base [MOD modulus] := by
              change
                (if shifted ≠ 0 then
                    cMulMod base base modulus
                  else
                    base) ≡ base * base [MOD modulus]
              rw [if_pos hshiftNonzero, cMulMod_eq_mod hmodulus]
              exact Nat.mod_modEq _ _
            exact hnextBaseMod.pow shifted
          · have hshiftZero : shifted = 0 := by omega
            simp only [hshiftZero, pow_zero]
            exact Nat.ModEq.rfl
        have ih :=
          inductionHypothesis shifted (by simpa [shifted] using hshift)
            hnextResult hnextBase
        have hcombined :
            nextResult * nextBase ^ shifted ≡
              (result * base ^ (exponent % 2)) *
                (base * base) ^ shifted [MOD modulus] :=
          hnextResultMod.mul hnextBasePow
        have harithmetic :
            (result * base ^ (exponent % 2)) *
                (base * base) ^ shifted =
              result * base ^ exponent := by
          rw [pow_binary_decomposition base exponent]
          ring
        rw [harithmetic] at hcombined
        exact ih.trans hcombined

/-- The C exponentiation helper returns the canonical power residue. -/
theorem cPowMod_eq_mod
    {base exponent modulus : Nat}
    (hmodulus : 0 < modulus) :
    cPowMod base exponent modulus = base ^ exponent % modulus := by
  have hone : 1 % modulus < modulus := Nat.mod_lt _ hmodulus
  have hbase : base % modulus < modulus := Nat.mod_lt _ hmodulus
  have hloopLt :
      cPowModLoop (1 % modulus) (base % modulus) exponent modulus <
        modulus :=
    cPowModLoop_lt hmodulus hone hbase
  have hloopMod :
      cPowModLoop (1 % modulus) (base % modulus) exponent modulus ≡
        (1 % modulus) * (base % modulus) ^ exponent [MOD modulus] :=
    cPowModLoop_modEq hmodulus hone hbase
  have honeMod : 1 % modulus ≡ 1 [MOD modulus] :=
    Nat.mod_modEq _ _
  have hbaseMod : base % modulus ≡ base [MOD modulus] :=
    Nat.mod_modEq _ _
  have htarget :
      (1 % modulus) * (base % modulus) ^ exponent ≡
        base ^ exponent [MOD modulus] := by
    simpa using honeMod.mul (hbaseMod.pow exponent)
  have heqMod :
      cPowModLoop (1 % modulus) (base % modulus) exponent modulus %
          modulus =
        base ^ exponent % modulus :=
    hloopMod.trans htarget
  rw [Nat.mod_eq_of_lt hloopLt] at heqMod
  simpa [cPowMod] using heqMod

/-- The source exponentiation result remains a `uint64_t` word whenever its
nonzero modulus is a word. -/
theorem cPowMod_word_fits
    {base exponent modulus : Nat}
    (hmodulus : 0 < modulus)
    (hmodulusWord : modulus < limbBase) :
    cPowMod base exponent modulus < limbBase := by
  rw [cPowMod_eq_mod hmodulus]
  exact (Nat.mod_lt _ hmodulus).trans hmodulusWord

/-- The source helper and the proved V2 Pratt operation denote the same
element of `ZMod modulus`. -/
theorem cPowMod_cast_eq_fastPow
    {base exponent modulus : Nat}
    (hmodulus : 0 < modulus) :
    (cPowMod base exponent modulus : ZMod modulus) =
      fastPow modulus base exponent := by
  rw [cPowMod_eq_mod hmodulus, fastPow_eq_pow]
  simp

/-- Equality with the source word `1` is exactly equality with one in the
Pratt check's `ZMod` semantics.  The strict `1 < modulus` hypothesis is the
nondegenerate prime-row regime used by the C caller. -/
theorem cPowMod_eq_one_iff_fastPow_eq_one
    {base exponent modulus : Nat}
    (hmodulus : 1 < modulus) :
    cPowMod base exponent modulus = 1 ↔
      fastPow modulus base exponent = 1 := by
  constructor
  · intro hsource
    rw [← cPowMod_cast_eq_fastPow (by omega)]
    simp [hsource]
  · intro hfast
    have hcast :
        (cPowMod base exponent modulus : ZMod modulus) =
          (1 : ZMod modulus) := by
      rw [cPowMod_cast_eq_fastPow (by omega)]
      exact hfast
    have hmodEq :
        cPowMod base exponent modulus ≡ 1 [MOD modulus] :=
      (ZMod.natCast_eq_natCast_iff _ _ _).mp (by
        simpa only [Nat.cast_one] using hcast)
    have hsourceLt :
        cPowMod base exponent modulus < modulus := by
      rw [cPowMod_eq_mod (by omega)]
      exact Nat.mod_lt _ (by omega)
    change
      cPowMod base exponent modulus % modulus =
        1 % modulus at hmodEq
    rw [Nat.mod_eq_of_lt hsourceLt,
      Nat.mod_eq_of_lt hmodulus] at hmodEq
    exact hmodEq

/-- Literal source-level residue pass over one complete factor list. -/
def cLucasResidueCheck
    (p witness : Nat) (primeFactors : List Nat) : Bool :=
  decide (cPowMod witness (p - 1) p = 1) &&
    primeFactors.all fun factor =>
      decide (cPowMod witness ((p - 1) / factor) p ≠ 1)

/-- The C loop's residue decisions are exactly the V2 Pratt decisions. -/
theorem cLucasResidueCheck_eq
    {p witness : Nat} (primeFactors : List Nat)
    (hp : 1 < p) :
    cLucasResidueCheck p witness primeFactors =
      lucasResidueCheck p witness primeFactors := by
  unfold cLucasResidueCheck lucasResidueCheck
  have htail :
      (fun factor =>
          decide (cPowMod witness ((p - 1) / factor) p ≠ 1)) =
        (fun factor =>
          decide (fastPow p witness ((p - 1) / factor) ≠ 1)) := by
    funext factor
    exact Bool.decide_congr
      (not_congr (cPowMod_eq_one_iff_fastPow_eq_one hp))
  rw [htail]
  exact congrArg
    (fun check => check && primeFactors.all fun factor =>
      decide (fastPow p witness ((p - 1) / factor) ≠ 1))
    (Bool.decide_congr (cPowMod_eq_one_iff_fastPow_eq_one hp))

/-- Removing duplicate factor references does not change a universal Boolean
residue pass. -/
theorem all_dedup_eq_all
    (values : List Nat) (predicate : Nat → Bool) :
    values.dedup.all predicate = values.all predicate := by
  apply Bool.eq_iff_iff.mpr
  simp only [List.all_eq_true, List.mem_dedup]

/-- The C source checks every multiplicity-preserving reference.  The V2
Pratt kernel checks the deduplicated factor values; the two decisions are
identical. -/
theorem cLucasResidueCheck_eq_dedup
    {p witness : Nat} (primeFactors : List Nat)
    (hp : 1 < p) :
    cLucasResidueCheck p witness primeFactors =
      lucasResidueCheck p witness primeFactors.dedup := by
  rw [cLucasResidueCheck_eq primeFactors hp]
  unfold lucasResidueCheck
  rw [all_dedup_eq_all]

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CModularRefinement

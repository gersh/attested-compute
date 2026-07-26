/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.Fixed128

/-!
# Source-level C integer primitives for the Sqrt218 checker

This file models the fixed-width integer expressions in
`cpu_checker/sqrt218/sqrt218_cpu_checker.c`.  Unsigned C words are represented
by naturals together with explicit `< 2^64` guards.  In particular, this is
not a model that silently gives C operations unbounded-natural semantics:

* `wordAdd` and `wordSub` wrap modulo `2^64`;
* `addCarry` is the literal post-addition comparison used by the C source;
* `mulWide32` is the source's four-`u32` wide-product decomposition;
* the checked two-limb operations use the same success/rejection guards as C.

The refinement theorems below show that every successful checked operation
agrees with the architecture-neutral `U128` natural-number specification.
They are data-independent and do not load or replay a certificate.

This is a source-semantics bridge.  It does not claim that a particular
compiler or machine-code binary refines the C source.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-! ## Unsigned word and big-endian field models -/

/-- One past the largest `uint32_t` value. -/
def halfBase : Nat := 2 ^ 32

/-- The largest `uint64_t` value. -/
def wordMax : Nat := limbBase - 1

theorem halfBase_pos : 0 < halfBase := by
  norm_num [halfBase]

theorem limbBase_eq_halfBase_sq :
    limbBase = halfBase * halfBase := by
  norm_num [limbBase, halfBase]

/-- The value of the C expression `(uint16_t)p[0] << 8 | p[1]`. -/
def readBE16 (b0 b1 : UInt8) : Nat :=
  b0.toNat * 2 ^ 8 + b1.toNat

/-- The value of the four cast-before-shift terms in `tg_read_be32`. -/
def readBE32 (b0 b1 b2 b3 : UInt8) : Nat :=
  b0.toNat * 2 ^ 24 +
    b1.toNat * 2 ^ 16 +
    b2.toNat * 2 ^ 8 +
    b3.toNat

/-- The value of the eight cast-before-shift terms in `tg_read_be64`. -/
def readBE64
    (b0 b1 b2 b3 b4 b5 b6 b7 : UInt8) : Nat :=
  b0.toNat * 2 ^ 56 +
    b1.toNat * 2 ^ 48 +
    b2.toNat * 2 ^ 40 +
    b3.toNat * 2 ^ 32 +
    b4.toNat * 2 ^ 24 +
    b5.toNat * 2 ^ 16 +
    b6.toNat * 2 ^ 8 +
    b7.toNat

theorem readBE16_fits (b0 b1 : UInt8) :
    readBE16 b0 b1 < 2 ^ 16 := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  norm_num [readBE16] at *
  omega

theorem readBE32_fits (b0 b1 b2 b3 : UInt8) :
    readBE32 b0 b1 b2 b3 < 2 ^ 32 := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  have h2 := UInt8.toNat_lt b2
  have h3 := UInt8.toNat_lt b3
  norm_num [readBE32] at *
  omega

theorem readBE64_fits (b0 b1 b2 b3 b4 b5 b6 b7 : UInt8) :
    readBE64 b0 b1 b2 b3 b4 b5 b6 b7 < limbBase := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  have h2 := UInt8.toNat_lt b2
  have h3 := UInt8.toNat_lt b3
  have h4 := UInt8.toNat_lt b4
  have h5 := UInt8.toNat_lt b5
  have h6 := UInt8.toNat_lt b6
  have h7 := UInt8.toNat_lt b7
  norm_num [readBE64, limbBase] at *
  omega

/-! ## Exact `uint64_t` wraparound primitives -/

/-- Unsigned `uint64_t` addition, including its C wraparound. -/
def wordAdd (left right : Nat) : Nat :=
  (left + right) % limbBase

/-- Literal carry test `result < left` used by the C implementation. -/
def addCarry (left right : Nat) : Nat :=
  if wordAdd left right < left then 1 else 0

/-- Unsigned `uint64_t` subtraction, including its C wraparound.

The branch expression is an arithmetic spelling of subtraction modulo
`2^64`; it avoids relying on Lean's truncating `Nat.sub` for the borrow case.
-/
def wordSub (left right : Nat) : Nat :=
  if right ≤ left then left - right else limbBase + left - right

theorem wordAdd_lt (left right : Nat) :
    wordAdd left right < limbBase :=
  Nat.mod_lt _ limbBase_pos

theorem wordSub_lt {left right : Nat}
    (hleft : left < limbBase) (hright : right < limbBase) :
    wordSub left right < limbBase := by
  unfold wordSub
  split
  · omega
  · omega

/-- The wrapped low word plus the literal carry reconstructs the exact sum. -/
theorem wordAdd_addCarry {left right : Nat}
    (hleft : left < limbBase) (hright : right < limbBase) :
    wordAdd left right + addCarry left right * limbBase =
      left + right := by
  by_cases hsum : left + right < limbBase
  · have hwrap : wordAdd left right = left + right := by
      exact Nat.mod_eq_of_lt hsum
    have hncarry : ¬wordAdd left right < left := by
      rw [hwrap]
      omega
    rw [addCarry, if_neg hncarry, hwrap]
    omega
  · have hbase : limbBase ≤ left + right := Nat.le_of_not_gt hsum
    have htwice : left + right - limbBase < limbBase := by
      omega
    have hwrap :
        wordAdd left right = left + right - limbBase := by
      rw [wordAdd, Nat.mod_eq_sub_mod hbase,
        Nat.mod_eq_of_lt htwice]
    have hcarry : wordAdd left right < left := by
      rw [hwrap]
      omega
    rw [addCarry, if_pos hcarry, hwrap]
    omega

theorem addCarry_le_one (left right : Nat) :
    addCarry left right ≤ 1 := by
  unfold addCarry
  split <;> omega

/-- Exact source model of `tg_u64_add_checked`. -/
def wordAddChecked (left right : Nat) : Option Nat :=
  let result := wordAdd left right
  if result < left then none else some result

theorem wordAddChecked_sound {left right result : Nat}
    (hleft : left < limbBase) (hright : right < limbBase)
    (hcheck : wordAddChecked left right = some result) :
    result < limbBase ∧ result = left + right := by
  change
    (if wordAdd left right < left then none
      else some (wordAdd left right)) = some result at hcheck
  split at hcheck
  · contradiction
  next hncarry =>
    cases hcheck
    have hreconstruct := wordAdd_addCarry hleft hright
    have hcarry : addCarry left right = 0 := by
      simp [addCarry, hncarry]
    constructor
    · exact wordAdd_lt left right
    · simp [hcarry] at hreconstruct
      exact hreconstruct

/-- Exact source model of `tg_u64_mul_checked`. -/
def wordMulChecked (left right : Nat) : Option Nat :=
  if left ≠ 0 ∧ wordMax / left < right then
    none
  else
    some (left * right)

theorem wordMulChecked_sound
    {left right result : Nat}
    (_hleft : left < limbBase)
    (_hright : right < limbBase)
    (hcheck : wordMulChecked left right = some result) :
    result < limbBase ∧ result = left * right := by
  unfold wordMulChecked at hcheck
  by_cases hoverflow : left ≠ 0 ∧ wordMax / left < right
  · rw [if_pos hoverflow] at hcheck
    contradiction
  · rw [if_neg hoverflow] at hcheck
    cases hcheck
    constructor
    · by_cases hzero : left = 0
      · simp [hzero, limbBase_pos]
      · have hquotient : right ≤ wordMax / left := by
          by_contra hnot
          exact hoverflow ⟨hzero, by omega⟩
        have hproduct : right * left ≤ wordMax :=
          (Nat.le_div_iff_mul_le
            (Nat.zero_lt_of_ne_zero hzero)).mp hquotient
        have hproduct' : left * right ≤ wordMax := by
          simpa only [Nat.mul_comm] using hproduct
        dsimp only [wordMax] at hproduct'
        omega
    · rfl

/-- A mathematically fitting sum follows the successful C checked-add path. -/
theorem wordAddChecked_eq_some_of_sum_fits
    {left right : Nat}
    (hsum : left + right < limbBase) :
    wordAddChecked left right = some (left + right) := by
  unfold wordAddChecked wordAdd
  rw [Nat.mod_eq_of_lt hsum]
  rw [if_neg (by omega)]

/-! ## Literal four-`u32` wide multiplication -/

structure WideProduct where
  high : Nat
  low : Nat
  deriving Repr, DecidableEq

/-- The arithmetic form of `tg_mul64_wide`.

`% halfBase` models `& 0xffffffff`, `/ halfBase` models `>> 32`,
and the final addition in `low` models the source's disjoint-bit `|`.
-/
def mulWide32 (left right : Nat) : WideProduct :=
  let left0 := left % halfBase
  let left1 := left / halfBase
  let right0 := right % halfBase
  let right1 := right / halfBase
  let p00 := left0 * right0
  let p01 := left0 * right1
  let p10 := left1 * right0
  let p11 := left1 * right1
  let middle :=
    p00 / halfBase + p01 % halfBase + p10 % halfBase
  {
    low := p00 % halfBase + (middle % halfBase) * halfBase
    high :=
      p11 + p01 / halfBase + p10 / halfBase +
        middle / halfBase
  }

theorem mulWide32_value (left right : Nat) :
    (mulWide32 left right).high * limbBase +
        (mulWide32 left right).low =
      left * right := by
  let left0 := left % halfBase
  let left1 := left / halfBase
  let right0 := right % halfBase
  let right1 := right / halfBase
  let p00 := left0 * right0
  let p01 := left0 * right1
  let p10 := left1 * right0
  let p11 := left1 * right1
  let middle :=
    p00 / halfBase + p01 % halfBase + p10 % halfBase
  have hleft : left0 + halfBase * left1 = left := by
    simpa [left0, left1] using Nat.mod_add_div left halfBase
  have hright : right0 + halfBase * right1 = right := by
    simpa [right0, right1] using Nat.mod_add_div right halfBase
  have hp00 :
      p00 % halfBase + halfBase * (p00 / halfBase) = p00 :=
    Nat.mod_add_div p00 halfBase
  have hp01 :
      p01 % halfBase + halfBase * (p01 / halfBase) = p01 :=
    Nat.mod_add_div p01 halfBase
  have hp10 :
      p10 % halfBase + halfBase * (p10 / halfBase) = p10 :=
    Nat.mod_add_div p10 halfBase
  have hmiddle :
      middle % halfBase + halfBase * (middle / halfBase) = middle :=
    Nat.mod_add_div middle halfBase
  have hcore :
      (p11 + p01 / halfBase + p10 / halfBase +
          middle / halfBase) * limbBase +
          (p00 % halfBase + (middle % halfBase) * halfBase) =
        p11 * limbBase + p01 * halfBase +
          p10 * halfBase + p00 := by
    dsimp only [middle] at hmiddle ⊢
    norm_num [limbBase, halfBase] at hp00 hp01 hp10 hmiddle ⊢
    omega
  rw [show (mulWide32 left right).high =
      p11 + p01 / halfBase + p10 / halfBase +
        middle / halfBase by
      simp [mulWide32, left0, left1, right0, right1,
        p00, p01, p10, p11, middle]]
  rw [show (mulWide32 left right).low =
      p00 % halfBase + (middle % halfBase) * halfBase by
      simp [mulWide32, left0, left1, right0, right1,
        p00, p01, p10, middle]]
  rw [hcore]
  calc
    p11 * limbBase + p01 * halfBase + p10 * halfBase + p00 =
        (left1 * halfBase + left0) *
          (right1 * halfBase + right0) := by
      simp only [p00, p01, p10, p11]
      rw [limbBase_eq_halfBase_sq]
      ring
    _ = left * right := by
      have hleft' : left1 * halfBase + left0 = left := by
        calc
          left1 * halfBase + left0 =
              left0 + halfBase * left1 := by ac_rfl
          _ = left := hleft
      have hright' : right1 * halfBase + right0 = right := by
        calc
          right1 * halfBase + right0 =
              right0 + halfBase * right1 := by ac_rfl
          _ = right := hright
      rw [hleft', hright']

theorem mulWide32_valid {left right : Nat}
    (hleft : left < limbBase) (hright : right < limbBase) :
    (mulWide32 left right).high < limbBase ∧
      (mulWide32 left right).low < limbBase := by
  let left0 := left % halfBase
  let left1 := left / halfBase
  let right0 := right % halfBase
  let right1 := right / halfBase
  let p00 := left0 * right0
  let p01 := left0 * right1
  let p10 := left1 * right0
  let middle :=
    p00 / halfBase + p01 % halfBase + p10 % halfBase
  have hhalf : 0 < halfBase := halfBase_pos
  have hp00mod : p00 % halfBase < halfBase :=
    Nat.mod_lt _ hhalf
  have hmiddlemod : middle % halfBase < halfBase :=
    Nat.mod_lt _ hhalf
  have hlow :
      (mulWide32 left right).low < limbBase := by
    simp only [mulWide32]
    change
      p00 % halfBase + middle % halfBase * halfBase < limbBase
    rw [limbBase_eq_halfBase_sq]
    norm_num [halfBase] at hp00mod hmiddlemod ⊢
    omega
  have hproduct :
      left * right < limbBase * limbBase :=
    Nat.mul_lt_mul_of_lt_of_lt hleft hright
  have hvalue := mulWide32_value left right
  constructor
  · norm_num [limbBase] at hproduct hvalue ⊢
    omega
  · exact hlow

/-! ## Exact checked two-limb operations -/

/-- Literal lexicographic implementation of `tg_sq218_u128_compare`. -/
def compare (left right : U128) : Ordering :=
  if left.hi < right.hi then
    .lt
  else if right.hi < left.hi then
    .gt
  else if left.lo < right.lo then
    .lt
  else if right.lo < left.lo then
    .gt
  else
    .eq

theorem compare_eq_lt_iff {left right : U128}
    (hleft : left.Valid) (hright : right.Valid) :
    compare left right = .lt ↔ left.toNat < right.toNat := by
  rcases hleft with ⟨hlhi, hllo⟩
  rcases hright with ⟨hrhi, hrlo⟩
  unfold compare
  by_cases h0 : left.hi < right.hi
  · simp only [h0, if_true]
    norm_num [U128.toNat, limbBase] at *
    omega
  · simp only [h0, if_false]
    by_cases h1 : right.hi < left.hi
    · simp only [h1, if_true, reduceCtorEq]
      norm_num [U128.toNat, limbBase] at *
      omega
    · simp only [h1, if_false]
      by_cases h2 : left.lo < right.lo
      · simp only [h2, if_true]
        norm_num [U128.toNat, limbBase] at *
        omega
      · simp only [h2, if_false]
        by_cases h3 : right.lo < left.lo
        · simp only [h3, if_true, reduceCtorEq]
          norm_num [U128.toNat, limbBase] at *
          omega
        · simp only [h3, if_false, reduceCtorEq]
          norm_num [U128.toNat, limbBase] at *
          omega

theorem compare_eq_eq_iff {left right : U128} :
    compare left right = .eq ↔ left = right := by
  unfold compare
  by_cases h0 : left.hi < right.hi
  · simp only [h0, if_true, reduceCtorEq, false_iff]
    intro heq
    cases heq
    exact (Nat.lt_irrefl _ h0).elim
  · simp only [h0, if_false]
    by_cases h1 : right.hi < left.hi
    · simp only [h1, if_true, reduceCtorEq, false_iff]
      intro heq
      cases heq
      exact (Nat.lt_irrefl _ h1).elim
    · simp only [h1, if_false]
      by_cases h2 : left.lo < right.lo
      · simp only [h2, if_true, reduceCtorEq, false_iff]
        intro heq
        cases heq
        exact (Nat.lt_irrefl _ h2).elim
      · simp only [h2, if_false]
        by_cases h3 : right.lo < left.lo
        · simp only [h3, if_true, reduceCtorEq, false_iff]
          intro heq
          cases heq
          exact (Nat.lt_irrefl _ h3).elim
        · simp only [h3, if_false, true_iff]
          have hhi : left.hi = right.hi :=
            Nat.le_antisymm
              (Nat.le_of_not_gt h1)
              (Nat.le_of_not_gt h0)
          have hlo : left.lo = right.lo :=
            Nat.le_antisymm
              (Nat.le_of_not_gt h3)
              (Nat.le_of_not_gt h2)
          cases left with
          | mk leftHi leftLo =>
            cases right with
            | mk rightHi rightLo =>
              simp only at hhi hlo
              subst rightHi
              subst rightLo
              rfl

theorem compare_eq_gt_iff {left right : U128}
    (hleft : left.Valid) (hright : right.Valid) :
    compare left right = .gt ↔ right.toNat < left.toNat := by
  rcases hleft with ⟨hlhi, hllo⟩
  rcases hright with ⟨hrhi, hrlo⟩
  unfold compare
  by_cases h0 : left.hi < right.hi
  · simp only [h0, if_true, reduceCtorEq]
    norm_num [U128.toNat, limbBase] at *
    omega
  · simp only [h0, if_false]
    by_cases h1 : right.hi < left.hi
    · simp only [h1, if_true]
      norm_num [U128.toNat, limbBase] at *
      omega
    · simp only [h1, if_false]
      by_cases h2 : left.lo < right.lo
      · simp only [h2, if_true, reduceCtorEq]
        norm_num [U128.toNat, limbBase] at *
        omega
      · simp only [h2, if_false]
        by_cases h3 : right.lo < left.lo
        · simp only [h3, if_true]
          norm_num [U128.toNat, limbBase] at *
          omega
        · simp only [h3, if_false, reduceCtorEq]
          norm_num [U128.toNat, limbBase] at *
          omega

/-- Low word computed before the checked two-limb addition guard. -/
def addLow (left right : U128) : Nat :=
  wordAdd left.lo right.lo

/-- Carry computed by the exact C comparison `low < left.lo`. -/
def addLowCarry (left right : U128) : Nat :=
  addCarry left.lo right.lo

/-- Wrapped high-word sum computed before checking overflow. -/
def addHigh (left right : U128) : Nat :=
  wordAdd left.hi right.hi

/-- The two rejection clauses in `tg_sq218_u128_add_checked`. -/
def addOverflow (left right : U128) : Prop :=
  addHigh left right < left.hi ∨
    wordMax - addHigh left right < addLowCarry left right

private instance (left right : U128) :
    Decidable (addOverflow left right) := by
  unfold addOverflow
  infer_instance

/-- Source-level model of `tg_sq218_u128_add_checked`. -/
def addChecked (left right : U128) : Option U128 :=
  if addOverflow left right then
    none
  else
    some
      ⟨addHigh left right + addLowCarry left right,
        addLow left right⟩

/-- Borrow computed by the exact C comparison `left.lo < right.lo`. -/
def subBorrow (left right : U128) : Nat :=
  if left.lo < right.lo then 1 else 0

/-- Source-level model of `tg_sq218_u128_sub_checked`. -/
def subChecked (left right : U128) : Option U128 :=
  if compare left right = .lt then
    none
  else
    some
      ⟨left.hi - right.hi - subBorrow left right,
        wordSub left.lo right.lo⟩

/-- Wide product of the low input limb by the multiplier. -/
def mulLowProduct (left : U128) (right : Nat) : WideProduct :=
  mulWide32 left.lo right

/-- Wide product of the high input limb by the multiplier. -/
def mulHighProduct (left : U128) (right : Nat) : WideProduct :=
  mulWide32 left.hi right

/-- Source-level model of `tg_sq218_u128_mul_u64_checked`. -/
def mulWordChecked (left : U128) (right : Nat) : Option U128 :=
  if right < limbBase then
    if (mulHighProduct left right).high = 0 then
      match
          wordAddChecked
            (mulHighProduct left right).low
            (mulLowProduct left right).high with
      | some resultHigh =>
          some ⟨resultHigh, (mulLowProduct left right).low⟩
      | none => none
    else
      none
  else
    none

private theorem valid_toNat_lt_capacity {value : U128}
    (hvalue : value.Valid) :
    value.toNat < capacity := by
  rcases hvalue with ⟨hhi, hlo⟩
  norm_num [U128.toNat, capacity, limbBase] at *
  omega

private theorem valid_ext {left right : U128}
    (hleft : left.Valid) (hright : right.Valid)
    (heq : left.toNat = right.toNat) :
    left = right := by
  rcases hleft with ⟨hlhi, hllo⟩
  rcases hright with ⟨hrhi, hrlo⟩
  cases left with
  | mk leftHi leftLo =>
    cases right with
    | mk rightHi rightLo =>
      simp only [U128.toNat] at heq
      congr <;> norm_num [limbBase] at * <;> omega

private theorem spec_checkedOfNat_eq_some {value : Nat} {result : U128}
    (hresult : result.Valid) (heq : result.toNat = value) :
    U128.checkedOfNat value = some result := by
  have hvalue : value < capacity := by
    rw [← heq]
    exact valid_toNat_lt_capacity hresult
  simp only [U128.checkedOfNat, hvalue, if_true]
  congr 1
  apply valid_ext (U128.encode_valid hvalue) hresult
  rw [U128.encode_toNat, heq]

theorem addChecked_refines {left right result : U128}
    (hleft : left.Valid) (hright : right.Valid)
    (hcheck : addChecked left right = some result) :
    U128.addChecked left right = some result := by
  rcases hleft with ⟨hlhi, hllo⟩
  rcases hright with ⟨hrhi, hrlo⟩
  simp only [addChecked] at hcheck
  split at hcheck
  · contradiction
  next hguard =>
    cases hcheck
    have hnoHigh : ¬addHigh left right < left.hi := by
      intro h
      exact hguard (Or.inl h)
    have hnoCarry :
        ¬wordMax - addHigh left right <
          addLowCarry left right := by
      intro h
      exact hguard (Or.inr h)
    have hlowDecomp :
        addLow left right +
            addLowCarry left right * limbBase =
          left.lo + right.lo := by
      simpa [addLow, addLowCarry] using
        wordAdd_addCarry hllo hrlo
    have hhighDecomp :=
      wordAdd_addCarry hlhi hrhi
    have hhighCarryZero :
        addCarry left.hi right.hi = 0 := by
      have hnoHigh' :
          ¬wordAdd left.hi right.hi < left.hi := by
        simpa only [addHigh] using hnoHigh
      rw [addCarry, if_neg hnoHigh']
    have hvalid :
        (U128.mk
            (addHigh left right + addLowCarry left right)
            (addLow left right)).Valid := by
      constructor
      · have hhighlt := wordAdd_lt left.hi right.hi
        have hcarryLe := addCarry_le_one left.lo right.lo
        change addLowCarry left right ≤ 1 at hcarryLe
        change addHigh left right < limbBase at hhighlt
        dsimp only [wordMax] at hnoCarry
        change
          addHigh left right + addLowCarry left right <
            limbBase
        omega
      · exact wordAdd_lt left.lo right.lo
    have hvalue :
        (U128.mk
            (addHigh left right + addLowCarry left right)
            (addLow left right)).toNat =
          left.toNat + right.toNat := by
      have hhighExact :
          addHigh left right = left.hi + right.hi := by
        simp only [hhighCarryZero, zero_mul, add_zero] at hhighDecomp
        simpa only [addHigh] using hhighDecomp
      change
        (addHigh left right + addLowCarry left right) *
              limbBase +
            addLow left right =
          (left.hi * limbBase + left.lo) +
            (right.hi * limbBase + right.lo)
      norm_num [limbBase] at *
      omega
    unfold U128.addChecked
    exact spec_checkedOfNat_eq_some hvalid hvalue

theorem subChecked_refines {left right result : U128}
    (hleft : left.Valid) (hright : right.Valid)
    (hcheck : subChecked left right = some result) :
    U128.subChecked left right = some result := by
  have hnotlt : ¬left.toNat < right.toNat := by
    intro hlt
    have hcmp : compare left right = .lt :=
      (compare_eq_lt_iff hleft hright).2 hlt
    simp only [subChecked, hcmp, if_true] at hcheck
    contradiction
  have hle : right.toNat ≤ left.toNat := Nat.le_of_not_gt hnotlt
  change
    (if compare left right = .lt then none else
      some
        (U128.mk
          (left.hi - right.hi - subBorrow left right)
          (wordSub left.lo right.lo))) = some result at hcheck
  split at hcheck
  · cases hcheck
  next hcmp =>
    cases hcheck
    rcases hleft with ⟨hlhi, hllo⟩
    rcases hright with ⟨hrhi, hrlo⟩
    have hleExpanded :
        right.hi * limbBase + right.lo ≤
          left.hi * limbBase + left.lo := by
      simpa only [U128.toNat] using hle
    have hvalue :
        (U128.mk
            (left.hi - right.hi - subBorrow left right)
            (wordSub left.lo right.lo)).toNat =
          left.toNat - right.toNat := by
      simp only [U128.toNat]
      by_cases hlo : left.lo < right.lo
      · simp only [subBorrow, hlo, if_true, wordSub,
          Nat.not_le.mpr hlo, if_false]
        norm_num [limbBase] at *
        omega
      · have hlo' : right.lo ≤ left.lo := Nat.le_of_not_gt hlo
        simp only [subBorrow, hlo, if_false, wordSub, hlo', if_true]
        norm_num [limbBase] at *
        omega
    have hvalid :
        (U128.mk
            (left.hi - right.hi - subBorrow left right)
            (wordSub left.lo right.lo)).Valid := by
      constructor
      · by_cases hlo : left.lo < right.lo
        · simp only [subBorrow, hlo, if_true]
          norm_num [limbBase] at hleExpanded
          omega
        · simp only [subBorrow, hlo, if_false]
          omega
      · exact wordSub_lt hllo hrlo
    unfold U128.subChecked
    rw [if_pos hle]
    exact spec_checkedOfNat_eq_some hvalid hvalue

theorem mulWordChecked_refines {left result : U128} {right : Nat}
    (hleft : left.Valid)
    (hcheck : mulWordChecked left right = some result) :
    U128.mulWordChecked left right = some result := by
  rcases hleft with ⟨hlhi, hllo⟩
  simp only [mulWordChecked] at hcheck
  split at hcheck
  next hright =>
    split at hcheck
    next hhighZero =>
      split at hcheck
      next resultHigh hadd =>
        cases hcheck
        have hlowValid := mulWide32_valid hllo hright
        have hhighValid := mulWide32_valid hlhi hright
        change
          (mulLowProduct left right).high < limbBase ∧
            (mulLowProduct left right).low < limbBase at hlowValid
        change
          (mulHighProduct left right).high < limbBase ∧
            (mulHighProduct left right).low < limbBase at hhighValid
        have haddSound :=
          wordAddChecked_sound hhighValid.2 hlowValid.1 hadd
        have hlowValue := mulWide32_value left.lo right
        have hhighValue := mulWide32_value left.hi right
        change
          (mulLowProduct left right).high * limbBase +
              (mulLowProduct left right).low =
            left.lo * right at hlowValue
        change
          (mulHighProduct left right).high * limbBase +
              (mulHighProduct left right).low =
            left.hi * right at hhighValue
        have hvalue :
            (U128.mk resultHigh
                (mulLowProduct left right).low).toNat =
              left.toNat * right := by
          simp only [U128.toNat]
          rw [hhighZero] at hhighValue
          simp only [zero_mul, zero_add] at hhighValue
          rw [haddSound.2]
          calc
            ((mulHighProduct left right).low +
                    (mulLowProduct left right).high) *
                  limbBase +
                (mulLowProduct left right).low =
                (mulHighProduct left right).low * limbBase +
                  ((mulLowProduct left right).high * limbBase +
                    (mulLowProduct left right).low) := by ring
            _ = (left.hi * right) * limbBase +
                  left.lo * right := by
              rw [hhighValue, hlowValue]
            _ = (left.hi * limbBase + left.lo) * right := by
              ring
        have hvalid :
            (U128.mk resultHigh
                (mulLowProduct left right).low).Valid :=
          ⟨haddSound.1, hlowValid.2⟩
        simp only [U128.mulWordChecked, hright, if_true]
        exact spec_checkedOfNat_eq_some hvalid hvalue
      next => contradiction
    next => contradiction
  next => contradiction

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CPrimitives

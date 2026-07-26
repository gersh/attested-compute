/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Tactic

/-!
# Architecture-neutral two-limb arithmetic for the Sqrt218 CPU checker

This is the mathematical model of a pair of unsigned 64-bit limbs.  It
contains no production values and performs no certificate replay.

The C implementation in `cpu_checker/sqrt218/` uses explicit carry and a
four-`u32` wide product.  This module deliberately specifies the result
independently in natural numbers.  A future source/compiler refinement must
prove that the concrete limb instructions implement these definitions; no
such theorem or axiom is introduced here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

/-- One past the largest unsigned 64-bit value. -/
def limbBase : Nat := 2 ^ 64

/-- One past the largest unsigned 128-bit value. -/
def capacity : Nat := limbBase * limbBase

theorem limbBase_pos : 0 < limbBase := by
  norm_num [limbBase]

/-- Architecture-neutral image of two unsigned 64-bit limbs.

`Valid` is explicit because C's field types enforce it while this mathematical
container intentionally uses `Nat` for convenient reasoning. -/
structure U128 where
  hi : Nat
  lo : Nat
  deriving Repr, DecidableEq, Inhabited

namespace U128

def Valid (value : U128) : Prop :=
  value.hi < limbBase ∧ value.lo < limbBase

def toNat (value : U128) : Nat :=
  value.hi * limbBase + value.lo

def zero : U128 := ⟨0, 0⟩

def ofWord (word : Nat) : Option U128 :=
  if word < limbBase then some ⟨0, word⟩ else none

/-- Split a mathematical natural at the 64-bit limb boundary. -/
def encode (value : Nat) : U128 :=
  ⟨value / limbBase, value % limbBase⟩

/-- Reject rather than truncate a value at or above `2^128`. -/
def checkedOfNat (value : Nat) : Option U128 :=
  if value < capacity then some (encode value) else none

theorem encode_toNat (value : Nat) :
    (encode value).toNat = value := by
  simp only [encode, toNat]
  rw [Nat.mul_comm]
  exact Nat.div_add_mod value limbBase

theorem encode_valid {value : Nat} (hvalue : value < capacity) :
    (encode value).Valid := by
  constructor
  · simp only [encode]
    rw [Nat.div_lt_iff_lt_mul limbBase_pos]
    simpa only [capacity]
  · simp only [encode]
    exact Nat.mod_lt value limbBase_pos

theorem checkedOfNat_sound {value : Nat} {encoded : U128}
    (hcheck : checkedOfNat value = some encoded) :
    encoded.Valid ∧ encoded.toNat = value := by
  unfold checkedOfNat at hcheck
  split at hcheck
  next hlt =>
    cases hcheck
    exact ⟨encode_valid hlt, encode_toNat value⟩
  next => contradiction

theorem checkedOfNat_complete {value : Nat} (hvalue : value < capacity) :
    ∃ encoded, checkedOfNat value = some encoded ∧
      encoded.Valid ∧ encoded.toNat = value := by
  refine ⟨encode value, ?_, encode_valid hvalue, encode_toNat value⟩
  simp [checkedOfNat, hvalue]

/-- Checked exact addition; overflow is `none`, never wraparound. -/
def addChecked (left right : U128) : Option U128 :=
  checkedOfNat (left.toNat + right.toNat)

/-- Checked exact subtraction; underflow is `none`. -/
def subChecked (left right : U128) : Option U128 :=
  if right.toNat ≤ left.toNat then
    checkedOfNat (left.toNat - right.toNat)
  else
    none

/-- Checked multiplication by one unsigned 64-bit word. -/
def mulWordChecked (left : U128) (right : Nat) : Option U128 :=
  if right < limbBase then
    checkedOfNat (left.toNat * right)
  else
    none

theorem ofWord_sound {word : Nat} {encoded : U128}
    (hcheck : ofWord word = some encoded) :
    word < limbBase ∧ encoded.Valid ∧ encoded.toNat = word := by
  unfold ofWord at hcheck
  split at hcheck
  next hlt =>
    cases hcheck
    refine ⟨hlt, ?_, ?_⟩
    · exact ⟨by simp [limbBase],
        hlt⟩
    · simp [toNat]
  next => contradiction

theorem addChecked_sound {left right result : U128}
    (hcheck : addChecked left right = some result) :
    result.Valid ∧
      result.toNat = left.toNat + right.toNat :=
  checkedOfNat_sound hcheck

theorem subChecked_sound {left right result : U128}
    (hcheck : subChecked left right = some result) :
    result.Valid ∧ right.toNat ≤ left.toNat ∧
      result.toNat = left.toNat - right.toNat := by
  unfold subChecked at hcheck
  split at hcheck
  next hle =>
    exact ⟨(checkedOfNat_sound hcheck).1, hle,
      (checkedOfNat_sound hcheck).2⟩
  next => contradiction

theorem mulWordChecked_sound {left result : U128} {right : Nat}
    (hcheck : mulWordChecked left right = some result) :
    right < limbBase ∧ result.Valid ∧
      result.toNat = left.toNat * right := by
  unfold mulWordChecked at hcheck
  split at hcheck
  next hword =>
    exact ⟨hword, (checkedOfNat_sound hcheck).1,
      (checkedOfNat_sound hcheck).2⟩
  next => contradiction

/-- Strict numeric comparison used by both guards. -/
def lessThan (left right : U128) : Bool :=
  decide (left.toNat < right.toNat)

theorem lessThan_eq_true {left right : U128} :
    lessThan left right = true ↔ left.toNat < right.toNat := by
  simp [lessThan]

end U128

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker

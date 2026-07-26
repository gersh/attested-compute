/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Sound threshold filtering for Hurst affine extrema

The optimized squarefree guard first computes an inexpensive inward integer
approximation.  Exact replay can move a lower candidate down by at most one,
or an upper candidate up by at most one.  These lemmas identify the sound
second-pass candidate set:

* for a maximum, retain every approximation at least `maximum - 1`;
* for a minimum, retain every approximation at most `minimum + 1`.

Keeping an arbitrary fixed number of tied candidates is not justified by the
one-unit error bound.  A native implementation must revisit or emit *every*
candidate in the corresponding threshold set.  This module proves only the
architecture-independent ordering argument; it does not refine a GPU scan,
compaction, or integer implementation.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter

/-- If `r² ≤ y`, comparison with `C * r` is a sound inexpensive acceptance
test for the exact squared predicate `L² ≤ C² * y`. -/
theorem squared_bound_of_floor_sqrt_accept
    {L C r y : Nat}
    (hrootLower : r * r ≤ y)
    (haccept : L ≤ C * r) :
    L * L ≤ C * C * y := by
  calc
    L * L ≤ (C * r) * (C * r) :=
      Nat.mul_le_mul haccept haccept
    _ = C * C * (r * r) := by ring
    _ ≤ C * C * y := by
      exact Nat.mul_le_mul_left (C * C) hrootLower

/-- If `y < (r+1)²` and `C > 0`, comparison with `C * (r+1)` is a sound
inexpensive rejection test for the exact squared predicate. -/
theorem squared_bound_fails_of_floor_sqrt_reject
    {L C r y : Nat}
    (hconstant : 0 < C)
    (hrootUpper : y < (r + 1) * (r + 1))
    (hreject : C * (r + 1) ≤ L) :
    C * C * y < L * L := by
  have hcc : 0 < C * C := Nat.mul_pos hconstant hconstant
  calc
    C * C * y < C * C * ((r + 1) * (r + 1)) :=
      Nat.mul_lt_mul_of_pos_left hrootUpper hcc
    _ = (C * (r + 1)) * (C * (r + 1)) := by ring
    _ ≤ L * L := Nat.mul_le_mul hreject hreject

/-- A lower-bound approximation is inward by either zero or one integer unit. -/
def LowerCorrectionValid (approximation exact : Int) : Prop :=
  approximation - 1 ≤ exact ∧ exact ≤ approximation

/-- An upper-bound approximation is inward by either zero or one integer unit. -/
def UpperCorrectionValid (approximation exact : Int) : Prop :=
  approximation ≤ exact ∧ exact ≤ approximation + 1

/-- A lower candidate more than one unit below an approximate witness cannot
attain the exact maximum. -/
theorem lower_outside_threshold_strictly_below
    {candidateApprox candidateExact witnessApprox witnessExact : Int}
    (hcandidate : LowerCorrectionValid candidateApprox candidateExact)
    (hwitness : LowerCorrectionValid witnessApprox witnessExact)
    (houtside : candidateApprox < witnessApprox - 1) :
    candidateExact < witnessExact := by
  exact lt_of_le_of_lt hcandidate.2 (houtside.trans_le hwitness.1)

/-- An upper candidate more than one unit above an approximate witness cannot
attain the exact minimum. -/
theorem upper_outside_threshold_strictly_above
    {candidateApprox candidateExact witnessApprox witnessExact : Int}
    (hcandidate : UpperCorrectionValid candidateApprox candidateExact)
    (hwitness : UpperCorrectionValid witnessApprox witnessExact)
    (houtside : witnessApprox + 1 < candidateApprox) :
    witnessExact < candidateExact := by
  exact lt_of_le_of_lt hwitness.2 (houtside.trans_le hcandidate.1)

/-- Every exact maximizer lies in the complete one-unit threshold set around
an approximate maximizer. -/
theorem exact_maximizer_inside_lower_threshold
    {α : Type} {rows : List α} {witness best : α}
    (approximation exact : α → Int)
    (hwitnessMember : witness ∈ rows)
    (hbestMember : best ∈ rows)
    (hcorrection :
      ∀ row ∈ rows,
        LowerCorrectionValid (approximation row) (exact row))
    (happroximateMaximum :
      ∀ row ∈ rows, approximation row ≤ approximation witness)
    (hexactMaximum :
      ∀ row ∈ rows, exact row ≤ exact best) :
    approximation witness - 1 ≤ approximation best ∧
      approximation best ≤ approximation witness := by
  constructor
  · by_contra houtside
    have hstrict :
        exact best < exact witness :=
      lower_outside_threshold_strictly_below
        (hcorrection best hbestMember)
        (hcorrection witness hwitnessMember)
        (lt_of_not_ge houtside)
    exact (not_lt_of_ge (hexactMaximum witness hwitnessMember)) hstrict
  · exact happroximateMaximum best hbestMember

/-- Every exact minimizer lies in the complete one-unit threshold set around
an approximate minimizer. -/
theorem exact_minimizer_inside_upper_threshold
    {α : Type} {rows : List α} {witness best : α}
    (approximation exact : α → Int)
    (hwitnessMember : witness ∈ rows)
    (hbestMember : best ∈ rows)
    (hcorrection :
      ∀ row ∈ rows,
        UpperCorrectionValid (approximation row) (exact row))
    (happroximateMinimum :
      ∀ row ∈ rows, approximation witness ≤ approximation row)
    (hexactMinimum :
      ∀ row ∈ rows, exact best ≤ exact row) :
    approximation witness ≤ approximation best ∧
      approximation best ≤ approximation witness + 1 := by
  constructor
  · exact happroximateMinimum best hbestMember
  · by_contra houtside
    have hstrict :
        exact witness < exact best :=
      upper_outside_threshold_strictly_above
        (hcorrection best hbestMember)
        (hcorrection witness hwitnessMember)
        (lt_of_not_ge houtside)
    exact (not_lt_of_ge (hexactMinimum witness hwitnessMember)) hstrict

/-! ## Hierarchical reduction keys

The native affine scan records an exact source order along with every
candidate value.  A maximum uses the lexicographic key `(-value, order)`;
a minimum uses `(value, order)`.  Consequently an arbitrary hierarchy of
thread, block, and device reductions can use ordinary `min` and still select
the same value with the earliest source-order tie break.

These lemmas justify that algebraic reduction plan.  They do not refine a
particular CUDA shuffle, shared-memory reduction, or CUB invocation.
-/

/-- Value and exact source order retained by an affine extremum candidate. -/
structure OrderedCandidate where
  value : Int
  order : Nat
  deriving DecidableEq

/-- Lexicographic reduction key for a maximum with earliest-order ties. -/
def lowerKey (candidate : OrderedCandidate) : Int ×ₗ Nat :=
  toLex (-candidate.value, candidate.order)

/-- Lexicographic reduction key for a minimum with earliest-order ties. -/
def upperKey (candidate : OrderedCandidate) : Int ×ₗ Nat :=
  toLex (candidate.value, candidate.order)

/-- The maximum key retains the complete candidate identity. -/
theorem lowerKey_injective : Function.Injective lowerKey := by
  intro first second hequality
  cases first with
  | mk firstValue firstOrder =>
      cases second with
      | mk secondValue secondOrder =>
          simp only [lowerKey, toLex_inj, Prod.mk.injEq] at hequality
          simp only [OrderedCandidate.mk.injEq]
          exact ⟨neg_injective hequality.1, hequality.2⟩

/-- The minimum key retains the complete candidate identity. -/
theorem upperKey_injective : Function.Injective upperKey := by
  intro first second hequality
  cases first with
  | mk firstValue firstOrder =>
      cases second with
      | mk secondValue secondOrder =>
          simpa only [upperKey, toLex_inj, Prod.mk.injEq,
            OrderedCandidate.mk.injEq] using hequality

/-- Thread, block, and device maximum-key reductions may be regrouped
arbitrarily. -/
theorem lowerKey_min_assoc (first second third : Int ×ₗ Nat) :
    min (min first second) third =
      min first (min second third) :=
  min_assoc first second third

/-- Maximum-key reductions are independent of worker ordering. -/
theorem lowerKey_min_comm (first second : Int ×ₗ Nat) :
    min first second = min second first :=
  min_comm first second

/-- Replaying the same maximum candidate is harmless. -/
theorem lowerKey_min_idem (candidate : Int ×ₗ Nat) :
    min candidate candidate = candidate :=
  min_self candidate

/-- Thread, block, and device minimum-key reductions may be regrouped
arbitrarily. -/
theorem upperKey_min_assoc (first second third : Int ×ₗ Nat) :
    min (min first second) third =
      min first (min second third) :=
  min_assoc first second third

/-- Minimum-key reductions are independent of worker ordering. -/
theorem upperKey_min_comm (first second : Int ×ₗ Nat) :
    min first second = min second first :=
  min_comm first second

/-- Replaying the same minimum candidate is harmless. -/
theorem upperKey_min_idem (candidate : Int ×ₗ Nat) :
    min candidate candidate = candidate :=
  min_self candidate

end SparkInterval.TernaryGoldbach.HurstAffineCandidateFilter

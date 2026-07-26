/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib

/-!
# Square-only form of the CH25 ψ lower-endpoint filter

The source worker compares a nonnegative fixed-point error with `sqrt (2x)`.
Its optimized fast path avoids computing an integer square root: it squares
the fixed-point floor or ceiling and compares that integer directly with
`2x`.  These lemmas prove the accept and reject decisions are unchanged.

They concern exact natural-number arithmetic.  Connecting machine `u128`
operations to these naturals remains part of the executable refinement
boundary.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.PsiLowerFilter

/-- A strict square comparison is the old square-root comparison, including
the exact-perfect-square boundary case. -/
theorem square_lt_iff_sqrt_boundary
    (bound ceiling : Nat) :
    ceiling * ceiling < bound ↔
      ceiling ≤ Nat.sqrt bound ∧
        (ceiling < Nat.sqrt bound ∨
          Nat.sqrt bound * Nat.sqrt bound < bound) := by
  constructor
  · intro hsquare
    have hle : ceiling ≤ Nat.sqrt bound :=
      Nat.le_sqrt.mpr (Nat.le_of_lt hsquare)
    refine ⟨hle, ?_⟩
    rcases lt_or_eq_of_le hle with hlt | heq
    · exact Or.inl hlt
    · exact Or.inr (by simpa [heq] using hsquare)
  · rintro ⟨hle, hboundary⟩
    rcases hboundary with hlt | hsqrt
    · nlinarith [Nat.sqrt_le bound]
    · nlinarith

/-- The non-strict accept branch can replace `ceiling ≤ sqrt bound` by one
integer multiplication and comparison. -/
theorem square_le_iff_le_sqrt (bound ceiling : Nat) :
    ceiling * ceiling ≤ bound ↔ ceiling ≤ Nat.sqrt bound :=
  Nat.le_sqrt.symm

/-- In the strict branch, a nonzero fixed-point remainder means the true
quotient is strictly below its ceiling.  This is exactly the exceptional
accept case in the original square-root filter. -/
theorem strict_accept_square_iff
    (bound ceiling : Nat) (hasRemainder : Prop) [Decidable hasRemainder] :
    (ceiling * ceiling < bound ∨
        (hasRemainder ∧ ceiling * ceiling ≤ bound)) ↔
      ceiling ≤ Nat.sqrt bound ∧
        (ceiling < Nat.sqrt bound ∨ hasRemainder ∨
          Nat.sqrt bound * Nat.sqrt bound < bound) := by
  by_cases hremainder : hasRemainder
  · constructor
    · intro h
      have hsquare : ceiling * ceiling ≤ bound :=
        h.elim Nat.le_of_lt (fun remainder => remainder.2)
      exact ⟨Nat.le_sqrt.mpr hsquare, Or.inr (Or.inl hremainder)⟩
    · rintro ⟨hle, _⟩
      exact Or.inr ⟨hremainder, Nat.le_sqrt.mp hle⟩
  · constructor
    · intro h
      have hsquare : ceiling * ceiling < bound := by
        rcases h with hlt | hrem
        · exact hlt
        · exact False.elim (hremainder hrem.1)
      rcases (square_lt_iff_sqrt_boundary bound ceiling).mp hsquare with
        ⟨hle, hboundary⟩
      refine ⟨hle, ?_⟩
      rcases hboundary with hlt | hsqrt
      · exact Or.inl hlt
      · exact Or.inr (Or.inr hsqrt)
    · rintro ⟨hle, hboundary⟩
      have hstrict :
          ceiling < Nat.sqrt bound ∨
            Nat.sqrt bound * Nat.sqrt bound < bound := by
        rcases hboundary with hlt | hrest
        · exact Or.inl hlt
        · rcases hrest with hrem | hsqrt
          · exact False.elim (hremainder hrem)
          · exact Or.inr hsqrt
      exact Or.inl (
        (square_lt_iff_sqrt_boundary bound ceiling).mpr
          ⟨hle, hstrict⟩)

/-- The old reject test `sqrt bound < floor` is exactly the direct-square
reject test. -/
theorem sqrt_lt_iff_bound_lt_square (bound floor : Nat) :
    Nat.sqrt bound < floor ↔ bound < floor * floor :=
  Nat.sqrt_lt

end SparkInterval.TernaryGoldbach.PsiLowerFilter

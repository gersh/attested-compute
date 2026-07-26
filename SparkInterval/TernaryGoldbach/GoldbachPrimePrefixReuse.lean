/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import Mathlib.Data.Nat.Prime.Basic
import Mathlib.Data.Finset.Range
import Mathlib.Tactic

/-!
# Reusing a completed prime-table prefix

The GoldbachGPU candidate already constructs the exact set of primes through
`smallHigh`.  When the phase-2 bound is no larger, filtering that completed
table at the phase-2 bound gives exactly the table produced by an independent
sieve at that bound.

This file models the mathematical table equality.  The bounded CUDA
diagnostic separately checks equality of the two ordered C++ vectors,
element-for-element.  No compiler or hardware refinement is claimed here.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.GoldbachPrimePrefixReuse

/-- Abstract finite prime table matching a complete sieve through `bound`. -/
def primeTable (bound : Nat) : Finset Nat :=
  (Finset.range (bound + 1)).filter Nat.Prime

/-- The reused bounded prefix contains exactly the same primes as a fresh
complete sieve through the smaller bound. -/
theorem filter_primeTable_eq (phase2Bound smallHigh : Nat)
    (hbound : phase2Bound ≤ smallHigh) :
    (primeTable smallHigh).filter (· ≤ phase2Bound) =
      primeTable phase2Bound := by
  ext n
  simp only [primeTable, Finset.mem_filter, Finset.mem_range]
  constructor
  · rintro ⟨⟨hnHigh, hnPrime⟩, hnBound⟩
    exact ⟨by omega, hnPrime⟩
  · rintro ⟨hnBound, hnPrime⟩
    exact ⟨⟨by omega, hnPrime⟩, by omega⟩

/-- Membership-level form used to review the C++ `upper_bound` prefix. -/
theorem mem_filtered_primeTable_iff (phase2Bound smallHigh n : Nat)
    (hbound : phase2Bound ≤ smallHigh) :
    n ∈ (primeTable smallHigh).filter (· ≤ phase2Bound) ↔
      n.Prime ∧ n ≤ phase2Bound := by
  rw [filter_primeTable_eq phase2Bound smallHigh hbound]
  simp only [primeTable, Finset.mem_filter, Finset.mem_range]
  constructor <;> rintro ⟨h₁, h₂⟩
  · exact ⟨h₂, by omega⟩
  · exact ⟨by omega, h₁⟩

#print axioms filter_primeTable_eq
#print axioms mem_filtered_primeTable_iff

end SparkInterval.TernaryGoldbach.GoldbachPrimePrefixReuse

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import TGComputeContracts.Sqrt218.Kernel
import Mathlib.Tactic

/-!
# Arithmetic refinement lemmas for the Sqrt218 external checker

The independent Python verifier spells ceiling division as a quotient plus a
nonzero-remainder bit, while the package-neutral Lean contract spells it as
`(numerator + (denominator - 1)) / denominator`.  It also writes squares as
explicit products in the two reciprocal-square-root formulas.

This module proves those representations equal for every admissible input.
The proofs are data-independent and do not evaluate a certificate archive.
They close only this small arithmetic edge; they do not model Python, a JSON
decoder, a compiler, an ISA, or a measured machine execution.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218Operational.ArithmeticRefinement

/-- The exact quotient/remainder implementation used by Python's
`_ceil_ratio`. -/
def quotientRemainderCeil (numerator denominator : Nat) : Nat :=
  numerator / denominator +
    if numerator % denominator = 0 then 0 else 1

/-- Quotient-plus-remainder ceiling agrees with the generic certificate
kernel whenever the denominator is positive. -/
theorem quotientRemainderCeil_eq_ceilDiv (numerator denominator : Nat)
    (hden : 0 < denominator) :
    quotientRemainderCeil numerator denominator =
      TGComputeContracts.Sqrt218.ceilDiv numerator denominator := by
  unfold quotientRemainderCeil TGComputeContracts.Sqrt218.ceilDiv
  rw [Nat.add_div hden]
  have hpredlt : denominator - 1 < denominator := by omega
  rw [Nat.div_eq_of_lt hpredlt, Nat.mod_eq_of_lt hpredlt]
  simp only [Nat.add_zero]
  have hmodlt := Nat.mod_lt numerator hden
  by_cases hzero : numerator % denominator = 0
  · simp [hzero, hden]
  · have hpos : 0 < numerator % denominator :=
      Nat.pos_of_ne_zero hzero
    have hle :
        denominator ≤ numerator % denominator + (denominator - 1) := by
      omega
    simp [hzero, hle]

/-- Product-spelled lower reciprocal-square-root expression used by the
external checker. -/
def reciprocalLower (value root : Nat) : Nat :=
  TGComputeContracts.Sqrt218.reciprocalScale * (2 * root) /
    (2 * root * root + (value - root * root))

/-- Product-spelled upper reciprocal-square-root expression used by the
external checker. -/
def reciprocalUpper (value root : Nat) : Nat :=
  quotientRemainderCeil
    (TGComputeContracts.Sqrt218.reciprocalScale *
      (4 * root * root + (value - root * root)))
    (root * (4 * root * root + 3 * (value - root * root)))

/-- The external lower expression is definitionally the same rational floor
as the package-neutral certificate expression. -/
theorem reciprocalLower_eq_contract (value root : Nat) :
    reciprocalLower value root =
      TGComputeContracts.Sqrt218.reciprocalLower value root := by
  simp only [reciprocalLower,
    TGComputeContracts.Sqrt218.reciprocalLower,
    TGComputeContracts.Sqrt218.sqrtRemainder, pow_two]
  congr 2 <;> ring

/-- The external upper expression is the same rational ceiling as the
package-neutral certificate expression for the positive square roots used by
the scan. -/
theorem reciprocalUpper_eq_contract (value root : Nat)
    (hroot : 0 < root) :
    reciprocalUpper value root =
      TGComputeContracts.Sqrt218.reciprocalUpper value root := by
  unfold reciprocalUpper TGComputeContracts.Sqrt218.reciprocalUpper
  rw [quotientRemainderCeil_eq_ceilDiv]
  · simp only [TGComputeContracts.Sqrt218.sqrtRemainder, pow_two]
    congr 2 <;> ring
  · have hfour : 0 < 4 * root * root := by positivity
    positivity

end SparkInterval.TernaryGoldbach.Sqrt218Operational.ArithmeticRefinement

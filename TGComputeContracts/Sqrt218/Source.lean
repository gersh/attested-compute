/-
Copyright (c) 2026 Gershon Bialer. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Gershon Bialer

This file is adapted from the project-owned source boundary in
`SparkInterval/TernaryGoldbach/Sqrt218SourceSemantics.lean`.
-/
import Mathlib.NumberTheory.Chebyshev

/-!
# Source contract for Helfgott's finite square-root Mangoldt check

This is the package-neutral, paper-shaped proposition proved by the generic
certificate kernel.  It deliberately contains no production rows, receipt,
signature, execution axiom, or reference to a particular CPU/GPU backend.
-/

set_option autoImplicit false

noncomputable section

namespace TGComputeContracts.Sqrt218

open scoped BigOperators ArithmeticFunction
open ArithmeticFunction Finset

/-- Finite endpoint in Helfgott's bounded check for (2.18). -/
def sourceCutoff : Nat := 2_000_000

/-- The literal square-root-weighted von Mangoldt sum in the source claim. -/
noncomputable def vonMangoldtSqrtNat (N : Nat) : Real :=
  ∑ n ∈ Finset.Icc 1 N,
    ArithmeticFunction.vonMangoldt n / Real.sqrt (n : Real)

/-- Exact bounded proposition consumed by the ordinary-Lean Abel
continuation.  Both inequalities are strict and the head range is nonempty. -/
structure SourceClaim : Prop where
  head : ∀ N : Nat, 1 ≤ N → N ≤ sourceCutoff →
    vonMangoldtSqrtNat N < 2 * 1.0004 * Real.sqrt (N : Real)
  anchor :
    vonMangoldtSqrtNat sourceCutoff -
        Chebyshev.psi (sourceCutoff : Real) /
          Real.sqrt (sourceCutoff : Real) <
      1.0004 * Real.sqrt (sourceCutoff : Real)

end TGComputeContracts.Sqrt218

end

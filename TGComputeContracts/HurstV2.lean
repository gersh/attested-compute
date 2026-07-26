/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: Apache-2.0 OR MIT -/

import Mathlib

/-!
# Shared source contract for the Hurst V2 campaign

This module is deliberately limited to the paper-shaped mathematical result.
It contains no receipt, key, execution checker, or axiom.  The identical source
is compiled in both `gpu_prover` and `claude_math`; a producer theorem may
inhabit `RealSourceClaims`, and an ordinary downstream theorem may identify
these three source-normal step functions with its live definitions.

This contract alone is not evidence that a computation ran.  A completed
handoff must additionally import a concrete generated receipt theorem whose
only project trust dependency is the single shared execution axiom.
-/

set_option autoImplicit false

namespace TGComputeContracts.HurstV2

open Finset
open scoped BigOperators

/-- Inclusive upper endpoint of the Mertens and squarefree computations. -/
def sourceLimit : Nat := 10_000_000_000_000_000

/-- Inclusive upper endpoint of Platt--Lambov equation (2.11). -/
def little211Limit : Nat := 1_000_000_000_000

/-- Inclusive upper endpoint of Platt's stronger little-Mertens computation. -/
def littleStrongerLimit : Nat := 7_727_068_587

/-- Exact source-normal Mertens step function. -/
noncomputable def mertensStep (x : Real) : Real :=
  ∑ n ∈ Finset.Iic ⌊x⌋₊, (ArithmeticFunction.moebius n : Real)

/-- Exact source-normal little-Mertens step function. -/
noncomputable def littleMertensStep (x : Real) : Real :=
  ∑ n ∈ Finset.Icc 1 ⌊x⌋₊,
    ((ArithmeticFunction.moebius n : Int) : Real) / (n : Real)

/-- Exact source-normal squarefree-counting step function. -/
noncomputable def squarefreeStep (x : Real) : Real :=
  ∑ n ∈ Finset.range (⌊x⌋₊ + 1),
    |(ArithmeticFunction.moebius n : Real)|

/-- Exact ordinary-real result shared by the producer and downstream proof.

The squarefree source atom has two independently quantified heads, so the four
named residuals correspond to five fields here. -/
structure RealSourceClaims : Prop where
  hurst : ∀ x : Real, 33 ≤ x → x ≤ sourceLimit →
    |mertensStep x| ≤ ((571 : Real) / 1_000) * Real.sqrt x
  squarefreeB1 : ∀ x : Real, (9_243 : Real) < x → x ≤ sourceLimit →
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (151 / 2_000 : Real) * Real.sqrt x
  squarefreeB2 : ∀ x : Real, (438_429 : Real) < x → x ≤ sourceLimit →
    |squarefreeStep x - (6 / Real.pi ^ 2) * x| ≤
      (57 / 2_000 : Real) * Real.sqrt x
  little211 : ∀ x : Real, 1 ≤ x → x ≤ little211Limit →
    |littleMertensStep x| ≤ Real.sqrt (2 / x)
  littleStronger : ∀ x : Real, 3 ≤ x → x ≤ littleStrongerLimit →
    |littleMertensStep x| ≤ 1 / (2 * Real.sqrt x)

end TGComputeContracts.HurstV2

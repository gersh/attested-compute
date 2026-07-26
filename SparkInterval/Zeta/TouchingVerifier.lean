/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.TouchingEndpointCertificate
import SparkInterval.Zeta.Verifier

/-!
# Finite-height zeta verification with touching strict brackets

This is the application-level counterpart of `TouchingEndpointCertificate`.
It replaces the strict closed-carrier separation in `ZetaVerifierEvidence`
with non-overlapping open interiors and strict endpoint signs.  All other
analytic inputs remain exactly the same: a critical-line evaluator bridge and
a global zeta-zero count upper bound.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta

/-- Evidence for a finite-height zeta verifier whose consecutive strict
sign-change brackets may share an endpoint. -/
structure TouchingZetaVerifierEvidence
    (f : Real -> Real) (height : Real) (count : Nat) where
  brackets : TouchingZeroCertificate f count
  continuous : brackets.ContinuousOnBrackets
  liesIn : brackets.LiesIn (heightDomain height)
  bridge : CriticalLineZeroBridge f height
  totalUpper : ZetaZeroCountUpperBound height count

namespace TouchingZetaVerifierEvidence

/-- The touching strict brackets account for all distinct critical-line zeros
in the finite rectangle. -/
theorem exact_criticalLine_count
    {f : Real -> Real} {height : Real} {count : Nat}
    (evidence : TouchingZetaVerifierEvidence f height count) :
    (criticalLineZerosIn (criticalRectangle height)).ncard = count := by
  have complete := evidence.brackets.complete_of_count_upperBound
    evidence.continuous evidence.liesIn
    (evidence.bridge.zeroCountUpperBound evidence.totalUpper)
  calc
    (criticalLineZerosIn (criticalRectangle height)).ncard =
        (zerosOn f (heightDomain height)).ncard :=
      evidence.bridge.criticalLineZerosIn_ncard_eq_zerosOn_ncard
    _ = count := complete.exactCount

/-- Equality between the touching-bracket lower bound and the global upper
bound forces equality with the total compact-region zero count. -/
theorem exact_total_count
    {f : Real -> Real} {height : Real} {count : Nat}
    (evidence : TouchingZetaVerifierEvidence f height count) :
    (criticalLineZerosIn (criticalRectangle height)).ncard =
      (zetaZerosIn (criticalRectangle height)).ncard := by
  apply Nat.le_antisymm
  · exact Set.ncard_le_ncard
      (criticalLineZerosIn_subset (criticalRectangle height))
      (zetaZerosIn_finite (isCompact_criticalRectangle height))
  · rw [evidence.exact_criticalLine_count]
    exact evidence.totalUpper.count_le

/-- Final finite-height Riemann-hypothesis consequence for touching strict
brackets. -/
theorem all_zeros_on_criticalLine
    {f : Real -> Real} {height : Real} {count : Nat}
    (evidence : TouchingZetaVerifierEvidence f height count) :
    ∀ z ∈ criticalRectangle height,
      riemannZeta z = 0 -> z.re = (1 : Real) / 2 :=
  all_zeros_to_height_on_criticalLine evidence.exact_total_count

end TouchingZetaVerifierEvidence

end SparkInterval.Zeta

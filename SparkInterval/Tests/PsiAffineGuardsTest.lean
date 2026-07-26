/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiAffineGuards

set_option autoImplicit false

namespace SparkInterval.Tests.PsiAffineGuardsTest

open SparkInterval.TernaryGoldbach
open PsiAffineGuards

example
    (lowerGuards : List LowerGuard) (upperGuards : List UpperGuard)
    (bounds : AdmissibleIncoming)
    {incomingLowerQ64 incomingUpperQ64 : Nat}
    (hcontains : bounds.Contains incomingLowerQ64 incomingUpperQ64)
    (hlower :
      ∀ guard ∈ lowerGuards, guard.SafeAt bounds.minimumLowerQ64)
    (hupper :
      ∀ guard ∈ upperGuards, guard.SafeAt bounds.maximumUpperQ64) :
    (∀ guard ∈ lowerGuards, guard.SafeAt incomingLowerQ64) ∧
      ∀ guard ∈ upperGuards, guard.SafeAt incomingUpperQ64 :=
  all_safe_of_extrema lowerGuards upperGuards bounds hcontains hlower hupper

#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerRadiusQ64_sq_le
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerRadiusQ64_sq_lt
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.strictLowerRadiusQ64_sq_lt
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.upperRadiusQ64_sq_le
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_mono
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.upperEndpointSafe_anti
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_of_radius
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_strict_of_radius
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.upperEndpointSafe_of_radius
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_of_q16_root
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.lowerEndpointSafe_strict_of_q16_root
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.upperEndpointSafe_of_q16_root
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.LowerRadiusGuard.safeAt_of_requirement
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.UpperRadiusGuard.safeAt_of_allowance
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.all_lower_safe_of_minimumIncoming
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.all_upper_safe_of_maximumIncoming
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.all_radius_safe_of_folds
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineGuards.all_safe_of_extrema

end SparkInterval.Tests.PsiAffineGuardsTest

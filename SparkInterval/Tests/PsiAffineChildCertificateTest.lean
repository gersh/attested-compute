/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.PsiAffineChildCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.PsiAffineChildCertificateTest

open SparkInterval.TernaryGoldbach
open PsiAffineChildCertificate

private def broadBounds : Bounds :=
  ⟨0, 100⟩

private def first : Child where
  index := 0
  lower := 2
  upperExclusive := 6
  primePowerEvents := 4
  primeEvents := 4
  higherPowerEvents := 0
  delta := ⟨4, 4⟩
  bounds := broadBounds

private def second : Child where
  index := 1
  lower := 6
  upperExclusive := 10
  primePowerEvents := 4
  primeEvents := 4
  higherPowerEvents := 0
  delta := ⟨4, 4⟩
  bounds := broadBounds

private def accepted : Certificate where
  sourceLower := 2
  sourceUpperExclusive := 10
  rootState := State.zero
  finalState := ⟨8, 8⟩
  children := [first, second]

example : accepted.check = true := by decide

private def reordered : Certificate :=
  { accepted with children := [second, first] }

example : reordered.check = false := by decide

private def wrongRoot : Certificate :=
  { accepted with rootState := ⟨1, 1⟩ }

example : wrongRoot.check = false := by decide

#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.Certificate.checker_sound
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.checkSource_sound
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.RadiusSemantics.all_safe
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.semanticRunSafe_of_chain
#print axioms
  SparkInterval.TernaryGoldbach.PsiAffineChildCertificate.Certificate.checked_semantic_run_safe

end SparkInterval.Tests.PsiAffineChildCertificateTest

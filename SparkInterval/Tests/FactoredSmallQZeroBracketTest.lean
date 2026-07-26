/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQZeroBracket

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQZeroBracket

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQZeroBracket
open SparkInterval.Zeta

abbrev TailInflationCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate

def pointDisk (re im : ℚ) : ComplexDisk := ⟨re, im, 0⟩

theorem point_contains (value : ℚ) :
    (pointDisk value 0).ContainsComplex (value : ℂ) := by
  unfold ComplexDisk.ContainsComplex
  have hcenter : (pointDisk value 0).center = (value : ℂ) := by
    apply Complex.ext <;>
      norm_num [pointDisk, ComplexDisk.center]
  rw [hcenter]
  norm_num [pointDisk]

def negativeScale : ComplexDisk.MulCertificate := {
  left := pointDisk (-2) 0
  right := pointDisk 1 0
  output := pointDisk (-2) 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def negativeTail : TailInflationCertificate := {
  input := pointDisk (-2) 0
  tailBound := 0
  output := pointDisk (-2) 0
}

def negativeUntilt : ComplexDisk.MulCertificate := {
  left := pointDisk (-2) 0
  right := pointDisk 1 0
  output := pointDisk (-2) 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def negativeCertificate :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := negativeScale
  timeTailInflation := negativeTail
  untiltTimesPeriodized := negativeUntilt
  sign := .negative
}

def positiveScale : ComplexDisk.MulCertificate := {
  left := pointDisk 2 0
  right := pointDisk 1 0
  output := pointDisk 2 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def positiveTail : TailInflationCertificate := {
  input := pointDisk 2 0
  tailBound := 0
  output := pointDisk 2 0
}

def positiveUntilt : ComplexDisk.MulCertificate := {
  left := pointDisk 2 0
  right := pointDisk 1 0
  output := pointDisk 2 0
  centerErrorBound := 0
  leftCenterNormBound := 2
  rightCenterNormBound := 1
}

def positiveCertificate :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := positiveScale
  timeTailInflation := positiveTail
  untiltTimesPeriodized := positiveUntilt
  sign := .positive
}

theorem negative_certificate_check :
    negativeCertificate.check (pointDisk (-2) 0) = true := by
  norm_num [negativeCertificate,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    negativeScale, negativeTail, negativeUntilt, pointDisk,
    StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem positive_certificate_check :
    positiveCertificate.check (pointDisk 2 0) = true := by
  norm_num [positiveCertificate,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    positiveScale, positiveTail, positiveUntilt, pointDisk,
    StrictSign.CertifiedBy,
    ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

theorem positive_certificate_detached_from_negative_disk :
    positiveCertificate.check (pointDisk (-2) 0) = false := by
  norm_num [positiveCertificate,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    positiveScale, pointDisk]

def fourierDisks (key : CellKey) : ComplexDisk :=
  if key.characterId = 7 then
    if key.frequency = 0 then pointDisk (-2) 0
    else if key.frequency = 1 then pointDisk 2 0
    else pointDisk 0 0
  else pointDisk 0 0

def lowerEndpoint : SignedEndpoint := {
  key := ⟨7, 0⟩
  time := 0
  certificate := negativeCertificate
}

def upperEndpoint : SignedEndpoint := {
  key := ⟨7, 1⟩
  time := 1
  certificate := positiveCertificate
}

def goodBracket : CompletedSignBracket := {
  a := 1
  lower := lowerEndpoint
  upper := upperEndpoint
}

theorem goodBracket_valid : goodBracket.IsValid fourierDisks := by
  refine ⟨by norm_num [goodBracket], by decide, by decide, ?_, ?_,
    by norm_num [goodBracket, lowerEndpoint, upperEndpoint],
    ?_, ?_, ?_⟩
  · norm_num [goodBracket, lowerEndpoint, SignedEndpoint.sourceTime]
  · norm_num [goodBracket, upperEndpoint, SignedEndpoint.sourceTime]
  · simpa [goodBracket, lowerEndpoint, SignedEndpoint.check,
      fourierDisks] using negative_certificate_check
  · simpa [goodBracket, upperEndpoint, SignedEndpoint.check,
      fourierDisks] using positive_certificate_check
  · simp [CompletedSignBracket.OppositeSigns, goodBracket,
      lowerEndpoint, upperEndpoint, negativeCertificate,
      positiveCertificate]

theorem goodBracket_check : goodBracket.check fourierDisks = true :=
  CompletedSignBracket.check_eq_true.mpr goodBracket_valid

def evaluator (t : ℝ) : ℝ := 4 * t - 2

theorem lower_evaluator_link : lowerEndpoint.EvaluatorLink evaluator := by
  refine ⟨(-2 : ℂ), ?_, by norm_num, ?_⟩
  · simpa [lowerEndpoint, negativeCertificate,
      SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
      negativeUntilt] using point_contains (-2)
  · norm_num [evaluator, lowerEndpoint]

theorem upper_evaluator_link : upperEndpoint.EvaluatorLink evaluator := by
  refine ⟨(2 : ℂ), ?_, by norm_num, ?_⟩
  · simpa [upperEndpoint, positiveCertificate,
      SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
      positiveUntilt] using point_contains 2
  · norm_num [evaluator, upperEndpoint]

theorem checked_rational_bracket :
    goodBracket.toRationalBracket.check = true ∧
      goodBracket.toRationalBracket.EnclosesEndpoints evaluator :=
  CompletedSignBracket.checkedRationalBracket goodBracket_check
    lower_evaluator_link upper_evaluator_link

theorem lower_realizes :
    lowerEndpoint.Realizes fourierDisks evaluator (-2 : ℂ) 1 0 1 := by
  refine ⟨?_, ?_, by norm_num [lowerEndpoint, negativeCertificate,
      negativeTail],
    ?_, by norm_num [completedValue], ?_⟩
  · simpa [lowerEndpoint, fourierDisks] using point_contains (-2)
  · simpa [lowerEndpoint, negativeCertificate, negativeScale] using
      point_contains 1
  · simpa [lowerEndpoint, negativeCertificate, negativeUntilt] using
      point_contains 1
  · norm_num [evaluator, lowerEndpoint, completedValue]

theorem upper_realizes :
    upperEndpoint.Realizes fourierDisks evaluator (2 : ℂ) 1 0 1 := by
  refine ⟨?_, ?_, by norm_num [upperEndpoint, positiveCertificate,
      positiveTail],
    ?_, by norm_num [completedValue], ?_⟩
  · simpa [upperEndpoint, fourierDisks] using point_contains 2
  · simpa [upperEndpoint, positiveCertificate, positiveScale] using
      point_contains 1
  · simpa [upperEndpoint, positiveCertificate, positiveUntilt] using
      point_contains 1
  · norm_num [evaluator, upperEndpoint, completedValue]

theorem checked_rational_bracket_from_arithmetic :
    goodBracket.toRationalBracket.check = true ∧
      goodBracket.toRationalBracket.EnclosesEndpoints evaluator :=
  CompletedSignBracket.checkedRationalBracket_of_realizes goodBracket_check
    lower_realizes upper_realizes

/-! The same fixture through the source-shaped formulas. -/

noncomputable def sourceB : ℝ := 2 * Real.pi
def sourceEta : ℝ := 0

theorem source_b_pos : 0 < sourceB := by
  unfold sourceB
  positivity

theorem source_scale_one : sourceScale sourceB = 1 := by
  unfold sourceScale sourceB
  field_simp [ne_of_gt Real.pi_pos]

theorem lower_source_realizes :
    lowerEndpoint.SourceRealizes fourierDisks evaluator (-2 : ℂ) 0
      sourceB sourceEta := by
  refine ⟨source_b_pos, by norm_num [sourceEta], by norm_num [sourceEta],
    ?_⟩
  simpa [source_scale_one, sourceUntilt, sourceEta] using lower_realizes

theorem upper_source_realizes :
    upperEndpoint.SourceRealizes fourierDisks evaluator (2 : ℂ) 0
      sourceB sourceEta := by
  refine ⟨source_b_pos, by norm_num [sourceEta], by norm_num [sourceEta],
    ?_⟩
  simpa [source_scale_one, sourceUntilt, sourceEta] using upper_realizes

theorem checked_rational_bracket_from_source_arithmetic :
    goodBracket.toRationalBracket.check = true ∧
      goodBracket.toRationalBracket.EnclosesEndpoints evaluator :=
  CompletedSignBracket.checkedRationalBracket_of_sourceRealizes
    goodBracket_check lower_source_realizes upper_source_realizes

/-! ## Fail-closed metadata tests -/

def sameSignEndpoint : SignedEndpoint :=
  { upperEndpoint with certificate := negativeCertificate }

def sameSignBracket : CompletedSignBracket :=
  { goodBracket with upper := sameSignEndpoint }

theorem same_sign_fails_closed :
    sameSignBracket.check (fun _ ↦ pointDisk (-2) 0) = false := by
  apply CompletedSignBracket.check_eq_false.mpr
  intro hvalid
  rcases hvalid with ⟨_, _, _, _, _, _, _, _, hopposite⟩
  simp [CompletedSignBracket.OppositeSigns, sameSignBracket,
    sameSignEndpoint, goodBracket, lowerEndpoint, upperEndpoint,
    negativeCertificate] at hopposite

def reversedBracket : CompletedSignBracket := {
  a := 1
  lower := upperEndpoint
  upper := lowerEndpoint
}

theorem reversed_endpoints_fail_closed :
    reversedBracket.check fourierDisks = false := by
  apply CompletedSignBracket.check_eq_false.mpr
  intro hvalid
  rcases hvalid with ⟨_, _, hsamples, _⟩
  norm_num [reversedBracket, lowerEndpoint, upperEndpoint] at hsamples

def equalTimeUpper : SignedEndpoint := { upperEndpoint with time := 0 }

def equalTimeBracket : CompletedSignBracket :=
  { goodBracket with upper := equalTimeUpper }

theorem equal_endpoints_fail_closed :
    equalTimeBracket.check fourierDisks = false := by
  apply CompletedSignBracket.check_eq_false.mpr
  intro hvalid
  rcases hvalid with ⟨_, _, _, _, _, htimes, _⟩
  norm_num [equalTimeBracket, equalTimeUpper, goodBracket, lowerEndpoint,
    upperEndpoint] at htimes

def detachedKeyUpper : SignedEndpoint :=
  { upperEndpoint with key := ⟨8, 1⟩ }

def detachedKeyBracket : CompletedSignBracket :=
  { goodBracket with upper := detachedKeyUpper }

theorem detached_character_key_fails_closed :
    detachedKeyBracket.check fourierDisks = false := by
  apply CompletedSignBracket.check_eq_false.mpr
  intro hvalid
  rcases hvalid with ⟨_, hcharacter, _⟩
  norm_num [detachedKeyBracket, detachedKeyUpper, goodBracket,
    lowerEndpoint, upperEndpoint] at hcharacter

def detachedPayloadLower : SignedEndpoint :=
  { lowerEndpoint with certificate := positiveCertificate }

def detachedPayloadBracket : CompletedSignBracket :=
  { goodBracket with lower := detachedPayloadLower }

theorem detached_payload_fails_closed :
    detachedPayloadBracket.check fourierDisks = false := by
  apply CompletedSignBracket.check_eq_false.mpr
  intro hvalid
  rcases hvalid with ⟨_, _, _, _, _, _, hlowerCheck, _⟩
  have hfalse :
      positiveCertificate.check (pointDisk (-2) 0) = true := by
    simpa [detachedPayloadBracket, detachedPayloadLower, goodBracket,
      lowerEndpoint, SignedEndpoint.check, fourierDisks] using hlowerCheck
  rw [positive_certificate_detached_from_negative_disk] at hfalse
  contradiction

/-! ## Family handoff -/

def oneFamily : CompletedSignBracketFamily 1 := {
  a := 1
  characterId := 7
  entries := fun _ ↦ goodBracket
}

theorem oneFamily_valid : oneFamily.IsValid fourierDisks := by
  refine ⟨by norm_num [oneFamily], ?_, ?_⟩
  · intro i
    exact ⟨by rfl, by rfl, by simpa [oneFamily] using goodBracket_valid⟩
  · constructor
    · intro i
      simpa [CompletedSignBracketFamily.toRationalBracketFamily, oneFamily]
        using CompletedSignBracket.toRationalBracket_isValid goodBracket_valid
    · intro i j hij
      omega

theorem oneFamily_check : oneFamily.check fourierDisks = true :=
  CompletedSignBracketFamily.check_eq_true.mpr oneFamily_valid

theorem oneFamily_exists_zeroCertificate :
    ∃ certificate : ZeroCertificate evaluator 1,
      ∀ i,
        (certificate.brackets i).lower =
            (oneFamily.entries i).lower.time ∧
        (certificate.brackets i).upper =
            (oneFamily.entries i).upper.time := by
  apply CompletedSignBracketFamily.exists_zeroCertificate oneFamily
    oneFamily_check
  intro i
  exact ⟨by simpa [oneFamily, goodBracket] using lower_evaluator_link,
    by simpa [oneFamily, goodBracket] using upper_evaluator_link⟩

#print axioms realProjection_contains_real
#print axioms CompletedSignBracket.toRationalBracket_check
#print axioms CompletedSignBracket.checkedRationalBracket_of_realizes
#print axioms CompletedSignBracket.checkedRationalBracket_of_sourceRealizes
#print axioms CompletedSignBracketFamily.exists_zeroCertificate
#print axioms checked_rational_bracket_from_arithmetic
#print axioms checked_rational_bracket_from_source_arithmetic
#print axioms oneFamily_exists_zeroCertificate

end SparkInterval.Tests.FactoredSmallQZeroBracket

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign
import SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCompletedSignModulusCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Tests.FactoredSmallQRawDFTComposition
open SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

abbrev OuterCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate

/-! ## Two distinct source moduli sharing only reusable arithmetic fixtures -/

def fullSpec (q : Nat) : Spec := ⟨q, [2], 1⟩
def sampleSpec (q : Nat) : SourceSampleSpec := ⟨q, [2], 1⟩
def modulusSpec (q : Nat) : ModulusSpec :=
  ⟨fullSpec q, sampleSpec q⟩

def source : SourceSpec :=
  ⟨[modulusSpec 3, modulusSpec 5]⟩

def postprocessCampaign (q : Nat) :
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.RawPostprocessCampaignCertificate :=
  { campaign with q := q }

def fourierDisks : CellKey → ComplexDisk :=
  SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks

/-! The completed-sign payload below is structurally satisfiable for the
non-real disk used by the earlier raw-DFT fixture.  This test exercises only
the finite checker.  The outer application theorem still requires an
explicit reality premise before deriving a mathematical sign. -/

def unitDisk : ComplexDisk := ⟨1, 0, 0⟩

def scaleProduct : ComplexDisk.MulCertificate := {
  left := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
  right := unitDisk
  output := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
  centerErrorBound := 0
  leftCenterNormBound := 122
  rightCenterNormBound := 1
}

def zeroTail :
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate := {
  input := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
  tailBound := 0
  output := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
}

def untiltProduct : ComplexDisk.MulCertificate := {
  left := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
  right := unitDisk
  output := SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output
  centerErrorBound := 0
  leftCenterNormBound := 122
  rightCenterNormBound := 1
}

def signPayload :
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate := {
  scaleTimesFourier := scaleProduct
  timeTailInflation := zeroTail
  untiltTimesPeriodized := untiltProduct
  sign := .positive
}

theorem sign_payload_check :
    signPayload.check
      SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output =
        true := by
  norm_num [signPayload,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.Accepted,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate.output,
    scaleProduct, zeroTail, untiltProduct, unitDisk,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk,
    StrictSign.CertifiedBy, ComplexDisk.MulCertificate.check,
    ComplexDisk.MulCertificate.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.check,
    SparkInterval.Dirichlet.FactoredSmallQPostprocess.TailInflationCertificate.WellFormed,
    ComplexDisk.productCenterErrorSq, ComplexDisk.centerNormSq]

def signBatch : Batch
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩, signPayload⟩]⟩

def signCampaign (q : Nat) : SignCampaignCertificate := {
  q := q
  roster := [2]
  transformLength := 1
  batches := [signBatch]
}

theorem postprocess_check (q : Nat) (hq : 3 ≤ q) :
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check
      (fullSpec q) termCount oddParity negativeFrequency
      (postprocessCampaign q) = true := by
  simp [SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check,
    fullSpec, postprocessCampaign, campaign, batch,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    payload_ok, hq]

theorem sign_campaign_check (q : Nat) (hq : 3 ≤ q) :
    sourceCheck (sampleSpec q) 1 fourierDisks (signCampaign q) = true := by
  simp [sourceCheck, SourceSampleSpec.FitsDFTLength,
    SourceSampleSpec.toCampaignSpec,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.payloadCheck,
    sampleSpec, signCampaign, signBatch, fourierDisks,
    SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    sign_payload_check, hq]

def bundle (q : Nat) : ModulusBundle 0 := {
  postprocessCampaign := postprocessCampaign q
  naturalDisks := fourierDisks
  fourierDisks := fourierDisks
  rawTransforms := rawTransforms
  bounds := bounds
  signCampaign := signCampaign q
}

theorem bundle_decoded (q characterId : Nat) :
    (bundle q).decodedTransform characterId = decodedTransform := by
  simp [ModulusBundle.decodedTransform, bundle, rawTransforms,
    raw_transform_decode]

theorem bundle_decoded_function (q : Nat) :
    (bundle q).decodedTransform = decodedTransforms := by
  funext characterId
  exact bundle_decoded q characterId

def outerCertificate : OuterCertificate 0 :=
  ⟨[bundle 3, bundle 5]⟩

def outerTermCount (_ : ModulusSpec) := termCount
def outerOddParity (_ : ModulusSpec) := oddParity
def outerNegativeFrequency (_ : ModulusSpec) := negativeFrequency

theorem bundle_check (q : Nat) (hq : 3 ≤ q) :
    (bundle q).check (modulusSpec q) termCount oddParity
      negativeFrequency = true := by
  simp only [ModulusBundle.check, Bool.and_eq_true]
  refine ⟨?_, postprocess_check q hq, ?_, ?_, sign_campaign_check q hq⟩
  · change
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.bridgeCheck
        (fullSpec q) (sampleSpec q) fourierDisks
          (bundle q).decodedTransform = true
    rw [bundle_decoded_function]
    norm_num [
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.bridgeCheck,
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
      modulusSpec,
      fullSpec, sampleSpec, fourierDisks,
      SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks,
      decodedTransforms,
      decodedTransform, DecodedCertificate.claimedOutput,
      diskStateOfList, diskAt, lineLength, finIndex]
  · change linkCheck (fullSpec q) (postprocessCampaign q) fourierDisks
      (fun characterId ↦
        ((bundle q).decodedTransform characterId).certificate) = true
    simp_rw [bundle_decoded]
    norm_num [linkCheck, checkRawOutputsDecodeTo, checkInputsLinked,
      postprocessCampaign, fullSpec, fourierDisks, campaign, batch,
      SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks,
      decodedTransform, DecodedCertificate.certificate,
      diskStateOfList, diskAt, lineLength, finIndex,
      SparkInterval.Tests.FactoredSmallQRawPostprocess.rawSample,
      SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.output_decode_eq
        SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail_decode]
  · simp [allRawChecks, bundle, modulusSpec, fullSpec,
      rawTransforms, bounds, raw_transform_check]

/-- A genuine two-modulus certificate is accepted in source order. -/
theorem two_modulus_check :
    outerCertificate.check source outerTermCount outerOddParity
      outerNegativeFrequency = true := by
  rw [SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate.check]
  simp only [Bool.and_eq_true]
  constructor
  · apply decide_eq_true
    norm_num [source, SourceSpec.WellFormed, SourceSpec.AllWellFormed,
      ModulusSpec.WellFormed,
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
      modulusSpec, fullSpec, sampleSpec, lineLength,
      SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed]
    simp
  · change checkPairs outerTermCount outerOddParity outerNegativeFrequency
      [modulusSpec 3, modulusSpec 5] [bundle 3, bundle 5] = true
    simp only [checkPairs, outerTermCount, outerOddParity,
      outerNegativeFrequency, Bool.and_eq_true]
    exact ⟨bundle_check 3 (by omega), bundle_check 5 (by omega), trivial⟩

/-! Reversing the two otherwise valid bundles fails: the first certificate
still says `q = 5`, while the first source entry says `q = 3`. -/
def reversedCertificate : OuterCertificate 0 :=
  ⟨[bundle 5, bundle 3]⟩

theorem reordered_bundles_fail_closed :
    reversedCertificate.check source outerTermCount outerOddParity
      outerNegativeFrequency = false := by
  simp [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate.check,
    source, SourceSpec.WellFormed,
    SourceSpec.AllWellFormed, ModulusSpec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    modulusSpec, fullSpec, sampleSpec,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    checkPairs, reversedCertificate, outerTermCount, outerOddParity,
    outerNegativeFrequency, ModulusBundle.check, bundle,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.bridgeCheck,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check,
    postprocessCampaign, campaign,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid]

/-! Duplicate source modulus numbers fail before any certificate lookup. -/
def duplicateSource : SourceSpec :=
  ⟨[modulusSpec 3, modulusSpec 3]⟩

theorem duplicate_modulus_fails_closed :
    outerCertificate.check duplicateSource outerTermCount outerOddParity
      outerNegativeFrequency = false := by
  simp [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate.check,
    duplicateSource, SourceSpec.WellFormed,
    modulusSpec, fullSpec]

/-! A source header is one modulus-wide parameter triple plus one time-tail
function.  This test intentionally proves only the ordered structural/grid
relation; it does not manufacture a functional-equation reality premise for
the non-real arithmetic fixture above. -/
def structuralHeader (_spec : ModulusSpec) : SourceHeader := {
  parameters :=
    SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaign.positiveSourceParameters
  timeTail := fun _key ↦ 0
}

theorem source_headers_are_order_aligned :
    SourceHeadersAligned source outerCertificate structuralHeader := by
  exact List.Forall₂.cons
    SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaign.positive_source_grid
    (List.Forall₂.cons
      SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaign.positive_source_grid
      List.Forall₂.nil)

#print axioms SourceSpec.WellFormed
#print axioms SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignModulusCampaign.Certificate.checker_sound
#print axioms requested_modulus_sample_has_direct_sign
#print axioms SourceApplicationInputsAligned.headers_aligned
#print axioms requested_modulus_sample_has_source_sign
#print axioms two_modulus_check
#print axioms reordered_bundles_fail_closed
#print axioms duplicate_modulus_fails_closed
#print axioms source_headers_are_order_aligned

end SparkInterval.Tests.FactoredSmallQRawCompletedSignModulusCampaign

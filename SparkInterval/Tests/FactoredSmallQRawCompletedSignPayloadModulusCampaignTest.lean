/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
import SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadModulusCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Tests.FactoredSmallQRawDFTComposition
open SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

abbrev OuterCertificate :=
  SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate

/-! ## Two source moduli with raw DFT-owned sign payloads -/

def fullSpec (q : Nat) : Spec := ⟨q, [2], 1⟩

def sampleSpec (q : Nat) : SourceSampleSpec := ⟨q, [2], 1⟩

def modulusSpec (q : Nat) : ModulusSpec :=
  ⟨fullSpec q, sampleSpec q⟩

def source : SourceSpec :=
  ⟨[modulusSpec 3, modulusSpec 5]⟩

def postprocessCampaign (q : Nat) :
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.RawPostprocessCampaignCertificate :=
  { SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.campaign with
    q := q }

def naturalDisks : CellKey → ComplexDisk :=
  SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks

def rawTransforms (_ : Nat) :
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.RawCertificate 0 :=
  SparkInterval.Tests.FactoredSmallQRawDFTComposition.rawTransform

def rawSignCampaign (q : Nat) : RawSignCampaignCertificate :=
  { SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.campaign with
    q := q }

theorem raw_payload_ok :
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.payloadCheck
      rawTransforms ⟨2, 0⟩
        SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.rawPayload =
      true := by
  have htransforms : rawTransforms =
      SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.rawTransforms := by
    rfl
  rw [htransforms]
  exact
    SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.payload_ok

theorem postprocess_check (q : Nat) (hq : 3 ≤ q) :
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check
      (fullSpec q)
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.termCount
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.oddParity
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.negativeFrequency
      (postprocessCampaign q) = true := by
  simp [SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign.check,
    fullSpec, postprocessCampaign,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.campaign,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.batch,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.payload_ok, hq]

theorem raw_sign_campaign_check (q : Nat) (hq : 3 ≤ q) :
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.check
      (fullSpec q) (sampleSpec q) rawTransforms (rawSignCampaign q) = true := by
  simp [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    fullSpec, sampleSpec, rawSignCampaign,
    SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.campaign,
    SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.batch,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    raw_payload_ok,
    hq]

def bundle (q : Nat) : ModulusBundle 0 := {
  postprocessCampaign := postprocessCampaign q
  naturalDisks := naturalDisks
  rawTransforms := rawTransforms
  bounds := SparkInterval.Tests.FactoredSmallQRawDFTComposition.bounds
  signCampaign := rawSignCampaign q
}

theorem bundle_decoded (q characterId : Nat) :
    (bundle q).decodedTransform characterId =
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransform := by
  simp [ModulusBundle.decodedTransform, bundle, rawTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.raw_transform_decode]

def outerCertificate : OuterCertificate 0 :=
  ⟨[bundle 3, bundle 5]⟩

def outerTermCount (_ : ModulusSpec) :=
  SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.termCount

def outerOddParity (_ : ModulusSpec) :=
  SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.oddParity

def outerNegativeFrequency (_ : ModulusSpec) :=
  SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.negativeFrequency

theorem bundle_check (q : Nat) (hq : 3 ≤ q) :
    (bundle q).check (modulusSpec q)
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.termCount
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.oddParity
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.negativeFrequency =
        true := by
  simp only [ModulusBundle.check, Bool.and_eq_true]
  refine ⟨raw_sign_campaign_check q hq, postprocess_check q hq, ?_, ?_⟩
  · change linkCheck (fullSpec q) (postprocessCampaign q) naturalDisks
      (fun characterId ↦
        ((bundle q).decodedTransform characterId).certificate) = true
    simp_rw [bundle_decoded]
    norm_num [linkCheck, checkRawOutputsDecodeTo, checkInputsLinked,
      postprocessCampaign, fullSpec, naturalDisks,
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.campaign,
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.batch,
      SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks,
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransform,
      DecodedCertificate.certificate, diskStateOfList, diskAt, lineLength,
      finIndex,
      SparkInterval.Tests.FactoredSmallQRawPostprocess.rawSample,
      SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.output_decode_eq
        SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail_decode]
  · simp [allRawChecks, bundle, modulusSpec, fullSpec, rawTransforms,
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.bounds,
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.raw_transform_check]

/-! Exact source order accepts two distinct modulus bundles. -/
theorem two_modulus_check :
    outerCertificate.check source outerTermCount outerOddParity
      outerNegativeFrequency = true := by
  rw [SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check]
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

/-! Reordering otherwise valid raw bundles fails at the first modulus-local
campaign header. -/
def reversedCertificate : OuterCertificate 0 :=
  ⟨[bundle 5, bundle 3]⟩

theorem first_reordered_bundle_fails :
    (bundle 5).check (modulusSpec 3)
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.termCount
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.oddParity
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.negativeFrequency =
        false := by
  simp [ModulusBundle.check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign.check,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement,
    modulusSpec, fullSpec, sampleSpec, bundle, rawSignCampaign,
    SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.campaign,
    SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadCampaign.batch,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign.SourceSampleSpec.toCampaignSpec,
    SparkInterval.Dirichlet.FactoredSmallQRawDFT.lineLength]

theorem reordered_bundles_fail_closed :
    reversedCertificate.check source outerTermCount outerOddParity
      outerNegativeFrequency = false := by
  have hsource : decide (source.WellFormed 0) = true := by
    have h := two_modulus_check
    simp only [
      SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check,
      Bool.and_eq_true] at h
    exact h.1
  rw [SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check,
    hsource]
  simp [checkPairs, reversedCertificate, source, outerTermCount,
    outerOddParity, outerNegativeFrequency, first_reordered_bundle_fails]

/-! Duplicate source modulus numbers fail before bundle replay. -/
def duplicateSource : SourceSpec :=
  ⟨[modulusSpec 3, modulusSpec 3]⟩

theorem duplicate_modulus_fails_closed :
    outerCertificate.check duplicateSource outerTermCount outerOddParity
      outerNegativeFrequency = false := by
  simp [
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.check,
    duplicateSource, SourceSpec.WellFormed, modulusSpec, fullSpec]

/-! This structural fixture checks source-header order only.  It deliberately
does not manufacture a reality premise for the non-real arithmetic disk. -/
def structuralHeader (_spec : ModulusSpec) : SourceHeader := {
  parameters := { a := 1, b := 1, eta := 0 }
  timeTail := fun _key ↦ 0
}

theorem structural_header_grid (spec : ModulusSpec) :
    (structuralHeader spec).parameters.GridValid 0 := by
  norm_num [structuralHeader,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceParameters.GridValid,
    SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign.SourceParameters.PositiveDenominators,
    lineLength]

theorem source_headers_are_order_aligned :
    SourceHeadersAligned source outerCertificate structuralHeader := by
  exact List.Forall₂.cons (structural_header_grid (modulusSpec 3))
    (List.Forall₂.cons (structural_header_grid (modulusSpec 5))
      List.Forall₂.nil)

#print axioms SourceSpec.WellFormed
#print axioms SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadModulusCampaign.Certificate.checker_sound
#print axioms SourceApplicationInputsAligned.headers_aligned
#print axioms requested_modulus_sample_has_raw_source_sign
#print axioms two_modulus_check
#print axioms reordered_bundles_fail_closed
#print axioms duplicate_modulus_fails_closed
#print axioms source_headers_are_order_aligned

end SparkInterval.Tests.FactoredSmallQRawCompletedSignPayloadModulusCampaign

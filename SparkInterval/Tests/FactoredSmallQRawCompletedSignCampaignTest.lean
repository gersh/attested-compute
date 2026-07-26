/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign
import SparkInterval.Tests.FactoredSmallQRawDFTCompositionTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign

def sourceSpec : SourceSampleSpec := ⟨3, [2], 1⟩

def positiveSourceParameters : SourceParameters := {
  a := 1
  b := 1
  eta := 0
}

theorem positive_source_denominators :
    positiveSourceParameters.PositiveDenominators := by
  norm_num [SourceParameters.PositiveDenominators,
    positiveSourceParameters]

theorem positive_source_grid :
    positiveSourceParameters.GridValid 0 := by
  norm_num [SourceParameters.GridValid,
    SourceParameters.PositiveDenominators,
    positiveSourceParameters, lineLength]

theorem source_time_is_derived :
    positiveSourceParameters.t ⟨2, 3⟩ = 3 := by
  norm_num [SourceParameters.t, positiveSourceParameters]

noncomputable def bookerParameters : SourceParameters := {
  a := SourceParameters.bookerA
  b := 5 / 64
  eta := 0
}

theorem booker_grid_is_satisfiable :
    SourceParameters.BookerGridValid bookerParameters 0 := by
  norm_num [SourceParameters.BookerGridValid, SourceParameters.GridValid,
    SourceParameters.PositiveDenominators, bookerParameters,
    SourceParameters.bookerA,
    lineLength]

def zeroDenominatorParameters : SourceParameters :=
  { positiveSourceParameters with b := 0 }

theorem zero_source_denominator_fails_closed :
    ¬ zeroDenominatorParameters.PositiveDenominators := by
  intro hpositive
  norm_num [SourceParameters.PositiveDenominators,
    zeroDenominatorParameters] at hpositive

def fourierDisks : CellKey → ComplexDisk :=
  SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks

theorem bridge_check :
    bridgeCheck
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec
      sourceSpec fourierDisks
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms =
        true := by
  norm_num [bridgeCheck, SourceDFTAgreement, sourceSpec, fourierDisks,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec,
    SparkInterval.Tests.FactoredSmallQDFTComposition.naturalDisks,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransform,
    DecodedCertificate.claimedOutput, diskStateOfList, diskAt,
    lineLength, finIndex]

/-- The retained source length cannot silently exceed the one-point DFT. -/
def oversizedSourceSpec : SourceSampleSpec := ⟨3, [2], 2⟩

theorem oversized_source_fails_closed :
    bridgeCheck
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec
      oversizedSourceSpec fourierDisks
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms =
        false := by
  norm_num [bridgeCheck, SourceDFTAgreement, oversizedSourceSpec,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec,
    lineLength]

/-- A source campaign for a different modulus cannot be attached to the raw
DFT line, even when its roster and sample count happen to match. -/
def wrongModulusSourceSpec : SourceSampleSpec := ⟨5, [2], 1⟩

theorem wrong_modulus_fails_closed :
    bridgeCheck
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec
      wrongModulusSourceSpec fourierDisks
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms =
        false := by
  norm_num [bridgeCheck, SourceDFTAgreement, wrongModulusSourceSpec,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec]

/-- Exact disk equality, not merely matching dimensions or keys, joins the
raw DFT and completed-sign layers. -/
def alteredFourierDisks (_ : CellKey) : ComplexDisk := ⟨0, 0, 0⟩

theorem altered_fourier_disk_fails_closed :
    bridgeCheck
      SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec
      sourceSpec alteredFourierDisks
      SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms =
        false := by
  norm_num [bridgeCheck, SourceDFTAgreement, sourceSpec,
    alteredFourierDisks,
    SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign.spec,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransforms,
    SparkInterval.Tests.FactoredSmallQRawDFTComposition.decodedTransform,
    DecodedCertificate.claimedOutput, diskStateOfList, diskAt,
    lineLength, finIndex,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk]

#print axioms bridgeCheck_sound
#print axioms requested_source_sample_has_direct_sign
#print axioms positive_source_denominators
#print axioms positive_source_grid
#print axioms source_time_is_derived
#print axioms booker_grid_is_satisfiable
#print axioms zero_source_denominator_fails_closed
#print axioms bridge_check
#print axioms oversized_source_fails_closed
#print axioms wrong_modulus_fails_closed
#print axioms altered_fourier_disk_fails_closed
#print axioms requested_source_sample_has_source_sign

end SparkInterval.Tests.FactoredSmallQRawCompletedSignCampaign

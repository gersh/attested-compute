/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFTComposition
import SparkInterval.Tests.FactoredSmallQRawPostprocessCampaignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQDFTComposition

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

def naturalDisks (_ :
    SparkInterval.Dirichlet.FactoredSmallQCampaign.CellKey) : ComplexDisk :=
  SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output

def transform (_ : ℕ) :
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate 0 := {
  input := ⟨fun _ ↦
    SparkInterval.Tests.FactoredSmallQRawPostprocess.typedTail.output⟩
  twiddleDisks := fun _ _ ↦ ⟨0, 0, 0⟩
  stages := []
}

theorem raw_outputs_decode :
    RawOutputsDecodeTo campaign naturalDisks := by
  intro batch hbatch cell hcell
  simp [campaign] at hbatch
  subst batch
  simp [batch] at hcell
  subst cell
  exact SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.output_decode_eq
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail_decode

theorem inputs_linked :
    InputsLinked spec naturalDisks transform := by
  constructor
  · rfl
  · intro characterId hcharacter index
    simp [transform, naturalDisks]

theorem links_check :
    linkCheck spec campaign naturalDisks transform = true := by
  simp [linkCheck, checkRawOutputsDecodeTo, checkInputsLinked, spec,
    campaign, batch, naturalDisks, transform,
    SparkInterval.Tests.FactoredSmallQRawPostprocess.rawSample,
    SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.output_decode_eq
      SparkInterval.Tests.FactoredSmallQRawPostprocess.rawTail_decode]

theorem transform_check :
    ∀ characterId, characterId ∈ spec.roster →
      (transform characterId).check = true := by
  intro characterId hcharacter
  simp [transform,
    SparkInterval.Dirichlet.FactoredSmallQDFT.Certificate.check,
    checkLinkedStages]

theorem roots_contain :
    ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := 0)
        (transform characterId).twiddleDisks positiveTwiddle := by
  intro characterId hcharacter stage hstage
  omega

theorem composed_output_contains :
    StateContains (transform 2).output
      (positiveRadix2Transform
        (exactSource 0 2
          (exactCellValue oddParity negativeFrequency bases prefactors deltas
            characters))) := by
  apply output_contains_positiveRadix2
    campaign_check base_disks character_disks prefactor_disks tail_bound
    raw_outputs_decode inputs_linked transform_check roots_contain
  simp [spec]

theorem checked_links_output_contains :
    StateContains (transform 2).output
      (positiveRadix2Transform
        (exactSource 0 2
          (exactCellValue oddParity negativeFrequency bases prefactors deltas
            characters))) := by
  apply output_contains_positiveRadix2_of_linkCheck
    campaign_check base_disks character_disks prefactor_disks tail_bound
    links_check transform_check roots_contain
  simp [spec]

#print axioms input_contains_bitReversed
#print axioms output_contains_positiveRadix2
#print axioms output_contains_positiveRadix2_of_linkCheck
#print axioms composed_output_contains
#print axioms checked_links_output_contains

end SparkInterval.Tests.FactoredSmallQDFTComposition

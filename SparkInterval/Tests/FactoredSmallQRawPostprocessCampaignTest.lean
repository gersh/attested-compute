/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign
import SparkInterval.Tests.FactoredSmallQRawPostprocessTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign
open SparkInterval.Tests.FactoredSmallQRawPostprocess

def spec : Spec := ⟨3, [2], 1⟩

def batch : Batch RawCertificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩, rawSample⟩]⟩

def campaign : RawPostprocessCampaignCertificate := {
  q := 3
  roster := [2]
  transformLength := 1
  batches := [batch]
}

def termCount (_ : CellKey) : ℕ := 2
def oddParity (_ : CellKey) : Bool := false
def negativeFrequency (_ : CellKey) : Bool := true
def bases (_ : CellKey) : ℂ := 2
def characters (_ : CellKey) : List ℂ := [(3 : ℂ), (5 : ℂ)]
def prefactors (_ : CellKey) : ℂ := pointValue 1 1
noncomputable def deltas (_ : CellKey) : ℂ := 1 / 4

theorem payload_ok :
    payloadCheck termCount oddParity negativeFrequency ⟨2, 0⟩
      rawSample = true := by
  have htruncation : rawSample.finiteSum.truncation = 2 := rfl
  have hparity : rawSample.finiteSum.oddParity = false := rfl
  have hnegative : rawSample.negativeFrequency = true := rfl
  simp [payloadCheck, termCount, oddParity, negativeFrequency,
    htruncation, hparity, hnegative, rawSample_check]

theorem campaign_check :
    check spec termCount oddParity negativeFrequency campaign = true := by
  simp [check, spec, campaign, batch,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    payload_ok]

theorem base_disks : BaseDisksContain campaign bases := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact ⟨SparkInterval.Tests.FactoredSmallQRawGaussianSum.realDisk 2,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawTwo_decode,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.realDisk_contains 2⟩

theorem character_disks : CharacterDisksContain campaign characters := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQRawGaussianSum.raw_characters

theorem prefactor_disks : PrefactorDisksContain campaign prefactors := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact ⟨pointDisk 1 1, rawOneOne_decode, pointDisk_contains 1 1⟩

theorem tail_bound : TailPerturbationsBound campaign deltas := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact ⟨1 / 2, rawHalf_decode, quarter_tail⟩

theorem requested_cell_contains :
    ∃ foundBatch, foundBatch ∈ campaign.batches ∧
      ∃ foundCell, foundCell ∈ foundBatch.cells ∧
        foundCell.key = ⟨2, 0⟩ ∧
        ∃ decoded :
            SparkInterval.Dirichlet.FactoredSmallQPostprocess.Certificate,
          foundCell.payload.decode = some decoded ∧
          foundCell.payload.tailInflation.output.decode = some decoded.output ∧
          (characters ⟨2, 0⟩).length = termCount ⟨2, 0⟩ ∧
          decoded.output.ContainsComplex
            (applyFrequencySignValue (negativeFrequency ⟨2, 0⟩)
                (prefactors ⟨2, 0⟩ *
                  SparkInterval.Dirichlet.FactoredSmallQGaussianSum.exactFiniteSum
                    (oddParity ⟨2, 0⟩) (bases ⟨2, 0⟩)
                    (characters ⟨2, 0⟩)) +
              deltas ⟨2, 0⟩) := by
  exact requested_output_contains_exact_postprocessed_sum
    (characterId := 2) (frequency := 0)
    campaign_check base_disks character_disks prefactor_disks tail_bound
    (by simp [spec]) (by simp [spec])

def wrongSign : CellKey → Bool := fun _ ↦ false

theorem wrong_sign_fails_closed :
    check spec termCount oddParity wrongSign campaign = false := by
  simp [check, spec, campaign, batch,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    payloadCheck, termCount, oddParity, wrongSign, rawSample,
    SparkInterval.Tests.FactoredSmallQRawGaussianSum.rawSample]

#print axioms checker_sound
#print axioms requested_output_contains_exact_postprocessed_sum
#print axioms requested_cell_contains
#print axioms wrong_sign_fails_closed

end SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

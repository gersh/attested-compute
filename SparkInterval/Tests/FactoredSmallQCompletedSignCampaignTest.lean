/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign
import SparkInterval.Tests.FactoredSmallQCompletedSignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQCompletedSignCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign

def spec : Spec := ⟨3, [2], 1⟩

def sourceSpec : SourceSampleSpec := ⟨3, [2], 1⟩

def oversizedSourceSpec : SourceSampleSpec := ⟨3, [2], 5⟩

def batch : Batch
    SparkInterval.Dirichlet.FactoredSmallQCompletedSign.Certificate :=
  ⟨0, 0, [2], [⟨⟨2, 0⟩,
    SparkInterval.Tests.FactoredSmallQCompletedSign.sample⟩]⟩

def campaign : SignCampaignCertificate := {
  q := 3
  roster := [2]
  transformLength := 1
  batches := [batch]
}

def fourierDisks (_ : CellKey) :=
  SparkInterval.Tests.FactoredSmallQCompletedSign.pointDisk 2 0
def fourier (_ : CellKey) : ℂ := 2
def scale (_ : CellKey) : ℝ := 3
noncomputable def timeTail (_ : CellKey) : ℂ := 1 / 4
def untilt (_ : CellKey) : ℝ := 2

theorem campaign_check : check spec fourierDisks campaign = true := by
  simp [check, campaign, batch, spec, payloadCheck,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchChain,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.BatchCellsValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.expectedKeys,
    SparkInterval.Tests.FactoredSmallQCompletedSign.sample_check,
    fourierDisks]

theorem source_check :
    sourceCheck sourceSpec 4 fourierDisks campaign = true := by
  simpa [sourceCheck, SourceSampleSpec.FitsDFTLength,
    SourceSampleSpec.toCampaignSpec, sourceSpec, spec] using campaign_check

/-- Even a valid one-sample sign campaign cannot claim that its retained
sample range fits in an empty full transform. -/
theorem empty_dft_length_fails_closed :
    sourceCheck sourceSpec 0 fourierDisks campaign = false := by
  simp [sourceCheck, SourceSampleSpec.FitsDFTLength, sourceSpec]

theorem oversized_source_range_fails_closed :
    sourceCheck oversizedSourceSpec 4 fourierDisks campaign = false := by
  simp [sourceCheck, SourceSampleSpec.FitsDFTLength, oversizedSourceSpec]

theorem fourier_contains :
    FourierDisksContain campaign fourierDisks fourier := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQCompletedSign.point_contains 2

theorem scales_contain : ScaleDisksContain campaign scale := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQCompletedSign.point_contains 3

theorem tails_bound : TimeTailsBound campaign timeTail := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQCompletedSign.quarter_tail

theorem untilts_contain : UntiltDisksContain campaign untilt := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQCompletedSign.point_contains 2

theorem completed_real :
    CompletedValuesReal campaign fourier scale timeTail untilt := by
  intro foundBatch hbatch foundCell hcell
  simp [campaign] at hbatch
  subst foundBatch
  simp [batch] at hcell
  subst foundCell
  exact SparkInterval.Tests.FactoredSmallQCompletedSign.completed_is_real

theorem requested_sign :
    ∃ foundBatch, foundBatch ∈ campaign.batches ∧
      ∃ foundCell, foundCell ∈ foundBatch.cells ∧
        foundCell.key = ⟨2, 0⟩ ∧
        foundCell.payload.sign.Holds
          (completedValue (fourier ⟨2, 0⟩) (scale ⟨2, 0⟩)
            (timeTail ⟨2, 0⟩) (untilt ⟨2, 0⟩)).re := by
  exact requested_sample_has_sign campaign_check fourier_contains
    scales_contain tails_bound untilts_contain completed_real
    (by simp [spec]) (by simp [spec])

theorem requested_source_sign :
    0 < 4 ∧
      ∃ foundBatch, foundBatch ∈ campaign.batches ∧
        ∃ foundCell, foundCell ∈ foundBatch.cells ∧
          foundCell.key = ⟨2, 0⟩ ∧
          foundCell.payload.sign.Holds
            (completedValue (fourier ⟨2, 0⟩) (scale ⟨2, 0⟩)
              (timeTail ⟨2, 0⟩) (untilt ⟨2, 0⟩)).re := by
  exact requested_source_sample_has_sign source_check fourier_contains
    scales_contain tails_bound untilts_contain completed_real
    (by simp [sourceSpec]) (by simp [sourceSpec])

#print axioms checker_sound
#print axioms sourceCheck_sound
#print axioms requested_sample_has_sign
#print axioms requested_source_sample_has_sign
#print axioms requested_sign
#print axioms requested_source_sign
#print axioms empty_dft_length_fails_closed
#print axioms oversized_source_range_fails_closed

end SparkInterval.Tests.FactoredSmallQCompletedSignCampaign

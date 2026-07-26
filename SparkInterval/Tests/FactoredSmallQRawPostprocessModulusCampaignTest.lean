/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign
import SparkInterval.Tests.FactoredSmallQRawPostprocessCampaignTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawPostprocessModulusCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign
open SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign

def source : SourceSpec := ⟨[spec]⟩
def outerCertificate : Certificate := ⟨[campaign]⟩

def outerTermCount (_ : Spec) := termCount
def outerOddParity (_ : Spec) := oddParity
def outerNegativeFrequency (_ : Spec) := negativeFrequency
def outerBases (_ : Spec) := bases
def outerCharacters (_ : Spec) := characters
def outerPrefactors (_ : Spec) := prefactors
noncomputable def outerDeltas (_ : Spec) := deltas

theorem outer_check :
    check source outerCertificate outerTermCount outerOddParity
      outerNegativeFrequency = true := by
  simp only [check, outerCertificate, source,
    SparkInterval.Dirichlet.FactoredSmallQModulusCampaign.Certificate.check,
    Bool.and_eq_true, decide_eq_true_eq]
  constructor
  · norm_num [SourceSpec.WellFormed, SourceSpec.AllWellFormed, spec,
      SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed]
  · simp [checkPairs, payloadFor, outerTermCount, outerOddParity,
      outerNegativeFrequency]
    exact campaign_check

theorem analytic_inputs :
    AnalyticInputsContain source outerCertificate outerBases outerPrefactors
      outerDeltas outerCharacters := by
  exact List.Forall₂.cons
    ⟨base_disks, character_disks, prefactor_disks, tail_bound⟩
    List.Forall₂.nil

theorem requested_outer_cell_contains :
    ∃ modulusCertificate, modulusCertificate ∈ outerCertificate.moduli ∧
      ∃ batch, batch ∈ modulusCertificate.batches ∧
        ∃ cell, cell ∈ batch.cells ∧
          cell.key = ⟨2, 0⟩ ∧
          ∃ decoded :
              SparkInterval.Dirichlet.FactoredSmallQPostprocess.Certificate,
            cell.payload.decode = some decoded ∧
            cell.payload.tailInflation.output.decode = some decoded.output ∧
            (outerCharacters spec ⟨2, 0⟩).length =
              outerTermCount spec ⟨2, 0⟩ ∧
            decoded.output.ContainsComplex
              (SparkInterval.Dirichlet.FactoredSmallQPostprocess.applyFrequencySignValue
                  (outerNegativeFrequency spec ⟨2, 0⟩)
                  (outerPrefactors spec ⟨2, 0⟩ *
                    SparkInterval.Dirichlet.FactoredSmallQGaussianSum.exactFiniteSum
                      (outerOddParity spec ⟨2, 0⟩)
                      (outerBases spec ⟨2, 0⟩)
                      (outerCharacters spec ⟨2, 0⟩)) +
                outerDeltas spec ⟨2, 0⟩) := by
  exact requested_output_contains_exact_postprocessed_sum
    outer_check analytic_inputs (by simp [source])
    (by simp [spec]) (by simp [spec])

#print axioms requested_output_contains_exact_postprocessed_sum
#print axioms requested_outer_cell_contains

end SparkInterval.Tests.FactoredSmallQRawPostprocessModulusCampaign

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCampaign
import SparkInterval.Tests.FactoredSmallQRawTraceTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawCampaign
open SparkInterval.Dirichlet.FactoredSmallQRawTrace
open SparkInterval.Tests.FactoredSmallQRawTrace

def sourceSpec : Spec := {
  q := 997
  roster := [11]
  transformLength := 1
}

def expectedTermCount (_key : CellKey) : Nat := 3

def onlyBatch : Batch RawTraceCertificate := {
  ordinal := 0
  characterStart := 0
  characters := [11]
  cells := [⟨⟨11, 0⟩, rawSample⟩]
}

def campaignSample : RawCampaignCertificate := {
  q := 997
  roster := [11]
  transformLength := 1
  batches := [onlyBatch]
}

theorem raw_sample_term_count_check :
    rawSample.checkForTermCount 2 3 = true := by
  simp only [RawTraceCertificate.checkForTermCount, Bool.and_eq_true,
    decide_eq_true_eq]
  exact ⟨⟨by norm_num, by norm_num [rawSample]⟩, rawSample_check⟩

theorem campaign_sample_check :
    check sourceSpec expectedTermCount campaignSample = true := by
  norm_num [check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    BatchChain, BatchCellsValid, expectedKeys, sourceSpec, expectedTermCount,
    campaignSample, onlyBatch,
    payloadCheck, raw_sample_term_count_check]

/-- Changing only the application-owned truncation invalidates the same raw
campaign; the payload cannot choose its own term count. -/
def wrongTermCount (_key : CellKey) : Nat := 4

theorem wrong_term_count_fails :
    check sourceSpec wrongTermCount campaignSample = false := by
  norm_num [check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.check,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Certificate.CoverageValid,
    SparkInterval.Dirichlet.FactoredSmallQCampaign.Spec.WellFormed,
    BatchChain, BatchCellsValid, expectedKeys, sourceSpec, wrongTermCount,
    campaignSample, onlyBatch, payloadCheck,
    RawTraceCertificate.checkForTermCount, rawSample]

#print axioms checker_sound
#print axioms requested_output_contains_exact_after
#print axioms campaign_sample_check
#print axioms wrong_term_count_fails

end SparkInterval.Tests.FactoredSmallQRawCampaign

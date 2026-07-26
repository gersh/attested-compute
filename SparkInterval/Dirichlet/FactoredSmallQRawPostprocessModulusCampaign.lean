/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

/-!
# Exact postprocessed arithmetic across the small-`q` modulus list

This module specializes the generic outer-modulus checker to the complete raw
postprocessing payload.  The application owns an ordered list of modulus
specifications and, for each specification and cell, the exact truncation,
parity, frequency-sign branch, and analytic values.  An accepted certificate
must match that list in order and must contain every character/frequency cell.

The main theorem is deliberately a lookup theorem.  Given a source modulus,
character, and frequency, it returns the actual raw cell at that exact location
and proves that its decoded final disk encloses the named finite Gaussian sum,
prefactor product, sign branch, and analytic tail.  The analytic containment
premises remain visible and are aligned with the same ordered modulus list;
neither a digest nor a physical execution claim can supply them.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign

open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQModulusCampaign
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

abbrev Certificate :=
  FactoredSmallQModulusCampaign.Certificate RawCertificate

/-- Application-owned arithmetic metadata for every source modulus and cell. -/
def payloadFor
    (termCount : Spec → CellKey → ℕ)
    (oddParity negativeFrequency : Spec → CellKey → Bool)
    (spec : Spec) : CellKey → RawCertificate → Bool :=
  payloadCheck (termCount spec) (oddParity spec) (negativeFrequency spec)

/-- Exact ordered modulus coverage plus the complete raw arithmetic checker at
every source-owned cell. -/
def check (source : SourceSpec) (certificate : Certificate)
    (termCount : Spec → CellKey → ℕ)
    (oddParity negativeFrequency : Spec → CellKey → Bool) : Bool :=
  certificate.check source
    (payloadFor termCount oddParity negativeFrequency)

/-- Analytic hypotheses aligned by the same `Forall₂` relation as the checked
source/certificate pair.  This prevents a valid hypothesis for one modulus
from being reused for a different modulus certificate. -/
def AnalyticInputsContain
    (source : SourceSpec) (certificate : Certificate)
    (w prefactors delta : Spec → CellKey → ℂ)
    (characters : Spec → CellKey → List ℂ) : Prop :=
  List.Forall₂
    (fun spec modulusCertificate ↦
      BaseDisksContain modulusCertificate (w spec) ∧
      CharacterDisksContain modulusCertificate (characters spec) ∧
      PrefactorDisksContain modulusCertificate (prefactors spec) ∧
      TailPerturbationsBound modulusCertificate (delta spec))
    source.moduli certificate.moduli

private theorem single_check_of_valid
    {spec : Spec}
    {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {certificate : RawPostprocessCampaignCertificate}
    (hcoverage : certificate.CoverageValid spec)
    (hpayloads : certificate.PayloadsValid
      (payloadCheck termCount oddParity negativeFrequency)) :
    FactoredSmallQRawPostprocessCampaign.check spec termCount oddParity
      negativeFrequency certificate = true := by
  simp only [FactoredSmallQRawPostprocessCampaign.check,
    FactoredSmallQCampaign.Certificate.check, Bool.and_eq_true,
    decide_eq_true_eq]
  refine ⟨hcoverage, ?_⟩
  apply List.all_eq_true.mpr
  intro batch hbatch
  apply List.all_eq_true.mpr
  intro cell hcell
  exact hpayloads batch hbatch cell hcell

private theorem exists_aligned_modulus
    {termCount : Spec → CellKey → ℕ}
    {oddParity negativeFrequency : Spec → CellKey → Bool}
    {w prefactors delta : Spec → CellKey → ℂ}
    {characters : Spec → CellKey → List ℂ}
    {specs : List Spec}
    {certificates : List RawPostprocessCampaignCertificate}
    (hmatched : Matched (payloadFor termCount oddParity negativeFrequency)
      specs certificates)
    (hanalytic : List.Forall₂
      (fun spec modulusCertificate ↦
        BaseDisksContain modulusCertificate (w spec) ∧
        CharacterDisksContain modulusCertificate (characters spec) ∧
        PrefactorDisksContain modulusCertificate (prefactors spec) ∧
        TailPerturbationsBound modulusCertificate (delta spec))
      specs certificates)
    {spec : Spec} (hspec : spec ∈ specs) :
    ∃ modulusCertificate, modulusCertificate ∈ certificates ∧
      modulusCertificate.CoverageValid spec ∧
      modulusCertificate.PayloadsValid
        (payloadCheck (termCount spec) (oddParity spec)
          (negativeFrequency spec)) ∧
      BaseDisksContain modulusCertificate (w spec) ∧
      CharacterDisksContain modulusCertificate (characters spec) ∧
      PrefactorDisksContain modulusCertificate (prefactors spec) ∧
      TailPerturbationsBound modulusCertificate (delta spec) := by
  induction hmatched with
  | nil => simp at hspec
  | @cons headSpec headCertificate tailSpecs tailCertificates
      headMatched tailMatched inductionHypothesis =>
      cases hanalytic with
      | cons headAnalytic tailAnalytic =>
          simp only [List.mem_cons] at hspec
          rcases hspec with hspec | hspec
          · subst spec
            exact ⟨headCertificate, by simp, headMatched.1,
              headMatched.2, headAnalytic⟩
          · rcases inductionHypothesis tailAnalytic hspec with
              ⟨found, hfound, hcoverage, hpayloads, hinputs⟩
            exact ⟨found, by simp [hfound], hcoverage, hpayloads, hinputs⟩

/-- Every exact source modulus/character/frequency triple returns its actual
raw payload and a containment proof for the complete postprocessed finite
arithmetic expression. -/
theorem requested_output_contains_exact_postprocessed_sum
    {source : SourceSpec} {certificate : Certificate}
    {termCount : Spec → CellKey → ℕ}
    {oddParity negativeFrequency : Spec → CellKey → Bool}
    {w prefactors delta : Spec → CellKey → ℂ}
    {characters : Spec → CellKey → List ℂ}
    (hcheck : check source certificate termCount oddParity
      negativeFrequency = true)
    (hanalytic : AnalyticInputsContain source certificate w prefactors delta
      characters)
    {spec : Spec} (hspec : spec ∈ source.moduli)
    {characterId frequency : ℕ}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ modulusCertificate, modulusCertificate ∈ certificate.moduli ∧
      ∃ batch, batch ∈ modulusCertificate.batches ∧
        ∃ cell, cell ∈ batch.cells ∧
          cell.key = ⟨characterId, frequency⟩ ∧
          ∃ decoded : FactoredSmallQPostprocess.Certificate,
            cell.payload.decode = some decoded ∧
            cell.payload.tailInflation.output.decode = some decoded.output ∧
            (characters spec ⟨characterId, frequency⟩).length =
              termCount spec ⟨characterId, frequency⟩ ∧
            decoded.output.ContainsComplex
              (applyFrequencySignValue
                  (negativeFrequency spec ⟨characterId, frequency⟩)
                  (prefactors spec ⟨characterId, frequency⟩ *
                    FactoredSmallQGaussianSum.exactFiniteSum
                      (oddParity spec ⟨characterId, frequency⟩)
                      (w spec ⟨characterId, frequency⟩)
                      (characters spec ⟨characterId, frequency⟩)) +
                delta spec ⟨characterId, frequency⟩) := by
  have hsound := FactoredSmallQModulusCampaign.Certificate.checker_sound
    (show certificate.check source
      (payloadFor termCount oddParity negativeFrequency) = true from hcheck)
  rcases exists_aligned_modulus hsound.2 hanalytic hspec with
    ⟨modulusCertificate, hmodulus, hcoverage, hpayloads,
      hbases, hcharacters, hprefactors, htails⟩
  have hsingle := single_check_of_valid hcoverage hpayloads
  rcases FactoredSmallQRawPostprocessCampaign.requested_output_contains_exact_postprocessed_sum
      hsingle hbases hcharacters hprefactors htails hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hkey, decoded, hdecode, houtput,
      hlength, hcontains⟩
  exact ⟨modulusCertificate, hmodulus, batch, hbatch, cell, hcell, hkey,
    decoded, hdecode, houtput, hlength, hcontains⟩

end SparkInterval.Dirichlet.FactoredSmallQRawPostprocessModulusCampaign

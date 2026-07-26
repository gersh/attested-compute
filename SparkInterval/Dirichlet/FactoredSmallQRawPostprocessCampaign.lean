/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

/-!
# Source-owned campaign of raw small-`q` postprocessing certificates

This module composes exact character/frequency coverage with the raw finite
Gaussian sum, prefactor multiplication, frequency-sign branch, and analytic
tail inflation.  The application owns every truncation, parity, and sign bit;
the certificate cannot select a shorter sum or relabel a positive-frequency
output as a negative-frequency output.

The conclusion remains conditional on the honest analytic inputs: each raw
base, character, and prefactor disk must contain its named complex value, and
the additive analytic remainder must satisfy the decoded tail bound.  Those
premises are not manufactured from a hash or physical-run claim.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocess

abbrev RawPostprocessCampaignCertificate :=
  FactoredSmallQCampaign.Certificate RawCertificate

/-- Application-owned cell metadata plus the complete raw arithmetic check. -/
def payloadCheck (termCount : CellKey → ℕ)
    (oddParity negativeFrequency : CellKey → Bool)
    (key : CellKey) (raw : RawCertificate) : Bool :=
  decide (raw.finiteSum.truncation = termCount key) &&
    (decide (raw.finiteSum.oddParity = oddParity key) &&
      (decide (raw.negativeFrequency = negativeFrequency key) &&
        raw.check (termCount key)))

/-- Exact source-domain coverage and one accepted final arithmetic payload at
every requested character/frequency key. -/
def check (spec : Spec) (termCount : CellKey → ℕ)
    (oddParity negativeFrequency : CellKey → Bool)
    (certificate : RawPostprocessCampaignCertificate) : Bool :=
  certificate.check spec
    (payloadCheck termCount oddParity negativeFrequency)

/-- Honest analytic input boundary for each decoded exponential base. -/
def BaseDisksContain (certificate : RawPostprocessCampaignCertificate)
    (w : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ disk : ComplexDisk,
        cell.payload.finiteSum.seed.base.decode = some disk ∧
        disk.ContainsComplex (w cell.key)

/-- Honest analytic input boundary for every exact character value. -/
def CharacterDisksContain (certificate : RawPostprocessCampaignCertificate)
    (characters : CellKey → List ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      RawContainsCharacters cell.payload.finiteSum.rows
        (characters cell.key)

/-- Honest analytic input boundary for the complete character-dependent
prefactor at every cell. -/
def PrefactorDisksContain (certificate : RawPostprocessCampaignCertificate)
    (prefactors : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ disk : ComplexDisk,
        cell.payload.prefactor.decode = some disk ∧
        disk.ContainsComplex (prefactors cell.key)

/-- Honest analytic tail boundary.  The exact rational bound is recovered
from the same raw cell whose final disk is used in the conclusion. -/
def TailPerturbationsBound
    (certificate : RawPostprocessCampaignCertificate)
    (delta : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ tailBound : ℚ,
        Binary64.decodeFinite cell.payload.tailInflation.tailBoundBits =
          some tailBound ∧
        ‖delta cell.key‖ ≤ (tailBound : ℝ)

theorem checker_sound
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {certificate : RawPostprocessCampaignCertificate}
    (hcheck : check spec termCount oddParity negativeFrequency certificate =
      true) :
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid
        (payloadCheck termCount oddParity negativeFrequency) :=
  FactoredSmallQCampaign.Certificate.checker_sound hcheck

/-- Every requested cell exposes its actual raw/typed linkage and a final
disk enclosing the complete application-sized postprocessed Gaussian value. -/
theorem requested_output_contains_exact_postprocessed_sum
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {certificate : RawPostprocessCampaignCertificate}
    (hcheck : check spec termCount oddParity negativeFrequency certificate =
      true)
    (hbases : BaseDisksContain certificate w)
    (hcharacters : CharacterDisksContain certificate characters)
    (hprefactors : PrefactorDisksContain certificate prefactors)
    (htails : TailPerturbationsBound certificate delta)
    {characterId frequency : ℕ}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ batch, batch ∈ certificate.batches ∧
      ∃ cell, cell ∈ batch.cells ∧
        cell.key = ⟨characterId, frequency⟩ ∧
        ∃ decoded : FactoredSmallQPostprocess.Certificate,
          cell.payload.decode = some decoded ∧
          cell.payload.tailInflation.output.decode = some decoded.output ∧
          (characters ⟨characterId, frequency⟩).length =
            termCount ⟨characterId, frequency⟩ ∧
          decoded.output.ContainsComplex
            (applyFrequencySignValue
                (negativeFrequency ⟨characterId, frequency⟩)
                (prefactors ⟨characterId, frequency⟩ *
                  exactFiniteSum (oddParity ⟨characterId, frequency⟩)
                    (w ⟨characterId, frequency⟩)
                    (characters ⟨characterId, frequency⟩)) +
              delta ⟨characterId, frequency⟩) := by
  have hsound := checker_sound hcheck
  rcases certificate.exists_cell_for_requested_key
      hsound.1 hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hcellKey⟩
  have hpayload := hsound.2 batch hbatch cell hcell
  have hpayload' := hpayload
  simp only [payloadCheck, Bool.and_eq_true, decide_eq_true_eq] at hpayload'
  rcases hbases batch hbatch cell hcell with
    ⟨baseDisk, hbaseDecode, hbase⟩
  have hbase' : baseDisk.ContainsComplex
      (w ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hbase
  have hcharacters' : RawContainsCharacters cell.payload.finiteSum.rows
      (characters ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hcharacters batch hbatch cell hcell
  rcases hprefactors batch hbatch cell hcell with
    ⟨prefactorDisk, hprefactorDecode, hprefactor⟩
  have hprefactor' : prefactorDisk.ContainsComplex
      (prefactors ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hprefactor
  rcases htails batch hbatch cell hcell with
    ⟨tailBound, htailDecode, htail⟩
  have htail' : ‖delta ⟨characterId, frequency⟩‖ ≤
      (tailBound : ℝ) := by
    simpa [hcellKey] using htail
  rcases RawCertificate.accepted_output_contains_exact_finite_sum
      hpayload'.2.2.2 hbaseDecode hbase' hcharacters'
      hprefactorDecode hprefactor' htailDecode htail' with
    ⟨decoded, hdecode, _, houtputDecode, hlength, hcontains⟩
  have htermCount : cell.payload.finiteSum.truncation =
      termCount ⟨characterId, frequency⟩ := by
    simpa [hcellKey] using hpayload'.1
  have hparity : cell.payload.finiteSum.oddParity =
      oddParity ⟨characterId, frequency⟩ := by
    simpa [hcellKey] using hpayload'.2.1
  have hnegative : cell.payload.negativeFrequency =
      negativeFrequency ⟨characterId, frequency⟩ := by
    simpa [hcellKey] using hpayload'.2.2.1
  rw [htermCount] at hlength
  rw [hparity, hnegative] at hcontains
  exact ⟨batch, hbatch, cell, hcell, hcellKey, decoded, hdecode,
    houtputDecode, hlength, hcontains⟩

end SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

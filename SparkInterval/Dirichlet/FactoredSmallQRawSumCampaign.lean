/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum

/-!
# Source-owned coverage composed with raw finite-Gaussian sums

This module requires exactly one raw finite-sum payload for every key in the
application-owned Cartesian product of the character roster and transform
frequencies.  The application also fixes the exact term count of each key;
the untrusted payload cannot shorten its own sum by choosing a smaller
`truncation` field.

The conclusion is an exact-rational arithmetic postcondition.  Analytic base
and character containment remain explicit premises, and no parser or physical
execution claim is made here.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQRawGaussianSum

abbrev RawSumCampaignCertificate :=
  FactoredSmallQCampaign.Certificate RawSumTraceCertificate

/-- Application-owned parity and exact truncation plus the complete raw
arithmetic check. -/
def payloadCheck (termCount : CellKey → ℕ)
    (oddParity : CellKey → Bool) (key : CellKey)
    (raw : RawSumTraceCertificate) : Bool :=
  decide (raw.truncation = termCount key) &&
  decide (raw.oddParity = oddParity key) &&
  raw.check (termCount key)

/-- Exact source-domain coverage and one accepted sum payload at every key. -/
def check (spec : Spec) (termCount : CellKey → ℕ)
    (oddParity : CellKey → Bool)
    (certificate : RawSumCampaignCertificate) : Bool :=
  certificate.check spec (payloadCheck termCount oddParity)

/-- Honest analytic input boundary for each decoded exponential base. -/
def BaseDisksContain (certificate : RawSumCampaignCertificate)
    (w : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ base : ComplexDisk,
        cell.payload.seed.base.decode = some base ∧
        base.ContainsComplex (w cell.key)

/-- Honest analytic input boundary for the character values in every row. -/
def CharacterDisksContain (certificate : RawSumCampaignCertificate)
    (characters : CellKey → List ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      RawContainsCharacters cell.payload.rows (characters cell.key)

/-- Soundness exposes both exact global coverage and every checked raw
payload. -/
theorem checker_sound
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity : CellKey → Bool}
    {certificate : RawSumCampaignCertificate}
    (hcheck : check spec termCount oddParity certificate = true) :
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid (payloadCheck termCount oddParity) :=
  FactoredSmallQCampaign.Certificate.checker_sound hcheck

/-- Every requested `(character, frequency)` has one accepted raw payload
whose decoded output encloses the exact application-sized finite Gaussian
sum. -/
theorem requested_output_contains_exact_finite_sum
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity : CellKey → Bool}
    {w : CellKey → ℂ} {characters : CellKey → List ℂ}
    {certificate : RawSumCampaignCertificate}
    (hcheck : check spec termCount oddParity certificate = true)
    (hbases : BaseDisksContain certificate w)
    (hcharacters : CharacterDisksContain certificate characters)
    {characterId frequency : ℕ}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ batch, batch ∈ certificate.batches ∧
      ∃ cell, cell ∈ batch.cells ∧
        cell.key = ⟨characterId, frequency⟩ ∧
        ∃ decoded : SumTraceCertificate,
          cell.payload.decode = some decoded ∧
          (characters ⟨characterId, frequency⟩).length =
            termCount ⟨characterId, frequency⟩ ∧
          decoded.output.ContainsComplex
            (exactFiniteSum (oddParity ⟨characterId, frequency⟩)
              (w ⟨characterId, frequency⟩)
              (characters ⟨characterId, frequency⟩)) := by
  have hsound := checker_sound hcheck
  rcases certificate.exists_cell_for_requested_key
      hsound.1 hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hcellKey⟩
  have hpayload := hsound.2 batch hbatch cell hcell
  have hpayload' :
      payloadCheck termCount oddParity ⟨characterId, frequency⟩
        cell.payload = true := by
    simpa [hcellKey] using hpayload
  simp only [payloadCheck, Bool.and_eq_true, decide_eq_true_eq] at hpayload'
  rcases hbases batch hbatch cell hcell with
    ⟨base, hbaseDecode, hbaseContains⟩
  have hbaseContains' :
      base.ContainsComplex (w ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hbaseContains
  have hcharacterDisks :
      RawContainsCharacters cell.payload.rows
        (characters ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hcharacters batch hbatch cell hcell
  rcases
      RawSumTraceCertificate.accepted_output_contains_exact_finite_sum_of_base_decode
        hpayload'.2 hbaseDecode hbaseContains' hcharacterDisks with
    ⟨decoded, hdecode, hlength, hcontains⟩
  have htermCount : cell.payload.truncation =
      termCount ⟨characterId, frequency⟩ := hpayload'.1.1
  have hparity : cell.payload.oddParity =
      oddParity ⟨characterId, frequency⟩ := hpayload'.1.2
  rw [htermCount] at hlength
  rw [hparity] at hcontains
  exact ⟨batch, hbatch, cell, hcell, hcellKey,
    decoded, hdecode, hlength, hcontains⟩

end SparkInterval.Dirichlet.FactoredSmallQRawSumCampaign

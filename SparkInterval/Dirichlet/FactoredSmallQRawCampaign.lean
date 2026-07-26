/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQRawTrace

/-!
# Source-owned coverage composed with raw Gaussian recurrence certificates

This is the first end-to-end composition point for the small-`q` arithmetic
bridge.  The application supplies the expected modulus, character roster,
transform length, and truncation function.  The certificate cannot redefine
that domain.  For every exact `(character, frequency)` key, the checker then
requires a raw binary64 trace with exactly `T - 1` recurrence updates.

The conclusion is intentionally limited to the recurrence state.  Finite-sum
accumulation, prefactor/tail arithmetic, DFT butterflies, analytic seed
containment, canonical byte parsing, and physical execution are subsequent
layers; none is smuggled into this theorem through a hash or an axiom.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQSeed
open SparkInterval.Dirichlet.FactoredSmallQTrace
open SparkInterval.Dirichlet.FactoredSmallQRawTrace
open SparkInterval.Dirichlet.FactoredSmallQCampaign

abbrev RawCampaignCertificate :=
  FactoredSmallQCampaign.Certificate RawTraceCertificate

/-- Fixed per-cell arithmetic check.  `termCount` belongs to the application
specification, not to the untrusted payload. -/
def payloadCheck (termCount : FactoredSmallQCampaign.CellKey → Nat)
    (key : FactoredSmallQCampaign.CellKey)
    (raw : RawTraceCertificate) : Bool :=
  raw.checkForTermCount (termCount key - 1) (termCount key)

/-- Exact source-domain coverage plus all raw arithmetic checks. -/
def check (spec : FactoredSmallQCampaign.Spec)
    (termCount : FactoredSmallQCampaign.CellKey → Nat)
    (certificate : RawCampaignCertificate) : Bool :=
  FactoredSmallQCampaign.Certificate.check
    spec certificate (payloadCheck termCount)

/-- Honest analytic input boundary for the base exponential disk of every
cell.  This premise is satisfiable and remains visible until a separate
transcendental certificate discharges it. -/
def BaseDisksContain
    (certificate : RawCampaignCertificate)
    (w : FactoredSmallQCampaign.CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ base : ComplexDisk,
        cell.payload.base.decode = some base ∧
        base.ContainsComplex (w cell.key)

/-- The combined checker exposes both the exact source-owned coverage equation
and the accepted raw trace at every physical cell. -/
theorem checker_sound
    {spec : FactoredSmallQCampaign.Spec}
    {termCount : FactoredSmallQCampaign.CellKey → Nat}
    {certificate : RawCampaignCertificate}
    (hcheck : check spec termCount certificate = true) :
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid (payloadCheck termCount) :=
  FactoredSmallQCampaign.Certificate.checker_sound hcheck

/-- Clean application theorem for one requested source cell.  It returns the
actual raw payload selected by coverage, its exact-rational decoding, and the
recurrence enclosure at the application-owned truncation. -/
theorem requested_output_contains_exact_after
    {spec : FactoredSmallQCampaign.Spec}
    {termCount : FactoredSmallQCampaign.CellKey → Nat}
    {w : FactoredSmallQCampaign.CellKey → ℂ}
    {certificate : RawCampaignCertificate}
    (hcheck : check spec termCount certificate = true)
    (hbases : BaseDisksContain certificate w)
    {characterId frequency : Nat}
    (hcharacter : characterId ∈ spec.roster)
    (hfrequency : frequency < spec.transformLength) :
    ∃ batch, batch ∈ certificate.batches ∧
      ∃ cell, cell ∈ batch.cells ∧
        cell.key = ⟨characterId, frequency⟩ ∧
        ∃ decoded : TraceCertificate,
          cell.payload.decode = some decoded ∧
          decoded.output.z.ContainsComplex
            (ExactGaussianState.after
              (w ⟨characterId, frequency⟩)
              (termCount ⟨characterId, frequency⟩ - 1)).z ∧
          decoded.output.ratio.ContainsComplex
            (ExactGaussianState.after
              (w ⟨characterId, frequency⟩)
              (termCount ⟨characterId, frequency⟩ - 1)).ratio := by
  have hsound := checker_sound hcheck
  rcases certificate.exists_cell_for_requested_key
      hsound.1 hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hcellKey⟩
  have hpayload := hsound.2 batch hbatch cell hcell
  have hpayload' :
      cell.payload.checkForTermCount
        (termCount ⟨characterId, frequency⟩ - 1)
        (termCount ⟨characterId, frequency⟩) = true := by
    simpa [payloadCheck, hcellKey] using hpayload
  rcases hbases batch hbatch cell hcell with
    ⟨base, hbaseDecode, hbaseContains⟩
  have hbaseContains' :
      base.ContainsComplex (w ⟨characterId, frequency⟩) := by
    simpa [hcellKey] using hbaseContains
  rcases RawTraceCertificate.term_count_output_contains_exact_after_of_base_decode
        hpayload' hbaseDecode hbaseContains' with
    ⟨decoded, hdecode, hz, hratio⟩
  exact ⟨batch, hbatch, cell, hcell, hcellKey,
    decoded, hdecode, hz, hratio⟩

end SparkInterval.Dirichlet.FactoredSmallQRawCampaign

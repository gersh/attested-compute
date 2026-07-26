/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQCampaign
import SparkInterval.Dirichlet.FactoredSmallQCompletedSign

/-!
# Source-sample coverage for completed small-`q` signs

The full DFT uses a power-of-two guard length, while the reduced production
stream retains only source samples `0 <= k < sampleCount`.  This module gives
that reduced domain its own source-owned campaign check.  The production-facing
`SourceSampleSpec` names `sampleCount` separately and `sourceCheck` also checks
the explicit inequality `sampleCount <= fullDFTLength`.  Thus neither length
is silently reinterpreted as the other.  The lower-level `check` taking the
generic Cartesian-product `Spec` remains as a compatibility building block.

Every requested `(character, sample)` is tied to one checked scaling,
time-tail, untilting, and strict-sign certificate.  Fourier containment,
transcendental scale/untilt containment, the time-periodization error bound,
and reality of the completed value remain explicit analytic premises.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign

abbrev SignCampaignCertificate :=
  FactoredSmallQCampaign.Certificate
    FactoredSmallQCompletedSign.Certificate

/-! ## Source-sample domain and its relation to the full DFT -/

/-- Application-owned domain of the reduced post-DFT stream.  `sampleCount`
is deliberately not called `transformLength`: the full transform has a
different, generally larger, power-of-two guard length. -/
structure SourceSampleSpec where
  q : Nat
  roster : List Nat
  sampleCount : Nat
  deriving Repr, DecidableEq, BEq

namespace SourceSampleSpec

/-- The generic Cartesian-product domain used internally by the campaign
checker.  Its third field is populated with the explicitly named source
sample count. -/
def toCampaignSpec (spec : SourceSampleSpec) : FactoredSmallQCampaign.Spec :=
  ⟨spec.q, spec.roster, spec.sampleCount⟩

/-- A reduced source-sample stream can be indexed into the full DFT only when
its complete half-open range fits in that transform. -/
def FitsDFTLength (spec : SourceSampleSpec)
    (fullDFTLength : Nat) : Prop :=
  spec.sampleCount ≤ fullDFTLength

instance (spec : SourceSampleSpec) (fullDFTLength : Nat) :
    Decidable (spec.FitsDFTLength fullDFTLength) := by
  unfold FitsDFTLength
  infer_instance

end SourceSampleSpec

def payloadCheck (fourierDisks : CellKey → ComplexDisk)
    (key : CellKey) (certificate : FactoredSmallQCompletedSign.Certificate) :
    Bool :=
  certificate.check (fourierDisks key)

/-- Exact source roster times retained source-sample range, with a complete
strict-sign arithmetic certificate in every cell. -/
def check (spec : Spec) (fourierDisks : CellKey → ComplexDisk)
    (certificate : SignCampaignCertificate) : Bool :=
  certificate.check spec (payloadCheck fourierDisks)

/-- Production-facing check: exact source roster/sample coverage plus the
explicit relationship between retained samples and the full DFT domain. -/
def sourceCheck (spec : SourceSampleSpec) (fullDFTLength : Nat)
    (fourierDisks : CellKey → ComplexDisk)
    (certificate : SignCampaignCertificate) : Bool :=
  decide (spec.FitsDFTLength fullDFTLength) &&
    check spec.toCampaignSpec fourierDisks certificate

def FourierDisksContain (certificate : SignCampaignCertificate)
    (fourierDisks : CellKey → ComplexDisk)
    (fourier : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      (fourierDisks cell.key).ContainsComplex (fourier cell.key)

def ScaleDisksContain (certificate : SignCampaignCertificate)
    (scale : CellKey → ℝ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      cell.payload.scaleTimesFourier.right.ContainsComplex
        (scale cell.key : ℂ)

def TimeTailsBound (certificate : SignCampaignCertificate)
    (timeTail : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ‖timeTail cell.key‖ ≤
        (cell.payload.timeTailInflation.tailBound : ℝ)

def UntiltDisksContain (certificate : SignCampaignCertificate)
    (untilt : CellKey → ℝ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      cell.payload.untiltTimesPeriodized.right.ContainsComplex
        (untilt cell.key : ℂ)

/-- Functional-equation reality premise at exactly the values used by the
source-sample certificates. -/
def CompletedValuesReal (certificate : SignCampaignCertificate)
    (fourier : CellKey → ℂ) (scale : CellKey → ℝ)
    (timeTail : CellKey → ℂ) (untilt : CellKey → ℝ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      (completedValue (fourier cell.key) (scale cell.key)
        (timeTail cell.key) (untilt cell.key)).im = 0

theorem checker_sound {spec : Spec}
    {fourierDisks : CellKey → ComplexDisk}
    {certificate : SignCampaignCertificate}
    (hcheck : check spec fourierDisks certificate = true) :
    certificate.CoverageValid spec ∧
      certificate.PayloadsValid (payloadCheck fourierDisks) :=
  FactoredSmallQCampaign.Certificate.checker_sound hcheck

/-- Soundness of the source-facing check keeps both distinct length facts in
the theorem statement: campaign coverage is over `sampleCount`, and that
range fits inside `fullDFTLength`. -/
theorem sourceCheck_sound {spec : SourceSampleSpec}
    {fullDFTLength : Nat}
    {fourierDisks : CellKey → ComplexDisk}
    {certificate : SignCampaignCertificate}
    (hcheck : sourceCheck spec fullDFTLength fourierDisks certificate = true) :
    spec.FitsDFTLength fullDFTLength ∧
      certificate.CoverageValid spec.toCampaignSpec ∧
      certificate.PayloadsValid (payloadCheck fourierDisks) := by
  simp only [sourceCheck, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1, checker_sound hcheck.2⟩

/-- Every requested source sample has its actual certificate and its proved
strict sign. -/
theorem requested_sample_has_sign
    {spec : Spec} {fourierDisks : CellKey → ComplexDisk}
    {fourier : CellKey → ℂ} {scale : CellKey → ℝ}
    {timeTail : CellKey → ℂ} {untilt : CellKey → ℝ}
    {certificate : SignCampaignCertificate}
    (hcheck : check spec fourierDisks certificate = true)
    (hfourier : FourierDisksContain certificate fourierDisks fourier)
    (hscale : ScaleDisksContain certificate scale)
    (htimeTail : TimeTailsBound certificate timeTail)
    (huntilt : UntiltDisksContain certificate untilt)
    (hreal : CompletedValuesReal certificate fourier scale timeTail untilt)
    {characterId sample : ℕ}
    (hcharacter : characterId ∈ spec.roster)
    (hsample : sample < spec.transformLength) :
    ∃ batch, batch ∈ certificate.batches ∧
      ∃ cell, cell ∈ batch.cells ∧
        cell.key = ⟨characterId, sample⟩ ∧
        cell.payload.sign.Holds
          (completedValue
            (fourier ⟨characterId, sample⟩)
            (scale ⟨characterId, sample⟩)
            (timeTail ⟨characterId, sample⟩)
            (untilt ⟨characterId, sample⟩)).re := by
  have hsound := checker_sound hcheck
  rcases certificate.exists_cell_for_requested_key
      hsound.1 hcharacter hsample with
    ⟨batch, hbatch, cell, hcell, hkey⟩
  have hpayload := hsound.2 batch hbatch cell hcell
  have hfourierCell := hfourier batch hbatch cell hcell
  have hscaleCell := hscale batch hbatch cell hcell
  have htailCell := htimeTail batch hbatch cell hcell
  have huntiltCell := huntilt batch hbatch cell hcell
  have hrealCell := hreal batch hbatch cell hcell
  have hsign := FactoredSmallQCompletedSign.Certificate.accepted_sign
    hpayload hfourierCell hscaleCell htailCell huntiltCell hrealCell
  rw [hkey] at hsign
  exact ⟨batch, hbatch, cell, hcell, hkey, hsign⟩

/-- Source-facing lookup theorem.  Besides the checked strict sign, it returns
the exact bound placing the retained sample index inside the named full DFT.
A later DFT-to-sign composition theorem can therefore construct a `Fin`
index without assuming that `sampleCount` equals the guard length. -/
theorem requested_source_sample_has_sign
    {spec : SourceSampleSpec} {fullDFTLength : Nat}
    {fourierDisks : CellKey → ComplexDisk}
    {fourier : CellKey → ℂ} {scale : CellKey → ℝ}
    {timeTail : CellKey → ℂ} {untilt : CellKey → ℝ}
    {certificate : SignCampaignCertificate}
    (hcheck : sourceCheck spec fullDFTLength fourierDisks certificate = true)
    (hfourier : FourierDisksContain certificate fourierDisks fourier)
    (hscale : ScaleDisksContain certificate scale)
    (htimeTail : TimeTailsBound certificate timeTail)
    (huntilt : UntiltDisksContain certificate untilt)
    (hreal : CompletedValuesReal certificate fourier scale timeTail untilt)
    {characterId sample : ℕ}
    (hcharacter : characterId ∈ spec.roster)
    (hsample : sample < spec.sampleCount) :
    sample < fullDFTLength ∧
      ∃ batch, batch ∈ certificate.batches ∧
        ∃ cell, cell ∈ batch.cells ∧
          cell.key = ⟨characterId, sample⟩ ∧
          cell.payload.sign.Holds
            (completedValue
              (fourier ⟨characterId, sample⟩)
              (scale ⟨characterId, sample⟩)
              (timeTail ⟨characterId, sample⟩)
              (untilt ⟨characterId, sample⟩)).re := by
  have hsound := sourceCheck_sound hcheck
  have hchecks :
      decide (spec.FitsDFTLength fullDFTLength) = true ∧
        check spec.toCampaignSpec fourierDisks certificate = true := by
    simpa only [sourceCheck, Bool.and_eq_true] using hcheck
  constructor
  · exact Nat.lt_of_lt_of_le hsample hsound.1
  · exact requested_sample_has_sign hchecks.2 hfourier hscale htimeTail
      huntilt hreal hcharacter hsample

end SparkInterval.Dirichlet.FactoredSmallQCompletedSignCampaign

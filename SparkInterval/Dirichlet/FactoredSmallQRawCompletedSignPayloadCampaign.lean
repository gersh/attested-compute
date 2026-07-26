/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSign
import SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignCampaign

/-!
# Source campaigns with raw completed-sign payloads

This module removes the separately entered typed sign-certificate boundary.
Each source-sample payload is a
`FactoredSmallQRawCompletedSign.RawCertificate`, and its checker obtains the
Fourier operand from the literal raw DFT output list:

```
rawTransforms[character].output[sample]?
```

A missing word fails.  A present word is passed directly to the raw sign
checker's literal attachment test; no producer-supplied rational Fourier table
intervenes.  Exact source-domain coverage is checked over the retained sample
count, while `SourceDFTAgreement` separately proves that range fits in the
full power-of-two DFT line.

The application theorem composes the raw postprocessing/DFT theorem, the
proved radix-2/direct-DFT identity, and the raw completed-sign source theorem.
All analytic base, character, prefactor, tail, root, scale, untilt, and reality
premises remain explicit.  No byte parser or physical execution is trusted.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQCompletedSign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

abbrev SourceSampleSpec :=
  FactoredSmallQCompletedSignCampaign.SourceSampleSpec

abbrev SourceParameters :=
  FactoredSmallQRawCompletedSignCampaign.SourceParameters

abbrev RawSignCertificate :=
  FactoredSmallQRawCompletedSign.RawCertificate

abbrev RawSignCampaignCertificate :=
  FactoredSmallQCampaign.Certificate RawSignCertificate

/-! ## Direct raw-word payload checker -/

/-- The only Fourier word admitted for a payload is the literal word at its
source-owned character/sample coordinate in the raw DFT output line. -/
def payloadCheck {logLength : Nat}
    (rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength)
    (key : CellKey) (payload : RawSignCertificate) : Bool :=
  match (rawTransforms key.characterId).output[key.frequency]? with
  | none => false
  | some fourierWord => payload.check fourierWord

/-- Exact full/source domain agreement, exact source Cartesian-product
coverage, and direct checking against every literal DFT output word. -/
def check {logLength : Nat} (fullSpec : Spec)
    (sourceSpec : SourceSampleSpec)
    (rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength)
    (certificate : RawSignCampaignCertificate) : Bool :=
  decide
      (FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement
        logLength fullSpec sourceSpec) &&
    certificate.check sourceSpec.toCampaignSpec
      (payloadCheck rawTransforms)

theorem checker_sound {logLength : Nat} {fullSpec : Spec}
    {sourceSpec : SourceSampleSpec}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {certificate : RawSignCampaignCertificate}
    (hcheck : check fullSpec sourceSpec rawTransforms certificate = true) :
    FactoredSmallQRawCompletedSignCampaign.SourceDFTAgreement
        logLength fullSpec sourceSpec ∧
      certificate.CoverageValid sourceSpec.toCampaignSpec ∧
      certificate.PayloadsValid (payloadCheck rawTransforms) := by
  simp only [check, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  exact ⟨hcheck.1,
    FactoredSmallQCampaign.Certificate.checker_sound hcheck.2⟩

/-! ## Explicit analytic inputs for raw sign payloads -/

def ScaleDisksContain (certificate : RawSignCampaignCertificate)
    (parameters : SourceParameters) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ disk : ComplexDisk,
        cell.payload.scaleTimesFourier.right.decode = some disk ∧
        disk.ContainsComplex (sourceScale parameters.b : ℂ)

def TimeTailsBound (certificate : RawSignCampaignCertificate)
    (timeTail : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ tailBound : ℚ,
        Binary64.decodeFinite
            cell.payload.timeTailInflation.tailBoundBits = some tailBound ∧
        ‖timeTail cell.key‖ ≤ (tailBound : ℝ)

def UntiltDisksContain (certificate : RawSignCampaignCertificate)
    (parameters : SourceParameters) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      ∃ disk : ComplexDisk,
        cell.payload.untiltTimesPeriodized.right.decode = some disk ∧
        disk.ContainsComplex
          (sourceUntilt parameters.eta (parameters.t cell.key) : ℂ)

/-- Functional-equation reality for the exact direct DFT value and exact
source formula at every checked raw sign payload. -/
def SourceCompletedValuesReal {logLength : Nat}
    (certificate : RawSignCampaignCertificate)
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ)
    (parameters : SourceParameters) (timeTail : CellKey → ℂ) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      (sourceCompletedValue
        (FactoredSmallQRawCompletedSignCampaign.directFourier
          (logLength := logLength) oddParity negativeFrequency w prefactors
          delta characters cell.key)
        parameters.b parameters.eta (parameters.t cell.key)
        (timeTail cell.key)).im = 0

/-! ## Full arithmetic composition at one requested source sample -/

/-- Every requested source sample returns one literal raw DFT output word,
its direct-positive-DFT enclosure, and the raw sign payload checked against
that exact word.  The final sign is for the expanded source formula at
`t = sample/a`; all source guards and the full/source length equation remain
visible in the conclusion. -/
theorem requested_source_sample_has_raw_source_sign
    {logLength : Nat}
    {fullSpec : Spec} {sourceSpec : SourceSampleSpec}
    {termCount : CellKey → Nat}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {postprocessCampaign : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {rawTransforms : Nat →
      FactoredSmallQRawDFT.RawCertificate logLength}
    {decodedTransforms : Nat →
      FactoredSmallQRawDFT.DecodedCertificate logLength}
    {bounds : Nat → FactoredSmallQRawDFT.Bounds}
    {signCampaign : RawSignCampaignCertificate}
    {parameters : SourceParameters} {timeTail : CellKey → ℂ}
    (hsignCheck : check fullSpec sourceSpec rawTransforms signCampaign = true)
    (hpostprocess :
      FactoredSmallQRawPostprocessCampaign.check fullSpec termCount oddParity
        negativeFrequency postprocessCampaign = true)
    (hbases : BaseDisksContain postprocessCampaign w)
    (hcharacters : CharacterDisksContain postprocessCampaign characters)
    (hprefactors : PrefactorDisksContain postprocessCampaign prefactors)
    (hpostprocessTails : TailPerturbationsBound postprocessCampaign delta)
    (houtputs : RawOutputsDecodeTo postprocessCampaign naturalDisks)
    (hrawLinked : RawTransformsLinked fullSpec naturalDisks rawTransforms
      decodedTransforms)
    (hrawChecks : ∀ characterId, characterId ∈ fullSpec.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ fullSpec.roster →
      TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle)
    (hgrid : parameters.GridValid logLength)
    (hscale : ScaleDisksContain signCampaign parameters)
    (htimeTail : TimeTailsBound signCampaign timeTail)
    (huntilt : UntiltDisksContain signCampaign parameters)
    (hreal : SourceCompletedValuesReal (logLength := logLength) signCampaign
      oddParity negativeFrequency w prefactors delta characters parameters
      timeTail)
    {characterId sample : Nat}
    (hcharacter : characterId ∈ sourceSpec.roster)
    (hsample : sample < sourceSpec.sampleCount) :
    0 < parameters.a ∧
      0 < parameters.b ∧
      -1 < parameters.eta ∧ parameters.eta < 1 ∧
      parameters.b =
        (FactoredSmallQRawDFT.lineLength logLength : ℝ) / parameters.a ∧
      sample < FactoredSmallQRawDFT.lineLength logLength ∧
      ∃ fourierWord : ComplexDisk.Raw,
        (rawTransforms characterId).output[sample]? = some fourierWord ∧
        ∃ fourierDisk : ComplexDisk,
          fourierWord.decode = some fourierDisk ∧
          fourierDisk.ContainsComplex
            (FactoredSmallQRawCompletedSignCampaign.directFourier
              (logLength := logLength) oddParity negativeFrequency w
              prefactors delta characters ⟨characterId, sample⟩) ∧
          ∃ batch, batch ∈ signCampaign.batches ∧
            ∃ cell, cell ∈ batch.cells ∧
              cell.key = ⟨characterId, sample⟩ ∧
              ∃ typed : FactoredSmallQCompletedSign.Certificate,
                cell.payload.scaleTimesFourier.left = fourierWord ∧
                cell.payload.decode = some typed ∧
                FactoredSmallQRawCompletedSign.decodeStrictSign
                    cell.payload.signCode = some typed.sign ∧
                cell.payload.untiltTimesPeriodized.output.decode =
                  some typed.output ∧
                FactoredSmallQRawCompletedSign.RawCertificate.SourceGuards
                  parameters.b parameters.eta
                    (parameters.t ⟨characterId, sample⟩) ∧
                typed.sign.Holds
                  (sourceCompletedValue
                    (FactoredSmallQRawCompletedSignCampaign.directFourier
                      (logLength := logLength) oddParity negativeFrequency w
                      prefactors delta characters ⟨characterId, sample⟩)
                    parameters.b parameters.eta
                    (parameters.t ⟨characterId, sample⟩)
                    (timeTail ⟨characterId, sample⟩)).re := by
  have hsound := checker_sound hsignCheck
  have hdomains := hsound.1
  have hsampleLine : sample < FactoredSmallQRawDFT.lineLength logLength :=
    Nat.lt_of_lt_of_le hsample hdomains.2.2.2
  have hcharacterFull : characterId ∈ fullSpec.roster := by
    rw [hdomains.2.1]
    exact hcharacter
  let frequency : Fin (FactoredSmallQRawDFT.lineLength logLength) :=
    finIndex logLength sample
  have hfrequencyValue : frequency.val = sample :=
    Nat.mod_eq_of_lt hsampleLine
  have hraw := output_words_contain_postprocessed_radix2
    hpostprocess hbases hcharacters hprefactors hpostprocessTails houtputs
      hrawLinked hrawChecks hroots hcharacterFull frequency
  rcases hraw with
    ⟨fourierWord, hfourierWordAt, hfourierDecode, hradixContains⟩
  let source : ExactState logLength :=
    exactSource logLength characterId
      (exactCellValue oddParity negativeFrequency w prefactors delta
        characters)
  have hdirectContains :
      ((decodedTransforms characterId).claimedOutput.value frequency).ContainsComplex
        (positiveDFT source frequency) := by
    rw [← radix2CorrectFor source frequency]
    simpa [source] using hradixContains
  have hfourierWordSample :
      (rawTransforms characterId).output[sample]? = some fourierWord := by
    simpa [hfrequencyValue] using hfourierWordAt
  have hfourierContains :
      ((decodedTransforms characterId).claimedOutput.value frequency).ContainsComplex
        (FactoredSmallQRawCompletedSignCampaign.directFourier
          (logLength := logLength) oddParity negativeFrequency w prefactors
          delta characters ⟨characterId, sample⟩) := by
    simpa [FactoredSmallQRawCompletedSignCampaign.directFourier, source,
      frequency, hfrequencyValue] using hdirectContains
  rcases signCampaign.exists_cell_for_requested_key hsound.2.1 hcharacter
      hsample with ⟨batch, hbatch, cell, hcell, hkey⟩
  have hpayload := hsound.2.2 batch hbatch cell hcell
  change payloadCheck rawTransforms cell.key cell.payload = true at hpayload
  rw [hkey] at hpayload
  change
    (match (rawTransforms characterId).output[sample]? with
      | none => false
      | some word => cell.payload.check word) = true at hpayload
  rw [hfourierWordSample] at hpayload
  rcases hscale batch hbatch cell hcell with
    ⟨scaleDisk, hscaleDecode, hscaleContains⟩
  rcases htimeTail batch hbatch cell hcell with
    ⟨tailBound, htailDecode, htailBound⟩
  rcases huntilt batch hbatch cell hcell with
    ⟨untiltDisk, huntiltDecode, huntiltContains⟩
  have hrealCell := hreal batch hbatch cell hcell
  rw [hkey] at htailBound
  rw [hkey] at huntiltContains
  rw [hkey] at hrealCell
  have hguards :
      FactoredSmallQRawCompletedSign.RawCertificate.SourceGuards
        parameters.b parameters.eta
          (parameters.t ⟨characterId, sample⟩) := by
    refine ⟨hgrid.1.2, hgrid.2.1, hgrid.2.2.1, ?_⟩
    unfold FactoredSmallQRawCompletedSignCampaign.SourceParameters.t
    exact div_nonneg (Nat.cast_nonneg _) (le_of_lt hgrid.1.1)
  have hsourceSign :=
    FactoredSmallQRawCompletedSign.RawCertificate.accepted_source_sign
      hguards hpayload hfourierDecode hfourierContains hscaleDecode
      hscaleContains htailDecode htailBound huntiltDecode huntiltContains
      hrealCell
  rcases hsourceSign with
    ⟨typed, hattached, htypedDecode, hsignDecode, houtputDecode,
      hsourceGuards, hstrictSign⟩
  refine ⟨hgrid.1.1, hgrid.1.2, hgrid.2.1, hgrid.2.2.1,
    hgrid.2.2.2, hsampleLine, fourierWord, hfourierWordSample,
    (decodedTransforms characterId).claimedOutput.value frequency,
    hfourierDecode, hfourierContains, batch, hbatch, cell, hcell, hkey,
    typed, hattached, htypedDecode, hsignDecode, houtputDecode,
    hsourceGuards, hstrictSign⟩

end SparkInterval.Dirichlet.FactoredSmallQRawCompletedSignPayloadCampaign

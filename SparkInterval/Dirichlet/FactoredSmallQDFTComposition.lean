/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFT
import SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

/-!
# Composition from raw postprocessed cells into radix-2 transform lines

The raw postprocessing campaign produces one final disk in natural frequency
order for every `(character, frequency)`.  The radix-2 checker starts from a
bit-reversed line.  This module makes the intervening equation explicit:

```
transform[chi].input[i]
  = naturalDisks[chi, reverseBits(logLength, i)]
```

with indices represented by the same total finite lookup used by the DFT
module.  A second exact equation identifies every raw cell's decoded final
disk with `naturalDisks[cell.key]`.  These two links let the source-owned
campaign theorem construct the DFT's bit-reversed input-containment premise.

The result is a pure Lean composition theorem.  It does not claim that a
physical output stream populated either table, and it retains every analytic
base/character/prefactor/tail premise from the raw campaign.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQDFTComposition

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign

/-- The exact postprocessed value named by one application-owned cell. -/
def exactCellValue
    (oddParity negativeFrequency : CellKey → Bool)
    (w prefactors delta : CellKey → ℂ)
    (characters : CellKey → List ℂ) (key : CellKey) : ℂ :=
  applyFrequencySignValue (negativeFrequency key)
      (prefactors key * exactFiniteSum (oddParity key) (w key)
        (characters key)) +
    delta key

/-- Exact complex source line in natural frequency order. -/
def exactSource (logLength characterId : ℕ)
    (values : CellKey → ℂ) : ExactState logLength :=
  ⟨fun frequency ↦ values ⟨characterId, frequency.val⟩⟩

/-- Every raw final disk decodes to the application-visible natural-order
disk table.  This is an exact equality, not merely a digest comparison. -/
def RawOutputsDecodeTo
    (certificate : RawPostprocessCampaignCertificate)
    (naturalDisks : CellKey → ComplexDisk) : Prop :=
  ∀ batch, batch ∈ certificate.batches →
    ∀ cell, cell ∈ batch.cells →
      cell.payload.tailInflation.output.decode =
        some (naturalDisks cell.key)

/-- Executable replay of every raw-output/natural-table equality. -/
def checkRawOutputsDecodeTo
    (certificate : RawPostprocessCampaignCertificate)
    (naturalDisks : CellKey → ComplexDisk) : Bool :=
  certificate.batches.all fun batch ↦
    batch.cells.all fun cell ↦
      match cell.payload.tailInflation.output.decode with
      | none => false
      | some disk => decide (disk = naturalDisks cell.key)

theorem checkRawOutputsDecodeTo_sound
    {certificate : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    (hcheck : checkRawOutputsDecodeTo certificate naturalDisks = true) :
    RawOutputsDecodeTo certificate naturalDisks := by
  intro batch hbatch cell hcell
  have hbatchCheck :=
    (List.all_eq_true.mp hcheck) batch hbatch
  have hcellCheck :=
    (List.all_eq_true.mp hbatchCheck) cell hcell
  cases hdecode : cell.payload.tailInflation.output.decode with
  | none => simp [hdecode] at hcellCheck
  | some disk =>
      simp only [hdecode, decide_eq_true_eq] at hcellCheck
      simp [hcellCheck]

/-- Source transform length and the exact natural-to-bit-reversed disk link
for every requested character. -/
def InputsLinked {logLength : ℕ} (spec : Spec)
    (naturalDisks : CellKey → ComplexDisk)
    (transforms : ℕ → FactoredSmallQDFT.Certificate logLength) : Prop :=
  spec.transformLength = 2 ^ logLength ∧
  ∀ characterId, characterId ∈ spec.roster →
    ∀ index,
      (transforms characterId).input.value index =
        naturalDisks ⟨characterId,
          (finIndex logLength (reverseBits logLength index.val)).val⟩

/-- Finite Boolean replay of the transform-length and bit-reversal equations.
The producer cannot choose which indices are visited. -/
def checkInputsLinked {logLength : ℕ} (spec : Spec)
    (naturalDisks : CellKey → ComplexDisk)
    (transforms : ℕ → FactoredSmallQDFT.Certificate logLength) : Bool :=
  decide (spec.transformLength = 2 ^ logLength) &&
    spec.roster.all fun characterId ↦
      (List.range (2 ^ logLength)).all fun index ↦
        decide ((transforms characterId).input.value
            (finIndex logLength index) =
          naturalDisks ⟨characterId,
            (finIndex logLength (reverseBits logLength index)).val⟩)

theorem checkInputsLinked_sound {logLength : ℕ}
    {spec : Spec} {naturalDisks : CellKey → ComplexDisk}
    {transforms : ℕ → FactoredSmallQDFT.Certificate logLength}
    (hcheck : checkInputsLinked spec naturalDisks transforms = true) :
    InputsLinked spec naturalDisks transforms := by
  simp only [checkInputsLinked, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  refine ⟨hcheck.1, ?_⟩
  intro characterId hcharacter index
  have hcharacterCheck :=
    (List.all_eq_true.mp hcheck.2) characterId hcharacter
  have hindexCheck :=
    (List.all_eq_true.mp hcharacterCheck) index.val
      (List.mem_range.mpr index.isLt)
  simp only [decide_eq_true_eq] at hindexCheck
  have hfin : finIndex logLength index.val = index := by
    apply Fin.ext
    exact Nat.mod_eq_of_lt index.isLt
  simpa [hfin] using hindexCheck

/-- One compact link check for both raw-output decoding and bit reversal. -/
def linkCheck {logLength : ℕ} (spec : Spec)
    (certificate : RawPostprocessCampaignCertificate)
    (naturalDisks : CellKey → ComplexDisk)
    (transforms : ℕ → FactoredSmallQDFT.Certificate logLength) : Bool :=
  checkRawOutputsDecodeTo certificate naturalDisks &&
    checkInputsLinked spec naturalDisks transforms

theorem linkCheck_sound {logLength : ℕ}
    {spec : Spec} {certificate : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {transforms : ℕ → FactoredSmallQDFT.Certificate logLength}
    (hcheck : linkCheck spec certificate naturalDisks transforms = true) :
    RawOutputsDecodeTo certificate naturalDisks ∧
      InputsLinked spec naturalDisks transforms := by
  simp only [linkCheck, Bool.and_eq_true] at hcheck
  exact ⟨checkRawOutputsDecodeTo_sound hcheck.1,
    checkInputsLinked_sound hcheck.2⟩

/-- Exact per-cell campaign containment supplies the bit-reversed input
invariant required by the typed radix-2 theorem. -/
theorem input_contains_bitReversed {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {certificate : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {transforms : ℕ → FactoredSmallQDFT.Certificate logLength}
    (hcheck : check spec termCount oddParity negativeFrequency certificate =
      true)
    (hbases : BaseDisksContain certificate w)
    (hcharacters : CharacterDisksContain certificate characters)
    (hprefactors : PrefactorDisksContain certificate prefactors)
    (htails : TailPerturbationsBound certificate delta)
    (hdecode : RawOutputsDecodeTo certificate naturalDisks)
    (hinputs : InputsLinked spec naturalDisks transforms)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    StateContains (transforms characterId).input
      (bitReversed
        (exactSource logLength characterId
          (exactCellValue oddParity negativeFrequency w prefactors delta
            characters))) := by
  intro index
  let reversedIndex : Fin (2 ^ logLength) :=
    finIndex logLength (reverseBits logLength index.val)
  let key : CellKey := ⟨characterId, reversedIndex.val⟩
  have hfrequency : reversedIndex.val < spec.transformLength := by
    rw [hinputs.1]
    exact reversedIndex.isLt
  rcases requested_output_contains_exact_postprocessed_sum
      hcheck hbases hcharacters hprefactors htails hcharacter hfrequency with
    ⟨batch, hbatch, cell, hcell, hcellKey, decoded, _,
      hrawOutput, _, hcontains⟩
  have hnatural := hdecode batch hbatch cell hcell
  rw [hcellKey] at hnatural
  have hdisk : naturalDisks key = decoded.output := by
    change cell.payload.tailInflation.output.decode =
      some (naturalDisks key) at hnatural
    rw [hrawOutput] at hnatural
    exact (Option.some.inj hnatural).symm
  rw [hinputs.2 characterId hcharacter index]
  rw [hdisk]
  simpa [key, reversedIndex, bitReversed, exactSource, exactCellValue] using
    hcontains

/-- Complete typed arithmetic composition through the positive-sign radix-2
network for one requested character. -/
theorem output_contains_positiveRadix2 {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {certificate : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {transforms : ℕ → FactoredSmallQDFT.Certificate logLength}
    (hcheck : check spec termCount oddParity negativeFrequency certificate =
      true)
    (hbases : BaseDisksContain certificate w)
    (hcharacters : CharacterDisksContain certificate characters)
    (hprefactors : PrefactorDisksContain certificate prefactors)
    (htails : TailPerturbationsBound certificate delta)
    (hdecode : RawOutputsDecodeTo certificate naturalDisks)
    (hinputs : InputsLinked spec naturalDisks transforms)
    (htransformChecks : ∀ characterId, characterId ∈ spec.roster →
      (transforms characterId).check = true)
    (hroots : ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := logLength)
        (transforms characterId).twiddleDisks positiveTwiddle)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    StateContains (transforms characterId).output
      (positiveRadix2Transform
        (exactSource logLength characterId
          (exactCellValue oddParity negativeFrequency w prefactors delta
            characters))) := by
  apply FactoredSmallQDFT.Certificate.output_contains_positiveRadix2
    (htransformChecks characterId hcharacter)
    (input_contains_bitReversed hcheck hbases hcharacters hprefactors htails
      hdecode hinputs hcharacter)
    (hroots characterId hcharacter)

/-- Boolean-link form of the complete composition theorem. -/
theorem output_contains_positiveRadix2_of_linkCheck {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {certificate : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {transforms : ℕ → FactoredSmallQDFT.Certificate logLength}
    (hcampaign :
      check spec termCount oddParity negativeFrequency certificate = true)
    (hbases : BaseDisksContain certificate w)
    (hcharacters : CharacterDisksContain certificate characters)
    (hprefactors : PrefactorDisksContain certificate prefactors)
    (htails : TailPerturbationsBound certificate delta)
    (hlinks : linkCheck spec certificate naturalDisks transforms = true)
    (htransformChecks : ∀ characterId, characterId ∈ spec.roster →
      (transforms characterId).check = true)
    (hroots : ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := logLength)
        (transforms characterId).twiddleDisks positiveTwiddle)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    StateContains (transforms characterId).output
      (positiveRadix2Transform
        (exactSource logLength characterId
          (exactCellValue oddParity negativeFrequency w prefactors delta
            characters))) := by
  rcases linkCheck_sound hlinks with ⟨hdecode, hinputs⟩
  exact output_contains_positiveRadix2 hcampaign hbases hcharacters
    hprefactors htails hdecode hinputs htransformChecks hroots hcharacter

end SparkInterval.Dirichlet.FactoredSmallQDFTComposition

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQDFTComposition
import SparkInterval.Dirichlet.FactoredSmallQRawDFT

/-!
# Composition of raw postprocessed cells with bounded raw DFT certificates

`FactoredSmallQDFTComposition` proves that exact per-cell postprocessing
supplies the bit-reversed input-containment invariant of the typed radix-2
checker.  `FactoredSmallQRawDFT` proves that a bounded, finite raw-binary64
butterfly trace realizes that typed checker and binds its derived final state
to explicit raw output words.

The theorem below composes those two statements.  Its two exact link premises
are intentionally visible:

* each postprocessing campaign output decodes to `naturalDisks[cell.key]`;
* each decoded raw DFT input is the bit reversal of that natural-order table.

No byte-parser, compiler, GPU, CPU, or physical-execution claim is made.
Analytic seed, character, prefactor, tail, and transcendental-root premises
remain explicit.
-/

set_option autoImplicit false

namespace SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQGaussianSum
open SparkInterval.Dirichlet.FactoredSmallQPostprocess
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Dirichlet.FactoredSmallQRawPostprocessCampaign
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition

/-- Exact link between each requested raw DFT object, its order-preserving
decoded certificate, and the natural-order postprocessing disk table. -/
def RawTransformsLinked {logLength : ℕ} (spec : Spec)
    (naturalDisks : CellKey → ComplexDisk)
    (rawTransforms : ℕ → RawCertificate logLength)
    (decodedTransforms : ℕ → DecodedCertificate logLength) : Prop :=
  (∀ characterId, characterId ∈ spec.roster →
    (rawTransforms characterId).decode =
      some (decodedTransforms characterId)) ∧
  InputsLinked spec naturalDisks
    (fun characterId ↦ (decodedTransforms characterId).certificate)

/-- The raw link exposes the named decoding for every requested character. -/
theorem decode_eq_of_linked {logLength : ℕ} {spec : Spec}
    {naturalDisks : CellKey → ComplexDisk}
    {rawTransforms : ℕ → RawCertificate logLength}
    {decodedTransforms : ℕ → DecodedCertificate logLength}
    (hlinked : RawTransformsLinked spec naturalDisks rawTransforms
      decodedTransforms)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    (rawTransforms characterId).decode =
      some (decodedTransforms characterId) :=
  hlinked.1 characterId hcharacter

/-- Exact campaign arithmetic constructs the input invariant for the decoded
raw DFT certificate. -/
theorem raw_input_contains_bitReversed {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {campaign : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {rawTransforms : ℕ → RawCertificate logLength}
    {decodedTransforms : ℕ → DecodedCertificate logLength}
    (hcampaign : check spec termCount oddParity negativeFrequency campaign =
      true)
    (hbases : BaseDisksContain campaign w)
    (hcharacters : CharacterDisksContain campaign characters)
    (hprefactors : PrefactorDisksContain campaign prefactors)
    (htails : TailPerturbationsBound campaign delta)
    (houtputs : RawOutputsDecodeTo campaign naturalDisks)
    (hlinked : RawTransformsLinked spec naturalDisks rawTransforms
      decodedTransforms)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    StateContains (decodedTransforms characterId).certificate.input
      (bitReversed
        (exactSource logLength characterId
          (exactCellValue oddParity negativeFrequency w prefactors delta
            characters))) := by
  exact SparkInterval.Dirichlet.FactoredSmallQDFTComposition.input_contains_bitReversed
    hcampaign hbases hcharacters hprefactors htails houtputs hlinked.2
      hcharacter

/-- Complete raw-word endpoint for one requested character.  Each returned
word is a literal member of the raw output list, decodes to the checked disk,
and that disk contains the exact positive-sign radix-2 transform of the full
postprocessed source line. -/
theorem output_words_contain_postprocessed_radix2 {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {campaign : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {rawTransforms : ℕ → RawCertificate logLength}
    {decodedTransforms : ℕ → DecodedCertificate logLength}
    {bounds : ℕ → Bounds}
    (hcampaign : check spec termCount oddParity negativeFrequency campaign =
      true)
    (hbases : BaseDisksContain campaign w)
    (hcharacters : CharacterDisksContain campaign characters)
    (hprefactors : PrefactorDisksContain campaign prefactors)
    (htails : TailPerturbationsBound campaign delta)
    (houtputs : RawOutputsDecodeTo campaign naturalDisks)
    (hlinked : RawTransformsLinked spec naturalDisks rawTransforms
      decodedTransforms)
    (hchecks : ∀ characterId, characterId ∈ spec.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        (rawTransforms characterId).output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some
          ((decodedTransforms characterId).claimedOutput.value frequency) ∧
        ((decodedTransforms characterId).claimedOutput.value frequency).ContainsComplex
            ((positiveRadix2Transform
              (exactSource logLength characterId
                (exactCellValue oddParity negativeFrequency w prefactors
                  delta characters))).value frequency) := by
  apply RawCertificate.output_words_contain_positiveRadix2
    (hchecks characterId hcharacter)
    (decode_eq_of_linked hlinked hcharacter)
    (raw_input_contains_bitReversed hcampaign hbases hcharacters
      hprefactors htails houtputs hlinked hcharacter)
    (hroots characterId hcharacter)

/-- Boolean postprocess-link variant.  `linkCheck` discharges the two finite
postprocessing-table equations; raw transform decoding remains the explicit
order-preserving equation in `RawTransformsLinked`. -/
theorem output_words_contain_postprocessed_radix2_of_linkCheck
    {logLength : ℕ}
    {spec : Spec} {termCount : CellKey → ℕ}
    {oddParity negativeFrequency : CellKey → Bool}
    {w prefactors delta : CellKey → ℂ}
    {characters : CellKey → List ℂ}
    {campaign : RawPostprocessCampaignCertificate}
    {naturalDisks : CellKey → ComplexDisk}
    {rawTransforms : ℕ → RawCertificate logLength}
    {decodedTransforms : ℕ → DecodedCertificate logLength}
    {bounds : ℕ → Bounds}
    (hcampaign : check spec termCount oddParity negativeFrequency campaign =
      true)
    (hbases : BaseDisksContain campaign w)
    (hcharacters : CharacterDisksContain campaign characters)
    (hprefactors : PrefactorDisksContain campaign prefactors)
    (htails : TailPerturbationsBound campaign delta)
    (hpostprocessLinks : linkCheck spec campaign naturalDisks
      (fun characterId ↦ (decodedTransforms characterId).certificate) = true)
    (hdecodes : ∀ characterId, characterId ∈ spec.roster →
      (rawTransforms characterId).decode =
        some (decodedTransforms characterId))
    (hchecks : ∀ characterId, characterId ∈ spec.roster →
      (rawTransforms characterId).check (bounds characterId) = true)
    (hroots : ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := logLength)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle)
    {characterId : ℕ} (hcharacter : characterId ∈ spec.roster) :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        (rawTransforms characterId).output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some
          ((decodedTransforms characterId).claimedOutput.value frequency) ∧
        ((decodedTransforms characterId).claimedOutput.value frequency).ContainsComplex
            ((positiveRadix2Transform
              (exactSource logLength characterId
                (exactCellValue oddParity negativeFrequency w prefactors
                  delta characters))).value frequency) := by
  rcases linkCheck_sound hpostprocessLinks with ⟨houtputs, hinputs⟩
  exact output_words_contain_postprocessed_radix2 hcampaign hbases
    hcharacters hprefactors htails houtputs ⟨hdecodes, hinputs⟩ hchecks
      hroots hcharacter

end SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition

/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
import SparkInterval.Tests.FactoredSmallQDFTCompositionTest

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQRawDFTComposition

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.FactoredSmallQDFTComposition
open SparkInterval.Dirichlet.FactoredSmallQRawDFT
open SparkInterval.Dirichlet.FactoredSmallQRawDFTComposition
open SparkInterval.Tests.FactoredSmallQRawPostprocess
open SparkInterval.Tests.FactoredSmallQRawPostprocessCampaign
open SparkInterval.Tests.FactoredSmallQDFTComposition

def rawTransform : RawCertificate 0 := {
  input := [rawTail.output]
  twiddleRows := []
  stages := []
  output := [rawTail.output]
}

def decodedTransform : DecodedCertificate 0 := {
  inputValues := [typedTail.output]
  twiddleValues := []
  stageValues := []
  outputValues := [typedTail.output]
}

def transformBounds : Bounds := ⟨0, 1, 2⟩

theorem final_word_decode :
    rawTail.output.decode =
      some typedTail.output :=
  SparkInterval.Dirichlet.FactoredSmallQRawPostprocess.RawTailInflationCertificate.output_decode_eq
    rawTail_decode

theorem raw_transform_decode :
    rawTransform.decode = some decodedTransform := by
  simp [RawCertificate.decode, CanonicalShape, rawTransform,
    decodedTransform, lineLength, decodeDisks, decodeDiskRows,
    decodeStages, decodeList, final_word_decode]

theorem decoded_transform_check :
    decodedTransform.certificate.check = true := by
  simp [decodedTransform, DecodedCertificate.certificate,
    Certificate.check, checkLinkedStages]

theorem decoded_output_linked : decodedTransform.OutputLinked := by
  intro frequency
  fin_cases frequency
  rfl

theorem decoded_table_radii_nonnegative :
    decodedTransform.TableRadiiNonnegative := by
  norm_num [DecodedCertificate.TableRadiiNonnegative, decodedTransform,
    typedTail, SparkInterval.Tests.FactoredSmallQRawPostprocess.pointDisk]

theorem raw_transform_check :
    rawTransform.check transformBounds = true := by
  have hbounds : rawTransform.boundsCheck transformBounds = true := by
    norm_num [RawCertificate.boundsCheck, RawCertificate.recordCount,
      rawTransform, transformBounds, lineLength]
  have hlink : decide decodedTransform.OutputLinked = true :=
    decide_eq_true decoded_output_linked
  have hradii : decide decodedTransform.TableRadiiNonnegative = true :=
    decide_eq_true decoded_table_radii_nonnegative
  rw [RawCertificate.check, hbounds]
  simp only [Bool.true_and]
  rw [raw_transform_decode]
  change ((decodedTransform.certificate.check &&
    decide decodedTransform.OutputLinked) &&
      decide decodedTransform.TableRadiiNonnegative) = true
  rw [decoded_transform_check, hlink, hradii]
  rfl

def rawTransforms (_ : ℕ) : RawCertificate 0 := rawTransform
def decodedTransforms (_ : ℕ) : DecodedCertificate 0 := decodedTransform
def bounds (_ : ℕ) : Bounds := transformBounds

theorem raw_transforms_linked :
    RawTransformsLinked spec naturalDisks
      rawTransforms decodedTransforms := by
  constructor
  · intro characterId hcharacter
    exact raw_transform_decode
  · constructor
    · rfl
    · intro characterId hcharacter index
      fin_cases index
      rfl

theorem all_transform_checks :
    ∀ characterId, characterId ∈ spec.roster →
      (rawTransforms characterId).check (bounds characterId) = true := by
  intro characterId hcharacter
  exact raw_transform_check

theorem all_roots_contain :
    ∀ characterId, characterId ∈ spec.roster →
      TwiddlesContain (logLength := 0)
        (decodedTransforms characterId).certificate.twiddleDisks
        positiveTwiddle := by
  intro characterId hcharacter stage hstage
  omega

/-- The postprocessed nontrivial campaign cell is now the exact source of a
bounded raw DFT certificate, and the theorem returns its literal raw output
word together with the arithmetic enclosure. -/
theorem composed_raw_output_word :
    ∀ frequency,
      ∃ rawDisk : ComplexDisk.Raw,
        (rawTransforms 2).output[frequency.val]? = some rawDisk ∧
        rawDisk.decode = some
          ((decodedTransforms 2).claimedOutput.value frequency) ∧
        ((decodedTransforms 2).claimedOutput.value frequency).ContainsComplex
          ((positiveRadix2Transform
            (exactSource 0 2
              (exactCellValue oddParity negativeFrequency
                bases prefactors deltas characters))).value frequency) := by
  apply output_words_contain_postprocessed_radix2
    campaign_check base_disks character_disks
    prefactor_disks tail_bound
    raw_outputs_decode raw_transforms_linked
    all_transform_checks all_roots_contain
  simp [spec]

#print axioms raw_input_contains_bitReversed
#print axioms output_words_contain_postprocessed_radix2
#print axioms output_words_contain_postprocessed_radix2_of_linkCheck
#print axioms raw_transform_check
#print axioms composed_raw_output_word

end SparkInterval.Tests.FactoredSmallQRawDFTComposition
